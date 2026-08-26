#!/usr/bin/env python3
"""Run bounded public research, then validate and persist it deterministically."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from growth_common import ROOT, apply_schema, canonical_domain, connect_db, normalize_public_url, utc_now
from growth_research import DEFAULT_BATCH_DIR, finish_research, import_batch, start_research

HERMES = "/home/azureuser/.local/bin/hermes"
HERMES_STATE = Path("/home/azureuser/.hermes/state.db")
HERMES_JOBS = Path("/home/azureuser/.hermes/cron/jobs.json")
JOB_NAME = "invoiceworkshop-level0-research"
PROMPT_PATH = ROOT / "docs" / "growth-jobs" / "invoiceworkshop-level0-research.txt"
MODEL = os.environ.get("GROWTH_RESEARCH_MODEL", "openai/gpt-5-mini")
PROVIDER = os.environ.get("GROWTH_RESEARCH_PROVIDER", "openrouter")
TOKEN_BUDGET = int(os.environ.get("GROWTH_RESEARCH_TOKEN_BUDGET", "50000"))
TOOL_BUDGET = int(os.environ.get("GROWTH_RESEARCH_TOOL_BUDGET", "10"))
MAX_TURNS = int(os.environ.get("GROWTH_RESEARCH_MAX_TURNS", "5"))
WALL_BUDGET_SECONDS = int(os.environ.get("GROWTH_RESEARCH_WALL_BUDGET_SECONDS", "180"))
MAX_PROSPECTS = 10
COMPETITOR_DOMAINS = {
    "abill.io", "bill.com", "freshbooks.com", "invoiceninja.com", "invoicey.io",
    "paypal.com", "quickbooks.intuit.com", "stripe.com", "waveapps.com", "xero.com",
    "zoho.com",
}


def resolve_job_id() -> str:
    registry = json.loads(HERMES_JOBS.read_text(encoding="utf-8"))
    matches = [str(row["id"]) for row in registry.get("jobs", []) if row.get("name") == JOB_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {JOB_NAME} job, found {len(matches)}")
    return matches[0]


def _extract_payload(response: str) -> dict:
    match = re.search(
        r"RESEARCH_BATCH_JSON_START\s*(\{.*?\})\s*RESEARCH_BATCH_JSON_END",
        response,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("model response did not contain the required JSON envelope")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict) or not isinstance(payload.get("prospects"), list):
        raise ValueError("model response payload has an invalid shape")
    examined = payload.get("candidates_examined")
    if isinstance(examined, bool) or not isinstance(examined, int) or not 0 <= examined <= 15:
        raise ValueError("candidates_examined must be an integer from 0 to 15")
    return payload


def _validated_batch(payload: dict) -> tuple[list[dict], int]:
    retained: list[dict] = []
    rejected = 0
    seen: set[tuple[str, str]] = set()
    for raw in payload["prospects"][:MAX_PROSPECTS]:
        try:
            if not isinstance(raw, dict) or raw.get("direct_competitor") is not False:
                raise ValueError("direct competitor or invalid object")
            page_url = normalize_public_url(str(raw.get("page_url", "")))
            source_url = normalize_public_url(str(raw.get("source_url", "")))
            contact_url = normalize_public_url(str(raw.get("contact_method", "")))
            domain = canonical_domain(page_url)
            if domain in COMPETITOR_DOMAINS or any(
                domain.endswith("." + blocked) for blocked in COMPETITOR_DOMAINS
            ):
                raise ValueError("known direct competitor")
            score = raw.get("opportunity_score")
            if isinstance(score, bool) or not isinstance(score, int) or score < 65:
                raise ValueError("qualification score below 65")
            if raw.get("requires_payment") is not False:
                raise ValueError("paid opportunity")
            key = (domain, page_url)
            if key in seen:
                raise ValueError("duplicate in model batch")
            seen.add(key)
            normalized = dict(raw)
            normalized.pop("direct_competitor", None)
            normalized["page_url"] = page_url
            normalized["source_url"] = source_url
            normalized["contact_method"] = contact_url
            retained.append(normalized)
        except (TypeError, ValueError):
            rejected += 1
    return retained, rejected


def _session_usage(usage: dict) -> dict:
    session_id = str(usage.get("session_id") or "").strip()
    if not session_id or not HERMES_STATE.is_file():
        return {}
    connection = sqlite3.connect(f"file:{HERMES_STATE.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT id, model, started_at, ended_at, end_reason, tool_call_count,
                  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                  reasoning_tokens, api_call_count
             FROM sessions WHERE id=?""",
        (session_id,),
    ).fetchone()
    connection.close()
    return dict(row) if row else {}


