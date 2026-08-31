from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import apply_schema, connect_db  # noqa: E402
from growth_measure import classify_traffic, collect_ga4, collect_gsc  # noqa: E402


class FakeGoogle:
    def query_gsc(self, _site, body):
        dimensions = body["dimensions"]
        if dimensions == ["date"]:
            return {"rows": [{
                "keys": ["2026-08-30"], "clicks": 1, "impressions": 4,
                "ctr": 0.25, "position": 12.0,
            }]}
        if dimensions == ["date", "query", "page", "country", "device"]:
            return {"rows": [{
                "keys": ["2026-08-30", "invoice tool", "https://invoiceworkshop.com/",
                         "usa", "DESKTOP"],
                "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 4.0,
            }]}
        return {"rows": []}

    def run_ga_report(self, _property, body):
        names = [item["name"] for item in body["dimensions"]]
        metrics = [item["name"] for item in body["metrics"]]
        if names == ["date"]:
            return {"rows": [{
                "dimensionValues": [{"value": "20260830"}],
                "metricValues": [{"value": "3"}, {"value": "2"}, {"value": "5"}],
            }]}
        if names == ["date", "eventName"]:
            return {"rows": [{
                "dimensionValues": [{"value": "20260830"}, {"value": "tool_started"}],
                "metricValues": [{"value": "2"}],
            }]}
        dimensions = [
            {"value": "20260830"}, {"value": "newsletter"},
            {"value": "email"}, {"value": "Email"},
        ]
        if names[-1] == "eventName":
            return {"rows": [{
                "dimensionValues": [*dimensions, {"value": "pdf_downloaded"}],
                "metricValues": [{"value": "1"}],
            }]}
        self.assertEqual(metrics, ["totalUsers", "sessions", "screenPageViews"])
        return {"rows": [{
            "dimensionValues": dimensions,
            "metricValues": [{"value": "2"}, {"value": "3"}, {"value": "5"}],
        }]}

    def assertEqual(self, left, right):
        if left != right:
            raise AssertionError(f"{left!r} != {right!r}")


class GrowthMeasureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(Path(self.temp.name) / "growth.db")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_persists_combined_gsc_dimensions(self):
        collect_gsc(
            FakeGoogle(), self.connection, "sc-domain:invoiceworkshop.com",
            "2026-08-24", "2026-08-30", "2026-08-31T00:00:00+00:00",
        )
        row = self.connection.execute("SELECT * FROM gsc_query_facts").fetchone()
        self.assertEqual(row["query"], "invoice tool")
        self.assertEqual(row["page"], "https://invoiceworkshop.com/")
        self.assertEqual(row["country"], "usa")
        self.assertEqual(row["device"], "DESKTOP")
        self.assertEqual(row["date"], "2026-08-30")

    def test_persists_ga4_acquisition_without_inventing_internal_status(self):
        collect_ga4(
            FakeGoogle(), self.connection, "123", "2026-08-24", "2026-08-30",
            "2026-08-31T00:00:00+00:00",
        )
        row = self.connection.execute("SELECT * FROM ga4_acquisition").fetchone()
        self.assertEqual(row["source_medium"], "newsletter / email")
        self.assertEqual(row["sessions"], 3)
        self.assertEqual(row["pdf_downloads"], 1)
        self.assertEqual(row["traffic_class"], "unknown")

    def test_internal_classification_requires_explicit_patterns(self):
        self.assertEqual(classify_traffic("qa / test", []), ("unknown", None))
        traffic_class, reason = classify_traffic("qa / test", ["qa / *"])
        self.assertEqual(traffic_class, "internal")
        self.assertIn("qa / *", reason)


if __name__ == "__main__":
    unittest.main()
