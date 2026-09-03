from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_surface as surface  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402


def family(**overrides) -> dict:
    base = {
        "key": "test-family", "name": "Test", "route": "/test-route/",
        "demand": "a real query with real results",
        "differentiators": [
            surface._d("tax_computation", "rate differs"),
            surface._d("tax_identifier", "different registration number"),
            surface._d("currency", "different currency"),
        ],
        "product_change": "locale preset", "build_scope": "content_only",
    }
    base.update(overrides)
    return base


class GateTests(unittest.TestCase):
    def test_a_family_with_real_functional_differences_is_admitted(self):
        gate = surface.check(family(), taken=set())
        self.assertEqual(gate["functional"], 3)

    def test_a_family_must_say_whether_its_capability_exists(self):
        """A family needing a product change the worker cannot make is queued,
        not offered to it, so the scope has to be stated."""
        with self.assertRaises(surface.GateRefusal) as raised:
            surface.check(family(build_scope=None), taken=set())
        self.assertIn("build scope", str(raised.exception))

    def test_the_scope_is_reported_so_the_executor_can_filter_on_it(self):
        self.assertEqual(surface.check(family(), taken=set())["build_scope"], "content_only")

    def test_wording_alone_is_refused(self):
        """The whole point: a page family that only renames things is scaled
        content abuse, and no traffic target makes that a good trade."""
        with self.assertRaises(surface.GateRefusal) as raised:
            surface.check(family(differentiators=[
                surface._d("heading", "says plumber"),
                surface._d("description", "mentions plumbing"),
                surface._d("copy", "plumbing examples"),
            ]), taken=set())
        self.assertIn("scaled content abuse", str(raised.exception))

    def test_one_functional_difference_is_not_enough(self):
        with self.assertRaises(surface.GateRefusal):
            surface.check(family(differentiators=[
                surface._d("currency", "different currency"),
                surface._d("heading", "different heading"),
                surface._d("copy", "different examples"),
            ]), taken=set())

    def test_too_few_differences_is_refused(self):
        with self.assertRaises(surface.GateRefusal):
            surface.check(family(differentiators=[
                surface._d("currency", "x"), surface._d("tax_label", "y")]), taken=set())

    def test_no_product_change_is_refused(self):
        with self.assertRaises(surface.GateRefusal) as raised:
            surface.check(family(product_change="none: the tool behaves identically"),
                          taken=set())
        self.assertIn("no product change", str(raised.exception))

    def test_no_demand_evidence_is_refused(self):
        with self.assertRaises(surface.GateRefusal):
            surface.check(family(demand=""), taken=set())

    def test_a_route_already_served_is_refused(self):
        with self.assertRaises(surface.GateRefusal):
            surface.check(family(), taken={"/test-route/"})

    def test_an_invented_differentiator_kind_is_refused(self):
        """Otherwise the gate could be satisfied by making up a category."""
        with self.assertRaises(surface.GateRefusal) as raised:
            surface.check(family(differentiators=[
                surface._d("vibes", "feels different"),
                surface._d("synergy", "more synergy"),
                surface._d("currency", "real"),
            ]), taken=set())
        self.assertIn("unrecognised", str(raised.exception))

    def test_presentational_kinds_can_never_count_as_functional(self):
        self.assertFalse(surface.FUNCTIONAL_KINDS & surface.PRESENTATIONAL_KINDS)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_the_shipped_catalogue_refuses_the_wording_only_family(self):
        result = surface.evaluate(self.connection)
        refused = {item["family"] for item in result["refused"]}
        self.assertIn("trade-generic-copy-only", refused)

    def test_every_admitted_family_names_a_product_change(self):
        surface.evaluate(self.connection)
        for row in self.connection.execute(
            "SELECT family_key, product_change FROM page_families WHERE status='admitted'"
        ):
            self.assertTrue(row["product_change"].strip())
            self.assertFalse(row["product_change"].lower().startswith("none"))

    def test_refusals_record_their_reason(self):
        surface.evaluate(self.connection)
        row = self.connection.execute(
            "SELECT refusal_reason FROM page_families WHERE status='refused' LIMIT 1"
        ).fetchone()
        self.assertTrue(row["refusal_reason"])

    def test_admission_queues_the_page(self):
        surface.evaluate(self.connection)
        queued = self.connection.execute(
            "SELECT COUNT(*) FROM page_candidates WHERE status='queued'").fetchone()[0]
        admitted = self.connection.execute(
            "SELECT COUNT(*) FROM page_families WHERE status='admitted'").fetchone()[0]
        self.assertEqual(queued, admitted)

    def test_evaluation_has_no_external_side_effects(self):
        self.assertEqual(surface.evaluate(self.connection)["external_side_effects"], "none")


