from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_outreach_policy as policy  # noqa: E402
from growth_level1a import initialize, seed_reference_data  # noqa: E402


def build_action(connection, *, organization="Coalesco", recipient="info@coalesco.co.uk",
                 execution_class="level1a_email", template="human_resource",
                 target="https://invoiceworkshop.com/invoice-template/") -> int:
    """A minimal action in the shape the policy checks expect."""
    seed_reference_data(connection)
    now = "2026-09-01T00:00:00+00:00"
    future = "2099-01-01T00:00:00+00:00"
    page = f"https://{organization.lower().replace(' ', '')}.example/resources/"
    cursor = connection.execute(
        """INSERT INTO prospects (domain, page_url, prospect_type, opportunity_score, risk,
             why_fit, audience, contact_method, requires_account, requires_payment,
             link_type, source_url, status, notes, discovered_at, updated_at)
           VALUES (?, ?, 'resource', 80, 'low', 'fit', 'aud', ?, 0, 0, 'editorial', ?,
                   'qualified', '', ?, ?)""",
        (f"{organization.lower().replace(' ', '')}.example", page, page, page, now, now),
    )
    prospect_id = int(cursor.lastrowid)
    connection.execute(
        """INSERT INTO prospect_qualification (prospect_id, channel, page_evidence,
             outbound_resources, target_url, proposed_action, confidence, second_pass_pass,
             review_reason, reviewed_at)
           VALUES (?, 'resource', 'ev', '[]', ?, 'suggest', 'high', 1, 'ok', ?)""",
        (prospect_id, target, now),
    )
    cursor = connection.execute(
        """INSERT INTO level1a_actions (prospect_id, organization, external_page_url,
             verified_contact_route, contact_kind, execution_class, recipient, form_handler,
             action_type, target_url, allowed_intent, allowed_claim_keys_json,
             forbidden_claims_json, relevance_terms_json, template_id, template_version,
             subject_value, opening_value, context_value, fit_value, close_value,
             max_followups, attachments_allowed, payment_allowed, external_action_approved,
             message_approved, suppression_state, page_title, page_excerpt,
             last_verified_at, verification_expires_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'resource_suggestion', ?, 'intent',
                   '["free_no_signup_local"]', '[]', '["resource"]', ?, 1,
                   'Subject', 'Hello team,', 'Context.', 'Fit.', 'Close.',
                   1, 0, 0, 0, 0, 'active', 'Title', 'Excerpt', ?, ?, ?, ?)""",
        (prospect_id, organization, page, page,
         "email" if execution_class == "level1a_email" else "form",
         execution_class, recipient if execution_class == "level1a_email" else None,
         target, template, now, future, now, now),
    )
    connection.commit()
    return int(cursor.lastrowid)


