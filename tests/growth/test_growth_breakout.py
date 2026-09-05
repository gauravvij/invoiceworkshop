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


class LaunchTests(Fixture):
    def test_the_eligibility_rule_is_one_week_not_thirty_days(self):
        """The 30-day figure came from a third-party launch guide, not from
        Product Hunt, and it was wrong."""
        self.assertEqual(breakout.PRODUCT_HUNT_LAUNCH["account_min_age_days"], 7)
        source = Path(breakout.__file__).read_text()
        self.assertIn("ONE WEEK old", source)
        self.assertNotIn("30+ days old", source)

    def test_the_target_date_is_a_tuesday(self):
        from datetime import date
        self.assertEqual(date.fromisoformat(
            breakout.PRODUCT_HUNT_LAUNCH["planned_for"]).weekday(), 1)

    def test_without_an_account_date_the_launch_is_blocked_not_assumed_ready(self):
        plan = breakout.launch_plan(self.connection)
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("cannot be verified", plan["eligibility"])

    def test_an_account_created_in_time_clears_the_date(self):
        plan = breakout.launch_plan(self.connection, account_created_on="2026-09-03")
        self.assertEqual(plan["status"], "planned")
        self.assertIn("clear for the target date", plan["eligibility"])

    def test_an_account_created_too_late_blocks_and_names_the_earliest_date(self):
        plan = breakout.launch_plan(self.connection, account_created_on="2026-09-12")
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("2026-09-19", plan["eligibility"])

    def test_the_launch_is_not_judged_on_upvotes(self):
        plan = breakout.launch_plan(self.connection)
        self.assertNotIn("upvotes", plan["judged_on"])
        self.assertIn("tool_starts", plan["judged_on"])
        self.assertIn("pdf_downloads", plan["judged_on"])

    def test_every_tool_page_gets_its_own_tracked_url(self):
        urls = breakout.launch_plan(self.connection)["tracked_urls"]
        self.assertEqual(len(set(urls.values())), len(urls))
        for url in urls.values():
            self.assertIn("utm_source=producthunt", url)

    def test_results_come_from_our_analytics_not_the_platform(self):
        breakout.launch_plan(self.connection)
        result = breakout.launch_results(self.connection)
        self.assertIn("landing_sessions", result)
        self.assertIn("completion_rate", result)
        self.assertNotIn("upvotes", result)


