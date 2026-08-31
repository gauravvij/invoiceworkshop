from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import apply_schema, connect_db  # noqa: E402
from growth_research_discovery import (  # noqa: E402
    fetch_candidate,
    import_vetted,
    scheduled_channels,
)


class ResearchDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "growth.db")
        self.connection = connect_db(self.db)
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_vetted_import_requires_same_site_explicit_contact_route(self):
        path = Path(self.temp.name) / "candidates.json"
        path.write_text(json.dumps([
            {
                "channel": "contractor",
                "page_url": "https://publisher.example/resources/contractors",
                "contact_url": "https://publisher.example/editorial-guidelines",
                "title": "Contractor resources",
                "snippet": "Educational resources for contractors.",
            },
            {
                "channel": "contractor",
                "page_url": "https://bad.example/resources",
                "contact_url": "https://different.example/contact",
            },
        ]), encoding="utf-8")
        result = import_vetted(self.connection, str(path))
        self.assertEqual(result, {"added": 1, "updated": 0, "rejected": 1})
        row = self.connection.execute("SELECT * FROM research_candidates").fetchone()
        self.assertEqual(row["state"], "queued")
        self.assertGreaterEqual(row["heuristic_score"], 80)

    def test_scheduled_channel_rotation_is_stable(self):
        selected = scheduled_channels(self.connection, 17)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(set(selected)), 3)

    @patch("growth_research_discovery.fetch_public_url")
    def test_candidate_fetch_verifies_page_and_contact_evidence(self, fetch):
        page = Mock(status_code=200, text=(
            "<html><body><h1>Tools for contractors</h1>" + " useful guidance" * 30
            + "</body></html>"
        ))
        contact = Mock(status_code=200, text=(
            "<html><body><h1>Editorial guidelines</h1>" + " submission details" * 15
            + "</body></html>"
        ))
        fetch.side_effect = [page, contact]
        evidence = fetch_candidate({
            "id": 1,
            "channel": "contractor",
            "page_url": "https://publisher.example/resources/contractors",
            "contact_url": "https://publisher.example/editorial-guidelines",
            "title": "Tools",
            "snippet": "Resources",
            "heuristic_score": 90,
        })
        self.assertIn("Tools for contractors", evidence["page_excerpt"])
        self.assertIn("Editorial guidelines", evidence["contact_excerpt"])
        self.assertTrue(evidence["contact_route_verified"])
        self.assertEqual(fetch.call_count, 2)

    @patch("growth_research_discovery.fetch_public_url")
    def test_candidate_fetch_rejects_reciprocal_listing(self, fetch):
        fetch.return_value = Mock(
            status_code=200,
            text="<html><body>" + ("Useful tool directory. " * 20)
            + "Free backlink required before submission.</body></html>",
        )
        with self.assertRaisesRegex(ValueError, "payment, sponsorship, or a reciprocal"):
            fetch_candidate({
                "id": 1,
                "channel": "directory",
                "page_url": "https://directory.example/submit",
                "contact_url": "https://directory.example/submit",
                "title": "Submit",
                "snippet": "Tools",
                "heuristic_score": 90,
            })


if __name__ == "__main__":
    unittest.main()
