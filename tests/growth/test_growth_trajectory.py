from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_auto_policy as policy  # noqa: E402
import growth_trajectory as trajectory  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def organic(self, sessions: int, pageviews: int | None = None):
        self.connection.execute(
            """INSERT INTO ga4_acquisition
                 (snapshot_date, date, source, medium, source_medium,
                  default_channel_group, users, sessions, pageviews,
                  window_start, window_end)
               VALUES ('2026-09-02', '2026-09-01', 'google', 'organic', 'google / organic',
                       'Organic Search', ?, ?, ?, '2026-08-01', '2026-09-02')""",
            (sessions, sessions, pageviews if pageviews is not None else sessions))
        self.connection.commit()


class ArithmeticTests(Fixture):
    def test_the_baseline_counts_organic_only(self):
        """All traffic so far is direct; counting it would understate the target
        by two orders of magnitude."""
        self.connection.execute(
            """INSERT INTO ga4_acquisition
                 (snapshot_date, date, source, medium, source_medium,
                  default_channel_group, users, sessions, pageviews,
                  window_start, window_end)
               VALUES ('2026-09-02', '2026-09-01', '(direct)', '(none)', '(direct) / (none)',
                       'Direct', 500, 500, 500, '2026-08-01', '2026-09-02')""")
        self.connection.commit()
        self.assertEqual(trajectory._baseline(self.connection)["organic_sessions_measured"], 0)

    def test_pageviews_per_session_is_measured_not_assumed(self):
        self.organic(sessions=100, pageviews=250)
        self.assertEqual(trajectory.pageviews_per_session(self.connection), 2.5)

    def test_a_worse_ratio_makes_the_requirement_harder(self):
        self.organic(sessions=10, pageviews=10)
        tight = trajectory.required_weekly_growth(self.connection)["multiple_required"]
        self.connection.execute("DELETE FROM ga4_acquisition")
        self.organic(sessions=10, pageviews=30)
        loose = trajectory.required_weekly_growth(self.connection)["multiple_required"]
        self.assertGreater(tight, loose)

    def test_the_requirement_is_reported_even_when_it_is_absurd(self):
        requirement = trajectory.required_weekly_growth(self.connection)
        self.assertGreater(requirement["multiple_required"], 1000)
        self.assertIn("%", requirement["weekly_growth_required"])


class PlanTests(Fixture):
    def test_targets_are_written_once_and_not_moved_to_fit_results(self):
        trajectory.plan(self.connection)
        before = self.connection.execute(
            "SELECT SUM(target) FROM growth_targets WHERE metric='published_pages'"
        ).fetchone()[0]
        self.organic(sessions=5000)
        self.assertEqual(trajectory.plan(self.connection)["status"], "already planned")
        after = self.connection.execute(
            "SELECT SUM(target) FROM growth_targets WHERE metric='published_pages'"
        ).fetchone()[0]
        self.assertEqual(before, after)

    def test_the_final_week_target_is_the_stated_goal(self):
        trajectory.plan(self.connection)
        final = self.connection.execute(
            """SELECT target FROM growth_targets
                WHERE metric='monthly_pageviews' AND week=?""", (trajectory.WEEKS,)
        ).fetchone()[0]
        self.assertGreater(final, trajectory.TARGET_PAGEVIEWS * 0.8)


