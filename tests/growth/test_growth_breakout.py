from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_allocation as allocation  # noqa: E402
import growth_breakout as breakout  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()


class GateTests(Fixture):
    def _destination(self, **over):
        base = {
            "key": "test", "channel": "directories", "name": "Test",
            "url": "https://example.org/", "audience_fit": "real people",
            "evidence": "checked on a date", "confidence": 0.5, "farm_signals": [],
        }
        base.update(over)
        return base

    def test_a_directory_farm_is_refused_on_its_own_properties(self):
        with self.assertRaises(breakout.DestinationRefusal) as caught:
            breakout.check(self._destination(farm_signals=["pay_for_followed_link"]))
        self.assertIn("paying for a followed link", str(caught.exception))

    def test_a_site_whose_audience_is_other_submitters_is_refused(self):
        with self.assertRaises(breakout.DestinationRefusal):
            breakout.check(self._destination(farm_signals=["audience_is_submitters"]))

    def test_an_unverified_destination_is_not_submitted_to_blind(self):
        with self.assertRaises(breakout.DestinationRefusal) as caught:
            breakout.check(self._destination(confidence=0.1))
        self.assertIn("could not be verified", str(caught.exception))

    def test_a_destination_with_nothing_recorded_about_it_is_refused(self):
        with self.assertRaises(breakout.DestinationRefusal):
            breakout.check(self._destination(evidence=""))

    def test_a_legitimate_destination_is_admitted(self):
        self.assertEqual(breakout.check(self._destination()), {"admitted": True})


class ExecutionClassTests(Fixture):
    def test_payment_forces_review(self):
        klass, why = breakout.execution_class({"requires_payment": True})
        self.assertEqual(klass, "REVIEW")
        self.assertIn("does not spend money unattended", why)

    def test_a_personal_identity_requirement_forces_review_and_is_never_faked(self):
        klass, why = breakout.execution_class({"requires_personal_identity": True})
        self.assertEqual(klass, "REVIEW")
        self.assertIn("inventing a founder", why)

    def test_community_standing_cannot_be_manufactured(self):
        klass, why = breakout.execution_class({"requires_community_posting": True})
        self.assertEqual(klass, "REVIEW")

    def test_an_external_account_forces_review(self):
        klass, _ = breakout.execution_class({"requires_account": True})
        self.assertEqual(klass, "REVIEW")

    def test_only_a_destination_demanding_nothing_is_auto(self):
        klass, _ = breakout.execution_class({
            "requires_account": False, "requires_payment": False,
            "requires_personal_identity": False, "requires_community_posting": False})
        self.assertEqual(klass, "AUTO")

    def test_outreach_pipelines_say_their_sends_are_still_gated(self):
        klass, why = breakout.execution_class({
            "channel": "creator_newsletter", "requires_account": False,
            "requires_payment": False, "requires_personal_identity": False,
            "requires_community_posting": False})
        self.assertEqual(klass, "AUTO")
        self.assertIn("Level-1A approval gate", why)

    def test_being_behind_target_cannot_move_a_destination_to_auto(self):
        """The class is derived from the destination only. Nothing in this
        module reads the trajectory, and a test asserts it stays that way."""
        source = Path(breakout.__file__).read_text()
        self.assertNotIn("growth_trajectory", source)
        self.assertNotIn("intensity", source)


class CatalogueTests(Fixture):
    def test_every_catalogued_destination_records_when_it_was_checked(self):
        for destination in breakout.DESTINATIONS:
            self.assertTrue(destination["verified_on"], destination["key"])
            self.assertTrue(destination["evidence"], destination["key"])

    def test_evaluate_admits_refuses_and_classifies(self):
        result = breakout.evaluate(self.connection)
        self.assertTrue(result["admitted"])
        self.assertTrue(result["refused"])
        keys = {row["key"] for row in result["refused"]}
        self.assertIn("generic-saas-listicle-farm", keys)

    def test_product_hunt_is_review_not_auto(self):
        breakout.evaluate(self.connection)
        row = self.connection.execute(
            "SELECT execution_class FROM breakout_destinations WHERE key='ph-launch'"
        ).fetchone()
        self.assertEqual(row["execution_class"], "REVIEW")

    def test_ranking_puts_speed_and_intent_ahead_of_raw_size(self):
        slow_giant = {"reach": 5000, "intent": 0.5, "confidence": 0.5,
                      "speed_days": 180, "effort": 3}
        fast_fit = {"reach": 500, "intent": 0.9, "confidence": 0.7,
                    "speed_days": 2, "effort": 1}
        self.assertGreater(breakout.score(fast_fit), breakout.score(slow_giant))


