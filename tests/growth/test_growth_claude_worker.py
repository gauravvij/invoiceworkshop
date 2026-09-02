from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_auto_policy as policy  # noqa: E402
import growth_claude_worker as worker  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402
from test_growth_auto_policy import seed_opportunity  # noqa: E402

OPPORTUNITY = {
    "id": 1,
    "opportunity_key": "gap:https://invoiceworkshop.com/invoice-template/",
    "opportunity_type": "SEO_PAGE_IMPROVEMENT",
    "title": "Close user-value gaps on /invoice-template/",
    "target_url": "https://invoiceworkshop.com/invoice-template/",
    "evidence": "no worked example showing the document and its arithmetic",
}


def envelope(result: dict, *, is_error: bool = False, cost: float = 0.42) -> str:
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": is_error,
        "num_turns": 6, "total_cost_usd": cost, "duration_ms": 41000,
        "session_id": "11111111-2222-3333-4444-555555555555",
        "result": json.dumps(result),
    })


class PromptTests(unittest.TestCase):
    def test_the_prompt_states_the_standard_rather_than_a_length_target(self):
        prompt = worker.build_prompt(OPPORTUNITY, {"queries": []})
        self.assertIn("Length is not the goal", prompt)
        self.assertIn("NO_ACTION", prompt)
        self.assertIn("Do not manufacture a change", prompt)
        # A word target would reintroduce exactly the failure mode the model was
        # corrected for.
        for forbidden in ("word count target", "at least 1000 words", "expand to"):
            self.assertNotIn(forbidden, prompt.lower())

    def test_the_prompt_carries_the_envelope_the_wrapper_will_enforce(self):
        prompt = worker.build_prompt(OPPORTUNITY, {})
        self.assertIn("src/content/generators.ts", prompt)
        self.assertIn("blocked_change_categories", prompt)
        self.assertIn("There is no shell", prompt)


