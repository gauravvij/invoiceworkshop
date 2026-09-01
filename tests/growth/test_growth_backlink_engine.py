from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_backlink_engine as engine  # noqa: E402
from growth_backlink_policy import (  # noqa: E402
    ACTIONABLE_LINK_REASONS,
    CHANNEL_QUERIES,
    SCORE_CEILINGS,
    TIER_A_MIN,
    TIER_B_MIN,
    TIER_C_MIN,
    classify_link_reason,
    target_for,
)


class PolicyTests(unittest.TestCase):
    def test_score_ceilings_total_one_hundred(self):
        self.assertEqual(sum(SCORE_CEILINGS.values()), 100)

    def test_seo_is_the_smallest_component(self):
        self.assertEqual(SCORE_CEILINGS["seo"], min(SCORE_CEILINGS.values()))
        self.assertLess(SCORE_CEILINGS["seo"], SCORE_CEILINGS["relevance"])
        self.assertLess(SCORE_CEILINGS["seo"], SCORE_CEILINGS["audience"])

    def test_tier_thresholds_are_ordered(self):
        self.assertGreater(TIER_A_MIN, TIER_B_MIN)
        self.assertGreater(TIER_B_MIN, TIER_C_MIN)

    def test_every_channel_has_queries(self):
        self.assertEqual(len(CHANNEL_QUERIES), 11)
        for channel, queries in CHANNEL_QUERIES.items():
            self.assertTrue(queries, channel)

    def test_targets_stay_inside_the_frozen_architecture(self):
        allowed = {
            "https://invoiceworkshop.com/",
            "https://invoiceworkshop.com/invoice-template/",
            "https://invoiceworkshop.com/construction-invoice-template/",
            "https://invoiceworkshop.com/contractor-invoice-template/",
            "https://invoiceworkshop.com/quotation-generator/",
            "https://invoiceworkshop.com/estimate-generator/",
            "https://invoiceworkshop.com/work-order-generator/",
            "https://invoiceworkshop.com/purchase-order-generator/",
            "https://invoiceworkshop.com/proforma-invoice-generator/",
        }
        samples = [
            "retainage change order jobsite", "sales quote template", "purchase order procurement",
            "proforma invoice", "job estimate", "work order dispatch", "invoice template",
            "resources for freelancers", "contractor invoice",
        ]
        for sample in samples:
            self.assertIn(target_for(sample), allowed, sample)

    def test_no_target_invents_a_synonym_page(self):
        for sample in ("free invoice generator", "invoice maker", "invoice builder"):
            self.assertEqual(target_for(sample), "https://invoiceworkshop.com/")

    def test_link_reason_classification(self):
        self.assertEqual(classify_link_reason("Acme raised a Series A funding round"), "funding_or_news")
        self.assertEqual(classify_link_reason("affiliate commission disclosure"), "affiliate")
        self.assertEqual(classify_link_reason("client login portal"), "login_portal")
        self.assertIn(classify_link_reason("best free invoicing tools roundup"), ACTIONABLE_LINK_REASONS)


class FilterTests(unittest.TestCase):
    def test_spam_is_rejected_outright(self):
        keep, reason = engine.cheap_filter(
            "resource_pages", "Buy backlinks DA 60", "link building package", "https://spam.example/x/"
        )
        self.assertFalse(keep)
        self.assertEqual(reason, "spam signal")

    def test_competitors_are_never_opportunities(self):
        keep, _ = engine.cheap_filter(
            "resource_pages", "Invoice resources for freelancers",
            "free small business invoicing tools", "https://www.freshbooks.com/resources/",
        )
        self.assertFalse(keep)

    def test_homepages_are_rejected(self):
        keep, reason = engine.cheap_filter(
            "resource_pages", "Freelance resources", "invoicing tools for small business",
            "https://example.org/",
        )
        self.assertFalse(keep)
        self.assertEqual(reason, "homepage rather than a specific page")

    def test_weak_topical_signal_is_rejected(self):
        keep, reason = engine.cheap_filter(
            "resource_pages", "Holiday photos", "a gallery of pictures", "https://example.org/photos/"
        )
        self.assertFalse(keep)
        self.assertEqual(reason, "insufficient topical signal")

    def test_strong_candidate_is_kept(self):
        keep, _ = engine.cheap_filter(
            "resource_pages", "Resources for freelancers",
            "free invoicing tools and templates for self-employed people",
            "https://example.org/resources/freelancers/",
        )
        self.assertTrue(keep)

    def test_community_results_are_confined_to_their_channel(self):
        reddit = "https://www.reddit.com/r/freelance/comments/abc/invoice_tool/"
        keep, _ = engine.cheap_filter("community", "Which invoice tool?", "recommendations", reddit)
        self.assertTrue(keep)
        keep, reason = engine.cheap_filter("resource_pages", "Which invoice tool?", "freelance resources", reddit)
        self.assertFalse(keep)
        self.assertEqual(reason, "community domain outside the community channel")

    def test_non_community_result_is_rejected_from_the_community_channel(self):
        keep, reason = engine.cheap_filter(
            "community", "Invoice resources", "freelance tools", "https://example.org/resources/"
        )
        self.assertFalse(keep)
        self.assertEqual(reason, "not a community platform")


