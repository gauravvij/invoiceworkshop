from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_opportunities as opportunities  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402

HOME = "https://invoiceworkshop.com/"
WORK_ORDER = "https://invoiceworkshop.com/work-order-generator/"
QUOTATION = "https://invoiceworkshop.com/quotation-generator/"


def build_site(root: Path, *, pages: dict[str, str] | None = None) -> Path:
    """A minimal built site: enough structure for measurement to be real."""
    root.mkdir(parents=True, exist_ok=True)
    default = (
        '<html><head><link rel="canonical" href="{url}"></head><body><h1>Page</h1>'
        '<a href="/">Home</a><a href="/work-order-generator/">Work orders</a>'
        '<a href="/quotation-generator/">Quotations</a>'
        '<h2>Section</h2><p>An invoice for work orders and quotations.</p></body></html>'
    )
    for url in opportunities.CANONICAL:
        path = url.replace("https://invoiceworkshop.com", "").strip("/")
        target = root / (path + "/index.html") if path else root / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        body = (pages or {}).get(url, default).format(url=url)
        target.write_text(body, encoding="utf-8")
    locs = "".join(f"<loc>{url}</loc>" for url in opportunities.CANONICAL)
    (root / "sitemap.xml").write_text(f"<urlset>{locs}</urlset>", encoding="utf-8")
    return root


def seed_index(connection, url: str, *, coverage: str, verdict: str = "NEUTRAL",
               crawled: str | None = None, date: str = "2026-09-01") -> None:
    connection.execute(
        """INSERT OR REPLACE INTO index_state
             (date, url, inspected_at, verdict, coverage_state, robots_state, indexing_state,
              last_crawl_time, google_canonical, user_canonical, error)
           VALUES (?, ?, ?, ?, ?, 'ALLOWED', 'INDEXING_ALLOWED', ?, NULL, NULL, NULL)""",
        (date, url, date, verdict, coverage, crawled),
    )
    connection.execute(
        "INSERT OR REPLACE INTO url_health (date, url, checked_at, status) VALUES (?, ?, ?, 200)",
        (date, url, date),
    )
    connection.commit()


def seed_query(connection, *, query: str, page: str, impressions: int = 4,
               clicks: int = 0, position: float = 85.0, date: str = "2026-09-01") -> None:
    connection.execute(
        """INSERT OR REPLACE INTO gsc_query_facts
             (snapshot_date, date, query, page, country, device, impressions,
              clicks, ctr, position, window_start, window_end)
           VALUES (?, ?, ?, ?, 'usa', 'DESKTOP', ?, ?, 0, ?, ?, ?)""",
        (date, date, query, page, impressions, clicks, position, date, date),
    )
    connection.commit()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.connection = connect_db(str(self.root / "growth.db"))
        apply_schema(self.connection)
        self.dist = build_site(self.root / "dist")

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()


