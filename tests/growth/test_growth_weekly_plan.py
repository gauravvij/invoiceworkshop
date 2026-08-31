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

    def test_plan_ranks_only_qualified_and_surfaces_research_statuses(self):
        connection = connect_db(self.db)
        now = utc_now()
        common = (
            "resource", 80, "low", "Relevant resource for independent businesses.",
            "Freelancers and small businesses use this resource.",
            "https://example.org/contact", 0, 0, "editorial", now, now,
        )
        qualified_cursor = connection.execute(
            """INSERT INTO prospects
               (domain,page_url,prospect_type,opportunity_score,risk,why_fit,audience,
                contact_method,requires_account,requires_payment,link_type,source_url,
                status,discovered_at,updated_at)
               VALUES ('qualified.example','https://qualified.example/resources',?,?,?,?,?,?,?,?,?,
                       'https://qualified.example/resources','qualified',?,?)""",
            common,
        )
        connection.execute(
            """INSERT INTO prospect_qualification
               (prospect_id,channel,page_evidence,outbound_resources,target_url,
                proposed_action,confidence,second_pass_pass,review_reason,reviewed_at)
               VALUES (?,'freelancer','Explicit useful-resource evidence.','[]',
                       'https://invoiceworkshop.com/','Suggest the useful resource.','high',1,
                       'This resource remains useful without considering SEO value.',?)""",
            (qualified_cursor.lastrowid, now),
        )
        rejected = list(common)
        rejected[1] = 99
        connection.execute(
            """INSERT INTO prospects
               (domain,page_url,prospect_type,opportunity_score,risk,why_fit,audience,
                contact_method,requires_account,requires_payment,link_type,source_url,
                status,rejection_reason,discovered_at,updated_at)
               VALUES ('rejected.example','https://rejected.example/resources',?,?,?,?,?,?,?,?,?,
                       'https://rejected.example/resources','rejected','insufficient evidence',?,?)""",
            rejected,
        )
        connection.execute(
            """INSERT INTO research_runs
               (hermes_job_id,started_at,finished_at,status,soft_token_budget,
                soft_tool_budget,candidates_examined,prospects_retained)
               VALUES ('research-test',?,?, 'budget_stopped',60000,10,8,1)""",
            (now, now),
        )
        connection.commit()
        connection.close()

        result = run_weekly(
            db=str(self.db), period=7, hermes_job_id="weekly-test", output_dir=self.output
        )
        content = Path(result["plan_path"]).read_text(encoding="utf-8")
        self.assertIn("qualified.example (score 80)", content)
        self.assertNotIn("rejected.example (score 99)", content)
        self.assertIn("budget_stopped=1", content)
        self.assertIn("qualified=1", content)
        self.assertIn("new/unreviewed=0", content)
        self.assertIn("Current research bounds: at most 3 cheap discovery queries", content)

if __name__ == "__main__":
    unittest.main()