def _record_usage(job_id: str, run_id: int, usage: dict, session: dict, result: dict,
                  started_at: str, finished_at: str, duration_ms: int, errors: list[str]) -> None:
    session_id = str(usage.get("session_id") or session.get("id") or f"research-run-{run_id}")
    input_tokens = int(usage.get("input_tokens") or session.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or session.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_tokens") or session.get("cache_read_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or session.get("cache_write_tokens") or 0)
    total = int(usage.get("total_tokens") or (input_tokens + output_tokens + cache_read + cache_write))
    values = (
        session_id, job_id, "research", started_at, finished_at, result["status"],
        usage.get("model") or session.get("model") or MODEL, input_tokens, output_tokens,
        cache_read, cache_write, int(usage.get("reasoning_tokens") or session.get("reasoning_tokens") or 0),
        total, int(usage.get("api_calls") or session.get("api_call_count") or 0),
        int(session.get("tool_call_count") or 0), duration_ms,
        int(result.get("candidates_examined") or 0), int(result.get("prospects_retained") or 0),
        int(result.get("duplicates_rejected") or 0), json.dumps(errors), utc_now(),
    )
    connection = connect_db()
    apply_schema(connection)
    connection.execute(
        """INSERT INTO agent_executions
           (session_id, hermes_job_id, job_name, started_at, finished_at, status,
            model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
            reasoning_tokens, total_tokens, api_calls, tool_calls,
            execution_duration_ms, candidates_examined, prospects_retained,
            duplicates_rejected, errors_json, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
             status=excluded.status, model=excluded.model, input_tokens=excluded.input_tokens,
             output_tokens=excluded.output_tokens, cache_read_tokens=excluded.cache_read_tokens,
             cache_write_tokens=excluded.cache_write_tokens, reasoning_tokens=excluded.reasoning_tokens,
             total_tokens=excluded.total_tokens, api_calls=excluded.api_calls,
             tool_calls=excluded.tool_calls, execution_duration_ms=excluded.execution_duration_ms,
             candidates_examined=excluded.candidates_examined,
             prospects_retained=excluded.prospects_retained,
             duplicates_rejected=excluded.duplicates_rejected,
             errors_json=excluded.errors_json, synced_at=excluded.synced_at""",
        values,
    )
    connection.commit()
    connection.close()


def _set_operation_state(success: bool, error: str | None) -> tuple[int, bool]:
    connection = connect_db()
    apply_schema(connection)
    row = connection.execute(
        "SELECT failure_streak FROM operation_state WHERE operation='prospect_research'"
    ).fetchone()
    previous = int(row[0]) if row else 0
    streak = 0 if success else previous + 1
    state = "paused" if streak >= 3 else "active"
    connection.execute(
        """INSERT INTO operation_state (operation, state, failure_streak, last_error, updated_at)
           VALUES ('prospect_research', ?, ?, ?, ?)
           ON CONFLICT(operation) DO UPDATE SET state=excluded.state,
             failure_streak=excluded.failure_streak, last_error=excluded.last_error,
             updated_at=excluded.updated_at""",
        (state, streak, error, utc_now()),
    )
    connection.commit()
    connection.close()
    return streak, state == "paused"


