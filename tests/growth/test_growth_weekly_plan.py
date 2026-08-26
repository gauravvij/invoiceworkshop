from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import apply_schema, connect_db, utc_now  # noqa: E402
from growth_weekly_plan import run_weekly  # noqa: E402


class WeeklyPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "growth.db"
        self.output = self.root / "plans"
        connection = connect_db(self.db)
        apply_schema(connection)
        today = date.today().isoformat()
        now = utc_now()
        connection.execute(
            """INSERT INTO metrics_daily
               (date, gsc_impressions, gsc_clicks, ga_sessions, ga_users,
                ga_pageviews, ga_tool_starts, ga_pdf_downloads, ga_returning, collected_at)
               VALUES (?, 0, 0, 11, 10, 12, 3, 1, 2, ?)""",
            (today, now),
        )
        for source, rows in (("gsc", 1), ("ga4", 2)):
            connection.execute(
                """INSERT INTO source_snapshots
                   (collected_at, source, status, row_count)
                   VALUES (?, ?, 'ok', ?)""",
                (now, source, rows),
            )
        connection.execute(
            """INSERT INTO url_health
               (date, url, checked_at, status)
               VALUES (?, 'https://invoiceworkshop.com/', ?, 200)""",
            (today, now),
        )
        connection.execute(
            """INSERT INTO index_state
               (date, url, inspected_at, verdict, coverage_state)
               VALUES (?, 'https://invoiceworkshop.com/', ?, 'PASS', 'Submitted and indexed')""",
            (today, now),
        )
        connection.execute(
            """INSERT INTO sitemap_state
               (date, path, collected_at, errors, warnings)
               VALUES (?, 'https://invoiceworkshop.com/sitemap.xml', ?, 0, 0)""",
            (today, now),
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_weekly_plan_is_deterministic_and_audited(self):
        self.output.mkdir()
        plan = self.output / f"{date.today().isoformat()}.md"
        plan.write_text("stale contradictory plan", encoding="utf-8")

        result = run_weekly(
            db=str(self.db), period=7, hermes_job_id="weekly-test", output_dir=self.output
        )

        content = plan.read_text(encoding="utf-8")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["evidence_rows_used"], {"gsc": 1, "ga4": 2})
        self.assertIn("11 sessions, 10 users, 12 pageviews", content)
        self.assertIn("Empty search evidence is recorded", content)
        self.assertNotIn("stale contradictory plan", content)
        connection = connect_db(self.db)
        row = connection.execute(
            "SELECT status, external_side_effects FROM level0_runs WHERE id=?",
            (result["run_id"],),
        ).fetchone()
        self.assertEqual(dict(row), {"status": "success", "external_side_effects": "none"})
        connection.close()

    def test_failed_source_is_logged_without_a_plan(self):
        connection = connect_db(self.db)
        connection.execute(
            "UPDATE source_snapshots SET status='failed', error='HTTP 403' WHERE source='gsc'"
        )
        connection.commit()
        connection.close()

        with self.assertRaises(ValueError):
            run_weekly(
                db=str(self.db), period=7, hermes_job_id="weekly-test", output_dir=self.output
            )

        self.assertFalse((self.output / f"{date.today().isoformat()}.md").exists())
        connection = connect_db(self.db)
        row = connection.execute(
            "SELECT status, errors_json, external_side_effects FROM level0_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["status"], "failure")
        self.assertIn("latest gsc source snapshot is not successful", row["errors_json"])
        self.assertEqual(row["external_side_effects"], "none")
        connection.close()


if __name__ == "__main__":
    unittest.main()
