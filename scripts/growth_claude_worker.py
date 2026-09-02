#!/usr/bin/env python3
"""Unattended Claude Code worker for one bounded AUTO growth task.

The deterministic pipeline decides *whether* to wake a reasoning agent and
*which* opportunity it may work on. This module is what actually wakes it, and
everything around the invocation is deliberately not the model's job:

* Claude gets Read, Edit, Grep and Glob. No shell, no network, no git, no
  deployment credentials. It cannot run the build, push a commit or reach
  production, so nothing it decides can reach users on its own.
* This wrapper validates the diff against the AUTO envelope, runs the local
  gates, commits, pushes, waits for CI, verifies production, and reverts if any
  of that fails. Those steps are ordinary code and cannot be argued with.
* Deciding to change nothing is a first-class success. A run that returns
  NO_ACTION costs one invocation and leaves the site alone, which is the right
  outcome most days.

Run:
    growth_claude_worker.py select                 # what would happen, no run
    growth_claude_worker.py run                    # pick and execute today's task
    growth_claude_worker.py run --opportunity-id N # execute exactly that task
    growth_claude_worker.py run --fixture          # exercise the path, touch nothing
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import growth_auto_policy as policy
from growth_common import (ROOT, apply_schema, connect_db, database_path,
                           record_escalation, utc_now)

CLAUDE = Path.home() / ".local" / "bin" / "claude"
LOCK_PATH = Path.home() / ".config" / "invoiceworkshop" / "growth-executor.lock"

MODEL = "opus"
FALLBACK_MODEL = "sonnet"
# A bounded editing task on two known files. If it has not finished inside this,
# something is wrong and waiting longer will not fix it.
CLAUDE_TIMEOUT_SECONDS = 900
MAX_BUDGET_USD = 5.0
CI_TIMEOUT_SECONDS = 1500

# The agent's answer has to be machine-readable, because the wrapper acts on it
# without a person in the loop.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["CHANGED", "NO_ACTION"]},
        "summary": {"type": "string"},
        "rationale": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "user_value": {"type": "string"},
    },
    "required": ["decision", "summary", "rationale"],
    "additionalProperties": False,
}

# Untracked files that live in the working copy and are not part of any change.
IGNORED_UNTRACKED = ("task_brief_cc.md", "task_brief_cc2.md", "test-results/",
                     "playwright-report/", "lighthouse-reports/")


class WorkerError(RuntimeError):
    """Something went wrong that must be recorded rather than worked around."""


def _git(*arguments: str, check: bool = True) -> str:
    result = subprocess.run(["git", *arguments], cwd=ROOT, check=False,
                            capture_output=True, text=True)
    if check and result.returncode != 0:
        raise WorkerError(f"git {' '.join(arguments)} failed: {result.stderr.strip()[:400]}")
    return result.stdout.strip()


def _dirty_paths() -> list[str]:
    return [path for path in policy.changed_files()
            if not any(path.startswith(ignored) for ignored in IGNORED_UNTRACKED)]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def build_prompt(opportunity: dict, evidence: dict) -> str:
    route = (opportunity.get("target_url") or "").replace("https://invoiceworkshop.com", "") or "/"
    return f"""You are making one bounded improvement to InvoiceWorkshop, a free
browser-based invoice and business-document generator. You are running
unattended: nobody will review your reasoning before this reaches production, so
the standard is what you would ship without being asked to justify it.

## The opportunity the growth system selected

{json.dumps(opportunity, indent=2, sort_keys=True, default=str)}

## Supporting evidence from the growth database

{json.dumps(evidence, indent=2, sort_keys=True, default=str)}

## What you may change

{policy.policy_document()}

Page content lives in `src/content/generators.ts` as a `sections` array. A
section is `{{ heading, paragraphs[], bullets?, terms?, table? }}`. A `table` has
`caption`, `columns[]`, `rows[][]`, `total[[label, value]]` and an optional
`note`. `terms` is a list of `{{ term, definition }}`. Follow the existing shape
exactly; the page component renders nothing else.

