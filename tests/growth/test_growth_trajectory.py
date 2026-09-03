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
            "SELECT SUM(target) FROM growth_targets WHERE metric='monthly_impressions'"
        ).fetchone()[0]
        self.organic(sessions=5000)
        self.assertEqual(trajectory.plan(self.connection)["status"], "already planned")
        after = self.connection.execute(
            "SELECT SUM(target) FROM growth_targets WHERE metric='monthly_impressions'"
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

    def _demand(self, queries: int, impressions: int):
        """Queries the site ranks for and impressions it earned. The floor reads
        these; it does not read how many pages produced them."""
        for n in range(queries):
            self.connection.execute(
                """INSERT INTO gsc_query_facts
                     (snapshot_date, date, query, page, country, device,
                      clicks, impressions, position, window_start, window_end)
                   VALUES ('2026-09-02', '2026-09-01', ?, ?, 'gbr', 'DESKTOP',
                           0, 1, 12.0, '2026-08-01', '2026-09-01')""",
                (f"query {n}", f"https://invoiceworkshop.com/page-{n % 20}/"))
        self.connection.execute(
            """INSERT INTO metrics_daily (date, collected_at, gsc_impressions)
               VALUES ('2026-09-01', '2026-09-02T00:00:00+00:00', ?)""",
            (impressions,))
        self.connection.commit()

    def test_far_short_of_the_demand_the_target_needs_floors_intensity_high(self):
        """The weekly curve is easy to meet early; the destination is not."""
        self._pages(13)
        level, reason = trajectory.structural_floor(self.connection)
        self.assertGreaterEqual(level, 4)
        self.assertIn("Structural shortfall on demand", reason)

    def test_enough_demand_removes_the_floor(self):
        self._demand(
            queries=int(trajectory.TERMINAL["ranking_queries"] * 0.8),
            impressions=int(trajectory.TERMINAL["monthly_impressions"] * 0.8))
        level, _ = trajectory.structural_floor(self.connection)
        self.assertEqual(level, 1)

    def test_pages_alone_never_remove_the_floor(self):
        """A thousand pages earning nothing is exactly the outcome the objective
        was rewritten to stop rewarding."""
        self._pages(1000)
        level, reason = trajectory.structural_floor(self.connection)
        self.assertEqual(level, 4)
        self.assertIn("Structural shortfall on demand", reason)

    def test_the_floor_applies_even_when_the_week_is_met(self):
        self._pages(13)
        self.organic(sessions=10_000_000)
        trajectory.plan(self.connection)
        result = trajectory.checkpoint(self.connection, week=1)
        # Sessions are wildly ahead of the curve and it changes nothing: the
        # demand the target needs still does not exist.
        self.assertEqual(result["detail"]["daily_sessions"]["ratio"], 1.5)
        self.assertGreaterEqual(result["intensity_after"], 4)
        self.assertIn("Structural shortfall on demand", result["verdict"])

    def test_a_short_queue_asks_for_research_not_a_lower_bar(self):
        self._pages(13)
        trajectory.plan(self.connection)
        trajectory.checkpoint(self.connection, week=1)
        row = self.connection.execute(
            "SELECT detail FROM escalations WHERE kind='surface_queue_short'").fetchone()
        self.assertIsNotNone(row)
        self.assertIn("never admitting weaker ones", row["detail"])
        self.assertIn("an empty queue is a legitimate steady state", row["detail"])


class SurfaceFirstTests(Fixture):
    def _admitted_content_page(self, route: str = "/synthetic-family/") -> None:
        """An admitted, unbuilt, content-only page waiting in the queue.

        Written directly rather than taken from the live catalogue: every family
        in it is either already shipped or needs product work, so a catalogue
        that legitimately has nothing content-only left would silently stop
        exercising the selection rule this test is about.
        """
        now = utc_now()
        self.connection.execute(
            """INSERT INTO page_families
                 (family_key, dimension, name, demand_evidence, differentiation,
                  product_change, gate_json, status, created_at, updated_at)
               VALUES ('synthetic', 'document', 'Synthetic', 'demand', '[]', 'change',
                       '{"build_scope": "content_only"}', 'admitted', ?, ?)""",
            (now, now))
        self.connection.execute(
            """INSERT INTO page_candidates
                 (slug, family_key, title, route, demand_score, differentiators,
                  status, created_at, updated_at)
               VALUES ('synthetic', 'synthetic', 'Synthetic', ?, 4.0, '[]',
                       'queued', ?, ?)""", (route, now, now))
        self.connection.commit()

    def test_a_queued_page_outranks_improving_an_existing_one(self):
        trajectory.plan(self.connection)
        trajectory.checkpoint(self.connection, week=4)
        self._admitted_content_page()
        candidate = policy.select_candidate(self.connection)
        self.assertTrue(candidate["eligible"])
        self.assertIn("surface_page", candidate)

    def test_the_weekly_page_quota_is_respected(self):
        self._admitted_content_page()
        self.connection.execute(
            """UPDATE page_candidates SET status='shipped', shipped_at=?""", (utc_now(),))
        self.connection.commit()
        self.assertIsNone(policy.next_surface_page(self.connection))


if __name__ == "__main__":
    unittest.main()


class ObjectiveTests(Fixture):
    """Page count is not an objective and must not be able to become one."""

    def test_no_target_is_a_count_of_pages_published(self):
        self.assertNotIn("published_pages", trajectory.TERMINAL)
        self.assertNotIn("published_pages", trajectory.WEIGHTS)
        self.assertNotIn("indexed_pages", trajectory.TERMINAL)
        self.assertNotIn("indexed_pages", trajectory.WEIGHTS)

    def test_every_scored_metric_is_something_the_market_does(self):
        """A page cannot satisfy any of these by existing. That is the property
        that stops the objective turning back into a publishing quota."""
        self.assertEqual(
            set(trajectory.WEIGHTS),
            {"ranking_queries", "queries_top_20", "queries_top_10",
             "monthly_impressions", "pages_with_impressions", "referring_domains",
             "daily_sessions"})
        self.assertAlmostEqual(sum(trajectory.WEIGHTS.values()), 1.0, places=6)

    def test_page_counts_are_still_measured_for_explanation(self):
        live = trajectory.measure(self.connection)
        for metric in trajectory.DIAGNOSTIC_ONLY:
            self.assertIn(metric, live)

    def test_the_structural_floor_reads_demand_not_pages(self):
        self.assertNotIn("published_pages", trajectory.FLOOR_METRICS)
        for metric in trajectory.FLOOR_METRICS:
            self.assertIn(metric, trajectory.WEIGHTS)

    def test_the_floor_never_asks_for_more_pages(self):
        level, reason = trajectory.structural_floor(self.connection)
        self.assertNotIn("pages the", reason)
        self.assertIn("never a lower bar or a larger page count", reason)

    def test_retargeting_leaves_surviving_metrics_untouched(self):
        trajectory.plan(self.connection)
        before = dict(self.connection.execute(
            "SELECT week, target FROM growth_targets WHERE experiment=? AND metric=?",
            (trajectory.EXPERIMENT, "monthly_impressions")))
        self.connection.execute(
            """INSERT INTO growth_targets (experiment, week, week_ending, metric, target)
               VALUES (?, 0, '2026-09-02', 'published_pages', 900)""",
            (trajectory.EXPERIMENT,))
        self.connection.commit()
        result = trajectory.reconcile_metrics(self.connection)
        self.assertIn("published_pages", result["metrics_dropped"])
        after = dict(self.connection.execute(
            "SELECT week, target FROM growth_targets WHERE experiment=? AND metric=?",
            (trajectory.EXPERIMENT, "monthly_impressions")))
        self.assertEqual(before, after)

    def test_the_weekly_ceiling_is_described_as_a_ceiling(self):
        source = Path(trajectory.__file__).read_text()
        self.assertIn("CEILINGS, never quotas to fill", source)
