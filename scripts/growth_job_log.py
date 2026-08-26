#!/usr/bin/env python3
"""Durable Level-0 run audit and bounded Google-read circuit breaker."""

from __future__ import annotations

import argparse
import json

from growth_common import apply_schema, connect_db, database_path, utc_now

GOOGLE_ERROR_PREFIXES = ("google_auth:", "gsc:", "ga4:", "sitemap:", "inspection:")


def initialize(db: str | None):
    connection = connect_db(database_path(db))
    apply_schema(connection)
    return connection


def start_run(db: str | None, job: str, hermes_job_id: str) -> dict:
    connection = initialize(db)
    now = utc_now()
    connection.execute(
        """UPDATE level0_runs
              SET finished_at=?, status='failure',
                  errors_json='["previous execution did not reach its bounded finish step"]'
            WHERE job_name=? AND status='running'""",
        (now, job),
    )
    collection_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM collection_runs"
    ).fetchone()[0]
    prospect_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM prospects"
    ).fetchone()[0]
    cursor = connection.execute(
        """INSERT INTO level0_runs
           (job_name, hermes_job_id, started_at, status,
            collection_run_start_id, prospect_start_id)
           VALUES (?, ?, ?, 'running', ?, ?)""",
        (job, hermes_job_id, now, collection_id, prospect_id),
    )
    operation = connection.execute(
        "SELECT state, failure_streak, last_error FROM operation_state WHERE operation='google_reads'"
    ).fetchone()
    connection.commit()
    result = {
        "run_id": cursor.lastrowid,
        "job": job,
        "started_at": now,
        "google_reads": dict(operation),
        "bounded_policy": "no immediate retry; next scheduled cadence only",
    }
    connection.close()
    return result


def cmd_start(args: argparse.Namespace) -> None:
    print(json.dumps(start_run(args.db, args.job, args.hermes_job_id), sort_keys=True))


def _collection_evidence(connection, row) -> tuple[int, int, list[str], bool]:
    collection = connection.execute(
        """SELECT id, started_at, status, errors_json FROM collection_runs
            WHERE id>? ORDER BY id DESC LIMIT 1""",
        (row["collection_run_start_id"],),
    ).fetchone()
    if collection is None:
        return 0, 0, [], row["job_name"] == "weekly"
    source_rows = {
        item["source"]: item["row_count"]
        for item in connection.execute(
            "SELECT source, row_count FROM source_snapshots WHERE collected_at=?",
            (collection["started_at"],),
        ).fetchall()
    }
    errors = json.loads(collection["errors_json"] or "[]")
    return (
        int(source_rows.get("gsc", 0)),
        int(source_rows.get("ga4", 0)),
        [str(error) for error in errors],
        collection["status"] == "ok",
    )


def _update_google_breaker(connection, errors: list[str]) -> dict:
    if any(error.startswith("google_reads:") for error in errors):
        current = connection.execute(
            "SELECT state, failure_streak, last_error FROM operation_state WHERE operation='google_reads'"
        ).fetchone()
        return dict(current)
    relevant = [error for error in errors if error.startswith(GOOGLE_ERROR_PREFIXES)]
    current = connection.execute(
        "SELECT state, failure_streak FROM operation_state WHERE operation='google_reads'"
    ).fetchone()
    if relevant:
        streak = int(current["failure_streak"]) + 1
        state = "paused" if streak >= 3 else "active"
        last_error = " | ".join(relevant)[:2000]
    else:
        streak = 0
        state = "active"
        last_error = None
    connection.execute(
        """UPDATE operation_state
              SET state=?, failure_streak=?, last_error=?, updated_at=?
            WHERE operation='google_reads'""",
        (state, streak, last_error, utc_now()),
    )
    return {"state": state, "failure_streak": streak, "last_error": last_error}


def finish_run(
    db: str | None,
    run_id: int,
    requested_status: str,
    requested_errors: list[str] | None = None,
) -> dict:
    connection = initialize(db)
    row = connection.execute(
        "SELECT * FROM level0_runs WHERE id=? AND status='running'", (run_id,)
    ).fetchone()
    if row is None:
        raise SystemExit("run does not exist or is already finished")
    gsc_rows, ga4_rows, collection_errors, collection_ok = _collection_evidence(connection, row)
    errors = [*collection_errors, *(requested_errors or [])]
    success = requested_status == "success" and collection_ok and not errors
    discovered = connection.execute(
        "SELECT COUNT(*) FROM prospects WHERE id>?", (row["prospect_start_id"],)
    ).fetchone()[0]
    updated = connection.execute(
        """SELECT COUNT(*) FROM prospects
            WHERE id<=? AND updated_at>=?""",
        (row["prospect_start_id"], row["started_at"]),
    ).fetchone()[0]
    breaker = _update_google_breaker(connection, errors) if row["job_name"] == "daily" else None
    finished = utc_now()
    connection.execute(
        """UPDATE level0_runs SET finished_at=?, status=?, gsc_rows_collected=?,
              ga4_rows_collected=?, prospects_discovered=?, prospects_updated=?,
              errors_json=?, external_side_effects='none'
            WHERE id=?""",
        (
            finished, "success" if success else "failure", gsc_rows, ga4_rows,
            discovered, updated, json.dumps(errors), run_id,
        ),
    )
    connection.commit()
    result = {
        "run_id": run_id,
        "finished_at": finished,
        "status": "success" if success else "failure",
        "gsc_rows_collected": gsc_rows,
        "ga4_rows_collected": ga4_rows,
        "prospects_discovered": discovered,
        "prospects_updated": updated,
        "errors": errors,
        "external_side_effects": "none",
        "model_api_usage": "recorded where available in Hermes session metadata",
        "google_reads": breaker,
    }
    connection.close()
    return result


def cmd_finish(args: argparse.Namespace) -> None:
    result = finish_run(args.db, args.run_id, args.status, args.error)
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "success":
        raise SystemExit(2)


def cmd_guard(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    row = connection.execute(
        "SELECT * FROM operation_state WHERE operation=?", (args.operation,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"unknown operation: {args.operation}")
    print(json.dumps(dict(row), sort_keys=True))
    if row["state"] == "paused":
        raise SystemExit(75)


def cmd_resume(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    connection.execute(
        """UPDATE operation_state SET state='active', failure_streak=0,
              last_error=NULL, updated_at=? WHERE operation=?""",
        (utc_now(), args.operation),
    )
    connection.commit()
    print(json.dumps({"operation": args.operation, "state": "active"}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db")
    commands = root.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--job", required=True, choices=("daily", "weekly"))
    start.add_argument("--hermes-job-id", required=True)
    start.set_defaults(handler=cmd_start)

    finish = commands.add_parser("finish")
    finish.add_argument("--run-id", required=True, type=int)
    finish.add_argument("--status", required=True, choices=("success", "failure"))
    finish.add_argument("--error", action="append", default=[])
    finish.set_defaults(handler=cmd_finish)

    guard = commands.add_parser("guard")
    guard.add_argument("--operation", required=True, choices=("google_reads",))
    guard.set_defaults(handler=cmd_guard)

    resume = commands.add_parser("resume")
    resume.add_argument("--operation", required=True, choices=("google_reads",))
    resume.set_defaults(handler=cmd_resume)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