class PreparationTests(Fixture):
    def test_preparing_a_review_destination_writes_the_whole_submission(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        bundle = breakout.bundle(self.connection, "ph-launch")["bundle"]
        for field in ("tagline", "description", "maker_comment", "assets_needed",
                      "tracked_url", "what_the_owner_must_do"):
            self.assertTrue(bundle.get(field), field)

    def test_the_owner_action_says_why_it_cannot_be_done_here(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        bundle = breakout.bundle(self.connection, "ph-launch")["bundle"]
        self.assertIn("real person", bundle["what_the_owner_must_do"])

    def test_preparation_sends_nothing(self):
        breakout.evaluate(self.connection)
        self.assertEqual(breakout.prepare(self.connection)["external_side_effects"], "none")

    def test_each_destination_gets_its_own_tracked_url(self):
        first = breakout.tracked_url("/", "ph-launch")
        second = breakout.tracked_url("/", "alternativeto")
        self.assertNotEqual(first, second)
        self.assertIn("utm_source=ph-launch", first)
        self.assertTrue(first.startswith("https://invoiceworkshop.com/"))

    def test_an_owner_escalation_names_what_is_waiting(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        row = self.connection.execute(
            "SELECT subject, detail FROM escalations WHERE kind='breakout_owner_launch'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("Product Hunt", row["detail"])


class TrafficMixTests(Fixture):
    def _sessions(self, group: str, sessions: int, downloads: int = 0):
        self.connection.execute(
            """INSERT INTO ga4_acquisition
                 (snapshot_date, date, source, medium, source_medium,
                  default_channel_group, users, sessions, pageviews, tool_starts,
                  pdf_downloads, window_start, window_end)
               VALUES ('2026-09-03', '2026-09-02', ?, 'x', ?, ?, ?, ?, ?, 0, ?,
                       '2026-08-01', '2026-09-02')""",
            (group, group, group, sessions, sessions, sessions, downloads))
        self.connection.commit()

    def test_channels_are_reported_separately(self):
        self._sessions("Organic Search", 10, 2)
        self._sessions("Direct", 90, 1)
        mix = breakout.traffic_mix(self.connection)["mix"]
        self.assertEqual(mix["organic_search"]["sessions"], 10)
        self.assertEqual(mix["direct"]["sessions"], 90)
        self.assertEqual(mix["organic_search"]["share"], 0.1)

    def test_completion_rate_is_what_separates_a_good_channel_from_a_loud_one(self):
        self._sessions("Referral", 1000, 1)
        self._sessions("Organic Search", 100, 20)
        mix = breakout.traffic_mix(self.connection)["mix"]
        self.assertGreater(mix["organic_search"]["completion_rate"],
                           mix["referral"]["completion_rate"])

    def test_an_unrecognised_group_is_not_folded_into_a_bucket_it_may_not_belong_to(self):
        self._sessions("Some New Google Bucket", 5)
        self.assertIn("other", breakout.traffic_mix(self.connection)["mix"])


class AllocationTests(Fixture):
    def test_every_breakout_channel_is_in_the_weekly_portfolio(self):
        for channel in ("launch_platforms", "directories", "creator_newsletter",
                        "social_community", "product_loops", "linkable_assets"):
            self.assertIn(channel, allocation.CHANNELS)

    def test_a_channel_with_nothing_live_reads_as_untried_not_failed(self):
        evidence = allocation.channel_evidence(self.connection)
        self.assertIn("nothing has been attempted",
                      evidence["launch_platforms"]["detail"])

    def test_a_prepared_destination_is_not_counted_as_a_failed_attempt(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        self.assertEqual(
            allocation.channel_evidence(self.connection)["launch_platforms"]["attempts"], 0)

    def test_a_live_destination_that_sent_nobody_is_an_attempt_with_no_win(self):
        breakout.evaluate(self.connection)
        self.connection.execute(
            "UPDATE breakout_destinations SET status='live' WHERE key='ph-launch'")
        self.connection.execute(
            """INSERT INTO breakout_results (destination_key, observed_on, referral_sessions)
               VALUES ('ph-launch', '2026-09-04', 12)""")
        self.connection.commit()
        evidence = allocation.channel_evidence(self.connection)["launch_platforms"]
        self.assertEqual(evidence["attempts"], 1)
        self.assertEqual(evidence["wins"], 0)

    def test_high_variance_channels_keep_an_exploration_floor(self):
        """Killing a long-tailed channel on its first run of zeros is how a
        portfolio ends up holding only small reliable insufficient results."""
        allocation.ensure_channels(self.connection)
        self.connection.execute(
            "UPDATE channel_allocation SET weight=0.7 WHERE channel='launch_platforms'")
        self.connection.commit()
        breakout.evaluate(self.connection)
        self.connection.execute(
            "UPDATE breakout_destinations SET status='live' "
            "WHERE key IN ('ph-launch','uneed')")
        self.connection.commit()
        allocation.reallocate(self.connection)
        weight = self.connection.execute(
            "SELECT weight FROM channel_allocation WHERE channel='launch_platforms'"
        ).fetchone()[0]
        self.assertGreaterEqual(weight, allocation.EXPLORATION_FLOOR)


if __name__ == "__main__":
    unittest.main()
