#!/usr/bin/env python3
"""Run deterministic daily measurement and emit only meaningful LLM triggers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta

from growth_common import apply_schema, connect_db, database_path, utc_now
from growth_report import build_report

DAILY_JOB_ID = "a56bbe317393"
PYTHON = "/home/azureuser/growth-venv/bin/python"
NO_CHANGE_OUTPUT = {
    "meaningful": False,
    "external_side_effects": "none",
}


def _run(arguments: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments,
        cwd="/home/azureuser/invoiceworkshop",
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _job_log(db: str | None, arguments: list[str], expected_codes: set[int]) -> dict:
    command = [PYTHON, "scripts/growth_job_log.py"]
    if db:
        command.extend(("--db", db))
    command.extend(arguments)
    result = _run(command, timeout=60)
    if result.returncode not in expected_codes:
        raise RuntimeError(f"growth job audit exited {result.returncode}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("growth job audit returned invalid JSON") from error


def _latest_sources(connection) -> dict[str, dict]:
    rows = connection.execute(
        """SELECT s.* FROM source_snapshots s
           JOIN (SELECT source, MAX(collected_at) latest
                   FROM source_snapshots GROUP BY source) x
             ON x.source=s.source AND x.latest=s.collected_at"""
    ).fetchall()
    result = {}
    for row in rows:
        item = dict(row)
        item["totals"] = json.loads(item.pop("totals_json") or "{}")
        result[item["source"]] = item
    return result


def _latest_index(connection) -> dict[str, dict]:
    rows = connection.execute(
        """SELECT * FROM index_state
            WHERE date=(SELECT MAX(date) FROM index_state) ORDER BY url"""
    ).fetchall()
    return {
        row["url"]: {
            "verdict": row["verdict"],
            "coverage_state": row["coverage_state"],
            "error": row["error"],
        }
        for row in rows
    }


def _latest_breakdowns(connection) -> dict[tuple[str, str], dict]:
    rows = connection.execute(
        """SELECT * FROM gsc_breakdowns
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_breakdowns)"""
    ).fetchall()
    return {
        (row["dimension"], row["value"]): {
            "clicks": int(row["clicks"] or 0),
            "impressions": int(row["impressions"] or 0),
            "position": row["position"],
        }
        for row in rows
    }


def _placements(connection) -> dict[int, tuple]:
    return {
        int(row["id"]): (
            row["status"], row["link_present"], row["last_http_status"],
            row["consecutive_failures"],
        )
        for row in connection.execute(
            """SELECT id, status, link_present, last_http_status,
                      consecutive_failures FROM placements"""
        )
    }


def capture_state(connection) -> dict:
    collection_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM collection_runs"
    ).fetchone()[0]
    return {
        "collection_run_id": int(collection_id),
        "sources": _latest_sources(connection),
        "index": _latest_index(connection),
        "breakdowns": _latest_breakdowns(connection),
        "placements": _placements(connection),
    }


def _changed_enough(current: int, previous: int, absolute: int, percent: float) -> bool:
    delta = abs(current - previous)
    if delta < absolute:
        return False
    if previous == 0:
        return current >= absolute
    return (delta / previous) * 100 >= percent


def detect_signals(
    before: dict,
    after: dict,
    *,
    collection_status: str,
    collection_errors: list[str],
    gsc_absolute: int,
    gsc_percent: float,
    ga_absolute: int,
    ga_percent: float,
) -> list[dict]:
    signals: list[dict] = []
    if collection_status != "ok" or collection_errors:
        signals.append({
            "type": "measurement_failure",
            "status": collection_status,
            "errors": collection_errors[:5],
        })
    previous_source_failures = [
        name for name, source in before["sources"].items()
        if source.get("status") not in {"ok", "empty"} or source.get("error")
    ]
    current_source_failures = [
        name for name, source in after["sources"].items()
        if source.get("status") not in {"ok", "empty"} or source.get("error")
    ]
    if previous_source_failures and not current_source_failures and collection_status == "ok":
        signals.append({
            "type": "measurement_recovered",
            "previous_failed_sources": sorted(previous_source_failures),
        })

    old_gsc = before["sources"].get("gsc", {}).get("totals", {})
    new_gsc = after["sources"].get("gsc", {}).get("totals", {})
    for metric in ("clicks", "impressions"):
        old = int(old_gsc.get(metric, 0))
        new = int(new_gsc.get(metric, 0))
        threshold = 1 if metric == "clicks" else gsc_absolute
        if _changed_enough(new, old, threshold, gsc_percent):
            signals.append({
                "type": "gsc_delta", "metric": metric, "previous": old,
                "current": new, "delta": new - old,
            })

    old_ga = before["sources"].get("ga4", {}).get("totals", {})
    new_ga = after["sources"].get("ga4", {}).get("totals", {})
    for metric in ("sessions", "users", "pageviews", "tool_started", "pdf_downloaded"):
        old = int(old_ga.get(metric, 0))
        new = int(new_ga.get(metric, 0))
        absolute = 2 if metric == "pdf_downloaded" else ga_absolute
        if _changed_enough(new, old, absolute, ga_percent):
            signals.append({
                "type": "ga4_delta", "metric": metric, "previous": old,
                "current": new, "delta": new - old,
            })

    old_queries = {
        value for (dimension, value), row in before["breakdowns"].items()
        if dimension == "query" and row["impressions"] > 0
    }
    new_queries = [
        value for (dimension, value), row in after["breakdowns"].items()
        if dimension == "query" and row["impressions"] > 0 and value not in old_queries
    ]
    if new_queries:
        signals.append({"type": "new_gsc_queries", "values": sorted(new_queries)[:20]})

    for key, current in after["breakdowns"].items():
        previous = before["breakdowns"].get(key)
        if not previous or key[0] not in {"query", "page"}:
            continue
        if current["impressions"] < 5 or current["position"] is None or previous["position"] is None:
            continue
        movement = float(current["position"]) - float(previous["position"])
        if abs(movement) >= 3:
            signals.append({
                "type": "ranking_movement", "dimension": key[0], "value": key[1],
                "previous": previous["position"], "current": current["position"],
                "movement": movement,
            })

    index_changes = []
    for url, current in after["index"].items():
        previous = before["index"].get(url)
        if previous and current != previous:
            index_changes.append({"url": url, "previous": previous, "current": current})
    if index_changes:
        signals.append({"type": "index_state_changes", "changes": index_changes})

    changed_placements = []
    for placement_id, current in after["placements"].items():
        previous = before["placements"].get(placement_id)
        if previous != current:
            changed_placements.append({
                "placement_id": placement_id,
                "previous": previous,
                "current": current,
            })
    if changed_placements:
        signals.append({"type": "placement_changes", "changes": changed_placements})

    sitemap = after["sources"].get("sitemap", {}).get("totals", {})
    if int(sitemap.get("errors", 0)) or int(sitemap.get("warnings", 0)):
        signals.append({"type": "sitemap_anomaly", "totals": sitemap})
    health = after["sources"].get("health", {}).get("totals", {})
    if health and int(health.get("healthy", 0)) < int(health.get("checked", 0)):
        signals.append({"type": "url_health_anomaly", "totals": health})
    return signals


def _compact_context(connection, collection, signals: list[dict]) -> dict:
    report = build_report(connection, 7)
    sources = _latest_sources(connection)
    index_rows = report["latest_index_state"]
    operation = connection.execute(
        "SELECT state, failure_streak, last_error FROM operation_state WHERE operation='google_reads'"
    ).fetchone()
    return {
        "meaningful": bool(signals),
        "signals": signals,
        "collection": {
            "run_id": int(collection["id"]),
            "status": collection["status"],
            "gsc_rows": int(sources.get("gsc", {}).get("row_count", 0)),
            "ga4_rows": int(sources.get("ga4", {}).get("row_count", 0)),
            "health": sources.get("health", {}).get("totals", {}),
            "sitemap": sources.get("sitemap", {}).get("totals", {}),
            "inspection": sources.get("inspection", {}).get("totals", {}),
        },
        "seven_day_totals": report["totals"],
        "gsc_breakdown_rows": {
            name: len(report["gsc_breakdowns"][name])
            for name in ("query", "page", "country", "device")
        },
        # One canonical metric. `verdict == "PASS"` was standing in for
        # "indexed" and is not the same thing: the verdict grades overall health,
        # while coverageState is what actually says whether Google holds the
        # page. classify_index reads coverageState and is the only place that
        # decision is made.
        "indexation": _indexation(index_rows),
        "urls_inspected": len(index_rows),
        "google_reads": dict(operation),
        "external_side_effects": "none",
    }


def _indexation(index_rows) -> dict:
    from growth_opportunities import classify_index

    buckets = {"indexed": 0, "crawled_not_indexed": 0,
               "discovered_not_crawled": 0, "unknown": 0}
    for row in index_rows:
        buckets[classify_index(dict(row))] += 1
    return buckets


def run_daily_monitor(
    *, db: str | None, gsc_absolute: int, gsc_percent: float,
    ga_absolute: int, ga_percent: float,
) -> dict:
    try:
        _run([PYTHON, "scripts/growth_usage_sync.py", *(["--db", db] if db else [])], timeout=60)
    except Exception:
        pass
    started = _job_log(
        db, ["start", "--job", "daily", "--hermes-job-id", DAILY_JOB_ID], {0}
    )
    run_id = int(started["run_id"])
    connection = connect_db(database_path(db))
    apply_schema(connection)
    before = capture_state(connection)
    connection.close()

    command = ["bash", "scripts/run_growth_daily.sh"]
    environment = os.environ.copy()
    if db:
        environment["GROWTH_DB_PATH"] = str(database_path(db))
    measurement = subprocess.run(
        command,
        cwd="/home/azureuser/invoiceworkshop",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )

    connection = connect_db(database_path(db))
    apply_schema(connection)
    after = capture_state(connection)
    collection = connection.execute(
        "SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if collection is None or int(collection["id"]) <= before["collection_run_id"]:
        connection.close()
        error = "deterministic collection did not create a collection run"
        _job_log(
            db,
            ["finish", "--run-id", str(run_id), "--status", "failure", "--error", error],
            {2},
        )
        return {
            "meaningful": True,
            "signals": [{"type": "measurement_failure", "errors": [error]}],
            "external_side_effects": "none",
        }
    collection_errors = json.loads(collection["errors_json"] or "[]")
    signals = detect_signals(
        before,
        after,
        collection_status=str(collection["status"]),
        collection_errors=collection_errors,
        gsc_absolute=gsc_absolute,
        gsc_percent=gsc_percent,
        ga_absolute=ga_absolute,
        ga_percent=ga_percent,
    )
    connection.close()

    if measurement.returncode == 0 and collection["status"] == "ok":
        finished = _job_log(
            db, ["finish", "--run-id", str(run_id), "--status", "success"], {0}
        )
    else:
        error = f"deterministic measurement exited {measurement.returncode}"
        finished = _job_log(
            db,
            ["finish", "--run-id", str(run_id), "--status", "failure", "--error", error],
            {2},
        )
    connection = connect_db(database_path(db))
    apply_schema(connection)
    collection = connection.execute(
        "SELECT * FROM collection_runs WHERE id=?", (int(collection["id"]),)
    ).fetchone()
    context = _compact_context(connection, collection, signals)
    connection.execute(
        """INSERT INTO measurement_signals
           (collection_run_id, previous_collection_run_id, created_at,
            meaningful, signal_count, signals_json, context_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            int(collection["id"]), before["collection_run_id"] or None, utc_now(),
            int(bool(signals)), len(signals), json.dumps(signals, sort_keys=True),
            json.dumps(context, sort_keys=True),
        ),
    )
    connection.execute(
        """UPDATE level0_runs
              SET model_api_usage_json=? WHERE id=?""",
        (
            json.dumps({
                "measurement_agent_invoked": False,
                "conditional_analysis": "Hermes monitor-controlled",
            }, sort_keys=True),
            run_id,
        ),
    )
    connection.commit()
    if signals:
        monitor_output = context
    else:
        previous_meaningful = connection.execute(
            """SELECT context_json FROM measurement_signals
                WHERE meaningful=1 AND collection_run_id<>?
                ORDER BY id DESC LIMIT 1""",
            (int(collection["id"]),),
        ).fetchone()
        monitor_output = (
            json.loads(previous_meaningful["context_json"])
            if previous_meaningful else NO_CHANGE_OUTPUT
        )
    connection.close()
    return monitor_output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--gsc-impression-absolute", type=int, default=10)
    parser.add_argument("--gsc-percent", type=float, default=25.0)
    parser.add_argument("--ga-absolute", type=int, default=10)
    parser.add_argument("--ga-percent", type=float, default=50.0)
    args = parser.parse_args()
    context = run_daily_monitor(
        db=args.db,
        gsc_absolute=args.gsc_impression_absolute,
        gsc_percent=args.gsc_percent,
        ga_absolute=args.ga_absolute,
        ga_percent=args.ga_percent,
    )
    print(json.dumps(context, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