class InvocationTests(unittest.TestCase):
    def _invoke(self, completed, **kwargs):
        with mock.patch("subprocess.run", return_value=completed) as runner:
            result = worker.invoke_claude("prompt", **kwargs)
        return result, runner.call_args[0][0]

    def test_the_agent_gets_no_shell_and_no_deployment_reach(self):
        completed = mock.Mock(returncode=0, stdout=envelope({"decision": "NO_ACTION",
                                                             "summary": "s", "rationale": "r"}),
                              stderr="")
        _, command = self._invoke(completed)
        tools = command[command.index("--tools") + 1]
        self.assertEqual(sorted(tools.split(",")), ["Edit", "Glob", "Grep", "Read"])
        self.assertIn("--restricted", command)
        for forbidden in ("Bash", "WebFetch", "WebSearch", "Write", "Agent", "Task"):
            self.assertNotIn(forbidden, tools)

    def test_every_run_is_cost_and_time_bounded(self):
        completed = mock.Mock(returncode=0, stdout=envelope({"decision": "NO_ACTION",
                                                             "summary": "s", "rationale": "r"}),
                              stderr="")
        _, command = self._invoke(completed)
        self.assertIn("--max-budget-usd", command)
        self.assertEqual(command[command.index("--max-budget-usd") + 1],
                         str(worker.MAX_BUDGET_USD))
        self.assertIn("--json-schema", command)

    def test_permission_mode_is_never_bypass(self):
        completed = mock.Mock(returncode=0, stdout=envelope({"decision": "NO_ACTION",
                                                             "summary": "s", "rationale": "r"}),
                              stderr="")
        _, command = self._invoke(completed)
        self.assertEqual(command[command.index("--permission-mode") + 1], "acceptEdits")

    def test_the_prompt_is_not_exposed_in_the_process_table(self):
        """A scheduled run's argv is world-readable; the prompt carries evidence."""
        completed = mock.Mock(returncode=0, stdout=envelope({"decision": "NO_ACTION",
                                                             "summary": "s", "rationale": "r"}),
                              stderr="")
        with mock.patch("subprocess.run", return_value=completed) as runner:
            worker.invoke_claude("SECRET-EVIDENCE-MARKER")
        command = runner.call_args[0][0]
        self.assertNotIn("SECRET-EVIDENCE-MARKER", " ".join(command))
        self.assertEqual(runner.call_args.kwargs["input"], "SECRET-EVIDENCE-MARKER")

    def test_a_timeout_is_reported_rather_than_raised(self):
        import subprocess
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5)):
            result = worker.invoke_claude("prompt", timeout=5)
        self.assertEqual(result["outcome"], "timeout")

    def test_missing_authentication_is_an_operating_state_not_a_crash(self):
        completed = mock.Mock(returncode=1, stdout="", stderr="Error: not logged in")
        result, _ = self._invoke(completed)
        self.assertEqual(result["outcome"], "blocked_auth")

    def test_a_usage_limit_is_recognised_as_blocked_rather_than_broken(self):
        completed = mock.Mock(returncode=1, stdout="", stderr="429 usage limit reached")
        result, _ = self._invoke(completed)
        self.assertEqual(result["outcome"], "blocked_auth")

    def test_unparseable_output_is_an_error_not_a_change(self):
        completed = mock.Mock(returncode=0, stdout="not json at all", stderr="")
        result, _ = self._invoke(completed)
        self.assertEqual(result["outcome"], "error")

    def test_usage_is_captured_for_the_cost_review(self):
        completed = mock.Mock(returncode=0, stdout=envelope(
            {"decision": "NO_ACTION", "summary": "s", "rationale": "r"}, cost=1.25), stderr="")
        result, _ = self._invoke(completed)
        self.assertEqual(result["cost_usd"], 1.25)
        self.assertEqual(result["num_turns"], 6)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)
        seed_opportunity(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _run(self, invoke_result, *, dirty=(), diff="+ text", **patches):
        """Drive `execute` with the outside world stubbed.

        Everything real stays real: the policy check, the database writes and
        the ordering of the gates. Only the model, git, npm and the network are
        replaced, because those are what cannot run inside a test.
        """
        defaults = {
            "_dirty_paths": mock.Mock(side_effect=[[], list(dirty)]),
            "invoke_claude": mock.Mock(return_value=invoke_result),
            "_git": mock.Mock(return_value="abc1234"),
            "_revert_working_tree": mock.Mock(),
        }
        defaults.update(patches)
        with mock.patch.object(policy, "working_diff", return_value=diff), \
             mock.patch("subprocess.run",
                        return_value=mock.Mock(returncode=0, stdout="", stderr="")), \
             mock.patch.multiple(worker, **defaults):
            return worker.execute(self.connection, dict(OPPORTUNITY))

    def test_a_dirty_working_tree_refuses_before_anything_runs(self):
        with mock.patch.object(worker, "_dirty_paths", return_value=["src/lib/x.ts"]), \
             mock.patch.object(worker, "invoke_claude") as invoke:
            result = worker.execute(self.connection, dict(OPPORTUNITY))
        invoke.assert_not_called()
        self.assertEqual(result["outcome"], "refused")

    def test_no_action_records_a_run_and_changes_nothing(self):
        result = self._run({"outcome": "completed", "cost_usd": 0.4, "num_turns": 3,
                            "verdict": {"decision": "NO_ACTION", "summary": "already covered",
                                        "rationale": "the page already answers this"}})
        self.assertEqual(result["outcome"], "no_action")
        stored = self.connection.execute(
            "SELECT outcome, cost_usd, deployed FROM claude_runs").fetchone()
        self.assertEqual(stored["outcome"], "no_action")
        self.assertEqual(stored["deployed"], 0)

    def test_a_declined_opportunity_stops_being_proposed(self):
        self._run({"outcome": "completed", "verdict": {
            "decision": "NO_ACTION", "summary": "s", "rationale": "no real gap here"}})
        state = self.connection.execute(
            "SELECT state, dismissed_reason FROM growth_opportunities").fetchone()
        self.assertEqual(state["state"], "dismissed")
        self.assertIn("no real gap here", state["dismissed_reason"])

    def test_a_change_outside_the_envelope_is_reverted_and_never_committed(self):
        result = self._run(
            {"outcome": "completed", "verdict": {"decision": "CHANGED", "summary": "s",
                                                 "rationale": "r"}},
            dirty=["src/lib/documents/money.ts"],
            local_validation=mock.Mock(),
        )
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(self.connection.execute(
            "SELECT deployed FROM claude_runs").fetchone()[0], 0)

    def test_a_failed_local_gate_is_reverted_and_never_committed(self):
        revert = mock.Mock()
        result = self._run(
            {"outcome": "completed", "verdict": {"decision": "CHANGED", "summary": "s",
                                                 "rationale": "r"}},
            dirty=["src/content/generators.ts"],
            local_validation=mock.Mock(return_value={
                "failed_at": "build", "build": {"passed": False, "output": "type error"}}),
            _revert_working_tree=revert,
        )
        self.assertEqual(result["outcome"], "validation_failed")
        revert.assert_called_once()
        self.assertIsNone(self.connection.execute(
            "SELECT commit_sha FROM claude_runs").fetchone()[0])

    def test_a_failed_gate_does_not_record_an_experiment(self):
        self._run(
            {"outcome": "completed", "verdict": {"decision": "CHANGED", "summary": "s",
                                                 "rationale": "r"}},
            dirty=["src/content/generators.ts"],
            local_validation=mock.Mock(return_value={
                "failed_at": "e2e", "e2e": {"passed": False, "output": "fail"}}),
        )
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM growth_experiments").fetchone()[0], 0)

    def test_a_ci_failure_reverts_the_commit_and_deploys_nothing(self):
        result = self._run(
            {"outcome": "completed", "verdict": {"decision": "CHANGED", "summary": "s",
                                                 "rationale": "r"}},
            dirty=["src/content/generators.ts"],
            local_validation=mock.Mock(return_value={"build": {"passed": True}}),
            wait_for_ci=mock.Mock(return_value={"run_id": "9", "conclusion": "failure",
                                                "passed": False}),
            verify_production=mock.Mock(),
        )
        self.assertEqual(result["outcome"], "deploy_failed")
        self.assertEqual(self.connection.execute(
            "SELECT deployed FROM claude_runs").fetchone()[0], 0)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM growth_experiments").fetchone()[0], 0)

    def test_a_failed_production_check_rolls_back(self):
        result = self._run(
            {"outcome": "completed", "verdict": {"decision": "CHANGED", "summary": "s",
                                                 "rationale": "r"}},
            dirty=["src/content/generators.ts"],
            local_validation=mock.Mock(return_value={"build": {"passed": True}}),
            wait_for_ci=mock.Mock(return_value={"run_id": "9", "conclusion": "success",
                                                "passed": True}),
            verify_production=mock.Mock(return_value={"passed": False, "status": 200,
                                                      "single_h1": False}),
            time=mock.Mock(sleep=lambda _: None, monotonic=lambda: 0.0),
        )
        self.assertEqual(result["outcome"], "rolled_back")
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM growth_experiments").fetchone()[0], 0)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM escalations WHERE kind='production_verification'"
        ).fetchone()[0], 1)

    def test_a_verified_deployment_records_the_experiment_and_closes_the_opportunity(self):
        result = self._run(
            {"outcome": "completed", "cost_usd": 0.9,
             "verdict": {"decision": "CHANGED", "summary": "added a worked example",
                         "rationale": "readers could not check the arithmetic",
                         "user_value": "impressions on arithmetic phrasings"}},
            dirty=["src/content/generators.ts"],
            local_validation=mock.Mock(return_value={"build": {"passed": True}}),
            wait_for_ci=mock.Mock(return_value={"run_id": "9", "conclusion": "success",
                                                "passed": True}),
            verify_production=mock.Mock(return_value={"passed": True, "status": 200}),
            time=mock.Mock(sleep=lambda _: None, monotonic=lambda: 0.0),
        )
        self.assertEqual(result["outcome"], "changed")
        self.assertEqual(result["deployed"], 1)
        experiment = self.connection.execute(
            "SELECT action, evaluate_after, baseline_json FROM growth_experiments").fetchone()
        self.assertEqual(experiment["action"], "added a worked example")
        self.assertEqual(self.connection.execute(
            "SELECT state FROM growth_opportunities").fetchone()[0], "done")

    def test_blocked_authentication_leaves_the_opportunity_queued_and_escalates(self):
        result = self._run({"outcome": "blocked_auth", "error": "not logged in"})
        self.assertEqual(result["outcome"], "blocked_auth")
        self.assertEqual(self.connection.execute(
            "SELECT state FROM growth_opportunities").fetchone()[0], "open")
        escalation = self.connection.execute(
            "SELECT severity, subject FROM escalations WHERE kind='claude_unavailable'"
        ).fetchone()
        self.assertIsNotNone(escalation)

    def test_a_fixture_run_that_edits_anything_is_refused(self):
        revert = mock.Mock()
        result = self._run_fixture(revert)
        self.assertEqual(result["outcome"], "refused")
        revert.assert_called_once()

    def _run_fixture(self, revert):
        with mock.patch.multiple(
            worker,
            _dirty_paths=mock.Mock(side_effect=[[], ["src/content/generators.ts"]]),
            invoke_claude=mock.Mock(return_value={
                "outcome": "completed",
                "verdict": {"decision": "CHANGED", "summary": "s", "rationale": "r"}}),
            _git=mock.Mock(return_value="abc"),
            _revert_working_tree=revert,
        ):
            return worker.execute(self.connection, dict(OPPORTUNITY), fixture=True)


