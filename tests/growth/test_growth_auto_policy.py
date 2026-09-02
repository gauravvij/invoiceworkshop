from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_auto_policy as policy  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402

CONTENT = "src/content/generators.ts"


def diff_for(added: list[str], path: str = CONTENT) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}\n"


class EnvelopeTests(unittest.TestCase):
    def test_an_ordinary_copy_change_is_allowed(self):
        checks = policy.validate_change(
            [CONTENT], diff_for(["  heading: 'A worked example',",
                                 "  paragraphs: ['Subtotal $100.00, tax at 8% is $8.00.'],"]))
        self.assertTrue(checks["within_file_allowlist"])

    def test_a_file_outside_the_allowlist_is_refused(self):
        for path in ("package.json", "src/pages/index.astro", "src/lib/documents/money.ts",
                     ".github/workflows/ci.yml", "scripts/growth_level1a.py",
                     "src/components/workspace/DocumentWorkspace.tsx"):
            with self.assertRaises(policy.PolicyRefusal, msg=path):
                policy.validate_change([path], diff_for(["x"], path))

    def test_a_route_change_is_refused_even_in_an_allowed_file(self):
        with self.assertRaises(policy.PolicyRefusal) as raised:
            policy.validate_change([CONTENT], diff_for(["  path: '/new-page/',"]))
        self.assertIn("route", str(raised.exception))

    def test_a_canonical_change_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change(
                ["src/layouts/BaseLayout.astro"],
                diff_for(['<link rel="canonical" href="https://elsewhere.example/">'],
                         "src/layouts/BaseLayout.astro"))

    def test_a_new_dependency_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal) as raised:
            policy.validate_change([CONTENT], diff_for(["import dayjs from 'dayjs';"]))
        self.assertIn("package import", str(raised.exception))

    def test_reading_configuration_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change([CONTENT], diff_for(["const key = process.env.SECRET;"]))

    def test_a_network_call_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change([CONTENT], diff_for(["  fetch('/api/thing')"]))

    def test_touching_persistence_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change([CONTENT], diff_for(["localStorage.setItem('a','b')"]))

    def test_a_new_external_link_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal) as raised:
            policy.validate_change(
                [CONTENT], diff_for(["text: 'See https://some-partner.example/guide'"]))
        self.assertIn("external URL", str(raised.exception))

    def test_a_link_to_our_own_site_is_allowed(self):
        policy.validate_change(
            [CONTENT], diff_for(["text: 'https://invoiceworkshop.com/invoice-template/'"]))

    def test_an_unreviewed_product_claim_is_refused(self):
        for claim in ("We guarantee your invoice is legally valid.",
                      "Bank-level security for your data.",
                      "Fully GDPR compliant invoicing.",
                      "The #1 invoice generator."):
            with self.assertRaises(policy.PolicyRefusal, msg=claim):
                policy.validate_change([CONTENT], diff_for([f"  '{claim}',"]))

    def test_a_sprawling_change_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change([CONTENT], diff_for([f"line {n}" for n in range(500)]))

    def test_touching_too_many_files_is_refused(self):
        many = [CONTENT, "src/styles/global.css",
                "src/components/GeneratorPage.astro", "src/layouts/BaseLayout.astro"]
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change(many, diff_for(["x"]))

    def test_an_empty_change_is_refused(self):
        with self.assertRaises(policy.PolicyRefusal):
            policy.validate_change([], "")

    def test_the_policy_document_states_both_sides_of_the_envelope(self):
        document = policy.policy_document()
        for expected in ("allowed_files", "blocked_files", "allowed_change_categories",
                         "blocked_change_categories", "max_changed_lines"):
            self.assertIn(expected, document)
        self.assertIn("padding written to make a page longer", document)


