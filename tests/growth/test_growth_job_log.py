from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import connect_db  # noqa: E402
from growth_job_log import cmd_finish, cmd_start  # noqa: E402


class JobLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "growth.db")
        self.sequence = 0

    def tearDown(self):
        self.temp.cleanup()

    def start(self) -> int:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cmd_start(argparse.Namespace(db=self.db, job="daily", hermes_job_id="daily-id"))
        return json.loads(output.getvalue())["run_id"]

    def add_collection(self, status: str, errors: list[str], gsc_rows=0, ga4_rows=0):
        connection = connect_db(self.db)
        self.sequence += 1
        started = f"2026-08-26T12:00:{self.sequence:02d}+00:00"
        connection.execute(
            "INSERT INTO collection_runs (started_at, finished_at, status, errors_json) VALUES (?, ?, ?, ?)",
            (started, started, status, json.dumps(errors)),
        )
        for source, rows in (("gsc", gsc_rows), ("ga4", ga4_rows)):
            connection.execute(
                """INSERT INTO source_snapshots
                   (collected_at, source, status, row_count) VALUES (?, ?, 'ok', ?)""",
                (started, source, rows),
            )
        connection.commit()
        connection.close()

    def finish(self, run_id: int, status="success", errors=None):
        args = argparse.Namespace(db=self.db, run_id=run_id, status=status, error=errors or [])
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_finish(args)

    def test_records_required_evidence(self):
        run_id = self.start()
        self.add_collection("ok", [], gsc_rows=4, ga4_rows=3)
        self.finish(run_id)
        connection = connect_db(self.db)
        row = connection.execute("SELECT * FROM level0_runs WHERE id=?", (run_id,)).fetchone()
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["gsc_rows_collected"], 4)
        self.assertEqual(row["ga4_rows_collected"], 3)
        self.assertEqual(row["external_side_effects"], "none")

    def test_three_consecutive_google_failures_trip_breaker(self):
        for _ in range(3):
            run_id = self.start()
            self.add_collection("failed", ["gsc: HTTP 403"])
            with self.assertRaises(SystemExit):
                self.finish(run_id, status="failure")
        connection = connect_db(self.db)
        row = connection.execute(
            "SELECT state, failure_streak FROM operation_state WHERE operation='google_reads'"
        ).fetchone()
        self.assertEqual(dict(row), {"state": "paused", "failure_streak": 3})

    def test_next_start_closes_abandoned_run(self):
        abandoned = self.start()
        self.start()
        connection = connect_db(self.db)
        row = connection.execute("SELECT status, errors_json FROM level0_runs WHERE id=?", (abandoned,)).fetchone()
        self.assertEqual(row["status"], "failure")
        self.assertIn("did not reach", row["errors_json"])


if __name__ == "__main__":
    unittest.main()
