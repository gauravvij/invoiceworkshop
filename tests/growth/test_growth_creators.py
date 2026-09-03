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
            "status": "qualified", "contact_route": "email",
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
        self.assertIn("no business email published on their own site", reason)

    def test_a_form_that_could_not_be_verified_is_rejected_not_assumed_usable(self):
        """The two gates agree: qualification admits exactly what the policy can
        admit, so the backlog never fills with prospects that can never be used."""
        pid = self._fetched(contact_kind="form", recipient=None,
                            contact_form_url=None, form_checks_json="{}")
        status, reason = self._judge(pid)
        self.assertEqual(status, "rejected")
        self.assertIn("no verified contact route", reason)

    def test_a_domain_named_after_an_invoicing_product_is_a_competitor(self):
        vendor, why = creators._is_vendor("https://invoiceace.app/blog/x", "Freelance tips", "")
        self.assertTrue(vendor)
        self.assertIn("named after an invoicing product", why)
        # Our own domain is excluded by the blocked-domain list before this runs.
        clean, _ = creators._is_vendor("https://example.org/blog/x", "Tools I use", "")
        self.assertFalse(clean)

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
        result = policy.admit(self.connection, self.prospect(
            recipient="founder@example.org", contact_route="email"))
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


class FormRouteTests(Fixture):
    """A contact form is a route the organization published for this purpose.
    Every condition below is a fact on the form's own page."""

    def _verify(self, body: str, url: str = "https://example.org/contact"):
        import growth_backlink_engine as engine
        original = engine.fetch
        engine.fetch = lambda _u: (200, body)
        try:
            return creators.verify_form(url)
        finally:
            engine.fetch = original

    GOOD = ('<html><body><h1>Contact us</h1>'
            '<p>Get in touch about editorial or partnership enquiries.</p>'
            '<form action="/send"><textarea name="message"></textarea></form>'
            '</body></html>')

    def test_a_public_editorial_contact_form_is_usable(self):
        verdict = self._verify(self.GOOD)
        self.assertTrue(verdict["usable"], verdict["blockers"])

    def test_a_captcha_ends_the_assessment_and_is_never_worked_around(self):
        verdict = self._verify(self.GOOD.replace("<form", '<div class="g-recaptcha"></div><form'))
        self.assertFalse(verdict["usable"])
        self.assertIn("anti-bot control", " ".join(verdict["blockers"]))
        # The module must contain no bypass machinery at all.
        source = Path(creators.__file__).read_text().lower()
        for forbidden in ("2captcha", "anticaptcha", "solve_captcha", "captcha_solver"):
            self.assertNotIn(forbidden, source)

    def test_a_form_behind_a_login_is_not_a_public_route(self):
        verdict = self._verify(self.GOOD.replace(
            "<textarea", '<input type="password" name="p"><textarea'))
        self.assertFalse(verdict["usable"])
        self.assertIn("behind a login", " ".join(verdict["blockers"]))

    def test_a_complaint_or_ticket_form_is_not_repurposed(self):
        for wrong in ("File a complaint", "Submit a ticket", "GDPR request"):
            verdict = self._verify(self.GOOD.replace("Get in touch about editorial", wrong))
            self.assertFalse(verdict["usable"], wrong)
            self.assertIn("different purpose", " ".join(verdict["blockers"]), wrong)

    def test_a_site_that_says_no_is_believed(self):
        verdict = self._verify(self.GOOD.replace(
            "</form>", "</form><p>No unsolicited pitches, please.</p>"))
        self.assertFalse(verdict["usable"])
        self.assertIn("says in writing", " ".join(verdict["blockers"]))

    def test_a_form_asking_for_payment_is_refused(self):
        verdict = self._verify(self.GOOD.replace("</form>", "</form><p>Submission fee applies.</p>"))
        self.assertFalse(verdict["usable"])

    def test_a_page_that_is_not_a_contact_route_is_refused(self):
        verdict = self._verify('<html><body><h1>Blog</h1><form><textarea></textarea></form></body></html>')
        self.assertFalse(verdict["usable"])
        self.assertIn("does not identify itself", " ".join(verdict["blockers"]))

    def test_a_mandatory_personal_name_escalates_rather_than_being_invented(self):
        verdict = self._verify(self.GOOD.replace(
            "<textarea", '<input type="text" name="first_name" required><textarea'))
        self.assertFalse(verdict["usable"])
        self.assertTrue(verdict["review"])
        self.assertIn("cannot be answered truthfully as an organization",
                      verdict["review_reason"])

    def test_an_unreadable_form_page_is_not_assumed_fine(self):
        import growth_backlink_engine as engine
        original = engine.fetch
        engine.fetch = lambda _u: (404, "")
        try:
            verdict = creators.verify_form("https://example.org/contact")
        finally:
            engine.fetch = original
        self.assertFalse(verdict["usable"])
        self.assertIn("could not be read", " ".join(verdict["blockers"]))


