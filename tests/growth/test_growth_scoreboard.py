from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_scoreboard as scoreboard  # noqa: E402
import growth_trajectory as trajectory  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402


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
                  tool_starts, pdf_downloads, window_start, window_end)
               VALUES ('2026-09-02', '2026-09-01', 'google', 'organic',
                       'google / organic', 'Organic Search', ?, ?, ?, 12, 5,
                       '2026-08-01', '2026-09-01')""",
            (sessions, sessions, pageviews if pageviews is not None else sessions))
        self.connection.commit()


class ShapeTests(Fixture):
    def test_every_group_the_owner_asked_for_is_present(self):
        board = scoreboard.build(self.connection)
        for group in ("search_surface", "google", "authority", "usage", "velocity",
                      "target_gap"):
            self.assertIn(group, board)

    def test_the_google_group_reports_the_ranking_bands(self):
        google = scoreboard.build(self.connection)["google"]
        for key in ("queries_top_50", "queries_top_20", "queries_top_10",
                    "impressions", "clicks", "indexed_pages"):
            self.assertIn(key, google)

    def test_usage_reports_product_completion_not_just_visits(self):
        self.organic(sessions=100, pageviews=150)
        usage = scoreboard.build(self.connection)["usage"]
        self.assertEqual(usage["tool_starts"], 12)
        self.assertEqual(usage["pdf_downloads"], 5)
        self.assertEqual(usage["pageviews_per_session"], 1.5)

    def test_spend_is_labelled_as_a_list_price_estimate(self):
        velocity = scoreboard.build(self.connection)["velocity"]
        self.assertIn("not an amount billed", velocity["spend_note"])

    def test_addressable_demand_says_what_it_does_not_measure(self):
        surface = scoreboard.build(self.connection)["search_surface"]
        self.assertIn("no keyword-volume source is connected",
                      surface["addressable_demand_note"])


class VerdictTests(Fixture):
    def test_a_zero_baseline_is_reported_as_structurally_behind(self):
        gap = scoreboard.build(self.connection)["target_gap"]
        self.assertEqual(gap["trajectory_status"], "STRUCTURALLY_BEHIND")
        self.assertIn("not a rate this strategy produces", gap["verdict"])

    def test_a_baseline_that_makes_the_target_easy_reads_as_breakout(self):
        self.organic(sessions=14_000)
        gap = scoreboard.build(self.connection)["target_gap"]
        self.assertEqual(gap["trajectory_status"], "ON_BREAKOUT_TRAJECTORY")

    def test_the_middle_band_exists_and_is_reachable(self):
        # Chosen so the required weekly rate lands between the two ceilings.
        self.organic(sessions=120)
        gap = scoreboard.build(self.connection)["target_gap"]
        self.assertEqual(gap["trajectory_status"], "POSSIBLE_BUT_BEHIND")
        self.assertIn("step change", gap["verdict"])

    def test_the_status_vocabulary_is_exactly_the_three_owner_terms(self):
        self.assertEqual(
            scoreboard.STATUSES,
            ("ON_BREAKOUT_TRAJECTORY", "POSSIBLE_BUT_BEHIND", "STRUCTURALLY_BEHIND"))

    def test_the_run_rate_is_organic_only(self):
        """Direct traffic is not evidence the search strategy is working, and
        counting it would flatter the gap by two orders of magnitude."""
        self.connection.execute(
            """INSERT INTO ga4_acquisition
                 (snapshot_date, date, source, medium, source_medium,
                  default_channel_group, users, sessions, pageviews,
                  window_start, window_end)
               VALUES ('2026-09-02', '2026-09-01', '(direct)', '(none)',
                       '(direct) / (none)', 'Direct', 5000, 5000, 6000,
                       '2026-08-01', '2026-09-01')""")
        self.connection.commit()
        gap = scoreboard.build(self.connection)["target_gap"]
        self.assertEqual(gap["current_monthly_pageview_run_rate"], 0)


class HonestyTests(Fixture):
    def test_the_scoreboard_writes_no_target(self):
        trajectory.plan(self.connection)
        before = sorted(map(tuple, self.connection.execute(
            "SELECT week, metric, target FROM growth_targets")))
        scoreboard.publish(self.connection)
        after = sorted(map(tuple, self.connection.execute(
            "SELECT week, metric, target FROM growth_targets")))
        self.assertEqual(before, after)

    def test_the_objective_line_denies_page_count(self):
        self.assertIn("Page count is not in it",
                      scoreboard.build(self.connection)["objective"])

    def test_a_hardened_verdict_escalates_only_after_the_first_weeks(self):
        scoreboard.publish(self.connection)
        self.assertEqual(0, self.connection.execute(
            "SELECT COUNT(*) FROM escalations WHERE kind='trajectory_structurally_behind'"
        ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
