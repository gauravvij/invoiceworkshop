from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

RUNNER = SCRIPTS / "run_backlink_daily.sh"


def _step_positions(source: str) -> dict[str, int]:
    """Position of each pipeline step, ignoring comments."""
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    return {
        "poll": body.index("growth_level1a_mailbox.py poll"),
        "placements": body.index("verify-placements"),
        "outbound": body.index("growth_level1a.py run-approved"),
        "discovery": body.index("growth_backlink_engine.py cycle"),
    }


class DailyOrderTests(unittest.TestCase):
    def setUp(self):
        self.source = RUNNER.read_text(encoding="utf-8")
        self.at = _step_positions(self.source)

    def test_replies_are_processed_before_outbound(self):
        """A reply arriving before the run must be able to cancel a follow-up."""
        self.assertLess(self.at["poll"], self.at["outbound"])

    def test_placements_are_verified_before_outbound(self):
        self.assertLess(self.at["placements"], self.at["outbound"])

    def test_discovery_runs_last(self):
        for step in ("poll", "placements", "outbound"):
            self.assertLess(self.at[step], self.at["discovery"], step)

    def test_a_failed_poll_blocks_outbound(self):
        self.assertIn("inbound_ok=0", self.source)
        self.assertIn('"$inbound_ok" -ne 1', self.source)
        self.assertIn("reply state is unknown", self.source)

    def test_poll_failure_is_not_silently_swallowed(self):
        # `poll || true` would hide an inbound failure and let a follow-up send.
        self.assertNotIn("growth_level1a_mailbox.py poll || true", self.source)

    def test_outbound_is_gated_by_the_owner_controlled_env_file(self):
        self.assertIn("level1.env", self.source)
        self.assertIn('"${LEVEL1_OUTBOUND_ENABLED:-false}" == "true"', self.source)

    def test_runner_sends_only_through_the_approved_executor(self):
        self.assertIn("run-approved", self.source)
        for forbidden in ("execute --action-id", "send_plaintext", "--recipient"):
            self.assertNotIn(forbidden, self.source, forbidden)

    def test_deployed_copy_matches_the_repository(self):
        deployed = Path.home() / ".hermes/scripts/invoiceworkshop-backlink-daily.sh"
        if not deployed.is_file():
            self.skipTest("scheduler copy not present in this environment")
        self.assertEqual(deployed.read_text(encoding="utf-8"), self.source)


class FollowUpOrderingTests(unittest.TestCase):
    def test_executor_checks_reply_state_before_sending(self):
        source = (SCRIPTS / "growth_level1a.py").read_text(encoding="utf-8")
        validate = source.index("def validate_action(")
        live_gate = source.index("if live:", validate)
        window = source[validate:live_gate]
        # These run for every attempt, before the live-only switches are read.
        self.assertIn("level1a_replies", window)
        self.assertIn("level1a_suppressions", window)
        self.assertIn("FROM placements", window)


if __name__ == "__main__":
    unittest.main()
