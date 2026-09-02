from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_allocation as allocation  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402
from growth_level1a import seed_reference_data  # noqa: E402


def add_experiment(connection, *, action_type: str, outcome: str | None,
                   evaluate_after: str = "2026-01-01") -> None:
    connection.execute(
        """INSERT INTO growth_experiments
             (hypothesis, action, action_type, started_at, evaluate_after, outcome, updated_at)
           VALUES ('h', 'a', ?, '2026-01-01T00:00:00+00:00', ?, ?, '2026-01-01T00:00:00+00:00')""",
        (action_type, evaluate_after, outcome),
    )
    connection.commit()


def add_outreach(connection, *, organization: str, sent: int = 1, replies: int = 0,
                 positive: int = 0, bounced: bool = False,
                 suppression: str = "active", prospect_type: str = "resource") -> int:
    seed_reference_data(connection)
    now = "2026-09-01T00:00:00+00:00"
    page = f"https://{organization}.example/resources/"
    cursor = connection.execute(
        """INSERT INTO prospects (domain, page_url, prospect_type, opportunity_score, risk,
             why_fit, audience, contact_method, requires_account, requires_payment,
             link_type, source_url, status, notes, discovered_at, updated_at)
           VALUES (?, ?, ?, 80, 'low', 'fit', 'aud', ?, 0, 0, 'editorial', ?, 'qualified',
                   '', ?, ?)""",
        (f"{organization}.example", page, prospect_type, page, page, now, now),
    )
    prospect_id = int(cursor.lastrowid)
    cursor = connection.execute(
        """INSERT INTO level1a_actions (prospect_id, organization, external_page_url,
             verified_contact_route, contact_kind, execution_class, recipient, action_type,
             target_url, allowed_intent, allowed_claim_keys_json, forbidden_claims_json,
             relevance_terms_json, template_id, template_version, subject_value, opening_value,
             context_value, fit_value, close_value, max_followups, attachments_allowed,
             payment_allowed, external_action_approved, message_approved, suppression_state,
             page_title, page_excerpt, last_verified_at, verification_expires_at,
             created_at, updated_at)
           VALUES (?, ?, ?, ?, 'email', 'level1a_email', ?, 'resource_suggestion',
                   'https://invoiceworkshop.com/invoice-template/', 'intent', '[]', '[]', '[]',
                   'human_resource', 1, 's', 'o', 'c', 'f', 'cl', 1, 0, 0, 1, 1, ?,
                   't', 'e', ?, '2099-01-01T00:00:00+00:00', ?, ?)""",
        (prospect_id, organization, page, page, f"info@{organization}.example",
         suppression, now, now, now),
    )
    action_id = int(cursor.lastrowid)
    for attempt in range(sent):
        connection.execute(
            """INSERT INTO level1a_action_audit
                 (action_id, message_id, attempt_number, mode, started_at, finished_at,
                  subject, body, recipient_or_route, source_page, target_url, message_hash,
                  validation_result, delivery_state, suppression_state, external_side_effects)
               VALUES (?, ?, ?, 'live', ?, ?, 's', 'b', 'r', 'p', 't', 'h', 'passed', ?,
                       'active', 'email_sent')""",
            (action_id, f"{organization}-{attempt}", attempt, now, now,
             "bounced" if bounced else "submitted"),
        )
    for index in range(replies):
        connection.execute(
            """INSERT INTO level1a_replies
                 (action_id, provider_message_id, received_at, classification,
                  requires_escalation, automated_action, content_hash)
               VALUES (?, ?, ?, ?, 0, 'none', 'h')""",
            (action_id, f"{organization}-r{index}", now,
             "positive" if index < positive else "decline"),
        )
    connection.commit()
    return action_id


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()