## The standard this change is held to

The site is a seven-day-old domain with roughly ten lifetime search impressions
and no clicks. Length is not the goal and never has been: Google states no
preferred word count, and a section that exists to make a page longer is a
regression, not an improvement. Add something a reader could act on, or add
nothing.

Good work here looks like: a worked example whose arithmetic a reader can check
against what the tool produces; a comparison that answers the question people
actually arrive with (which of these documents do I need?); an explanation
without which someone cannot finish the task. Every number you write must be
arithmetically correct and internally consistent — someone will check a total
against their own invoice.

Bad work looks like: generic filler, restating something already on the page,
padding a checklist, inventing statistics, or a claim about the product that
nobody reviewed.

## Constraints you cannot test your way around

You have Read, Edit, Grep and Glob. There is no shell. You cannot run the build,
run tests, commit, or deploy — a wrapper does all of that after you exit, checks
your diff against the policy above, and reverts everything if any gate fails. So
write the change carefully the first time and keep it small: at most
{policy.MAX_CHANGED_FILES} files and {policy.MAX_DIFF_LINES} changed lines.

## Deciding not to act

If, having read the page, the opportunity is not real — the value is already
there, the evidence is too thin, or the honest change would be outside the
policy — make no edit and return NO_ACTION. That is a correct and expected
outcome. Do not manufacture a change to have something to show.

## Your task

Read {route} in `src/content/generators.ts`, decide whether the stated gap is
genuinely a gap for a user of that page, and if it is, close it. Then return the
JSON result: `decision` CHANGED or NO_ACTION, a one-line `summary`, a `rationale`
naming the user need you served or why you declined, and `files_changed`.
"""


def build_surface_prompt(page: dict) -> str:
    """Prompt for creating one new page in an already-admitted family.

    The family passed the admission gate before this ran, which means the tool
    genuinely behaves differently on this route. The job here is to write the
    page that explains that difference accurately -- not to invent a reason for
    the page to exist.
    """
    return f"""You are adding one page to InvoiceWorkshop, a free browser-based
invoice and business-document generator.

## The page

{json.dumps(page, indent=2, sort_keys=True, default=str)}

## Why this page is allowed to exist

The family it belongs to passed an admission gate that required at least two
FUNCTIONAL differences in what the tool produces -- not wording, but computation,
fields, validation, structure or output. Those differences are listed above. The
product change that delivers them is: {page.get('product_change')}

Your job is to write the page around a difference that already exists. If, having
read the code, the difference does NOT already exist, return NO_ACTION and say so.
Do not write a page describing behaviour the tool does not have.

## How pages are built here

Page content lives in `src/content/generators.ts`. A country page is an entry
with `path`, `kind`, `locale`, `dynamic: true`, `title`, `description`, `h1`,
`eyebrow`, `intro`, `reassurance`, `sections[]` and `related[]`. The shared
`src/pages/[slug]/index.astro` route builds every entry with `dynamic: true`, so
no new route file is needed and the sitemap follows automatically. Read
`src/lib/documents/locales.ts` for the presets and copy the shape of an existing
country entry exactly.

## The standard

Everything factual on the page must be correct for that jurisdiction: the tax
label, the standard rate, what the registration number is called, and what the
tax authority requires on the face of the document. If you are not certain of a
figure, leave it out rather than guess -- a wrong rate on an invoice template is
worse than a missing one.

Every number in a worked example must reconcile. Tax is computed per line and
summed (see `src/lib/documents/money.ts`), so a worked example must add up the
same way the tool does.

Do not pad. A page that says the same thing as the other country pages with the
tax renamed is the failure mode this whole system exists to prevent.

## Constraints

