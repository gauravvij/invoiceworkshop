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
from urllib.parse import urlsplit

from growth_common import ROOT, apply_schema, canonical_domain, connect_db, normalize_public_url, utc_now
from growth_research import DEFAULT_BATCH_DIR, finish_research, import_batch, start_research
from growth_research_discovery import discover, prepare_shortlist, scheduled_channels
from growth_research_policy import QUALIFIED_TARGET_MIN, SHORTLIST_MIN

HERMES = "/home/azureuser/.local/bin/hermes"
HERMES_STATE = Path("/home/azureuser/.hermes/state.db")
HERMES_JOBS = Path("/home/azureuser/.hermes/cron/jobs.json")
JOB_NAME = "invoiceworkshop-level0-research"
PROMPT_PATH = ROOT / "docs" / "growth-jobs" / "invoiceworkshop-level0-research.txt"
MODEL = os.environ.get("GROWTH_RESEARCH_MODEL", "openai/gpt-5.6-luna")
PROVIDER = os.environ.get("GROWTH_RESEARCH_PROVIDER", "openrouter")
REASONING = os.environ.get("GROWTH_RESEARCH_REASONING", "none")
TOOLSETS = os.environ.get("GROWTH_RESEARCH_TOOLSETS", "clarify")
TOKEN_BUDGET = int(os.environ.get("GROWTH_RESEARCH_TOKEN_BUDGET", "60000"))
TOOL_BUDGET = int(os.environ.get("GROWTH_RESEARCH_TOOL_BUDGET", "10"))
MAX_TURNS = int(os.environ.get("GROWTH_RESEARCH_MAX_TURNS", "6"))
WALL_BUDGET_SECONDS = int(os.environ.get("GROWTH_RESEARCH_WALL_BUDGET_SECONDS", "180"))
MAX_PROSPECTS = 10
COMPETITOR_DOMAINS = {
    "abill.io", "bill.com", "freshbooks.com", "invoiceninja.com", "invoicey.io",
    "paypal.com", "paymoapp.com", "quickbooks.intuit.com", "stripe.com",
    "waveapps.com", "xero.com", "zoho.com", "buildern.com", "flowlu.com",
    "joist.com", "support.construction", "tallysolutions.com",
}
PROSPECT_TYPES = {"resource", "editorial", "directory", "community", "discovery", "broken", "gap", "other"}
CONTACT_ROUTE = re.compile(r"(?:contact|write[-_/ ]?for[-_/ ]?us|contribut|editorial|submit|advertis|guest|pitch)", re.I)


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


def _validated_batch(
    payload: dict, allowed_candidates: list[dict] | None = None
) -> tuple[list[dict], int]:
    retained: list[dict] = []
    rejected = 0
    seen: set[tuple[str, str]] = set()
    allowed = {
        (item["page_url"], item["contact_url"]): item
        for item in (allowed_candidates or [])
    }
    for raw in payload["prospects"][:MAX_PROSPECTS]:
        try:
            supplied = None
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
            if raw.get("prospect_type") not in PROSPECT_TYPES:
                raise ValueError("invalid prospect type")
            score = raw.get("opportunity_score")
            if isinstance(score, bool) or not isinstance(score, int) or score < 65:
                raise ValueError("qualification score below 65")
            if raw.get("risk") not in {"low", "medium"}:
                raise ValueError("unacceptable risk")
            if not isinstance(raw.get("requires_account"), bool):
                raise ValueError("requires_account is not boolean")
            if raw.get("requires_payment") is not False:
                raise ValueError("paid opportunity")
            if allowed_candidates is not None:
                supplied = allowed.get((page_url, contact_url))
                if supplied is None:
                    raise ValueError("candidate or contact route was not in deterministic shortlist")
                if raw.get("channel") != supplied["channel"]:
                    raise ValueError("candidate channel differs from deterministic shortlist")
            if len(str(raw.get("why_fit", "")).strip()) < 20 or len(
                str(raw.get("audience", "")).strip()
            ) < 20:
                raise ValueError("insufficient factual evidence")
            if len(str(raw.get("page_evidence", "")).strip()) < 40:
                raise ValueError("page evidence is not specific enough")
            if raw.get("confidence") not in {"high", "medium"}:
                raise ValueError("qualification confidence is too low")
            if raw.get("second_pass_pass") is not True or len(
                str(raw.get("second_pass_reason", "")).strip()
            ) < 30:
                raise ValueError("second-pass quality review did not pass")
            target_url = normalize_public_url(str(raw.get("target_url", "")))
            if not target_url.startswith("https://invoiceworkshop.com/"):
                raise ValueError("invalid target URL")
            if len(str(raw.get("proposed_action", "")).strip()) < 15:
                raise ValueError("proposed action is missing")
            page_path = urlsplit(page_url).path.rstrip("/")
            source_path = urlsplit(source_url).path.rstrip("/")
            contact_path = urlsplit(contact_url).path.rstrip("/")
            if not page_path or not source_path:
                raise ValueError("homepage is not qualification evidence")
            route_verified = bool(supplied and supplied.get("contact_route_verified"))
            if (not contact_path or not CONTACT_ROUTE.search(contact_path)) and not route_verified:
                raise ValueError("contact URL is not an explicit editorial/contact route")
            contact_domain = canonical_domain(contact_url)
            source_domain = canonical_domain(source_url)
            if not (
                domain == contact_domain
                or domain.endswith("." + contact_domain)
                or contact_domain.endswith("." + domain)
            ):
                raise ValueError("contact route is not on the candidate site")
            if not (
                domain == source_domain
                or domain.endswith("." + source_domain)
                or source_domain.endswith("." + domain)
            ):
                raise ValueError("source evidence is not on the candidate site")
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