class ReallocationTests(Fixture):
    def test_no_evidence_moves_no_weight(self):
        result = allocation.reallocate(self.connection)
        for decision in result["decisions"]:
            self.assertEqual(decision["decision"], "insufficient_evidence", decision["channel"])
            self.assertEqual(decision["new_weight"], 1.0)

    def test_a_channel_that_repeatedly_fails_loses_weight(self):
        for _ in range(4):
            add_experiment(self.connection, action_type="page_improvement", outcome="negative")
        first = allocation.reallocate(self.connection)
        page = next(d for d in first["decisions"] if d["channel"] == "page_improvement")
        self.assertEqual(page["decision"], "reduce")
        self.assertLess(page["new_weight"], 1.0)

        second = allocation.reallocate(self.connection)
        again = next(d for d in second["decisions"] if d["channel"] == "page_improvement")
        self.assertLess(again["new_weight"], page["new_weight"])

    def test_a_failing_channel_is_never_zeroed(self):
        for _ in range(4):
            add_experiment(self.connection, action_type="page_improvement", outcome="negative")
        for _ in range(20):
            allocation.reallocate(self.connection)
        weight = self.connection.execute(
            "SELECT weight FROM channel_allocation WHERE channel='page_improvement'"
        ).fetchone()[0]
        self.assertGreaterEqual(weight, allocation.WEIGHT_FLOOR)

    def test_a_channel_that_wins_gains_weight(self):
        for outcome in ("positive", "positive", "neutral", "negative"):
            add_experiment(self.connection, action_type="page_improvement", outcome=outcome)
        result = allocation.reallocate(self.connection)
        page = next(d for d in result["decisions"] if d["channel"] == "page_improvement")
        self.assertEqual(page["decision"], "increase")
        self.assertGreater(page["new_weight"], 1.0)

    def test_a_running_experiment_is_not_counted_as_a_failure(self):
        add_experiment(self.connection, action_type="page_improvement", outcome=None,
                       evaluate_after="2099-01-01")
        result = allocation.reallocate(self.connection)
        page = next(d for d in result["decisions"] if d["channel"] == "page_improvement")
        self.assertEqual(page["decision"], "insufficient_evidence")
        self.assertEqual(page["attempts"], 0)

    def test_every_decision_is_recorded_including_the_non_decisions(self):
        allocation.reallocate(self.connection)
        rows = self.connection.execute(
            "SELECT channel, decision FROM allocation_decisions"
        ).fetchall()
        self.assertEqual(len(rows), len(allocation.CHANNELS))
        self.assertTrue(all(row["decision"] == "insufficient_evidence" for row in rows))

    def test_reallocation_has_no_external_side_effects(self):
        self.assertEqual(allocation.reallocate(self.connection)["external_side_effects"], "none")