class RouteQualificationTests(Fixture):
    def test_a_prospect_with_a_verified_form_qualifies_on_the_form_route(self):
        pid = self.prospect(status="fetched", contact_kind="form", recipient=None,
                            contact_form_url="https://example.org/contact",
                            form_checks_json='{"has_form": true, "no_captcha": true}',
                            form_blockers="")
        creators.qualify(self.connection)
        row = self.connection.execute(
            "SELECT status, contact_route FROM creator_prospects WHERE id=?", (pid,)).fetchone()
        self.assertEqual(row["status"], "qualified")
        self.assertEqual(row["contact_route"], "form")

    def test_a_blocked_form_does_not_qualify(self):
        pid = self.prospect(status="fetched", contact_kind="form", recipient=None,
                            contact_form_url="https://example.org/contact",
                            form_checks_json='{"has_form": true}',
                            form_blockers="protected by an anti-bot control (recaptcha)")
        creators.qualify(self.connection)
        row = self.connection.execute(
            "SELECT status, rejection_reason FROM creator_prospects WHERE id=?", (pid,)).fetchone()
        self.assertEqual(row["status"], "rejected")
        self.assertIn("anti-bot control", row["rejection_reason"])

    def test_an_email_still_outranks_a_form_but_only_slightly(self):
        by_email = self.connection.execute(
            "SELECT * FROM creator_prospects WHERE id=?",
            (self.prospect(status="fetched"),)).fetchone()
        by_form = dict(by_email)
        by_form["contact_kind"], by_form["recipient"] = "form", None
        self.assertGreater(creators.fit_score(by_email), creators.fit_score(by_form))
        self.assertLess(creators.fit_score(by_email) - creators.fit_score(by_form),
                        creators.fit_score(by_email) * 0.3)


class PolicyV2Tests(Fixture):
    def test_the_policy_offers_exactly_the_two_owner_approved_routes(self):
        self.assertEqual(policy.POLICY_VERSION, 2)
        self.assertEqual(set(policy.POLICY["contact_routes"]), {"email", "form"})

    def test_captcha_bypass_is_forbidden_in_the_signed_text(self):
        form = policy.POLICY["contact_routes"]["form"]
        self.assertTrue(form["captcha_bypass_forbidden_absolutely"])
        self.assertTrue(form["no_captcha_to_bypass"])
        self.assertTrue(form["support_ticket_forms_forbidden"])
        self.assertTrue(form["legal_privacy_or_complaint_forms_forbidden"])
        self.assertTrue(form["site_instruction_forbidding_contact_is_honoured"])

    def test_a_form_is_never_followed_up(self):
        self.assertFalse(policy.POLICY["form_behaviour"]["automated_followup"])
        self.assertEqual(policy.POLICY["form_behaviour"]["max_initial_submissions"], 1)
        self.assertTrue(policy.POLICY["followups"]["forms_never_followed_up"])

    def test_an_unverified_submission_is_recorded_unknown_and_never_retried(self):
        self.assertTrue(policy.POLICY["form_behaviour"][
            "unverified_submission_recorded_as_unknown_never_retried"])

    def test_the_daily_ceiling_is_shared_across_both_routes(self):
        volume = policy.POLICY["volume"]
        self.assertEqual(volume["max_new_organizations_per_day"], 5)
        self.assertTrue(volume["shared_across_email_and_form"])
        self.assertTrue(volume["is_a_ceiling_not_a_quota"])

    def test_the_payload_shows_both_routes_and_the_form_rules(self):
        payload = policy.signing_payload()
        self.assertIn("CONTACT ROUTES", payload)
        self.assertIn("captcha_bypass_forbidden_absolutely=True", payload)
        self.assertIn("FORM BEHAVIOUR", payload)
        self.assertIn("SHARED across the email and form routes", payload)

    def test_v2_has_a_different_hash_from_v1(self):
        v1 = {**policy.POLICY, "policy_version": 1}
        del v1["contact_routes"]
        self.assertNotEqual(policy.policy_hash(), policy.policy_hash(v1))
