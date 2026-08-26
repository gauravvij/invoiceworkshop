from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import connect_db  # noqa: E402
from growth_research import finish_research, start_research  # noqa: E402
from growth_usage_sync import synchronize  # noqa: E402


class UsageSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = str(self.root / "growth.db")
        context = start_research(self.db, "research-id", 40_000, 10)
        finish_research(self.db, context["research_run_id"], "success", 9, 8, [])
        connection = connect_db(self.db)
        run = connection.execute("SELECT * FROM research_runs").fetchone()
        connection.close()
        start = datetime.fromisoformat(run["started_at"]).timestamp()
        end = datetime.fromisoformat(run["finished_at"]).timestamp()

        self.state = self.root / "state.db"
        state = sqlite3.connect(self.state)
        state.execute(
            """CREATE TABLE sessions (
               id TEXT, model TEXT, started_at REAL, ended_at REAL, end_reason TEXT,
               tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER,
               cache_read_tokens INTEGER, cache_write_tokens INTEGER,
               reasoning_tokens INTEGER, api_call_count INTEGER)"""
        )
        state.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, NULL, 8, 100, 20, 50, 0, 5, 4)",
            ("cron_research-id_20260826_120000", "openai/gpt-5-mini", start, end),
        )
        state.commit()
        state.close()

        self.executions = self.root / "executions.db"
        executions = sqlite3.connect(self.executions)
        executions.execute(
            """CREATE TABLE executions (
               id TEXT, job_id TEXT, status TEXT, started_at TEXT, finished_at TEXT,
               error TEXT)"""
        )
        start_iso = datetime.fromtimestamp(start, timezone.utc).isoformat()
        end_iso = datetime.fromtimestamp(end, timezone.utc).isoformat()
        executions.execute(
            "INSERT INTO executions VALUES ('exec-1', 'research-id', 'completed', ?, ?, NULL)",
            (start_iso, end_iso),
        )
        executions.commit()
        executions.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_sync_records_exact_usage_and_research_counts(self):
        result = synchronize(
            self.db, self.state, self.executions, extra_job_ids=["research-id"]
        )
        self.assertEqual(result["records_synced"], 1)
        connection = connect_db(self.db)
        row = connection.execute("SELECT * FROM agent_executions").fetchone()
        self.assertEqual(row["model"], "openai/gpt-5-mini")
        self.assertEqual(row["input_tokens"], 100)
        self.assertEqual(row["output_tokens"], 20)
        self.assertEqual(row["total_tokens"], 170)
        self.assertEqual(row["tool_calls"], 8)
        self.assertEqual(row["candidates_examined"], 9)
        self.assertEqual(row["prospects_retained"], 0)
        self.assertEqual(row["external_side_effects"], "none")
        connection.close()


if __name__ == "__main__":
    unittest.main()
