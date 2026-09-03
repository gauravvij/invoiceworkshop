from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_creator_policy as policy  # noqa: E402
import growth_creators as creators  # noqa: E402
import growth_outreach_policy as resource_policy  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def prospect(self, **over) -> int:
        row = {
            "domain": "example.org", "page_url": "https://example.org/tools",
            "name": "Example Freelance Weekly", "segment": "freelancer_newsletter",
            "last_activity_date": _days_ago(20), "audience_estimate": 12_000,
            "recommends_tools": 1, "coverage_kind": "editorial",
            "contact_url": "https://example.org/tools", "contact_kind": "email",
            "recipient": "hello@example.org", "contact_verified_at": utc_now(),
            "product_angle": "the free invoice-to-receipt workflow",
            "target_url": policy.APPROVED_ANGLES["freelancer_newsletter"],
            "status": "qualified",
        }
        row.update(over)
        columns = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cursor = self.connection.execute(
            f"""INSERT INTO creator_prospects ({columns}, discovered_at, updated_at)
                VALUES ({marks}, ?, ?)""",
            (*row.values(), utc_now(), utc_now()))
        self.connection.commit()
        return cursor.lastrowid


class SignalTests(Fixture):
    def test_a_publication_date_is_read_from_metadata_as_well_as_text(self):
        """Rejecting a live publication for putting its date in a machine-readable
        field is a parser bug wearing a quality gate's clothes."""
        self.assertEqual(creators._parse_date("", '<time datetime="2026-08-01">x</time>'),
                         "2026-08-01")
        self.assertEqual(creators._parse_date("", '"datePublished": "2026-07-04"'),
                         "2026-07-04")
        self.assertEqual(creators._parse_date("Posted Aug 12, 2026"), "2026-08-12")

    def test_a_future_date_is_a_template_artefact_not_a_publication(self):
        self.assertIsNone(creators._parse_date("2099-01-01"))

    def test_audience_is_only_counted_where_they_state_it(self):
        self.assertEqual(creators._audience("Join 12,400 subscribers")[0], 12_400)
        self.assertIsNone(creators._audience("a few readers")[0])
        # Implausible figures are a misparse, not a mega-audience.
        self.assertIsNone(creators._audience("99,000,000 followers")[0])

    def test_coverage_kind_distinguishes_paid_from_editorial(self):
        self.assertEqual(creators._coverage_kind("This post is sponsored by Acme"), "sponsored")
        self.assertEqual(creators._coverage_kind("we may earn a commission"), "affiliate")
        self.assertEqual(creators._coverage_kind("Here are the tools I use"), "editorial")


class QualificationTests(Fixture):
    def _fetched(self, **over) -> int:
        return self.prospect(status="fetched", **over)

    def _judge(self, prospect_id: int) -> tuple[str, str | None]:
        creators.qualify(self.connection)
        row = self.connection.execute(
            "SELECT status, rejection_reason FROM creator_prospects WHERE id=?",
            (prospect_id,)).fetchone()
        return row["status"], row["rejection_reason"]

    def test_a_qualifying_target_is_admitted(self):
        pid = self._fetched()
        self.assertEqual(self._judge(pid)[0], "qualified")

    def test_a_dead_publication_is_rejected_however_good_its_archive(self):
        pid = self._fetched(last_activity_date=_days_ago(400))
        status, reason = self._judge(pid)
        self.assertEqual(status, "rejected")
        self.assertIn("over", reason)

    def test_a_target_that_never_recommends_anything_is_rejected(self):
        pid = self._fetched(recommends_tools=0)
        status, reason = self._judge(pid)
        self.assertEqual(status, "rejected")
        self.assertIn("unpaid suggestion would be an interruption", reason)

    def test_a_paid_placement_only_site_is_rejected(self):
        pid = self._fetched(coverage_kind="sponsored")
        self.assertEqual(self._judge(pid)[0], "rejected")

    def test_no_public_contact_route_is_rejected(self):
        pid = self._fetched(contact_kind="unknown", recipient=None)
        status, reason = self._judge(pid)
        self.assertEqual(status, "rejected")
        self.assertIn("no public business contact route", reason)

    def test_reach_never_outweighs_fit_in_the_ranking(self):
        """A huge audience with no fit must not outrank a good one, which is the
        ranking this module exists to refuse."""
        small = self.connection.execute(
            "SELECT * FROM creator_prospects WHERE id=?", (self._fetched(audience_estimate=3_000),)
        ).fetchone()
        huge_but_stale = dict(small)
        huge_but_stale["audience_estimate"] = 900_000
        huge_but_stale["last_activity_date"] = _days_ago(200)
        huge_but_stale["coverage_kind"] = "sponsored"
        self.assertGreater(creators.fit_score(small), creators.fit_score(huge_but_stale))

    def test_the_gate_reads_no_traffic_target(self):
        source = Path(creators.__file__).read_text()
        for forbidden in ("growth_trajectory", "TARGET_PAGEVIEWS", "intensity("):
            self.assertNotIn(forbidden, source)


