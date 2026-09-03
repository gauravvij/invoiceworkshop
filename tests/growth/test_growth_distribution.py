from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_distribution as distribution  # noqa: E402
from growth_common import apply_schema, connect_db, utc_now  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)
        distribution.register(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()


class RegisterTests(Fixture):
    def test_every_shipped_surface_the_owner_listed_has_a_row(self):
        routes = {row["route"] for row in self.connection.execute(
            "SELECT route FROM product_distribution")}
        for route in ("/", "/proforma-invoice-generator/", "/quotation-generator/",
                      "/work-order-generator/", "/purchase-order-generator/",
                      "/estimate-generator/", "/construction-invoice-template/",
                      "/contractor-invoice-template/", "/receipt-generator/",
                      "/credit-note-generator/", "/timesheet-invoice-generator/",
                      "/delivery-note-template/", "/progress-draw-schedule/",
                      "/vat-invoice-template-uk/"):
            self.assertIn(route, routes, route)

    def test_every_row_names_a_cluster_an_audience_and_an_angle(self):
        for row in self.connection.execute("SELECT * FROM product_distribution"):
            self.assertTrue(row["search_cluster"], row["route"])
            self.assertTrue(row["resource_audience"], row["route"])
            self.assertTrue(row["linkable_angle"], row["route"])

    def test_a_surface_nobody_has_been_told_about_stays_marked_as_debt(self):
        states = {row["route"]: row["distribution_state"] for row in
                  self.connection.execute("SELECT route, distribution_state FROM product_distribution")}
        self.assertEqual(states["/receipt-generator/"], "debt")

    def test_one_prospect_is_research_not_distribution(self):
        """A single qualified target must not flip a surface out of debt: that
        is how a register stops being uncomfortable and starts being decorative."""
        now = utc_now()
        self.connection.execute(
            """INSERT INTO creator_prospects
                 (domain, page_url, segment, status, discovered_at, updated_at)
               VALUES ('a.org', 'https://a.org/', 'freelancer_newsletter', 'qualified', ?, ?)""",
            (now, now))
        self.connection.commit()
        distribution.measure(self.connection)
        state = self.connection.execute(
            "SELECT distribution_state FROM product_distribution WHERE route='/receipt-generator/'"
        ).fetchone()[0]
        self.assertEqual(state, "debt")
        self.assertGreaterEqual(distribution.MIN_TARGETS_FOR_TARGETED, 3)

    def test_the_debt_is_escalated(self):
        row = self.connection.execute(
            "SELECT subject FROM escalations WHERE kind='product_distribution_debt'").fetchone()
        self.assertIsNotNone(row)
        self.assertIn("no external audience", row["subject"])

    def test_success_is_defined_as_external_outcomes_only(self):
        report = distribution.report(self.connection)
        self.assertEqual(set(report["external_outcomes"]),
                         {"referral_sessions", "backlinks", "organic_clicks"})
        self.assertIn("not on this list on purpose", report["note"])

    def test_pages_built_and_tests_passed_are_not_counted_anywhere(self):
        source = Path(distribution.__file__).read_text()
        for vanity in ("pages_built", "tests_passed", "prospects_researched",
                       "lines_of_code"):
            self.assertNotIn(vanity, source)


class RankTests(Fixture):
    def test_effort_concentrates_on_three(self):
        result = distribution.rank(self.connection, top=3)
        self.assertEqual(len(result["push_now"]), 3)
        self.assertTrue(result["waiting"])
        self.assertIn("promoting everything equally", result["rule"])

    def test_the_ranking_does_not_just_reproduce_search_demand(self):
        """Search demand is the other engine's job. If it drove this list the
        homepage would top it forever and nothing else would ever be pushed."""
        source = Path(distribution.__file__).read_text()
        self.assertNotIn("gsc_impressions", source)
        top = [row["name"] for row in distribution.rank(self.connection, top=3)["push_now"]]
        self.assertIn("Progress Draw Schedule", top)

    def test_every_surface_gets_a_rank_so_none_is_silently_dropped(self):
        distribution.rank(self.connection, top=3)
        unranked = self.connection.execute(
            "SELECT COUNT(*) FROM product_distribution WHERE priority_rank IS NULL"
        ).fetchone()[0]
        self.assertEqual(unranked, 0)


if __name__ == "__main__":
    unittest.main()
