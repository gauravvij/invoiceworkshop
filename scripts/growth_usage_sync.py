#!/usr/bin/env python3
"""Synchronize Hermes agent usage into the local Level-0 audit store."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from growth_common import apply_schema, connect_db, database_path, utc_now

DEFAULT_HERMES_STATE = Path("/home/azureuser/.hermes/state.db")
DEFAULT_HERMES_EXECUTIONS = Path("/home/azureuser/.hermes/cron/executions.db")


def _epoch_iso(value: float | int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat(timespec="microseconds")


def _iso_epoch(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _closest_execution(executions: list[dict], started_at: float) -> dict | None:
    if not executions:
        return None
    candidate = min(
        executions,
        key=lambda row: abs((_iso_epoch(row.get("started_at")) or 0) - started_at),
    )
    distance = abs((_iso_epoch(candidate.get("started_at")) or 0) - started_at)
    return candidate if distance <= 300 else None


def _overlapping_local_run(connection, job_id: str, start: float, end: float) -> tuple[str, dict | None]:
    start_iso = _epoch_iso(start)
    end_iso = _epoch_iso(end)
    research = connection.execute(
        """SELECT * FROM research_runs
            WHERE hermes_job_id=? AND started_at<=?
              AND COALESCE(finished_at, started_at)>=?
            ORDER BY started_at DESC LIMIT 1""",
        (job_id, end_iso, start_iso),
    ).fetchone()
    if research:
        return "research", dict(research)
    level0 = connection.execute(
        """SELECT * FROM level0_runs
            WHERE hermes_job_id=? AND started_at<=?
              AND COALESCE(finished_at, started_at)>=?
            ORDER BY started_at DESC LIMIT 1""",
        (job_id, end_iso, start_iso),
    ).fetchone()
    if level0:
        return str(level0["job_name"]), dict(level0)
    return "unknown", None


def synchronize(
    db: str | None,
    hermes_state: Path,
    hermes_executions: Path,
    extra_job_ids: list[str] | None = None,
) -> dict:
    connection = connect_db(database_path(db))
    apply_schema(connection)
    job_ids = {
        str(row[0])
        for table in ("level0_runs", "research_runs")
        for row in connection.execute(f"SELECT DISTINCT hermes_job_id FROM {table}")
        if row[0]
    }
    job_ids.update(extra_job_ids or [])
    if not job_ids:
        connection.close()
        return {"sessions_seen": 0, "records_synced": 0}

    state = sqlite3.connect(f"file:{hermes_state.resolve()}?mode=ro", uri=True)
    state.row_factory = sqlite3.Row
    executions_db = sqlite3.connect(f"file:{hermes_executions.resolve()}?mode=ro", uri=True)
    executions_db.row_factory = sqlite3.Row
    records = 0
    sessions_seen = 0
    for job_id in sorted(job_ids):
        executions = [
            dict(row)
            for row in executions_db.execute(
                "SELECT * FROM executions WHERE job_id=? ORDER BY started_at", (job_id,)
            ).fetchall()
        ]
        sessions = state.execute(
            """SELECT id, model, started_at, ended_at, end_reason,
                      tool_call_count, input_tokens, output_tokens,
                      cache_read_tokens, cache_write_tokens, reasoning_tokens,
                      api_call_count
                 FROM sessions WHERE id LIKE ? ORDER BY started_at""",
            (f"cron_{job_id}_%",),
        ).fetchall()
        for session in sessions:
            sessions_seen += 1
            started = float(session["started_at"])
            ended = float(session["ended_at"] or session["started_at"])
            execution = _closest_execution(executions, started)
            job_name, local_run = _overlapping_local_run(connection, job_id, started, ended)
            candidates = None
            retained = None
            duplicates = None
            if job_name == "research" and local_run:
                candidates = int(local_run["candidates_examined"])
                retained = int(local_run["prospects_retained"])
                duplicates = int(local_run["duplicates_rejected"])
            elif local_run:
                retained = int(local_run["prospects_discovered"])
            input_tokens = int(session["input_tokens"] or 0)
            output_tokens = int(session["output_tokens"] or 0)
            cache_read = int(session["cache_read_tokens"] or 0)
            cache_write = int(session["cache_write_tokens"] or 0)
            total = input_tokens + output_tokens + cache_read + cache_write
            error = execution.get("error") if execution else session["end_reason"]
            status = execution.get("status") if execution else ("completed" if session["ended_at"] else "running")
            # The durable local audit is authoritative for semantic outcomes.
            # Hermes can report a technically completed agent session even
            # when the post-run budget/quality audit rejected its output.
            if job_name == "research" and local_run:
                status = str(local_run["status"])
            values = (
                session["id"],
                execution.get("id") if execution else None,
                job_id,
                job_name,
                _epoch_iso(started),
                _epoch_iso(ended) if session["ended_at"] else None,
                status,
                session["model"],
                input_tokens,
                output_tokens,
                cache_read,
                cache_write,
                int(session["reasoning_tokens"] or 0),
                total,
                int(session["api_call_count"] or 0),
                int(session["tool_call_count"] or 0),
                round((ended - started) * 1000) if session["ended_at"] else None,
                candidates,
                retained,
                duplicates,
                json.dumps([error] if error else []),
                utc_now(),
            )
            connection.execute(
                """INSERT INTO agent_executions
                   (session_id, hermes_execution_id, hermes_job_id, job_name,
                    started_at, finished_at, status, model, input_tokens,
                    output_tokens, cache_read_tokens, cache_write_tokens,
                    reasoning_tokens, total_tokens, api_calls, tool_calls,
                    execution_duration_ms, candidates_examined, prospects_retained,
                    duplicates_rejected, errors_json, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     hermes_execution_id=excluded.hermes_execution_id,
                     job_name=excluded.job_name, finished_at=excluded.finished_at,
                     status=excluded.status, model=excluded.model,
                     input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
                     cache_read_tokens=excluded.cache_read_tokens,
                     cache_write_tokens=excluded.cache_write_tokens,
                     reasoning_tokens=excluded.reasoning_tokens,
                     total_tokens=excluded.total_tokens, api_calls=excluded.api_calls,
                     tool_calls=excluded.tool_calls,
                     execution_duration_ms=excluded.execution_duration_ms,
                     candidates_examined=excluded.candidates_examined,
                     prospects_retained=excluded.prospects_retained,
                     duplicates_rejected=excluded.duplicates_rejected,
                     errors_json=excluded.errors_json, synced_at=excluded.synced_at""",
                values,
            )
            records += 1
    connection.commit()
    connection.close()
    state.close()
    executions_db.close()
    return {"sessions_seen": sessions_seen, "records_synced": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--hermes-state", type=Path, default=DEFAULT_HERMES_STATE)
    parser.add_argument("--hermes-executions", type=Path, default=DEFAULT_HERMES_EXECUTIONS)
    parser.add_argument("--job-id", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(synchronize(
        args.db, args.hermes_state, args.hermes_executions, args.job_id
    ), sort_keys=True))


if __name__ == "__main__":
    main()