class PolicyShapeTests(unittest.TestCase):
    def test_hash_is_stable_and_content_addressed(self):
        first = policy.policy_hash()
        self.assertEqual(first, policy.policy_hash())
        changed = json.loads(json.dumps(policy.POLICY))
        changed["volume"]["max_new_organizations_per_day"] = 50
        self.assertNotEqual(first, policy.policy_hash(changed))

    def test_signing_payload_states_the_limits_being_authorised(self):
        payload = policy.signing_payload()
        for expected in ("max_new_organizations_per_day=3", "followups_maximum=1",
                         "followup_wait_business_days=5", "form_outbound=False",
                         "community_posting=False", "account_creation=False",
                         "paid_placement=False", "level_1b=False"):
            self.assertIn(expected, payload, expected)
        self.assertIn(policy.policy_hash(), payload)

    def test_policy_does_not_widen_channels(self):
        self.assertEqual(policy.POLICY["channel"], "verified_public_business_email")
        for closed in ("form_outbound", "community_posting", "account_creation",
                       "paid_placement", "level_1b"):
            self.assertFalse(policy.POLICY[closed], closed)

    def test_policy_restricts_templates_and_claims(self):
        constraints = policy.POLICY["message_constraints"]
        self.assertTrue(constraints["claims_from_versioned_registry_only"])
        self.assertTrue(constraints["exactly_one_target_url"])
        self.assertTrue(constraints["target_url_must_be_canonical"])
        self.assertFalse(constraints["attachments"])
        self.assertFalse(constraints["arbitrary_links"])
        for family in constraints["template_families"]:
            self.assertIn(family, ("human_resource", "human_roundup", "short_directory"))


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = initialize(str(Path(self.temp.name) / "growth.db"))
        self.action_id = build_action(self.connection)
        self.form_id = build_action(
            self.connection, organization="Freelance Things", recipient=None,
            execution_class="level1a_form",
        )

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _activate(self):
        policy.store(self.connection)
        self.connection.execute(
            "UPDATE outreach_policy SET signed=1, active=1, signer_fingerprint='SHA256:test'"
        )
        self.connection.commit()

    def test_unsigned_policy_admits_nothing(self):
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertIn("no signed active outreach policy", result["reason"])

    def test_refusal_is_recorded_even_without_a_policy(self):
        policy.admit(self.connection, self.action_id)
        row = self.connection.execute(
            "SELECT admitted, refusal_reason FROM policy_admissions WHERE action_id=?",
            (self.action_id,),
        ).fetchone()
        self.assertEqual(row["admitted"], 0)
        self.assertIsNotNone(row["refusal_reason"])

    def test_a_stale_page_verification_blocks_admission(self):
        self._activate()
        self.connection.execute(
            "UPDATE level1a_actions SET verification_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (self.action_id,),
        )
        self.connection.commit()
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["page_verification_current"])

    def test_a_suppressed_action_is_refused(self):
        self._activate()
        self.connection.execute(
            "UPDATE level1a_actions SET suppression_state='declined' WHERE id=?", (self.action_id,)
        )
        self.connection.commit()
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["not_suppressed"])

    def test_a_personal_looking_recipient_is_refused(self):
        self._activate()
        self.connection.execute(
            "UPDATE level1a_actions SET recipient='ceo@coalesco.co.uk' WHERE id=?", (self.action_id,)
        )
        self.connection.commit()
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["recipient_not_personal"])

    def test_a_non_canonical_target_is_refused(self):
        self._activate()
        self.connection.execute(
            "UPDATE level1a_actions SET target_url='https://invoiceworkshop.com/invented/' WHERE id=?",
            (self.action_id,),
        )
        self.connection.commit()
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["target_url_canonical"])

    def test_a_form_action_is_refused_by_execution_class(self):
        self._activate()
        result = policy.admit(self.connection, self.form_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["execution_class_is_email"])

    def test_an_organization_already_contacted_is_refused(self):
        self._activate()
        self.connection.execute(
            """INSERT INTO level1a_action_audit
                 (action_id, message_id, attempt_number, mode, started_at, finished_at,
                  subject, body, recipient_or_route, source_page, target_url, message_hash,
                  validation_result, delivery_state, suppression_state, external_side_effects)
               VALUES (?, 'm', 0, 'live', '2026-09-01', '2026-09-01', 's', 'b', 'r', 'p', 't',
                       'h', 'passed', 'submitted', 'active', 'email_sent')""",
            (self.action_id,),
        )
        self.connection.commit()
        result = policy.admit(self.connection, self.action_id)
        self.assertFalse(result["admitted"])
        self.assertFalse(result["checks"]["organization_not_previously_contacted"])

    def test_a_tampered_stored_policy_is_rejected(self):
        self._activate()
        self.connection.execute("UPDATE outreach_policy SET policy_hash='deadbeef'")
        self.connection.commit()
        with self.assertRaises(SystemExit):
            policy.active_policy(self.connection)


class NoNewCapabilityTests(unittest.TestCase):
    def test_policy_module_cannot_send(self):
        source = (SCRIPTS / "growth_outreach_policy.py").read_text(encoding="utf-8")
        for forbidden in ("send_plaintext", "ZohoMailTransport", "requests.post", "smtplib"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_policy_reuses_the_existing_trust_anchor(self):
        source = (SCRIPTS / "growth_outreach_policy.py").read_text(encoding="utf-8")
        self.assertIn("verify_signature", source)
        # Verification is delegated; this module never runs a signing tool itself.
        self.assertNotIn("subprocess", source)


if __name__ == "__main__":
    unittest.main()
