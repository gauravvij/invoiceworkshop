from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import connect_db  # noqa: E402
from growth_research import finish_research, import_batch, start_research  # noqa: E402


def candidate(domain: str) -> dict:
    url = f"https://{domain}/resources/invoicing"
    return {
        "page_url": url,
        "source_url": url,
        "prospect_type": "resource",
        "opportunity_score": 72,
        "risk": "low",
        "why_fit": "A curated invoicing resource for independent businesses.",
        "audience": "Freelancers and small businesses.",
        "contact_method": "Public editorial guidelines observed; no action taken.",
        "requires_account": False,
        "requires_payment": False,
        "link_type": "editorial",
    }


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = str(self.root / "growth.db")
        self.batches = self.root / "batches"
        self.batches.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_batch(self, name: str, rows: list[dict]) -> Path:
        path = self.batches / name
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path

    def test_batch_import_deduplicates_and_finishes_without_side_effects(self):
        context = start_research(self.db, "research-id", 40_000, 10)
        run_id = context["research_run_id"]
        first = import_batch(
            self.db,
            run_id,
            str(self.write_batch("first.json", [candidate("one.example"), candidate("two.example")])),
            self.batches,
        )
        second = import_batch(
            self.db,
            run_id,
            str(self.write_batch("second.json", [candidate("one.example")])),
            self.batches,
        )
        result = finish_research(self.db, run_id, "success", 3, 8, [])

        self.assertEqual(first["prospects_retained"], 2)
        self.assertEqual(second["duplicates_rejected"], 1)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["prospects_retained"], 2)
        self.assertEqual(result["duplicates_rejected"], 1)
        self.assertEqual(result["external_side_effects"], "none")
        connection = connect_db(self.db)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM outreach").fetchone()[0], 0)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM prospects WHERE external_action_approved=1"
            ).fetchone()[0],
            0,
        )
        connection.close()

    def test_tool_budget_excess_fails_closed(self):
        context = start_research(self.db, "research-id", 40_000, 10)
        result = finish_research(
            self.db, context["research_run_id"], "success", 0, 11, []
        )
        self.assertEqual(result["status"], "failure")
        self.assertIn("tool budget exceeded", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