class OutreachCalibrationTests(Fixture):
    def test_a_small_cohort_keeps_calibrating(self):
        for index in range(3):
            add_outreach(self.connection, organization=f"org{index}", replies=1)
        result = allocation.calibrate_outreach(self.connection)
        self.assertEqual(result["recommendation"], "CONTINUE_CALIBRATION")

    def test_an_unfinished_cycle_does_not_count_as_completed(self):
        add_outreach(self.connection, organization="pending", sent=1)
        result = allocation.calibrate_outreach(self.connection, record=False)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["completed"], 0)

    def test_placements_recommend_signing_the_policy(self):
        for index in range(12):
            action_id = add_outreach(self.connection, organization=f"win{index}", sent=2,
                                     replies=1, positive=1)
            if index < 2:
                prospect = self.connection.execute(
                    "SELECT prospect_id FROM level1a_actions WHERE id=?", (action_id,)
                ).fetchone()[0]
                self.connection.execute(
                    """INSERT INTO placements (prospect_id, placement_url, link_target, status)
                       VALUES (?, ?, 'https://invoiceworkshop.com/invoice-template/', 'live')""",
                    (prospect, f"https://win{index}.example/list/"),
                )
        self.connection.commit()
        result = allocation.calibrate_outreach(self.connection)
        self.assertEqual(result["recommendation"], "SIGN_POLICY_AND_AUTONOMIZE")

    def test_silence_across_a_full_cohort_stops_the_channel(self):
        for index in range(16):
            add_outreach(self.connection, organization=f"quiet{index}", sent=2)
        result = allocation.calibrate_outreach(self.connection)
        self.assertEqual(result["recommendation"], "STOP_CHANNEL")

    def test_bad_delivery_is_diagnosed_before_the_offer_is_judged(self):
        for index in range(12):
            add_outreach(self.connection, organization=f"bounce{index}", sent=2, bounced=True)
        result = allocation.calibrate_outreach(self.connection)
        self.assertEqual(result["recommendation"], "MODIFY_POLICY_TEMPLATES")
        self.assertIn("deliverability", result["rationale"])

    def test_replies_without_interest_reduce_rather_than_stop(self):
        for index in range(12):
            add_outreach(self.connection, organization=f"meh{index}", sent=2, replies=1)
        result = allocation.calibrate_outreach(self.connection)
        self.assertEqual(result["recommendation"], "REDUCE_EMAIL_ALLOCATION")

    def test_outcomes_are_broken_down_by_prospect_class(self):
        add_outreach(self.connection, organization="assoc", prospect_type="resource")
        add_outreach(self.connection, organization="round", prospect_type="directory")
        result = allocation.calibrate_outreach(self.connection, record=False)
        self.assertEqual(set(result["by_class"]), {"resource", "directory"})

    def test_calibration_recommends_but_never_approves(self):
        """A recommendation must stay a recommendation: nothing it does may
        widen an approval, activate a policy or emit a message."""
        add_outreach(self.connection, organization="candidate", sent=2, replies=1, positive=1)
        self.connection.execute("UPDATE level1a_actions SET external_action_approved=0")
        self.connection.execute(
            """INSERT INTO outreach_policy (version, policy_hash, policy_json, created_at,
                 signed, active)
               VALUES (1, 'h', '{}', '2026-09-01T00:00:00+00:00', 0, 0)"""
        )
        self.connection.commit()
        allocation.calibrate_outreach(self.connection)
        allocation.reallocate(self.connection)
        approved = self.connection.execute(
            "SELECT COUNT(*) FROM level1a_actions WHERE external_action_approved=1"
        ).fetchone()[0]
        signed = self.connection.execute(
            "SELECT COUNT(*) FROM outreach_policy WHERE signed=1 OR active=1"
        ).fetchone()[0]
        sends = self.connection.execute(
            "SELECT COUNT(*) FROM level1a_action_audit WHERE mode='live'"
        ).fetchone()[0]
        self.assertEqual((approved, signed, sends), (0, 0, 2))


class ExperimentEvaluationTests(Fixture):
    def _experiment(self, *, url: str, baseline: str, days_ago: int) -> int:
        due = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
        cursor = self.connection.execute(
            """INSERT INTO growth_experiments
                 (hypothesis, action, action_type, target_url, started_at, evaluate_after,
                  baseline_json, updated_at)
               VALUES ('h', 'a', 'page_improvement', ?, '2026-08-01T00:00:00+00:00', ?, ?,
                       '2026-08-01T00:00:00+00:00')""",
            (url, due, baseline),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def test_an_experiment_inside_its_window_is_left_alone(self):
        self._experiment(url="https://invoiceworkshop.com/", baseline="{}", days_ago=-30)
        self.assertEqual(allocation.evaluate_due(self.connection)["count"], 0)

    def test_a_due_experiment_is_concluded_from_measured_movement(self):
        self._experiment(url="https://invoiceworkshop.com/",
                         baseline='{"impressions": 1, "clicks": 0}', days_ago=1)
        self.connection.execute(
            """INSERT INTO gsc_query_facts
                 (snapshot_date, date, query, page, country, device, impressions, clicks,
                  ctr, position, window_start, window_end)
               VALUES ('2026-09-01', '2026-09-01', 'q', 'https://invoiceworkshop.com/',
                       'usa', 'DESKTOP', 9, 0, 0, 40, '2026-09-01', '2026-09-01')"""
        )
        self.connection.commit()
        result = allocation.evaluate_due(self.connection)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["concluded"][0]["outcome"], "positive")

    def test_a_conclusion_states_that_it_is_weak_evidence(self):
        self._experiment(url="https://invoiceworkshop.com/", baseline="{}", days_ago=1)
        result = allocation.evaluate_due(self.connection)
        self.assertIn("weak evidence", result["concluded"][0]["conclusion"])


if __name__ == "__main__":
    unittest.main()
