#!/usr/bin/env python3
"""Watchdog for the unattended growth runtime.

Prints nothing when everything is healthy. That is the whole design: the
scheduler delivers stdout, so silence means "nothing needs you" and any output
at all means something does. A system that reports success every night trains
its owner to stop reading it.

Checks the things whose failure would be silent otherwise: a scheduler that
stopped firing, a collector that stopped collecting, a lock nobody released, an
unattended worker that keeps failing, and outreach that has gone quiet in a way
that needs a decision rather than more waiting.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from growth_common import (apply_schema, connect_db, database_path,
                           record_escalation, resolve_escalation, utc_now)

LOCKS = (
    Path.home() / ".config" / "invoiceworkshop" / "growth.lock",
    Path.home() / ".config" / "invoiceworkshop" / "growth-executor.lock",
)
STALE_LOCK_HOURS = 6
COLLECTION_STALE_HOURS = 30
SCHEDULER_STALE_HOURS = 30


def _age_hours(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() / 3600


def check_scheduler() -> list[dict]:
    """The scheduler is the thing keeping everything else alive, so a gateway
    that is not running is the one failure that hides all the others."""
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "hermes-gateway.service"],
        check=False, capture_output=True, text=True, timeout=30,
        env={**os.environ, "XDG_RUNTIME_DIR": os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")},
    )
    state = result.stdout.strip()
    if state != "active":
        return [{"kind": "scheduler_down", "severity": "critical",
                 "subject": "Hermes gateway is not running",
                 "detail": f"systemctl --user is-active returned '{state}'. "
                           "No scheduled growth job will fire until it is back.",
                 "fingerprint": "scheduler_down"}]
    return []


def check_collection(connection) -> list[dict]:
    row = connection.execute(
        "SELECT MAX(COALESCE(finished_at, started_at)) FROM collection_runs"
    ).fetchone()[0]
    age = _age_hours(row)
    if age is None or age > COLLECTION_STALE_HOURS:
        return [{"kind": "collection_stale", "severity": "warning",
                 "subject": "Search and analytics collection has stopped",
                 "detail": f"Last collection run was {'never' if age is None else f'{age:.0f}h ago'}; "
                           f"the threshold is {COLLECTION_STALE_HOURS}h. Every downstream "
                           "decision is now working from stale evidence.",
                 "fingerprint": "collection_stale"}]
    return []


def check_locks() -> list[dict]:
    problems = []
    for lock in LOCKS:
        if not lock.exists():
            continue
        held = subprocess.run(["flock", "-n", str(lock), "true"], check=False,
                              capture_output=True, timeout=30)
        if held.returncode == 0:
            continue
        age = (time.time() - lock.stat().st_mtime) / 3600
        if age > STALE_LOCK_HOURS:
            problems.append({
                "kind": "stale_lock", "severity": "critical",
                "subject": f"{lock.name} has been held for {age:.0f}h",
                "detail": "A growth job is wedged. Later jobs are queueing behind it "
                          "and will time out rather than run.",
                "fingerprint": f"stale_lock:{lock.name}"})
    return problems


def check_worker(connection) -> list[dict]:
    recent = [dict(row) for row in connection.execute(
        """SELECT outcome, started_at, error FROM claude_runs
            WHERE run_type<>'fixture' ORDER BY id DESC LIMIT 5""")]
    if len(recent) < 3:
        return []
    bad = {"error", "timeout", "validation_failed", "deploy_failed", "rolled_back", "refused"}
    if all(run["outcome"] in bad for run in recent[:3]):
        return [{"kind": "worker_failing", "severity": "warning",
                 "subject": "The unattended worker has failed three runs in a row",
                 "detail": "; ".join(f"{r['started_at'][:10]} {r['outcome']}: "
                                     f"{str(r['error'])[:120]}" for r in recent[:3]),
                 "fingerprint": "worker_failing"}]
    return []


def check_outreach(connection) -> list[dict]:
    """The one outreach condition that needs a person: the cohort has finished."""
    row = connection.execute(
        "SELECT recommendation, rationale FROM outreach_calibration ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None or row["recommendation"] == "CONTINUE_CALIBRATION":
        return []
    return [{"kind": "outreach_decision_due", "severity": "info",
             "subject": f"Outreach calibration finished: {row['recommendation']}",
             "detail": row["rationale"],
             "fingerprint": f"outreach_decision:{row['recommendation']}"}]


def check_milestones(connection) -> list[dict]:
    """Things worth interrupting someone for because they have never happened."""
    found = []
    placements = connection.execute(
        "SELECT COUNT(*) FROM placements WHERE status='live'").fetchone()[0]
    if placements:
        found.append({"kind": "milestone", "severity": "info",
                      "subject": f"First confirmed backlink ({placements} live)",
                      "detail": "A placement has been verified live. This is milestone A.",
                      "fingerprint": "milestone:first_backlink"})
    clicks = connection.execute(
        "SELECT COALESCE(SUM(gsc_clicks),0) FROM metrics_daily").fetchone()[0]
    if clicks:
        found.append({"kind": "milestone", "severity": "info",
                      "subject": f"First organic clicks recorded ({clicks})",
                      "detail": "Search Console has reported clicks for the first time.",
                      "fingerprint": "milestone:first_clicks"})
    return found


CHECKS = (
    ("scheduler", lambda connection: check_scheduler()),
    ("collection", check_collection),
    ("locks", lambda connection: check_locks()),
    ("worker", check_worker),
    ("outreach", check_outreach),
    ("milestones", check_milestones),
)


# Only these are re-derived from live state every run, so only these may be
# auto-resolved when they stop being raised.
HEALTH_OWNED_KINDS = ("scheduler_down", "collection_stale", "stale_lock",
                      "worker_failing", "health_check_error")


def run(connection) -> list[dict]:
    problems: list[dict] = []
    for name, check in CHECKS:
        try:
            problems.extend(check(connection))
        except Exception as error:  # a broken check must not silence the others
            problems.append({"kind": "health_check_error", "severity": "warning",
                             "subject": f"Health check '{name}' raised",
                             "detail": f"{type(error).__name__}: {error}",
                             "fingerprint": f"health_check_error:{name}"})
    raised = {problem["fingerprint"] for problem in problems}
    for problem in problems:
        record_escalation(connection, **problem)
    # A condition that has cleared should stop being reported -- but only the
    # conditions this module actually re-checks. Escalations raised elsewhere,
    # such as a refused change or a rolled-back deployment, describe something
    # that happened rather than something still true, and closing those here
    # would quietly discard them before anyone saw them.
    placeholders = ",".join("?" * len(HEALTH_OWNED_KINDS))
    for row in connection.execute(
        f"""SELECT fingerprint FROM escalations
             WHERE resolved_at IS NULL AND kind IN ({placeholders})""",
        HEALTH_OWNED_KINDS,
    ).fetchall():
        if row["fingerprint"] not in raised:
            resolve_escalation(connection, row["fingerprint"])
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--all", action="store_true",
                        help="Print the healthy result too, instead of staying silent")
    args = parser.parse_args()
    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    problems = run(connection)
    open_items = [dict(row) for row in connection.execute(
        """SELECT kind, severity, subject, detail, occurrences, last_seen_at
             FROM escalations WHERE resolved_at IS NULL AND acknowledged=0
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                     last_seen_at DESC""")]
    if open_items:
        print(json.dumps({"checked_at": utc_now(), "needs_attention": open_items},
                         indent=2, sort_keys=True, default=str))
    elif args.all:
        print(json.dumps({"checked_at": utc_now(), "status": "healthy",
                          "needs_attention": []}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