class PolicyTests(Fixture):
    def test_nothing_sends_without_a_signed_policy(self):
        pid = self.prospect()
        result = policy.admit(self.connection, pid)
        self.assertFalse(result["admitted"])
        self.assertIn("no signed active creator policy", result["reason"])

    def test_signing_the_resource_policy_does_not_authorise_this_channel(self):
        """Two authorizations, two tables. Signing one must never widen the other."""
        resource_policy.store(self.connection)
        self.connection.execute(
            "UPDATE outreach_policy SET signed=1, active=1, signer_fingerprint='x'")
        self.connection.commit()
        self.assertIsNotNone(resource_policy.active_policy(self.connection))
        self.assertIsNone(policy.active_policy(self.connection))
        self.assertFalse(policy.admit(self.connection, self.prospect())["admitted"])

    def _sign(self):
        policy.store(self.connection)
        self.connection.execute(
            "UPDATE creator_policy SET signed=1, active=1, signer_fingerprint='SHA256:test'")
        self.connection.commit()

    def test_a_qualifying_prospect_is_admitted_once_signed(self):
        self._sign()
        result = policy.admit(self.connection, self.prospect())
        self.assertTrue(result["admitted"], result.get("reason"))

    def test_an_angle_pointing_somewhere_unapproved_is_refused(self):
        self._sign()
        result = policy.admit(self.connection, self.prospect(
            target_url="https://invoiceworkshop.com/not-a-real-page/"))
        self.assertFalse(result["admitted"])
        self.assertIn("angle_target_is_approved", result["reason"])

    def test_a_stale_contact_verification_is_refused(self):
        self._sign()
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = policy.admit(self.connection, self.prospect(contact_verified_at=old))
        self.assertFalse(result["admitted"])
        self.assertIn("contact_verification_current", result["reason"])

    def test_a_personal_local_part_is_refused(self):
        self._sign()
        result = policy.admit(self.connection, self.prospect(recipient="founder@example.org"))
        self.assertFalse(result["admitted"])
        self.assertIn("recipient_not_personal_local_part", result["reason"])

    def test_a_form_only_contact_route_is_refused(self):
        self._sign()
        result = policy.admit(self.connection, self.prospect(
            contact_kind="form", recipient=None))
        self.assertFalse(result["admitted"])

    def test_the_daily_limit_is_five_organizations(self):
        self.assertEqual(policy.POLICY["volume"]["max_new_organizations_per_day"], 5)
        self.assertEqual(policy.POLICY["followups"]["maximum"], 1)
        self.assertEqual(policy.POLICY["followups"]["wait_business_days"], 5)

    def test_everything_the_owner_excluded_is_false_in_the_policy(self):
        for flag in ("direct_messages", "community_posting", "account_creation",
                     "paid_placement", "sponsorship_negotiation", "affiliate_agreements",
                     "attachments", "mass_generic_email", "form_outbound"):
            self.assertFalse(policy.POLICY[flag], flag)

    def test_the_signing_payload_says_it_is_a_separate_authorization(self):
        payload = policy.signing_payload()
        self.assertIn("THIS IS A SEPARATE AUTHORIZATION", payload)
        self.assertIn("max_new_organizations_per_day=5", payload)
        self.assertIn("NOT AUTHORISED", payload)
        for segment, url in policy.APPROVED_ANGLES.items():
            self.assertIn(f"{segment} -> {url}", payload)

    def test_the_payload_hash_changes_if_the_policy_changes(self):
        first = policy.policy_hash()
        changed = {**policy.POLICY, "volume": {"max_new_organizations_per_day": 50,
                                               "max_total_messages_per_day": 80}}
        self.assertNotEqual(first, policy.policy_hash(changed))

    def test_deliverability_is_measured_on_this_channel_alone(self):
        health = policy.deliverability(self.connection)
        self.assertTrue(health["healthy"])
        self.assertIn("below the 10 needed", health["detail"])
        self.assertEqual(policy.POLICY["auto_stop"]["max_bounce_rate"], 0.10)
        self.assertTrue(policy.POLICY["auto_stop"]["stops_channel_without_owner_action"])


if __name__ == "__main__":
    unittest.main()


class VendorTests(Fixture):
    """A company selling its own invoicing product is not a creator, and an
    unpaid tool suggestion to its content team is a wasted contact."""

    def test_a_named_competitor_is_rejected_by_domain(self):
        vendor, why = creators._is_vendor(
            "https://www.billdu.com/blog/best-invoicing-software/", "Best invoicing", "")
        self.assertTrue(vendor)
        self.assertIn("sells a competing product", why)

    def test_vendor_content_is_rejected_on_the_page_itself(self):
        vendor, why = creators._is_vendor(
            "https://someapp.example/blog/best-invoice-tools",
            "Best Invoice Software for Freelancers", "")
        self.assertTrue(vendor)
        self.assertIn("vendor content", why)

    def test_a_genuine_creator_page_is_not_flagged(self):
        vendor, _ = creators._is_vendor(
            "https://example.org/blog/tools-i-use",
            "The tools I use to run my freelance practice",
            "Here are the tools I use. I pay for none of these and nobody paid me.")
        self.assertFalse(vendor)

    def test_the_check_reuses_the_existing_engine_rather_than_a_second_list(self):
        source = Path(creators.__file__).read_text()
        self.assertIn("from growth_backlink_policy import BLOCKED_DOMAINS, COMPETITORS", source)
        self.assertIn("from growth_backlink_engine import _is_vendor_content", source)