class BudgetTests(unittest.TestCase):
    def test_the_scheduled_path_cannot_exceed_the_daily_cap(self):
        source = (SCRIPTS / "growth_claude_worker.py").read_text(encoding="utf-8")
        # The unattended branch goes through select_candidate, which counts the
        # day's runs; only an explicitly directed run may pass the override.
        self.assertIn("policy.select_candidate(connection)", source)
        self.assertIn("args.override_budget", source)
        directed = source.index("args.opportunity_id:")
        scheduled = source.index("candidate = policy.select_candidate(connection)")
        self.assertLess(directed, scheduled)
        self.assertNotIn("override_budget", source[scheduled:])


class NoPrivilegeEscalationTests(unittest.TestCase):
    def test_the_worker_never_asks_for_sudo(self):
        source = (SCRIPTS / "growth_claude_worker.py").read_text(encoding="utf-8")
        for forbidden in ("sudo", "CLOUDFLARE", "wrangler deploy", "ANYSEARCH_API_KEY",
                          "ZOHO", "--dangerously-skip-permissions"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_the_worker_cannot_send_outreach(self):
        source = (SCRIPTS / "growth_claude_worker.py").read_text(encoding="utf-8")
        for forbidden in ("growth_level1a", "run-approved", "approve-action",
                          "growth_outreach_policy"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_outreach_scripts_are_outside_the_editable_envelope(self):
        for path in ("scripts/growth_level1a.py", "scripts/growth_outreach_policy.py",
                     "scripts/growth_auto_policy.py", "scripts/growth_claude_worker.py"):
            with self.assertRaises(policy.PolicyRefusal, msg=path):
                policy.validate_change([path], f"--- a/{path}\n+++ b/{path}\n+x\n")


if __name__ == "__main__":
    unittest.main()