def run() -> dict:
    if not 5_000 <= TOKEN_BUDGET <= 200_000 or not 3 <= TOOL_BUDGET <= 25:
        raise RuntimeError("invalid research budget configuration")
    job_id = resolve_job_id()
    context = start_research(None, job_id, TOKEN_BUDGET, TOOL_BUDGET)
    run_id = int(context["research_run_id"])
    started_at = utc_now()
    started = time.monotonic()
    errors: list[str] = []
    usage: dict = {}
    payload = {"candidates_examined": 0, "prospects": []}
    response = ""
    with tempfile.TemporaryDirectory(prefix="invoiceworkshop-research-") as temp_name:
        temp = Path(temp_name)
        usage_path = temp / "usage.json"
        prompt = PROMPT_PATH.read_text(encoding="utf-8") + "\n\nRUNTIME_CONTEXT_JSON\n" + json.dumps(
            context, separators=(",", ":"), sort_keys=True
        )
        env = os.environ.copy()
        env["HERMES_MAX_ITERATIONS"] = str(MAX_TURNS)
        env["HERMES_IGNORE_USER_CONFIG"] = "1"
        env["HERMES_IGNORE_RULES"] = "1"
        command = [
            HERMES, "-z", prompt, "--usage-file", str(usage_path), "--model", MODEL,
            "--provider", PROVIDER, "--reasoning", "low", "--toolsets", "web,no_mcp",
            "--ignore-user-config", "--ignore-rules", "--in", str(ROOT),
        ]
        try:
            completed = subprocess.run(
                command, cwd=ROOT, env=env, text=True, capture_output=True,
                timeout=WALL_BUDGET_SECONDS, check=False,
            )
            response = completed.stdout
            if usage_path.is_file():
                usage = json.loads(usage_path.read_text(encoding="utf-8"))
            if completed.returncode != 0:
                errors.append(f"bounded research agent exited {completed.returncode}")
            else:
                payload = _extract_payload(response)
        except subprocess.TimeoutExpired:
            errors.append(f"wall-clock budget reached at {WALL_BUDGET_SECONDS} seconds")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))

    session = _session_usage(usage)
    tool_calls = int(session.get("tool_call_count") or 0)
    total_tokens = int(usage.get("total_tokens") or (
        int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
        + int(usage.get("cache_read_tokens") or 0) + int(usage.get("cache_write_tokens") or 0)
    ))
    budget_stopped = total_tokens > TOKEN_BUDGET or tool_calls > TOOL_BUDGET
    if total_tokens > TOKEN_BUDGET:
        errors.append(f"token budget exceeded: {total_tokens}>{TOKEN_BUDGET}")
    if tool_calls > TOOL_BUDGET:
        errors.append(f"tool budget exceeded: {tool_calls}>{TOOL_BUDGET}")

    retained_count = 0
    duplicates = 0
    validation_rejected = 0
    if not errors or budget_stopped:
        try:
            batch, validation_rejected = _validated_batch(payload)
            DEFAULT_BATCH_DIR.mkdir(parents=True, exist_ok=True)
            batch_path = DEFAULT_BATCH_DIR / f"run-{run_id}.json"
            batch_path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
            imported = import_batch(None, run_id, str(batch_path), DEFAULT_BATCH_DIR)
            retained_count = int(imported["prospects_retained"])
            duplicates = int(imported["duplicates_rejected"])
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"deterministic batch validation/import failed: {error}")

    requested_status = "budget_stopped" if budget_stopped else ("failure" if errors else "success")
    result = finish_research(
        None, run_id, requested_status, int(payload.get("candidates_examined") or 0),
        tool_calls, errors,
    )
    finished_at = utc_now()
    duration_ms = round((time.monotonic() - started) * 1000)
    result["model"] = usage.get("model") or session.get("model") or MODEL
    result["input_tokens"] = int(usage.get("input_tokens") or session.get("input_tokens") or 0)
    result["output_tokens"] = int(usage.get("output_tokens") or session.get("output_tokens") or 0)
    result["total_tokens"] = total_tokens
    result["tool_calls"] = tool_calls
    result["validation_rejected"] = validation_rejected
    result["duration_ms"] = duration_ms
    result["external_side_effects"] = "none"
    _record_usage(job_id, run_id, usage, session, result, started_at, finished_at, duration_ms, errors)
    streak, pause_required = _set_operation_state(result["status"] in {"success", "budget_stopped"}, errors[0] if errors else None)
    result["failure_streak"] = streak
    result["pause_required"] = pause_required
    if pause_required:
        subprocess.run([HERMES, "cron", "pause", job_id], cwd=ROOT, timeout=30, check=False,
                       text=True, capture_output=True)
    return result


def main() -> None:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "failure":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