class DistributionDebtTests(Fixture):
    def _built(self, family_key: str, name: str = "Family"):
        now = utc_now()
        self.connection.execute(
            """INSERT INTO page_families
                 (family_key, dimension, name, demand_evidence, differentiation,
                  product_change, status, created_at, updated_at)
               VALUES (?, 'document', ?, 'demand', '[]', 'change', 'built', ?, ?)""",
            (family_key, name, now, now))
        self.connection.commit()

    def test_a_family_that_shipped_with_no_audience_research_owes_distribution(self):
        self._built("doc-receipt", "Receipt generator")
        debt = breakout.distribution_debt(self.connection)
        self.assertEqual(len(debt["families_with_debt"]), 1)
        self.assertIn("qualified freelancer_newsletter targets",
                      debt["families_with_debt"][0]["owes"])

    def test_a_family_with_no_audience_chosen_at_all_is_named_as_such(self):
        self._built("doc-mystery", "Something")
        debt = breakout.distribution_debt(self.connection)
        self.assertIn("no audience segment chosen",
                      debt["families_with_debt"][0]["owes"])

    def test_the_debt_is_escalated_so_it_cannot_be_quietly_skipped(self):
        self._built("doc-receipt")
        breakout.distribution_debt(self.connection)
        row = self.connection.execute(
            "SELECT detail FROM escalations WHERE kind='distribution_debt'").fetchone()
        self.assertIsNotNone(row)
        self.assertIn("half-finished", row["detail"])

    def test_enough_audience_and_surfaces_clears_it(self):
        self._built("doc-receipt")
        breakout.evaluate(self.connection)
        now = utc_now()
        for n in range(breakout.MIN_TARGETS_PER_FAMILY):
            self.connection.execute(
                """INSERT INTO creator_prospects
                     (domain, page_url, segment, status, discovered_at, updated_at)
                   VALUES (?, ?, 'freelancer_newsletter', 'qualified', ?, ?)""",
                (f"e{n}.org", f"https://e{n}.org/", now, now))
        self.connection.commit()
        self.assertEqual(breakout.distribution_debt(self.connection)["families_with_debt"], [])

    def test_every_owner_required_destination_has_a_setup_procedure(self):
        for key in ("ph-launch", "alternativeto", "saashub", "uneed"):
            setup = breakout.OWNER_SETUP[key]
            self.assertTrue(setup["steps"], key)
            self.assertTrue(setup["after_setup"], key)
            self.assertLessEqual(setup["minutes"], 20, key)

    def test_setup_says_what_stops_needing_the_owner_afterwards(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        bundle = breakout.bundle(self.connection, "alternativeto")["bundle"]
        self.assertIn("no repeated owner research", bundle["after_setup"])


class BundleFreshnessTests(Fixture):
    """The launch is two weeks out and the product changes weekly. A bundle
    describing the product as it was three families ago is worse than none."""

    def test_the_tool_list_is_read_from_the_live_routes(self):
        tools = breakout.live_tools()
        self.assertIn("invoices", tools)
        self.assertIn("receipts", tools)
        self.assertIn("credit notes", tools)
        self.assertIn("timesheet invoices", tools)
        self.assertIn("delivery notes", tools)

    def test_the_copy_is_generated_not_stored(self):
        source = Path(breakout.__file__).read_text()
        # A module-level constant is a snapshot; these have to be functions so a
        # `prepare` run picks up whatever shipped since the last one.
        self.assertNotIn("POSITIONING = (", source)
        self.assertNotIn("DESCRIPTION = (", source)
        self.assertNotIn("MAKER_COMMENT = (", source)

    def test_the_positioning_is_a_workspace_not_an_invoice_generator(self):
        self.assertIn("paperwork workspace", breakout.positioning())
        self.assertIn("stopped being an invoice generator", breakout.description())
        self.assertIn("The free no-signup paperwork workspace", breakout.TAGLINE)

    def test_the_maker_comment_names_specific_product_decisions(self):
        comment = breakout.maker_comment()
        self.assertIn("delivery note has no prices", comment)
        self.assertIn("reconciles", comment)

    def test_re_preparing_refreshes_a_stale_bundle(self):
        breakout.evaluate(self.connection)
        breakout.prepare(self.connection)
        first = breakout.bundle(self.connection, "ph-launch")["bundle"]
        self.assertEqual(first["live_tools"], breakout.live_tools())
        self.assertIn("does not go stale", first["positioning_note"])


class PendingListingTests(Fixture):
    def setUp(self):
        super().setUp()
        self.connection.execute(
            """INSERT INTO breakout_destinations
                 (key, channel, name, url, submit_url, audience_fit, evidence, verified_on,
                  source_url, requires_account, requires_payment, requires_personal_identity,
                  requires_community_posting, reach, intent, speed_days, confidence, effort,
                  score, gate_status, execution_class, execution_reason, status, bundle_json,
                  notes, created_at, updated_at)
               VALUES ('launchpedia','directories','LaunchPedia','https://launchpedia.co/',
                       'https://launchpedia.co/submit','tools','probed','2026-09-04',
                       'https://launchpedia.co/',0,0,0,0,50,0.4,7,0.5,1.0,10.0,'admitted',
                       'AUTO','open form','submitted','{}','', '2026-09-04','2026-09-04')""")
        self.connection.commit()

    def _run(self, body, status=200):
        import urllib.request
        from unittest import mock

        class Response:
            def __init__(self):
                self.status = status

            def read(self):
                return body.encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with mock.patch.object(urllib.request, "urlopen", lambda *a, **k: Response()):
            return breakout.pending_listings(self.connection)

    def _state(self, result):
        return next(r for r in result["listings"] if r["destination"] == "LaunchPedia")["state"]

    def test_a_search_page_echoing_the_query_is_not_a_listing(self):
        # This is the actual failure: LaunchPedia's search page prints the query
        # back, so a text match on the brand reports a hit for a search that
        # found nothing.
        body = '<title>Search results for: invoice workshop</title><p>Nothing found for "invoice workshop"</p>'
        self.assertEqual(self._state(self._run(body)), "not public yet")

    def test_a_link_to_the_site_is_a_listing(self):
        body = '<a href="https://invoiceworkshop.com/">Invoice Workshop</a>'
        self.assertEqual(self._state(self._run(body)), "live and linking")
        status = self.connection.execute(
            "SELECT status FROM breakout_destinations WHERE key='launchpedia'").fetchone()[0]
        self.assertEqual(status, "live")

    def test_a_link_becomes_a_placement_row_only_once(self):
        body = '<a href="https://invoiceworkshop.com/">Invoice Workshop</a>'
        self._run(body)
        self._run(body)
        rows = self.connection.execute("SELECT COUNT(*) FROM placements").fetchone()[0]
        self.assertEqual(rows, 1)

    def test_a_naked_mention_is_reported_separately_from_a_link(self):
        body = '<p>See invoiceworkshop.com for details</p>'
        self.assertEqual(self._state(self._run(body)),
                         "mentions the domain but does not link to it")


class GuessedSlugTests(Fixture):
    """A detail URL we guessed reads as 'never approved' when the guess is wrong."""

    def setUp(self):
        super().setUp()
        self.connection.execute(
            """INSERT INTO breakout_destinations
                 (key, channel, name, url, submit_url, audience_fit, evidence, verified_on,
                  source_url, requires_account, requires_payment, requires_personal_identity,
                  requires_community_posting, reach, intent, speed_days, confidence, effort,
                  score, gate_status, execution_class, execution_reason, status, bundle_json,
                  notes, created_at, updated_at)
               VALUES ('toolpromote','directories','ToolPromote','https://toolpromote.com/',
                       'https://toolpromote.com/submit','tools','probed','2026-09-04',
                       'https://toolpromote.com/',0,0,0,0,50,0.4,2,0.5,1.0,10.0,'admitted',
                       'AUTO','open form','submitted','{}','', '2026-09-04','2026-09-04')""")
        self.connection.commit()

    def _run(self, pages):
        """`pages` maps URL to (status, body); anything unlisted is a 404."""
        import urllib.error
        import urllib.request
        from unittest import mock

        def urlopen(request, *a, **k):
            url = request.full_url if hasattr(request, "full_url") else request
            status, body = pages.get(url, (404, ""))
            if status != 200:
                raise urllib.error.HTTPError(url, status, "", None, None)

            class Response:
                def __init__(self):
                    self.status = status

                def read(self):
                    return body.encode()

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return Response()

        with mock.patch.object(urllib.request, "urlopen", urlopen):
            return breakout.pending_listings(self.connection)

    def _state(self, result):
        return next(r for r in result["listings"] if r["destination"] == "ToolPromote")

    def test_the_index_finds_a_listing_the_guessed_slug_missed(self):
        result = self._run({
            "https://toolpromote.com/tools": (
                200, '<a href="/tools/invoiceworkshop-free-paperwork">InvoiceWorkshop</a>'),
            "https://toolpromote.com/tools/invoiceworkshop-free-paperwork": (
                200, '<a href="https://invoiceworkshop.com">Visit</a>'),
        })
        row = self._state(result)
        self.assertEqual(row["state"], "live and linking")
        self.assertEqual(row["watch_page"],
                         "https://toolpromote.com/tools/invoiceworkshop-free-paperwork")

    def test_an_index_with_no_listing_still_reports_not_public(self):
        result = self._run({"https://toolpromote.com/tools": (200, "<p>279 tools</p>")})
        self.assertEqual(self._state(result)["state"], "not public yet")

    def test_the_link_to_our_own_site_is_not_followed_as_the_listing(self):
        # The index links out to invoiceworkshop.com in a sponsor slot. That is
        # the thing being looked for, not the route to it.
        result = self._run({
            "https://toolpromote.com/tools": (
                200, '<a href="https://invoiceworkshop.com">sponsor</a>'),
        })
        self.assertEqual(self._state(result)["state"], "not public yet")


class AssetWatchTests(Fixture):
    """Our own published pages are not in anyone's review queue."""

    def _add(self, key, channel, status):
        self.connection.execute(
            """INSERT INTO breakout_destinations
                 (key, channel, name, url, submit_url, audience_fit, evidence, verified_on,
                  source_url, requires_account, requires_payment, requires_personal_identity,
                  requires_community_posting, reach, intent, speed_days, confidence, effort,
                  score, gate_status, execution_class, execution_reason, status, bundle_json,
                  notes, created_at, updated_at)
               VALUES (?,?,?,'https://example.org/','','fit','probed','2026-09-05',
                       '',0,0,0,0,10,0.4,7,0.5,1.0,1.0,'admitted','AUTO','x',?,'{}','',
                       '2026-09-05','2026-09-05')""", (key, channel, key, status))
        self.connection.commit()

    def test_a_published_asset_is_not_reported_as_a_pending_listing(self):
        self._add("asset-x", "linkable_assets", "live")
        result = breakout.pending_listings(self.connection)
        self.assertEqual(result["listings"], [])

    def test_a_real_submission_is_still_watched(self):
        self._add("dir-x", "directories", "submitted")
        result = breakout.pending_listings(self.connection)
        self.assertEqual([r["destination"] for r in result["listings"]], ["dir-x"])