class HardRejectTests(unittest.TestCase):
    def test_reciprocal_requirement_is_rejected(self):
        self.assertEqual(
            engine.hard_reject("You must link back to us to be listed", "example.org", 0),
            "requires a reciprocal link",
        )

    def test_paid_placement_is_rejected(self):
        self.assertEqual(
            engine.hard_reject("Premium listing available", "example.org", 0),
            "paid or sponsored placement",
        )
        self.assertEqual(
            engine.hard_reject("A perfectly normal resource page", "example.org", 1),
            "paid or sponsored placement",
        )

    def test_clean_page_is_not_rejected(self):
        self.assertIsNone(
            engine.hard_reject("Resources for freelancers and invoicing guides", "example.org", 0)
        )


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = engine.initialize(str(Path(self.temp.name) / "growth.db"))

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _row(self, **overrides) -> sqlite3.Row:
        values = {
            "title": "Resources for freelancers",
            "page_evidence": "Free invoicing tools, templates and guides for self-employed freelancers and small business owners.",
            "page_url": "https://example.org/resources/freelancers/",
            "contact_kind": "email",
            "requires_account": 0,
            "requires_payment": 0,
            "opportunity_type": "resource",
        }
        values.update(overrides)
        return values

    def test_component_scores_respect_their_ceilings(self):
        parts = engine.score_opportunity(self._row())
        for key, ceiling in SCORE_CEILINGS.items():
            self.assertLessEqual(parts[key], ceiling, key)
        self.assertLessEqual(parts["total"], 100)

    def test_a_strong_page_outscores_a_weak_one(self):
        strong = engine.score_opportunity(self._row())
        weak = engine.score_opportunity(self._row(
            title="Corporate news", page_evidence="Quarterly announcements.",
            page_url="https://example.org/news/2026/q1/", contact_kind="unknown",
        ))
        self.assertGreater(strong["total"], weak["total"])

    def test_second_pass_rejects_an_unreachable_page(self):
        passed, reason = engine.second_pass(
            self._row(contact_kind="unknown"), engine.score_opportunity(self._row())
        )
        self.assertFalse(passed)
        self.assertIn("contact", reason)

    def test_second_pass_rejects_an_irrelevant_audience(self):
        row = self._row(
            title="Aquarium care",
            page_evidence="Fish tank cleaning tips and water chemistry basics.",
            page_url="https://example.org/aquariums/cleaning/",
        )
        passed, reason = engine.second_pass(row, engine.score_opportunity(row))
        self.assertFalse(passed)
        self.assertIn("audience", reason)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = engine.initialize(str(Path(self.temp.name) / "growth.db"))

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _insert(self, **overrides):
        values = {
            "domain": "example.org",
            "page_url": "https://example.org/resources/freelancers/",
            "channel": "resource_pages",
            "title": "Resources for freelancers",
            "page_evidence": "Free invoicing tools, templates and guides for self-employed freelancers and small business owners.",
            "contact_kind": "email",
            "recipient": "hello@example.org",
            "target_url": "https://invoiceworkshop.com/invoice-template/",
        }
        values.update(overrides)
        self.connection.execute(
            """INSERT INTO backlink_opportunities
                 (domain, page_url, channel, title, page_evidence, contact_kind, recipient,
                  target_url, discovered_at, updated_at, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-09-01', '2026-09-01', '2026-09-01')""",
            tuple(values[key] for key in (
                "domain", "page_url", "channel", "title", "page_evidence",
                "contact_kind", "recipient", "target_url")),
        )
        self.connection.commit()

    def test_qualification_tiers_and_rejects(self):
        self._insert()
        self._insert(domain="spam.example", page_url="https://spam.example/links/",
                     title="Buy backlinks DA 70", page_evidence="link building package pricing")
        counts = engine.qualify(self.connection)
        self.assertEqual(counts["reviewed"], 2)
        self.assertGreaterEqual(counts["reject"], 1)
        rejected = self.connection.execute(
            "SELECT rejection_reason FROM backlink_opportunities WHERE domain='spam.example'"
        ).fetchone()["rejection_reason"]
        self.assertIn("spam", rejected)

    def test_only_one_page_per_domain_survives_as_an_opportunity(self):
        for slug in ("freelancers", "invoicing", "billing"):
            self._insert(page_url=f"https://example.org/resources/{slug}/")
        engine.qualify(self.connection)
        live = self.connection.execute(
            "SELECT COUNT(*) FROM backlink_opportunities WHERE domain='example.org' AND tier IN ('A','B')"
        ).fetchone()[0]
        self.assertEqual(live, 1)

    def test_www_and_apex_are_the_same_page(self):
        self.assertEqual(
            engine.dedupe_key("https://www.example.org/resources/"),
            engine.dedupe_key("https://example.org/resources"),
        )

    def test_off_topic_page_is_rejected_despite_a_relevant_audience(self):
        self._insert(
            domain="union.example", page_url="https://union.example/resources/student-loans/",
            title="Student Loans for freelancers",
            page_evidence="Student loan repayment guidance for self-employed freelancers and small business owners.",
        )
        engine.qualify(self.connection)
        row = self.connection.execute(
            "SELECT tier, rejection_reason FROM backlink_opportunities WHERE domain='union.example'"
        ).fetchone()
        self.assertEqual(row["tier"], "reject")
        self.assertIn("unrelated to business billing", row["rejection_reason"])

    def test_domain_already_in_the_crm_is_not_re_offered(self):
        self.connection.execute(
            """INSERT INTO prospects (domain, page_url, prospect_type, opportunity_score, risk,
                 why_fit, audience, contact_method, link_type, source_url, status,
                 discovered_at, updated_at)
               VALUES ('example.org', 'https://example.org/resources/', 'resource', 80, 'low',
                 'x', 'y', 'https://example.org/contact/', 'editorial',
                 'https://example.org/resources/', 'qualified', '2026-09-01', '2026-09-01')"""
        )
        self.connection.commit()
        self._insert(page_url="https://example.org/resources/invoicing/")
        engine.qualify(self.connection)
        row = self.connection.execute(
            "SELECT tier, second_pass_reason FROM backlink_opportunities WHERE page_url LIKE '%invoicing%'"
        ).fetchone()
        self.assertEqual(row["tier"], "C")
        self.assertIn("already represented", row["second_pass_reason"])

    def test_channel_plan_rotates_queries_between_runs(self):
        first = engine.channel_plan(self.connection, ["resource_pages"], 2)
        self.connection.execute(
            """INSERT INTO backlink_channel_stats (channel, runs, effort_weight, updated_at)
               VALUES ('resource_pages', 1, 1.0, '2026-09-01')"""
        )
        self.connection.commit()
        second = engine.channel_plan(self.connection, ["resource_pages"], 2)
        self.assertNotEqual([q for _, q in first], [q for _, q in second])

    def test_barren_channels_lose_effort_weight(self):
        for _ in range(3):
            engine.update_channel_stats(self.connection, {"directory": {"raw": 10, "rejected": 10}})
        row = self.connection.execute(
            "SELECT barren_streak, effort_weight FROM backlink_channel_stats WHERE channel='directory'"
        ).fetchone()
        self.assertGreaterEqual(int(row["barren_streak"]), 3)
        self.assertLess(float(row["effort_weight"]), 1.0)

    def test_effort_weight_never_reaches_zero(self):
        for _ in range(30):
            engine.update_channel_stats(self.connection, {"directory": {"raw": 1, "rejected": 1}})
        weight = self.connection.execute(
            "SELECT effort_weight FROM backlink_channel_stats WHERE channel='directory'"
        ).fetchone()["effort_weight"]
        self.assertGreaterEqual(float(weight), 0.25)

    def test_runs_record_no_external_side_effects(self):
        run_id = engine.start_run(self.connection, "manual", ["resource_pages"])
        engine.finish_run(self.connection, run_id, status="success", raw_discovered=5)
        row = self.connection.execute(
            "SELECT external_side_effects, status FROM backlink_discovery_runs WHERE id=?", (run_id,)
        ).fetchone()
        self.assertEqual(row["external_side_effects"], "none")
        self.assertEqual(row["status"], "success")

    def test_engine_exposes_no_outbound_capability(self):
        source = (SCRIPTS / "growth_backlink_engine.py").read_text(encoding="utf-8")
        for forbidden in ("requests.post", "requests.put", "send_plaintext", "smtplib", "ZohoClient"):
            self.assertNotIn(forbidden, source, forbidden)


if __name__ == "__main__":
    unittest.main()
