from __future__ import annotations

import argparse
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import apply_schema, connect_db  # noqa: E402
from growth_db import cmd_add_prospect  # noqa: E402


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "growth.db"

    def tearDown(self):
        self.temp.cleanup()

    def prospect_args(self, **overrides):
        values = {
            "db": str(self.db),
            "page_url": "https://www.example.com/resources/invoicing",
            "source_url": "https://www.example.com/resources/invoicing",
            "type": "resource",
            "score": 72,
            "risk": "low",
            "why_fit": "Curated small-business invoicing resource page.",
            "audience": "Independent small businesses.",
            "contact_method": "Public editorial guidelines page; no action taken.",
            "requires_account": "no",
            "requires_payment": "no",
            "link_type": "editorial",
            "status": "qualified",
            "rejection_reason": "",
            "notes": "Public research only.",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_schema_has_level_zero_safety_defaults(self):
        connection = connect_db(self.db)
        apply_schema(connection)
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        self.assertEqual(version, "4")
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(prospects)")
        }
        self.assertEqual(columns["external_action_approved"][4], "0")

    def test_add_prospect_is_validated_and_deduplicated(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cmd_add_prospect(self.prospect_args())
            cmd_add_prospect(self.prospect_args())
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([message["status"] for message in messages], ["added", "duplicate"])

        connection = sqlite3.connect(self.db)
        row = connection.execute(
            "SELECT domain, external_action_approved FROM prospects"
        ).fetchone()
        self.assertEqual(row, ("example.com", 0))
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM outreach").fetchone()[0], 0)

    def test_rejected_prospect_requires_reason(self):
        with self.assertRaisesRegex(SystemExit, "rejection-reason"):
            cmd_add_prospect(self.prospect_args(status="rejected"))


if __name__ == "__main__":
    unittest.main()