if __name__ == "__main__":
    unittest.main()


class CountrySourcingTests(unittest.TestCase):
    """A country page states what a tax authority requires, so the gate wants
    the authority's own words on record before it admits one."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _locale(self, **overrides):
        family = {
            "key": "locale-xx", "jurisdiction": "xx", "build_scope": "content_only",
            "name": "Test locale", "route": "/test-locale/", "demand": "measured demand",
            "differentiators": [
                surface._d("tax_computation", "a rate"),
                surface._d("tax_identifier", "an identifier"),
                surface._d("currency", "a currency"),
            ],
            "product_change": "locale preset",
        }
        family.update(overrides)
        return family

    def _fact(self, key, *, url="https://gov.example/x", reverify="2099-01-01"):
        self.connection.execute(
            """INSERT INTO tax_facts
                 (jurisdiction, fact_key, value, source_name, source_url,
                  verified_on, reverify_by, confidence)
               VALUES ('xx', ?, '20%', 'Authority', ?, '2026-09-02', ?, 'primary_source')""",
            (key, url, reverify))
        self.connection.commit()

    def test_a_country_family_without_recorded_facts_is_refused(self):
        with self.assertRaises(surface.GateRefusal) as caught:
            surface.check(self._locale(), taken=set(),
                          facts=surface.fact_index(self.connection))
        self.assertIn("verified tax fact", str(caught.exception))
        self.assertIn("Competitor templates are not a source", str(caught.exception))

    def test_recorded_and_current_facts_admit_it(self):
        for n in range(surface.MIN_FACTS_PER_JURISDICTION):
            self._fact(f"fact{n}")
        gate = surface.check(self._locale(), taken=set(),
                             facts=surface.fact_index(self.connection))
        self.assertEqual(gate["sourced"], "xx")
        self.assertEqual(gate["facts"], surface.MIN_FACTS_PER_JURISDICTION)

    def test_a_fact_past_its_recheck_date_blocks_the_family(self):
        for n in range(surface.MIN_FACTS_PER_JURISDICTION):
            self._fact(f"fact{n}")
        self._fact("stale", reverify="2020-01-01")
        with self.assertRaises(surface.GateRefusal) as caught:
            surface.check(self._locale(), taken=set(),
                          facts=surface.fact_index(self.connection))
        self.assertIn("past their recheck date", str(caught.exception))

    def test_a_fact_with_no_source_url_blocks_the_family(self):
        for n in range(surface.MIN_FACTS_PER_JURISDICTION):
            self._fact(f"fact{n}")
        self._fact("unsourced", url="")
        with self.assertRaises(surface.GateRefusal) as caught:
            surface.check(self._locale(), taken=set(),
                          facts=surface.fact_index(self.connection))
        self.assertIn("no source URL", str(caught.exception))

    def test_a_country_family_cannot_skip_the_check_by_omitting_its_jurisdiction(self):
        with self.assertRaises(surface.GateRefusal) as caught:
            surface.check(self._locale(jurisdiction=None), taken=set(), facts={})
        self.assertIn("names no jurisdiction", str(caught.exception))

    def test_a_non_country_family_is_unaffected(self):
        gate = surface.check(
            {"key": "doc-thing", "build_scope": "product", "name": "Thing",
             "route": "/thing/", "demand": "demand",
             "differentiators": [surface._d("totals_logic", "a"),
                                 surface._d("required_field", "b"),
                                 surface._d("heading", "c")],
             "product_change": "new document kind"},
            taken=set(), facts={})
        self.assertEqual(gate["sourced"], "not_applicable")

    def test_no_shipped_country_page_asserts_a_requirement_the_audit_disproved(self):
        """The three claims the 2 September 2026 primary-source audit found wrong
        must not survive anywhere in the catalogue."""
        source = Path(surface.__file__).read_text()
        self.assertNotIn("as HMRC requires", source)
        self.assertNotIn("ATO requires the words", source)
        for abolished in ("5/12/18/28", "12/18/28"):
            self.assertNotIn(abolished, source)
