from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_compliance as compliance  # noqa: E402
import growth_outreach_policy as policy  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def prospect(self, **over) -> "sqlite3.Row":
        row = {"domain": "example.com", "page_url": "https://example.com/resources",
               "prospect_type": "resource", "opportunity_score": 5.0, "risk": "low",
               "why_fit": "publishes a small-business tool list", "audience": "smb",
               "contact_method": "hello@example.com",
               "source_url": "https://example.com/resources", "status": "qualified"}
        row.update(over)
        columns = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cursor = self.connection.execute(
            f"""INSERT INTO prospects ({columns}, discovered_at, updated_at)
                VALUES ({marks}, ?, ?)""", (*row.values(), utc_now(), utc_now()))
        self.connection.commit()
        return self.connection.execute(
            "SELECT * FROM prospects WHERE id=?", (cursor.lastrowid,)).fetchone()

    def complete_identity(self):
        compliance.set_identity(
            self.connection, legal_name="InvoiceWorkshop",
            from_name="InvoiceWorkshop", from_address="hello@invoiceworkshop.com",
            reply_to="hello@invoiceworkshop.com",
            postal_address="1 Example Street, Example City, EX1 1EX",
            optout_line="Reply STOP and we will not contact you again.")


class JurisdictionTests(Fixture):
    def test_a_country_coded_domain_settles_it(self):
        self.assertEqual(compliance.classify_jurisdiction("acme.co.uk", "")[0], "UK")
        self.assertEqual(compliance.classify_jurisdiction("acme.ca", "")[0], "CA")

    def test_structured_data_is_preferred_over_prose(self):
        code, why = compliance.classify_jurisdiction(
            "acme.com", 'addressCountry Canada\n"addressCountry": "Canada"')
        self.assertEqual(code, "CA")
        self.assertIn("structured data", why)

    def test_a_state_and_zip_identify_the_united_states(self):
        code, why = compliance.classify_jurisdiction("acme.com", "Austin, TX 78701")
        self.assertEqual(code, "US")
        self.assertIn("ZIP", why)

    def test_a_province_and_postal_code_identify_canada(self):
        self.assertEqual(
            compliance.classify_jurisdiction("acme.com", "Toronto, ON M5V 2T6")[0], "CA")

    def test_a_uk_registration_statement_identifies_the_uk(self):
        self.assertEqual(compliance.classify_jurisdiction(
            "acme.com", "Registered in England and Wales. Company number 01234567.")[0], "UK")

    def test_conflicting_evidence_is_unknown_rather_than_a_coin_toss(self):
        code, why = compliance.classify_jurisdiction(
            "acme.com", "Austin, TX 78701 and Toronto, ON M5V 2T6")
        self.assertEqual(code, "UNKNOWN")
        self.assertIn("conflicting", why)

    def test_no_evidence_is_unknown(self):
        self.assertEqual(compliance.classify_jurisdiction("acme.com", "hello")[0], "UNKNOWN")


class EntityTests(Fixture):
    def test_an_incorporated_body_is_corporate(self):
        for suffix in ("Acme Ltd", "Acme Limited", "Acme LLC", "Acme Inc.",
                       "The Example Association", "Example Foundation"):
            self.assertEqual(compliance.classify_entity(suffix)[0], "corporate", suffix)

    def test_a_page_about_freelancers_is_not_a_sole_trader(self):
        """An earlier version read the word 'freelancer' as self-description and
        labelled a freelancers' union and an authors' guild as sole traders."""
        kind, _ = compliance.classify_entity(
            "Resources for freelancers and freelance writers everywhere.",
            "Freelancers Union")
        self.assertEqual(kind, "corporate")

    def test_genuine_self_description_is_read_as_a_sole_trader(self):
        kind, why = compliance.classify_entity("I am a freelance designer based in Leeds.")
        self.assertEqual(kind, "sole_trader_or_individual")
        self.assertIn("describes itself", why)

    def test_incorporation_takes_precedence_over_a_mention(self):
        kind, _ = compliance.classify_entity("We help sole traders. Acme Ltd.")
        self.assertEqual(kind, "corporate")

    def test_no_evidence_is_unknown_not_assumed_corporate(self):
        self.assertEqual(compliance.classify_entity("A blog about things.")[0], "unknown")


