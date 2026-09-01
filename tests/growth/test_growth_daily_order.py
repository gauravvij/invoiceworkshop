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

    def test_search_key_is_loaded_without_sourcing_the_whole_env(self):
        for name in ("run_backlink_daily.sh", "run_backlink_deep.sh", "run_backlink_weekly.sh"):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertIn("ANYSEARCH_API_KEY", source, name)
            # Sourcing .env would pull Cloudflare/S3 credentials into a
            # read-only discovery job that has no use for them.
            self.assertNotIn('source "$REPO/.env"', source, name)
            self.assertNotIn("source .env", source, name)

    def test_growth_jobs_serialise_on_a_lock(self):
        """Two jobs sharing the SQLite file must queue, not collide."""
        for name in ("run_backlink_daily.sh", "run_backlink_deep.sh", "run_backlink_weekly.sh"):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertIn("flock", source, name)
            self.assertIn("GROWTH_LOCK_HELD", source, name)
            # -E 0 so a wait timeout exits cleanly rather than failing the job.
            self.assertIn("-E 0", source, name)

    def test_lock_is_taken_before_any_work_runs(self):
        source = self.source
        body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertLess(body.index("flock"), body.index("growth_level1a_mailbox.py poll"))

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