class EscalationTests(Fixture):
    def _checkpoint(self):
        trajectory.plan(self.connection)
        return trajectory.checkpoint(self.connection, week=4)

    def test_being_far_behind_escalates_to_the_top(self):
        result = self._checkpoint()
        self.assertEqual(result["intensity_after"], 5)
        self.assertGreater(result["quotas"]["pages_per_week"],
                           trajectory.INTENSITY[1]["pages_per_week"])

    def test_escalation_raises_quota_and_never_the_content_bar(self):
        self._checkpoint()
        source = (SCRIPTS / "growth_trajectory.py").read_text(encoding="utf-8")
        for knob in ("MIN_FUNCTIONAL", "MIN_DIFFERENTIATORS", "GateRefusal"):
            self.assertNotIn(knob, source, f"intensity must not reach {knob}")
        for level in trajectory.INTENSITY.values():
            self.assertIn("pages_per_week", level)

    def test_intensity_drives_the_executor_budget(self):
        self._checkpoint()
        self.assertEqual(policy.daily_run_budget(self.connection),
                         trajectory.INTENSITY[5]["claude_runs_per_day"])

    def test_intensity_eases_one_step_at_a_time(self):
        trajectory.plan(self.connection)
        trajectory.checkpoint(self.connection, week=4)
        self.connection.execute("DELETE FROM trajectory_checkpoints")
        self.organic(sessions=100_000)
        result = trajectory.checkpoint(self.connection, week=1)
        self.assertEqual(result["intensity_after"], 4)

    def test_a_structural_gap_at_maximum_intensity_is_escalated_to_a_person(self):
        self._checkpoint()
        row = self.connection.execute(
            "SELECT subject FROM escalations WHERE kind='trajectory_structural_gap'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_the_checkpoint_is_recorded_whatever_it_finds(self):
        self._checkpoint()
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM trajectory_checkpoints").fetchone()[0], 1)


class StructuralFloorTests(Fixture):
    def _pages(self, count: int):
        for n in range(count):
            self.connection.execute(
                """INSERT INTO page_content_stats (url, measured_at, words)
                   VALUES (?, '2026-09-02T00:00:00+00:00', 800)""",
                (f"https://invoiceworkshop.com/page-{n}/",))
        self.connection.commit()

    def test_far_short_of_the_needed_surface_area_floors_intensity_high(self):
        """The weekly curve is easy to meet early; the destination is not."""
        self._pages(13)
        level, reason = trajectory.structural_floor(self.connection)
        self.assertGreaterEqual(level, 4)
        self.assertIn("Structural shortfall", reason)

    def test_enough_pages_removes_the_floor(self):
        self._pages(int(trajectory.TERMINAL["published_pages"] * 0.8))
        level, _ = trajectory.structural_floor(self.connection)
        self.assertEqual(level, 1)

    def test_the_floor_applies_even_when_the_week_is_met(self):
        self._pages(13)
        self.organic(sessions=10_000_000)
        trajectory.plan(self.connection)
        result = trajectory.checkpoint(self.connection, week=1)
        # Sessions are wildly ahead of the curve and it changes nothing: the
        # surface area the target needs still does not exist.
        self.assertEqual(result["detail"]["daily_sessions"]["ratio"], 1.5)
        self.assertGreaterEqual(result["intensity_after"], 4)
        self.assertIn("Structural shortfall", result["verdict"])

    def test_a_short_queue_asks_for_research_not_a_lower_bar(self):
        self._pages(13)
        trajectory.plan(self.connection)
        trajectory.checkpoint(self.connection, week=1)
        row = self.connection.execute(
            "SELECT detail FROM escalations WHERE kind='surface_queue_short'").fetchone()
        self.assertIsNotNone(row)
        self.assertIn("never admitting weaker ones", row["detail"])


class SurfaceFirstTests(Fixture):
    def test_a_queued_page_outranks_improving_an_existing_one(self):
        import growth_surface
        trajectory.plan(self.connection)
        trajectory.checkpoint(self.connection, week=4)
        growth_surface.evaluate(self.connection)
        candidate = policy.select_candidate(self.connection)
        self.assertTrue(candidate["eligible"])
        self.assertIn("surface_page", candidate)

    def test_the_weekly_page_quota_is_respected(self):
        import growth_surface
        growth_surface.evaluate(self.connection)
        self.connection.execute(
            """UPDATE page_candidates SET status='shipped', shipped_at=?""", (utc_now(),))
        self.connection.commit()
        self.assertIsNone(policy.next_surface_page(self.connection))


if __name__ == "__main__":
    unittest.main()