You have Read, Edit, Grep and Glob. No shell, no build, no commit, no deploy: a
wrapper runs the gates afterwards and reverts everything if any of them fail.
Edit only `src/content/generators.ts`. At most {policy.MAX_DIFF_LINES} changed
lines.

Return the JSON result: `decision` CHANGED or NO_ACTION, a one-line `summary`, a
`rationale` naming the functional difference this page is built on, and
`files_changed`.
"""


def gather_evidence(connection, opportunity: dict) -> dict:
    url = opportunity.get("target_url")
    queries = [dict(row) for row in connection.execute(
        """SELECT query, impressions, clicks, position FROM gsc_query_facts
            WHERE page=? AND snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_query_facts)
            ORDER BY impressions DESC LIMIT 10""", (url,))]
    stats = connection.execute(
        """SELECT words, headings, internal_in, features_json FROM page_content_stats
            WHERE url=? ORDER BY measured_at DESC LIMIT 1""", (url,)).fetchone()
    diagnosis = connection.execute(
        """SELECT index_state, coverage_state, constraint_kind, recommended
             FROM index_diagnosis WHERE url=?
            ORDER BY diagnosed_at DESC LIMIT 1""", (url,)).fetchone()
    return {
        "search_queries_this_page_surfaces_for": queries,
        "measured_structure": dict(stats) if stats else None,
        "index_state": dict(diagnosis) if diagnosis else None,
        "note": ("word count is context only; it is not a target and closing the "
                 "gap must not be measured by it"),
    }


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------

def invoke_claude(prompt: str, *, model: str = MODEL, timeout: int = CLAUDE_TIMEOUT_SECONDS,
                  tools: str = "Read,Edit,Grep,Glob") -> dict:
    """Run Claude Code headlessly with the smallest tool set that can do the job."""
    command = [
        str(CLAUDE), "-p",
        "--output-format", "json",
        "--model", model,
        "--fallback-model", FALLBACK_MODEL,
        # No shell, no network, no git: file tools confined to the repository.
        "--restricted",
        "--tools", tools,
        "--permission-mode", "acceptEdits",
        "--add-dir", str(ROOT),
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--max-budget-usd", str(MAX_BUDGET_USD),
        "--json-schema", json.dumps(RESULT_SCHEMA),
    ]
    environment = os.environ.copy()
    environment.setdefault("HOME", str(Path.home()))
    # A scheduled run has no terminal and must never try to open one.
    environment["CI"] = "1"
    started = time.monotonic()
    try:
        # The prompt goes in on stdin rather than argv: a scheduled run's command
        # line is visible in the process table, and the prompt carries the
        # growth evidence for the page being changed.
        completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True,
                                   text=True, timeout=timeout, env=environment,
                                   input=prompt)
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout", "duration_ms": int((time.monotonic() - started) * 1000),
                "error": f"claude did not finish within {timeout}s"}

    duration = int((time.monotonic() - started) * 1000)
    raw = completed.stdout.strip()
    if completed.returncode != 0 and not raw:
        stderr = completed.stderr.strip()[:600]
        # Authentication and quota are ordinary operating states, not bugs: the
        # deterministic pipeline keeps running and the task stays queued.
        blocked = any(marker in stderr.lower() for marker in
                      ("not logged in", "authentication", "unauthorized", "credit balance",
                       "rate limit", "quota", "usage limit", "401", "403", "429"))
        return {"outcome": "blocked_auth" if blocked else "error",
                "duration_ms": duration, "error": stderr or f"exit {completed.returncode}"}
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return {"outcome": "error", "duration_ms": duration,
                "error": f"unparseable output: {raw[:400]}"}

    usage = {
        "cost_usd": envelope.get("total_cost_usd"),
        "num_turns": envelope.get("num_turns"),
        "duration_ms": envelope.get("duration_ms") or duration,
        "session_id": envelope.get("session_id"),
        "model": model,
    }
    if envelope.get("is_error"):
        status = str(envelope.get("api_error_status") or "")
        subtype = str(envelope.get("subtype") or "")
        blocked = status in {"401", "403", "429"} or "limit" in subtype
        return {"outcome": "blocked_auth" if blocked else "error", **usage,
                "error": f"{subtype or 'error'} {status}: {str(envelope.get('result'))[:300]}"}

    try:
        verdict = json.loads(envelope.get("result") or "{}")
    except json.JSONDecodeError:
        return {"outcome": "error", **usage,
                "error": f"result was not the requested JSON: {str(envelope.get('result'))[:300]}"}
    return {"outcome": "completed", "verdict": verdict, **usage}


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _run(command: list[str], *, timeout: int) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, check=False, capture_output=True,
                            text=True, timeout=timeout)
    tail = (result.stdout + result.stderr).strip().splitlines()[-25:]
    return result.returncode == 0, "\n".join(tail)


LOCAL_GATES = (
    ("build", ["npm", "run", "build"], 600),
    ("unit", ["npx", "vitest", "run"], 300),
    ("growth", ["/home/azureuser/growth-venv/bin/python", "-m", "unittest", "discover",
                "-s", "tests/growth", "-p", "test_*.py"], 900),
    # chromium plus the mobile project, which is where the overflow and
    # accessibility checks actually bite.
    ("e2e", ["npx", "playwright", "test", "--project=chromium", "--project=mobile-chrome"], 900),
)


def local_validation() -> dict:
    """Everything CI will check, checked here first so a failure never reaches main."""
    results = {}
    for name, command, timeout in LOCAL_GATES:
        ok, tail = _run(command, timeout=timeout)
        results[name] = {"passed": ok, "output": "" if ok else tail}
        if not ok:
            results["failed_at"] = name
            return results
    return results


def opportunities_canonical() -> tuple:
    import growth_opportunities
    return growth_opportunities.canonical_routes()


def verify_production(url: str) -> dict:
    """Confirm the deployed page is the page we meant to deploy."""
    checks: dict[str, object] = {}
    request = urllib.request.Request(url, headers={"User-Agent": "invoiceworkshop-growth"})
    with urllib.request.urlopen(request, timeout=30) as response:
        checks["status"] = response.status
        body = response.read().decode("utf-8", errors="ignore")
    checks["canonical_correct"] = f'rel="canonical" href="{url}"' in body
    checks["single_h1"] = len(re.findall(r"<h1", body, re.I)) == 1
    checks["has_title"] = bool(re.search(r"<title>[^<]+</title>", body, re.I))
    with urllib.request.urlopen(
        urllib.request.Request("https://invoiceworkshop.com/sitemap.xml",
                               headers={"User-Agent": "invoiceworkshop-growth"}), timeout=30
    ) as response:
        checks["sitemap_urls"] = len(re.findall(r"<loc>", response.read().decode("utf-8")))
    # The sitemap grows as the experiment adds pages, so the check is that it
    # did not SHRINK -- a page silently disappearing is the failure worth
    # catching, and a fixed count would have blocked every new page instead.
    expected = len(opportunities_canonical()) + 4  # tool pages plus about/privacy/terms/contact
    checks["sitemap_urls_expected_min"] = expected
    checks["passed"] = (checks["status"] == 200 and checks["canonical_correct"]
                        and checks["single_h1"] and checks["has_title"]
                        and int(checks["sitemap_urls"]) >= expected)
    return checks


def wait_for_ci(sha: str, timeout: int = CI_TIMEOUT_SECONDS) -> dict:
    """CI owns the deployment credentials, so its verdict is the deploy decision."""
    deadline = time.monotonic() + timeout
    run_id = None
    while time.monotonic() < deadline:
        listing = subprocess.run(
            ["gh", "run", "list", "--limit", "12", "--json",
             "databaseId,headSha,status,conclusion"],
            cwd=ROOT, check=False, capture_output=True, text=True, timeout=120)
        if listing.returncode == 0:
            for run in json.loads(listing.stdout or "[]"):
                if run.get("headSha") == sha:
                    run_id = str(run["databaseId"])
                    if run.get("status") == "completed":
                        return {"run_id": run_id, "conclusion": run.get("conclusion"),
                                "passed": run.get("conclusion") == "success"}
                    break
        time.sleep(20)
    return {"run_id": run_id, "conclusion": "timeout", "passed": False}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _revert_working_tree(paths: list[str]) -> None:
    for path in paths:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=ROOT,
                                 check=False, capture_output=True, text=True)
        if tracked.returncode == 0:
            _git("checkout", "--", path, check=False)
        else:
            target = ROOT / path
            if target.is_file():
                target.unlink()


RUN_COLUMNS = ("started_at", "finished_at", "run_type", "opportunity_key",
               "opportunity_id", "target_url", "model", "session_id", "outcome",
               "num_turns", "cost_usd", "duration_ms", "files_changed", "commit_sha",
               "ci_run_id", "deployed", "summary", "error")


def _record(connection, run: dict) -> dict:
    """Write the run to the ledger and stamp its row id onto the result."""
    values = {"finished_at": utc_now(), "opportunity_key": None, "opportunity_id": None,
              "target_url": None, "model": "", "session_id": None, "num_turns": None,
              "cost_usd": None, "duration_ms": None, "files_changed": "", "commit_sha": None,
              "ci_run_id": None, "deployed": 0, "summary": "", "error": None}
    values.update({name: run[name] for name in RUN_COLUMNS if name in run})
    cursor = connection.execute(
        f"""INSERT INTO claude_runs ({", ".join(RUN_COLUMNS)})
            VALUES ({", ".join(f":{name}" for name in RUN_COLUMNS)})""",
        values,
    )
    connection.commit()
    run["claude_run_id"] = int(cursor.lastrowid)
    return run


def _mark_attempt(connection, opportunity: dict, outcome: str) -> None:
    """Surface pages live in page_candidates, not growth_opportunities; the
    UPDATE simply matches nothing for them, which is the intended no-op."""
    connection.execute(
        """UPDATE growth_opportunities
              SET attempt_count=attempt_count+1, last_attempted_at=?,
                  last_attempt_outcome=?, updated_at=?
            WHERE opportunity_key=?""",
        (utc_now(), outcome, utc_now(), opportunity["opportunity_key"]),
    )
    connection.commit()


def execute(connection, opportunity: dict, *, fixture: bool = False,
            surface_page: dict | None = None) -> dict:
    started = utc_now()
    base = {"started_at": started, "run_type": "fixture" if fixture else "auto_opportunity",
            "opportunity_key": opportunity.get("opportunity_key"),
            "opportunity_id": opportunity.get("id"),
            "target_url": opportunity.get("target_url")}

    dirty = _dirty_paths()
    if dirty:
        run = {**base, "outcome": "refused",
               "error": f"working tree is not clean: {', '.join(dirty[:6])}"}
        _record(connection, run)
        return run

    before_sha = _git("rev-parse", "HEAD")
    if surface_page:
        prompt = build_surface_prompt(surface_page)
    else:
        prompt = build_prompt(opportunity, gather_evidence(connection, opportunity))
    if fixture:
        prompt = (prompt + "\n\n## FIXTURE RUN\n\nThis is a rehearsal of the unattended "
                  "path. Do not edit any file. Return NO_ACTION with a rationale that "
                  "states you were asked not to act.")

    result = invoke_claude(prompt)
    usage = {"model": result.get("model", MODEL), "session_id": result.get("session_id"),
             "num_turns": result.get("num_turns"), "cost_usd": result.get("cost_usd"),
             "duration_ms": result.get("duration_ms")}

    if result["outcome"] != "completed":
        run = {**base, **usage, "outcome": result["outcome"], "error": result.get("error")}
        _record(connection, run)
        if result["outcome"] == "blocked_auth":
            record_escalation(
                connection, kind="claude_unavailable", severity="warning",
                subject="Unattended Claude runs are blocked",
                detail=("Authentication or quota is unavailable. The deterministic growth "
                        "system continues; tasks needing reasoning stay queued. "
                        f"Detail: {str(result.get('error'))[:300]}"),
                fingerprint="claude_unavailable")
        return run

    verdict = result["verdict"]
    changed = _dirty_paths()

    if verdict.get("decision") == "NO_ACTION" or not changed:
        if changed:
            _revert_working_tree(changed)
        run = {**base, **usage, "outcome": "no_action",
               "summary": verdict.get("summary", "")[:500],
               "error": None}
        _record(connection, run)
        if not fixture:
            # A declined opportunity is a judgement worth keeping: it stops the
            # same non-gap being re-proposed every night.
            connection.execute(
                """UPDATE growth_opportunities
                      SET state='dismissed', dismissed_reason=?, updated_at=?
                    WHERE opportunity_key=?""",
                (f"declined by unattended review: {verdict.get('rationale','')[:300]}",
                 utc_now(), opportunity["opportunity_key"]))
            connection.commit()
        return run

    if fixture:
        _revert_working_tree(changed)
        run = {**base, **usage, "outcome": "refused",
               "error": "fixture run edited files; reverted"}
        _record(connection, run)
        return run

    # --- the change exists; now everything the model may not do ---------------
    try:
        checks = policy.validate_change(changed, policy.working_diff(changed))
    except policy.PolicyRefusal as refusal:
        _revert_working_tree(changed)
        run = {**base, **usage, "outcome": "refused", "files_changed": ",".join(changed),
               "summary": verdict.get("summary", "")[:500], "error": str(refusal)}
        _record(connection, run)
        _mark_attempt(connection, opportunity, "refused")
        record_escalation(connection, kind="auto_policy_refusal", severity="warning",
                          subject=f"AUTO change refused: {opportunity['opportunity_key']}",
                          detail=str(refusal), fingerprint=f"refusal:{opportunity['opportunity_key']}")
        return run

    validation = local_validation()
    if validation.get("failed_at"):
        _revert_working_tree(changed)
        run = {**base, **usage, "outcome": "validation_failed",
               "files_changed": ",".join(changed),
               "summary": verdict.get("summary", "")[:500],
               "error": f"{validation['failed_at']}: "
                        f"{validation[validation['failed_at']]['output'][:600]}"}
        _record(connection, run)
        _mark_attempt(connection, opportunity, "validation_failed")
        return run

    message = (f"{verdict.get('summary', 'Close a measured user-value gap')}\n\n"
               f"{verdict.get('rationale', '')}\n\n"
               f"Opportunity: {opportunity['opportunity_key']}\n"
               f"Evidence: {opportunity.get('evidence', '')[:400]}\n\n"
               "Made by the unattended growth worker inside the AUTO policy: diff scope\n"
               "validated, build, unit, growth and browser suites passed locally before\n"
               "this was committed.\n\n"
               "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>")
    _git("add", "--", *changed)
    _git("commit", "-q", "-m", message)
    sha = _git("rev-parse", "HEAD")
    push = subprocess.run(["git", "push"], cwd=ROOT, check=False,
                          capture_output=True, text=True, timeout=180)
    if push.returncode != 0:
        _git("reset", "--hard", before_sha, check=False)
        run = {**base, **usage, "outcome": "deploy_failed", "commit_sha": sha,
               "files_changed": ",".join(changed),
               "error": f"push failed: {push.stderr.strip()[:400]}"}
        _record(connection, run)
        _mark_attempt(connection, opportunity, "deploy_failed")
        return run

    ci = wait_for_ci(sha)
    if not ci["passed"]:
        # Deployment needs CI to pass, so nothing reached users. Take the commit
        # back off main so the next run starts from a known-good tree.
        _git("revert", "--no-edit", sha, check=False)
        subprocess.run(["git", "push"], cwd=ROOT, check=False, capture_output=True,
                       text=True, timeout=180)
        run = {**base, **usage, "outcome": "deploy_failed", "commit_sha": sha,
               "ci_run_id": ci.get("run_id"), "files_changed": ",".join(changed),
               "error": f"CI concluded {ci.get('conclusion')}; reverted, nothing deployed"}
        _record(connection, run)
        _mark_attempt(connection, opportunity, "deploy_failed")
        record_escalation(connection, kind="ci_failure", severity="warning",
                          subject="Unattended change failed CI and was reverted",
                          detail=f"commit {sha[:8]}, run {ci.get('run_id')}",
                          fingerprint=f"ci_failure:{sha}")
        return run

    time.sleep(20)  # give the edge a moment to serve the new version
    production = verify_production(opportunity["target_url"])
    if not production["passed"]:
        _git("revert", "--no-edit", sha, check=False)
        subprocess.run(["git", "push"], cwd=ROOT, check=False, capture_output=True,
                       text=True, timeout=180)
        run = {**base, **usage, "outcome": "rolled_back", "commit_sha": sha,
               "ci_run_id": ci.get("run_id"), "files_changed": ",".join(changed),
               "error": f"production verification failed: {json.dumps(production)}"}
        _record(connection, run)
        _mark_attempt(connection, opportunity, "rolled_back")
        record_escalation(connection, kind="production_verification", severity="critical",
                          subject="Deployed change failed production verification",
                          detail=f"commit {sha[:8]} reverted: {json.dumps(production)}",
                          fingerprint=f"prod_verify:{sha}")
        return run

    # Only now is it true that the change reached users.
    import growth_opportunities as opportunities
    baseline = connection.execute(
        """SELECT COALESCE(SUM(impressions),0) i, COALESCE(SUM(clicks),0) k, AVG(position) p
             FROM gsc_query_facts WHERE page=?
              AND snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_query_facts)""",
        (opportunity["target_url"],)).fetchone()
    opportunities.record_experiment(
        connection, opportunity_key=opportunity["opportunity_key"],
        hypothesis=verdict.get("rationale", "")[:900],
        action=verdict.get("summary", "")[:900],
        action_type="page_improvement", target_url=opportunity["target_url"],
        target_query=opportunity.get("target_query"),
        baseline={"impressions": int(baseline["i"]), "clicks": int(baseline["k"]),
                  "position": baseline["p"], "commit": sha[:12]},
        expected=verdict.get("user_value", "")[:500] or "unstated", days=45)
    if surface_page:
        connection.execute(
            """UPDATE page_candidates SET status='shipped', shipped_at=?, commit_sha=?,
                   updated_at=? WHERE slug=?""",
            (utc_now(), sha, utc_now(), surface_page["slug"]))
        connection.execute(
            "UPDATE page_families SET status='built', updated_at=? WHERE family_key=?",
            (utc_now(), surface_page["slug"]))
    else:
        connection.execute(
            """UPDATE growth_opportunities SET state='done', updated_at=?
                WHERE opportunity_key=?""",
            (utc_now(), opportunity["opportunity_key"]))
    connection.commit()
    _mark_attempt(connection, opportunity, "changed")

    run = {**base, **usage, "outcome": "changed", "commit_sha": sha,
           "ci_run_id": ci.get("run_id"), "deployed": 1,
           "files_changed": ",".join(changed),
           "summary": verdict.get("summary", "")[:500]}
    _record(connection, run)
    return run


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


FIXTURE_OPPORTUNITY = {
    "opportunity_key": "fixture:worker-selftest",
    "opportunity_type": "SEO_PAGE_IMPROVEMENT",
    "title": "Fixture: exercise the unattended path without touching the site",
    "target_url": "https://invoiceworkshop.com/",
    "evidence": "Fixture run. There is no real gap and no change is wanted.",
    "priority_band": 1, "expected_growth_value": 0.0,
}


DECISION_CODES = {"no_action", "claude_invoked", "deterministic_only",
                  "budget_exhausted", "locked", "blocked", "error"}


def _record_run(connection, started: str, summary: dict, claude_run_id: int | None = None) -> None:
    """One row per unattended run, whatever it decided.

    The table exists so that "nothing happened last week" and "the scheduler
    stopped last week" cannot look the same from the outside.
    """
    decision = summary.get("decision")
    connection.execute(
        """INSERT INTO autonomous_runs
             (started_at, finished_at, trigger, decision, reason, claude_run_id, steps_json)
           VALUES (?, ?, 'scheduler', ?, ?, ?, ?)""",
        (started, utc_now(),
         decision if decision in DECISION_CODES else "no_action",
         str(summary.get("reason", ""))[:800], claude_run_id,
         json.dumps(summary, sort_keys=True, default=str)),
    )
    connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("select", help="Report what would run today, and run nothing")
    commands.add_parser("policy", help="Print the AUTO change envelope")
    run = commands.add_parser("run", help="Execute at most one bounded AUTO task")
    run.add_argument("--opportunity-id", type=int)
    run.add_argument("--fixture", action="store_true",
                     help="Exercise the whole path against a fixture; changes nothing")
    run.add_argument("--override-budget", action="store_true",
                     help="Run a named opportunity even though today's budget is used. "
                          "Only a person directing a run may pass this; the scheduled "
                          "path never does, so unattended runs cannot exceed the cap.")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)

    if args.command == "policy":
        print(policy.policy_document())
        return
    if args.command == "select":
        print(json.dumps(policy.select_candidate(connection), indent=2,
                         sort_keys=True, default=str))
        return

    started = utc_now()
    handle = _lock()
    if handle is None:
        summary = {"decision": "locked",
                   "reason": "another executor run already holds the lock"}
        _record_run(connection, started, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    try:
        if args.fixture:
            result = execute(connection, FIXTURE_OPPORTUNITY, fixture=True)
        elif args.opportunity_id:
            row = connection.execute("SELECT * FROM growth_opportunities WHERE id=?",
                                     (args.opportunity_id,)).fetchone()
            if row is None:
                raise SystemExit(f"no opportunity {args.opportunity_id}")
            opportunity = dict(row)
            blocked = policy.disqualify(connection, opportunity)
            if not blocked and not args.override_budget and policy.runs_today(connection) >= policy.MAX_RUNS_PER_DAY:
                blocked = ("today's unattended run budget is used; pass --override-budget "
                           "to direct a run anyway")
            if blocked:
                summary = {"decision": "no_action", "reason": blocked, "claude_invoked": False}
                _record_run(connection, started, summary)
                print(json.dumps(summary, indent=2, sort_keys=True))
                return
            result = execute(connection, opportunity)
        else:
            candidate = policy.select_candidate(connection)
            if not candidate["eligible"]:
                # The common case, and the cheap one: nothing was worth a run,
                # no model was called, and the fact is still recorded so a quiet
                # week is distinguishable from a scheduler that stopped.
                summary = {"decision": candidate.get("code", "no_action"),
                           "reason": candidate["reason"],
                           "considered": candidate.get("considered", []),
                           "claude_invoked": False}
                _record_run(connection, started, summary)
                print(json.dumps(summary, indent=2, sort_keys=True))
                return
            result = execute(connection, candidate["opportunity"],
                             surface_page=candidate.get("surface_page"))
        _record_run(connection, started,
                    {"decision": "claude_invoked", "reason": result["outcome"],
                     "claude_invoked": True, "outcome": result["outcome"]},
                    claude_run_id=result.get("claude_run_id"))
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        if result["outcome"] in ("error", "timeout"):
            sys.exit(1)
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


if __name__ == "__main__":
    main()