class VerdictTests(Fixture):
    def _assess(self, text, recipient="hello@example.com", **over):
        """The recipient lives on the action, not on the prospect: `contact_method`
        holds the route URL. Reading it from the wrong place reported every
        organization as having no address."""
        prospect = self.prospect(**over)
        if recipient:
            self.connection.execute(
                """INSERT INTO level1a_templates
                     (template_id, version, action_type, subject_template,
                      opening_template, fit_template, close_template,
                      max_body_characters, created_at)
                   VALUES ('t', 1, 'resource_suggestion', 's', 'o', 'f', 'c', 900, ?)
                   ON CONFLICT DO NOTHING""", (utc_now(),))
            self.connection.execute(
                """INSERT INTO level1a_actions
                     (prospect_id, organization, external_page_url, verified_contact_route,
                      contact_kind, recipient, execution_class, action_type, target_url,
                      allowed_intent, allowed_claim_keys_json, forbidden_claims_json,
                      relevance_terms_json, template_id, template_version, subject_value,
                      opening_value, fit_value, close_value, page_title, page_excerpt,
                      created_at, updated_at)
                   VALUES (?, 'Example', ?, ?, 'email', ?, 'level1a_email',
                           'resource_suggestion', 'https://invoiceworkshop.com/',
                           'suggest', '[]', '[]', '[]', 't', 1, 's', 'o', 'f', 'c',
                           'title', 'excerpt', ?, ?)""",
                (prospect["id"], prospect["page_url"], prospect["page_url"], recipient,
                 utc_now(), utc_now()))
            self.connection.commit()
        return compliance.assess_row(self.connection, prospect, text)

    def test_a_published_refusal_is_honoured_before_anything_else(self):
        result = self._assess("Austin, TX 78701. No unsolicited email, please.")
        self.assertEqual(result["verdict"], "REJECT")
        self.assertIn("honoured whatever the jurisdiction allows", result["reasons"][0])

    def test_a_us_recipient_is_blocked_while_the_postal_address_is_missing(self):
        result = self._assess("Acme Inc. Austin, TX 78701. hello@example.com")
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertIn("postal_address", result["reasons"][0])
        self.assertIn("not invented", result["reasons"][0])

    def test_a_us_recipient_clears_once_the_owner_configures_identity(self):
        self.complete_identity()
        result = self._assess("Acme Inc. Austin, TX 78701. hello@example.com")
        self.assertEqual(result["verdict"], "ELIGIBLE")

    def test_a_uk_corporate_subscriber_is_eligible(self):
        result = self._assess("Acme Ltd. Registered in England and Wales. hello@example.com")
        self.assertEqual(result["verdict"], "ELIGIBLE")

    def test_a_uk_sole_trader_is_never_sent_to_unattended(self):
        result = self._assess(
            "I am a freelance consultant. Registered office in England. hello@example.com")
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertIn("sole trader or individual subscriber", result["reasons"][0])

    def test_uk_status_that_is_not_established_is_review(self):
        result = self._assess("A blog. Company number 01234567 nowhere stated. "
                              "Registered in England. hello@example.com",
                              page_url="https://example.co.uk/resources")
        self.assertIn(result["verdict"], ("REVIEW", "ELIGIBLE"))

    def test_canada_needs_the_address_published_on_the_page(self):
        result = self._assess("Acme Ltd. Toronto, ON M5V 2T6.")
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertIn("not visibly published on this page", result["reasons"][0])

    def test_canada_is_eligible_when_every_condition_is_evidenced(self):
        result = self._assess("Acme Ltd. Toronto, ON M5V 2T6. Email hello@example.com")
        self.assertEqual(result["verdict"], "ELIGIBLE")

    def test_canada_stores_the_source_url_and_the_observation_time(self):
        self._assess("Acme Ltd. Toronto, ON M5V 2T6. Email hello@example.com")
        row = self.connection.execute("SELECT * FROM outreach_compliance").fetchone()
        self.assertTrue(row["evidence_source_url"])
        self.assertTrue(row["evidence_observed_at"])
        self.assertEqual(row["address_published_by_org"], 1)
        self.assertEqual(row["relevant_to_role"], 1)

    def test_an_unknown_jurisdiction_is_review_not_a_guess(self):
        result = self._assess("Acme Ltd. hello@example.com")
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertIn("guessing at one country's rules", result["reasons"][0])

    def test_no_country_specific_rules_are_invented_beyond_the_three(self):
        self.assertEqual(set(compliance.CCTLD.values()), {"UK", "CA", "US"})


class IdentityTests(Fixture):
    def test_the_postal_address_is_never_defaulted(self):
        identity = compliance.sender_identity(self.connection)
        self.assertIn("postal_address", identity["missing"])
        self.assertFalse(identity["complete"])

    def test_a_missing_address_is_reported_as_an_owner_blocker(self):
        compliance.assess_all(self.connection)
        row = self.connection.execute(
            "SELECT subject FROM escalations WHERE kind='sender_identity_incomplete'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("postal_address", row["subject"])

    def test_configuring_it_clears_the_blocker(self):
        compliance.assess_all(self.connection)
        self.complete_identity()
        row = self.connection.execute(
            "SELECT resolved_at FROM escalations WHERE kind='sender_identity_incomplete'"
        ).fetchone()
        self.assertIsNotNone(row["resolved_at"])

    def test_the_message_footer_carries_what_is_configured(self):
        import growth_level1a
        self.assertEqual(growth_level1a._signature(self.connection).count("\n"), 1)
        self.complete_identity()
        signature = growth_level1a._signature(self.connection)
        self.assertIn("1 Example Street", signature)
        self.assertIn("Reply STOP", signature)


class PolicyIntegrationTests(Fixture):
    def test_the_signed_text_shows_the_jurisdiction_layer(self):
        payload = policy.signing_payload()
        self.assertIn("JURISDICTION LAYER", payload)
        self.assertIn("physical_postal_address=True", payload)
        self.assertIn("postal_address_never_invented=True", payload)
        self.assertIn("sole_trader_or_individual_subscriber=REVIEW", payload)
        self.assertIn("unknown_jurisdiction=REVIEW", payload)

    def test_the_layer_can_block_but_never_authorise(self):
        source = Path(compliance.__file__).read_text()
        # It may set REVIEW or REJECT, and ELIGIBLE only as the starting value
        # that every condition then has to survive.
        self.assertIn('verdict = "ELIGIBLE"', source)
        self.assertNotIn("admitted = True", source)

    def test_the_policy_version_moved_so_an_old_signature_cannot_cover_it(self):
        self.assertEqual(policy.POLICY_VERSION, 2)
        self.assertIn("jurisdiction_layer", policy.POLICY)
