from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_health as health  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def fresh_collection(self):
        self.connection.execute(
            """INSERT INTO collection_runs (started_at, finished_at, status)
               VALUES (?, ?, 'ok')""", (utc_now(), utc_now()))
        self.connection.commit()


class StalenessTests(Fixture):
    def test_collection_that_stopped_is_reported(self):
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        self.connection.execute(
            "INSERT INTO collection_runs (started_at, finished_at, status) VALUES (?,?,'ok')",
            (old, old))
        self.connection.commit()
        problems = health.check_collection(self.connection)
        self.assertEqual(problems[0]["kind"], "collection_stale")

    def test_a_never_collected_database_is_reported(self):
        self.assertTrue(health.check_collection(self.connection))

    def test_fresh_collection_is_silent(self):
        self.fresh_collection()
        self.assertEqual(health.check_collection(self.connection), [])


class WorkerHealthTests(Fixture):
    def _run(self, outcome: str):
        self.connection.execute(
            """INSERT INTO claude_runs (started_at, run_type, outcome)
               VALUES (?, 'auto_opportunity', ?)""", (utc_now(), outcome))
        self.connection.commit()

    def test_three_consecutive_failures_are_reported(self):
        for _ in range(3):
            self._run("validation_failed")
        problems = health.check_worker(self.connection)
        self.assertEqual(problems[0]["kind"], "worker_failing")

    def test_repeated_no_action_is_not_a_failure(self):
        for _ in range(5):
            self._run("no_action")
        self.assertEqual(health.check_worker(self.connection), [])

    def test_too_few_runs_to_judge_stays_quiet(self):
        self._run("error")
        self._run("error")
        self.assertEqual(health.check_worker(self.connection), [])


class EscalationTests(Fixture):
    def test_a_healthy_system_prints_nothing(self):
        self.fresh_collection()
        with mock.patch.object(health, "check_scheduler", return_value=[]), \
             mock.patch.object(health, "check_locks", return_value=[]):
            problems = health.run(self.connection)
        self.assertEqual(problems, [])
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL").fetchone()[0], 0)

    def test_repeats_collapse_onto_one_row(self):
        with mock.patch.object(health, "check_scheduler", return_value=[]), \
             mock.patch.object(health, "check_locks", return_value=[]):
            for _ in range(4):
                health.run(self.connection)
        row = self.connection.execute(
            "SELECT occurrences FROM escalations WHERE kind='collection_stale'").fetchone()
        self.assertEqual(row["occurrences"], 4)

    def test_a_condition_that_clears_is_resolved(self):
        with mock.patch.object(health, "check_scheduler", return_value=[]), \
             mock.patch.object(health, "check_locks", return_value=[]):
            health.run(self.connection)
            self.assertEqual(self.connection.execute(
                "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL").fetchone()[0], 1)
            self.fresh_collection()
            health.run(self.connection)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL").fetchone()[0], 0)

    def test_a_broken_check_does_not_silence_the_others(self):
        with mock.patch.object(health, "CHECKS", (
            ("scheduler", mock.Mock(side_effect=OSError("boom"))),
            ("collection", health.check_collection),
        )):
            problems = health.run(self.connection)
        kinds = {problem["kind"] for problem in problems}
        self.assertIn("health_check_error", kinds)
        self.assertIn("collection_stale", kinds)

    def test_the_first_backlink_is_a_milestone_worth_reporting(self):
        self.connection.execute(
            """INSERT INTO placements (placement_url, link_target, status)
               VALUES ('https://someone.example/list/',
                       'https://invoiceworkshop.com/invoice-template/', 'live')""")
        self.connection.commit()
        subjects = [problem["subject"] for problem in health.check_milestones(self.connection)]
        self.assertTrue(any("First confirmed backlink" in subject for subject in subjects))

    def test_an_unfinished_outreach_cohort_raises_nothing(self):
        self.connection.execute(
            """INSERT INTO outreach_calibration
                 (evaluated_at, cohort_size, completed, sent, delivered, bounced, replies,
                  positive_replies, placements, recommendation, rationale)
               VALUES (?, 10, 0, 3, 3, 0, 0, 0, 0, 'CONTINUE_CALIBRATION', 'too early')""",
            (utc_now(),))
        self.connection.commit()
        self.assertEqual(health.check_outreach(self.connection), [])

    def test_a_finished_cohort_asks_for_a_decision(self):
        self.connection.execute(
            """INSERT INTO outreach_calibration
                 (evaluated_at, cohort_size, completed, sent, delivered, bounced, replies,
                  positive_replies, placements, recommendation, rationale)
               VALUES (?, 12, 12, 24, 24, 0, 4, 2, 2, 'SIGN_POLICY_AND_AUTONOMIZE', 'works')""",
            (utc_now(),))
        self.connection.commit()
        problems = health.check_outreach(self.connection)
        self.assertEqual(problems[0]["kind"], "outreach_decision_due")


if __name__ == "__main__":
    unittest.main()
