from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import apply_schema, connect_db, utc_now  # noqa: E402
from growth_report import build_report  # noqa: E402


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(Path(self.temp.name) / "growth.db")
        apply_schema(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_report_totals_and_anomalies_are_evidence_based(self):
        today = date.today().isoformat()
        now = utc_now()
        self.connection.execute(
            """INSERT INTO metrics_daily
               (date, gsc_impressions, gsc_clicks, ga_users, ga_pageviews,
                ga_sessions, ga_tool_starts, ga_pdf_downloads, ga_returning, collected_at)
               VALUES (?, 12, 2, 4, 7, 5, 3, 1, 1, ?)""",
            (today, now),
        )
        self.connection.execute(
            """INSERT INTO url_health
               (date, url, checked_at, status, error)
               VALUES (?, 'https://invoiceworkshop.com/', ?, 503, 'HTTP 503')""",
            (today, now),
        )
        self.connection.execute(
            """INSERT INTO index_state
               (date, url, inspected_at, verdict, coverage_state)
               VALUES (?, 'https://invoiceworkshop.com/', ?, 'NEUTRAL', 'Discovered')""",
            (today, now),
        )
        self.connection.commit()

        report = build_report(self.connection, 7)
        self.assertEqual(report["totals"]["gsc_impressions"], 12)
        self.assertEqual(report["totals"]["ga_sessions"], 5)
        self.assertEqual(report["totals"]["ga_pdf_downloads"], 1)
        self.assertEqual(
            {item["type"] for item in report["anomalies"]},
            {"url_health", "index_state"},
        )


if __name__ == "__main__":
    unittest.main()