def seed_opportunity(connection, **overrides) -> int:
    now = utc_now()
    row = {
        "opportunity_key": "gap:https://invoiceworkshop.com/invoice-template/",
        "opportunity_type": "SEO_PAGE_IMPROVEMENT",
        "title": "Close user-value gaps",
        "target_url": "https://invoiceworkshop.com/invoice-template/",
        "evidence": "no worked example", "evidence_strength": "moderate",
        "expected_growth_value": 4.39, "priority_band": 1,
        "execution_tier": "AUTO", "state": "open", "basis": "prior",
        "channel": "page_improvement", "first_seen_at": now, "updated_at": now,
        **overrides,
    }
    columns = ", ".join(row)
    placeholders = ", ".join(f":{name}" for name in row)
    cursor = connection.execute(
        f"INSERT INTO growth_opportunities ({columns}) VALUES ({placeholders})", row)
    connection.commit()
    return int(cursor.lastrowid)


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _claude_run(self, *, run_type="auto_opportunity", started=None):
        self.connection.execute(
            """INSERT INTO claude_runs (started_at, run_type, outcome)
               VALUES (?, ?, 'no_action')""", (started or utc_now(), run_type))
        self.connection.commit()

    def test_a_qualifying_opportunity_is_selected(self):
        seed_opportunity(self.connection)
        result = policy.select_candidate(self.connection)
        self.assertTrue(result["eligible"])

    def test_outreach_never_wakes_the_reasoning_agent(self):
        seed_opportunity(self.connection, opportunity_key="outreach:x.example",
                         opportunity_type="RESOURCE_OUTREACH", execution_tier="AUTO")
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])

    def test_a_review_opportunity_is_skipped(self):
        seed_opportunity(self.connection, execution_tier="REVIEW")
        self.assertFalse(policy.select_candidate(self.connection)["eligible"])

    def test_a_lower_band_opportunity_is_skipped(self):
        seed_opportunity(self.connection, priority_band=2)
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertIn("priority band 2", result["considered"][0]["skipped"])

    def test_a_low_value_opportunity_is_skipped(self):
        seed_opportunity(self.connection, expected_growth_value=0.4)
        self.assertFalse(policy.select_candidate(self.connection)["eligible"])

    def test_the_daily_budget_stops_a_second_run(self):
        seed_opportunity(self.connection)
        self._claude_run()
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["code"], "budget_exhausted")

    def test_a_fixture_run_does_not_consume_the_budget(self):
        seed_opportunity(self.connection)
        self._claude_run(run_type="fixture")
        self.assertTrue(policy.select_candidate(self.connection)["eligible"])

    def test_a_page_inside_an_open_experiment_window_is_left_alone(self):
        seed_opportunity(self.connection)
        future = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        self.connection.execute(
            """INSERT INTO growth_experiments
                 (hypothesis, action, action_type, target_url, started_at, evaluate_after,
                  updated_at)
               VALUES ('h','a','page_improvement',
                       'https://invoiceworkshop.com/invoice-template/', ?, ?, ?)""",
            (utc_now(), future, utc_now()))
        self.connection.commit()
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertIn("open experiment", result["considered"][0]["skipped"])

    def test_the_same_opportunity_is_not_executed_twice_in_a_row(self):
        seed_opportunity(self.connection, attempt_count=1, last_attempted_at=utc_now())
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertIn("cooldown", result["considered"][0]["skipped"])

    def test_repeated_failures_stop_retrying_forever(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        seed_opportunity(self.connection, attempt_count=2, last_attempted_at=old)
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertIn("already attempted", result["considered"][0]["skipped"])

    def test_a_cooled_down_opportunity_becomes_eligible_again(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        seed_opportunity(self.connection, attempt_count=1, last_attempted_at=old)
        self.assertTrue(policy.select_candidate(self.connection)["eligible"])

    def test_nothing_open_means_no_action_rather_than_an_error(self):
        result = policy.select_candidate(self.connection)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["code"], "no_action")


if __name__ == "__main__":
    unittest.main()