def _quality_target_incomplete(candidates_examined: int, retained: int) -> bool:
    return candidates_examined < SHORTLIST_MIN or retained < QUALIFIED_TARGET_MIN


def _mark_unqualified(shortlist: list[dict], retained: list[dict]) -> None:
    retained_urls = {item["page_url"] for item in retained}
    connection = connect_db()
    apply_schema(connection)
    for item in shortlist:
        if item["page_url"] in retained_urls:
            continue
        connection.execute(
            """UPDATE research_candidates SET state='rejected',
                      rejection_reason='LLM second-pass qualification did not retain candidate',
                      updated_at=? WHERE id=? AND state='shortlisted'""",
            (utc_now(), item["candidate_id"]),
        )
    connection.commit()
    connection.close()


def _release_shortlist(shortlist: list[dict], reason: str) -> None:
    """Return an unprocessed deterministic shortlist to the queue after agent failure."""
    connection = connect_db()
    apply_schema(connection)
    for item in shortlist:
        connection.execute(
            """UPDATE research_candidates SET state='queued', rejection_reason=?, updated_at=?
                      WHERE id=? AND state='shortlisted'""",
            (f"qualification deferred: {reason}"[:1000], utc_now(), item["candidate_id"]),
        )
    connection.commit()
    connection.close()