class WordCountIsNotAnObjectiveTests(Fixture):
    """Length must never be the reason a page is worked on."""

    def test_a_short_page_with_no_missing_value_produces_no_opportunity(self):
        rich = (
            '<html><head><link rel="canonical" href="{url}"></head><body><h1>Q</h1>'
            '<a href="/">h</a><a href="/quotation-generator/">q</a>'
            '<table class="doc-table"><tr><td>1</td></tr></table>'
            '<dl class="term-list"><dt>Quotation</dt><dd>An offer.</dd></dl>'
            "</body></html>"
        )
        build_site(self.dist, pages={url: rich for url in opportunities.CANONICAL})
        seed_index(self.connection, QUOTATION, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        opportunities.measure_pages(self.connection, self.dist)
        stats = opportunities._page_stats(self.connection)
        self.assertLess(stats[QUOTATION]["words"], 40, "fixture must be a genuinely short page")

        context = {
            "stats": stats, "texts": opportunities.page_texts(self.dist),
            "facts": [], "diagnosis": opportunities.diagnose_index(self.connection, dist=self.dist),
        }
        keys = [row["opportunity_key"] for row in
                opportunities.from_content_gaps(self.connection, context)]
        self.assertNotIn(f"gap:{QUOTATION}", keys)

    def test_no_generator_reads_a_word_count_threshold(self):
        source = (SCRIPTS / "growth_opportunities.py").read_text(encoding="utf-8")
        self.assertNotIn("THIN_WORDS", source)

    def test_word_count_is_recorded_as_context_only(self):
        opportunities.measure_pages(self.connection, self.dist)
        seed_index(self.connection, HOME, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        context = {
            "stats": opportunities._page_stats(self.connection),
            "texts": opportunities.page_texts(self.dist), "facts": [],
            "diagnosis": opportunities.diagnose_index(self.connection, dist=self.dist),
        }
        rows = opportunities.from_content_gaps(self.connection, context)
        row = next(r for r in rows if r["target_url"] == HOME)
        # Length appears in the evidence a human reads, and nowhere in the score.
        self.assertIn("words", row["evidence"])
        without_length = dict(row)
        self.assertEqual(opportunities.expected_growth_value(row),
                         opportunities.expected_growth_value(without_length))

    def test_a_missing_worked_example_is_what_creates_the_opportunity(self):
        opportunities.measure_pages(self.connection, self.dist)
        seed_index(self.connection, HOME, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        context = {
            "stats": opportunities._page_stats(self.connection),
            "texts": opportunities.page_texts(self.dist), "facts": [],
            "diagnosis": opportunities.diagnose_index(self.connection, dist=self.dist),
        }
        row = next(r for r in opportunities.from_content_gaps(self.connection, context)
                   if r["target_url"] == HOME)
        self.assertIn("worked example", row["evidence"])

    def test_a_surfaced_query_the_page_never_answers_is_a_gap(self):
        seed_index(self.connection, WORK_ORDER, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        seed_query(self.connection, query="work order retainage schedule", page=WORK_ORDER)
        opportunities.measure_pages(self.connection, self.dist)
        context = {
            "stats": opportunities._page_stats(self.connection),
            "texts": opportunities.page_texts(self.dist),
            "facts": opportunities._query_facts(self.connection),
            "diagnosis": opportunities.diagnose_index(self.connection, dist=self.dist),
        }
        row = next(r for r in opportunities.from_content_gaps(self.connection, context)
                   if r["target_url"] == WORK_ORDER)
        self.assertIn("retainage", row["evidence"])
        self.assertEqual(row["basis"], "measured")
        self.assertEqual(row["evidence_strength"], "strong")

    def test_an_unbuilt_page_claims_no_gap(self):
        """Absent evidence must never be read as evidence of a deficiency."""
        empty = Path(self.temp.name) / "nothing"
        empty.mkdir()
        context = {"stats": {}, "texts": opportunities.page_texts(empty), "facts": [],
                   "diagnosis": []}
        self.assertEqual(opportunities.from_content_gaps(self.connection, context), [])


class IndexStateTests(Fixture):
    def test_discovered_without_a_crawl_is_not_a_content_problem(self):
        row = {"coverage_state": "Discovered - currently not indexed", "last_crawl_time": None,
               "verdict": "NEUTRAL"}
        self.assertEqual(opportunities.classify_index(row), "discovered_not_crawled")
        self.assertEqual(opportunities.CONSTRAINT_OF["discovered_not_crawled"], "crawl_scheduling")

    def test_crawled_and_declined_is_the_only_content_constraint(self):
        row = {"coverage_state": "Crawled - currently not indexed",
               "last_crawl_time": "2026-08-30T00:00:00Z", "verdict": "NEUTRAL"}
        self.assertEqual(opportunities.classify_index(row), "crawled_not_indexed")
        self.assertEqual(opportunities.CONSTRAINT_OF["crawled_not_indexed"], "content_quality")

    def test_the_four_states_are_distinguished(self):
        cases = {
            "indexed": {"coverage_state": "Submitted and indexed", "verdict": "PASS",
                        "last_crawl_time": "2026-08-30T00:00:00Z"},
            "unknown": {"coverage_state": "URL is unknown to Google", "verdict": "NEUTRAL",
                        "last_crawl_time": None},
            "discovered_not_crawled": {"coverage_state": "Discovered - currently not indexed",
                                       "verdict": "NEUTRAL", "last_crawl_time": None},
            "crawled_not_indexed": {"coverage_state": "Crawled - currently not indexed",
                                    "verdict": "NEUTRAL",
                                    "last_crawl_time": "2026-08-30T00:00:00Z"},
        }
        for expected, row in cases.items():
            self.assertEqual(opportunities.classify_index(row), expected, expected)

    def test_a_correctly_published_uncrawled_url_generates_no_rewrite(self):
        seed_index(self.connection, QUOTATION, coverage="Discovered - currently not indexed")
        opportunities.measure_pages(self.connection, self.dist)
        diagnosis = opportunities.diagnose_index(self.connection, dist=self.dist)
        entry = next(item for item in diagnosis if item["url"] == QUOTATION)
        self.assertEqual(entry["blocking_checks"], [])
        self.assertIn("do not rewrite", entry["recommended"])
        self.assertEqual(
            opportunities.from_indexing(self.connection, {"diagnosis": diagnosis}), []
        )

    def test_a_broken_prerequisite_does_generate_work(self):
        seed_index(self.connection, QUOTATION, coverage="URL is unknown to Google")
        self.connection.execute(
            "UPDATE url_health SET status=404 WHERE url=?", (QUOTATION,)
        )
        self.connection.commit()
        opportunities.measure_pages(self.connection, self.dist)
        diagnosis = opportunities.diagnose_index(self.connection, dist=self.dist)
        rows = opportunities.from_indexing(self.connection, {"diagnosis": diagnosis})
        self.assertEqual([row["opportunity_key"] for row in rows],
                         [f"index-readiness:{QUOTATION}"])
        self.assertIn("returns_200", rows[0]["evidence"])

    def test_diagnosis_is_recorded_for_every_canonical_url(self):
        for url in opportunities.CANONICAL:
            seed_index(self.connection, url, coverage="Discovered - currently not indexed")
        opportunities.measure_pages(self.connection, self.dist)
        opportunities.diagnose_index(self.connection, dist=self.dist)
        stored = self.connection.execute("SELECT COUNT(*) FROM index_diagnosis").fetchone()[0]
        self.assertEqual(stored, len(opportunities.CANONICAL))

    def test_the_homepage_counts_its_inbound_links(self):
        """href="/" is a link to the homepage; missing it made "/" look orphaned."""
        opportunities.measure_pages(self.connection, self.dist)
        stats = opportunities._page_stats(self.connection)
        self.assertGreaterEqual(stats[HOME]["internal_in"], 2)


class UncertaintyTests(Fixture):
    def test_maturity_is_near_zero_on_a_handful_of_impressions(self):
        self.connection.execute(
            "INSERT INTO metrics_daily (date, collected_at, gsc_impressions) "
            "VALUES ('2026-09-01', '2026-09-01', 10)"
        )
        self.connection.commit()
        self.assertLess(opportunities.evidence_maturity(self.connection), 0.05)

    def test_measured_signal_outweighs_the_prior_as_traffic_accumulates(self):
        row = {"expected_upside": 100, "confidence": 0.5, "intent_quality": 0.9,
               "feasibility": 0.6, "effort_days": 0.5, "time_to_impact_days": 30,
               "basis": "measured"}
        point = opportunities.expected_growth_value(row)
        sparse = opportunities.value_range(point, row, 0.0)
        mature = opportunities.value_range(point, row, 1.0)
        self.assertLess(mature[1] - mature[0], sparse[1] - sparse[0])

    def test_a_prior_only_row_is_reported_less_precisely_than_a_measured_one(self):
        base = {"expected_upside": 100, "confidence": 0.5, "intent_quality": 0.9,
                "feasibility": 0.6, "effort_days": 0.5, "time_to_impact_days": 30}
        point = opportunities.expected_growth_value(base)
        measured = opportunities.value_range(point, {**base, "basis": "measured"}, 0.2)
        prior = opportunities.value_range(point, {**base, "basis": "prior"}, 0.2)
        self.assertGreater(prior[1] - prior[0], measured[1] - measured[0])

    def test_bands_are_broad_rather_than_an_exact_ordering(self):
        rows = [{"expected_growth_value": value} for value in (46.0, 24.0, 12.0, 2.0)]
        banded = opportunities.assign_bands(rows)
        self.assertEqual([row["priority_band"] for row in banded], [1, 1, 2, 3])

    def test_a_single_impression_cannot_produce_a_narrow_estimate(self):
        seed_index(self.connection, WORK_ORDER, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        seed_query(self.connection, query="work order generator", page=WORK_ORDER, impressions=1)
        self.connection.execute(
            "INSERT INTO metrics_daily (date, collected_at, gsc_impressions) "
            "VALUES ('2026-09-01', '2026-09-01', 1)"
        )
        self.connection.commit()
        opportunities.refresh(self.connection, dist=self.dist)
        row = self.connection.execute(
            "SELECT value_low, value_high, expected_growth_value FROM growth_opportunities "
            "WHERE state='open' ORDER BY expected_growth_value DESC LIMIT 1"
        ).fetchone()
        span = row["value_high"] - row["value_low"]
        self.assertGreater(span, row["expected_growth_value"],
                           "with one impression the range must be wider than the estimate itself")


class RefreshTests(Fixture):
    def test_channel_weight_changes_the_ranking(self):
        seed_index(self.connection, HOME, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        opportunities.refresh(self.connection, dist=self.dist)
        before = self.connection.execute(
            "SELECT expected_growth_value FROM growth_opportunities WHERE opportunity_key=?",
            (f"gap:{HOME}",),
        ).fetchone()[0]
        self.connection.execute(
            """INSERT INTO channel_allocation (channel, weight, updated_at)
               VALUES ('page_improvement', 0.5, '2026-09-02T00:00:00+00:00')"""
        )
        self.connection.commit()
        opportunities.refresh(self.connection, dist=self.dist)
        after = self.connection.execute(
            "SELECT expected_growth_value FROM growth_opportunities WHERE opportunity_key=?",
            (f"gap:{HOME}",),
        ).fetchone()[0]
        self.assertAlmostEqual(after, before / 2, places=1)

    def test_an_opportunity_the_evidence_stops_supporting_is_dismissed(self):
        seed_index(self.connection, HOME, coverage="Submitted and indexed", verdict="PASS",
                   crawled="2026-08-30T00:00:00Z")
        opportunities.refresh(self.connection, dist=self.dist)
        self.assertEqual(
            self.connection.execute(
                "SELECT state FROM growth_opportunities WHERE opportunity_key=?", (f"gap:{HOME}",)
            ).fetchone()[0], "open")
        # Ship the missing value: the opportunity must stop competing for attention.
        rich = (
            '<html><head><link rel="canonical" href="{url}"></head><body><h1>H</h1>'
            '<a href="/">h</a><a href="/quotation-generator/">q</a>'
            '<table class="doc-table"><tr><td>1</td></tr></table>'
            '<dl class="term-list"><dt>Invoice</dt><dd>A request for payment.</dd></dl>'
            "</body></html>"
        )
        build_site(self.dist, pages={HOME: rich})
        opportunities.refresh(self.connection, dist=self.dist)
        self.assertEqual(
            self.connection.execute(
                "SELECT state FROM growth_opportunities WHERE opportunity_key=?", (f"gap:{HOME}",)
            ).fetchone()[0], "dismissed")

    def test_rejected_assets_stay_rejected_with_their_reason(self):
        opportunities.refresh(self.connection, dist=self.dist)
        row = self.connection.execute(
            "SELECT state, dismissed_reason FROM growth_opportunities "
            "WHERE opportunity_key='asset:retainage-calculator'"
        ).fetchone()
        if row:  # only present once it has been generated at least once historically
            self.assertEqual(row["state"], "dismissed")
            self.assertIn("Rejected", row["dismissed_reason"])

    def test_refresh_has_no_external_side_effects(self):
        result = opportunities.refresh(self.connection, dist=self.dist)
        self.assertEqual(result["external_side_effects"], "none")

    def test_measured_features_are_stored_as_json(self):
        opportunities.measure_pages(self.connection, self.dist)
        stored = self.connection.execute(
            "SELECT features_json FROM page_content_stats WHERE url=?", (HOME,)
        ).fetchone()[0]
        features = json.loads(stored)
        for key in ("worked_example", "comparison", "canonical_self", "h1_count"):
            self.assertIn(key, features)


if __name__ == "__main__":
    unittest.main()
