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
        "product_change": "locale preset",
    }
    base.update(overrides)
    return base


class GateTests(unittest.TestCase):
    def test_a_family_with_real_functional_differences_is_admitted(self):
        gate = surface.check(family(), taken=set())
        self.assertEqual(gate["functional"], 3)

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