def _session_usage(usage: dict, run_id: int) -> dict:
    session_id = str(usage.get("session_id") or "").strip()
    if not HERMES_STATE.is_file():
        return {}
    connection = sqlite3.connect(f"file:{HERMES_STATE.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    columns = """s.id, s.model, s.started_at, s.ended_at, s.end_reason,
                 s.tool_call_count, s.input_tokens, s.output_tokens,
                 s.cache_read_tokens, s.cache_write_tokens,
                 s.reasoning_tokens, s.api_call_count"""
    if session_id:
        row = connection.execute(
            f"SELECT {columns} FROM sessions s WHERE s.id=?", (session_id,)
        ).fetchone()
    else:
        # A hard wall-time kill occurs before --usage-file is finalized. The
        # unique run ID in the user prompt lets us recover exact session usage
        # without guessing from timestamps or another concurrent CLI session.
        marker = f'%"research_run_id":{run_id}%'
        row = connection.execute(
            f"""SELECT {columns}
                  FROM sessions s JOIN messages m ON m.session_id=s.id
                 WHERE m.role='user' AND m.content LIKE ?
                 ORDER BY s.started_at DESC LIMIT 1""",
            (marker,),
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
    connection = None
    try:
        connection = connect_db()
        apply_schema(connection)
        channels = scheduled_channels(connection, run_id)
        discovery = discover(connection, channels, searches_per_channel=1)
        prepared = prepare_shortlist(connection, SHORTLIST_MIN)
        connection.close()
        connection = None
    except Exception as error:
        if connection is not None:
            connection.close()
        errors.append(f"deterministic research preparation failed: {type(error).__name__}: {error}")
        result = finish_research(None, run_id, "failure", 0, 0, errors)
        finished_at = utc_now()
        duration_ms = round((time.monotonic() - started) * 1000)
        result.update({
            "model": "none", "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "tool_calls": 0, "validation_rejected": 0,
            "duration_ms": duration_ms, "external_side_effects": "none",
        })
        _record_usage(job_id, run_id, {}, {}, result, started_at, finished_at, duration_ms, errors)
        streak, pause_required = _set_operation_state(False, errors[0])
        result["failure_streak"] = streak
        result["pause_required"] = pause_required
        if pause_required:
            subprocess.run([HERMES, "cron", "pause", job_id], cwd=ROOT, timeout=30,
                           check=False, text=True, capture_output=True)
        return result
    shortlist = prepared["shortlist"]
    context["discovery"] = discovery
    context["candidate_shortlist"] = shortlist
    if not shortlist:
        errors.append("deterministic candidate pool produced no evidence-complete shortlist")
        result = finish_research(None, run_id, "budget_stopped", 0, 0, errors)
        finished_at = utc_now()
        duration_ms = round((time.monotonic() - started) * 1000)
        result.update({
            "model": "none", "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "tool_calls": 0, "validation_rejected": 0,
            "duration_ms": duration_ms, "external_side_effects": "none",
        })
        _record_usage(job_id, run_id, {}, {}, result, started_at, finished_at, duration_ms, errors)
        streak, pause_required = _set_operation_state(True, errors[0])
        result["failure_streak"] = streak
        result["pause_required"] = pause_required
        return result
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
            "--provider", PROVIDER, "--reasoning", REASONING, "--toolsets", TOOLSETS,
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
                detail = " ".join(completed.stderr.strip().split())[-600:]
                errors.append(
                    f"bounded research agent exited {completed.returncode}"
                    + (f": {detail}" if detail else "")
                )
            else:
                payload = _extract_payload(response)
        except subprocess.TimeoutExpired:
            errors.append(f"wall-clock budget reached at {WALL_BUDGET_SECONDS} seconds")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))

    session = _session_usage(usage, run_id)
    tool_calls = int(session.get("tool_call_count") or 0)
    total_tokens = int(usage.get("total_tokens") or (
        int(usage.get("input_tokens") or session.get("input_tokens") or 0)
        + int(usage.get("output_tokens") or session.get("output_tokens") or 0)
        + int(usage.get("cache_read_tokens") or session.get("cache_read_tokens") or 0)
        + int(usage.get("cache_write_tokens") or session.get("cache_write_tokens") or 0)
    ))
    budget_stopped = total_tokens > TOKEN_BUDGET or tool_calls > TOOL_BUDGET
    if total_tokens > TOKEN_BUDGET:
        errors.append(f"token budget exceeded: {total_tokens}>{TOKEN_BUDGET}")
    if tool_calls > TOOL_BUDGET:
        errors.append(f"tool budget exceeded: {tool_calls}>{TOOL_BUDGET}")

    retained_count = 0
    duplicates = 0
    validation_rejected = 0
    shortlist_finalized = False
    if not errors or budget_stopped:
        try:
            batch, validation_rejected = _validated_batch(payload, shortlist)
            DEFAULT_BATCH_DIR.mkdir(parents=True, exist_ok=True)
            batch_path = DEFAULT_BATCH_DIR / f"run-{run_id}.json"
            batch_path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
            imported = import_batch(None, run_id, str(batch_path), DEFAULT_BATCH_DIR)
            retained_count = int(imported["prospects_retained"])
            duplicates = int(imported["duplicates_rejected"])
            _mark_unqualified(shortlist, batch)
            shortlist_finalized = True
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"deterministic batch validation/import failed: {error}")
    if not shortlist_finalized:
        _release_shortlist(shortlist, errors[0] if errors else "qualification did not finish")

    incomplete_target = not errors and _quality_target_incomplete(
        int(payload.get("candidates_examined") or 0), retained_count
    )
    if incomplete_target:
        errors.append(
            "quality batch incomplete; completed qualified work was persisted for the next scheduled run"
        )
        budget_stopped = True
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
