#!/usr/bin/env python3
"""The Monday scoreboard for the 90-day experiment.

One page, every Monday, whether the news is good or not. It answers a single
question -- is 300,000-700,000 monthly pageviews within 90 days still reachable
from here -- and it answers it from measurements already in the database rather
than from a narrative written after the fact.

Two rules hold it honest:

  * Historical targets are read, never rewritten. A week that missed stays
    missed. The plan is written once and the only edits it accepts are metrics
    joining or leaving the objective, never a number moved to flatter a result.
  * Nothing here is a page count in disguise. Pages published and pages indexed
    appear because they explain the other rows, but the verdict is computed from
    what the market did: queries ranked, impressions earned, links given,
    sessions arriving.

The verdict is one of three, and the middle one is not a hedge:

  ON_BREAKOUT_TRAJECTORY  the compounding rate still required from today is one
                          a young site launching genuinely useful tools has been
                          observed to sustain
  POSSIBLE_BUT_BEHIND     the required rate is above that but not outside what a
                          step change in surface area and authority could produce
  STRUCTURALLY_BEHIND     the required rate is not something the current strategy
                          produces at all, and saying otherwise would be a lie
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import growth_trajectory as trajectory
from growth_common import apply_schema, connect_db, database_path, record_escalation, utc_now

# Weekly compounding rates. A young domain publishing genuinely differentiated
# tools can compound organic sessions fast from a small base; it does not double
# every week for a quarter without an external event, and a scoreboard that
# implied otherwise would be worthless.
BREAKOUT_CEILING = 0.40
POSSIBLE_CEILING = 0.75

STATUSES = ("ON_BREAKOUT_TRAJECTORY", "POSSIBLE_BUT_BEHIND", "STRUCTURALLY_BEHIND")


def _week_bounds(weeks_back: int = 1) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (now - timedelta(weeks=weeks_back)).isoformat(), now.isoformat()


def _one(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> float:
    row = connection.execute(sql, params).fetchone()
    return float(row[0] or 0) if row else 0.0


def search_surface(connection: sqlite3.Connection, since: str) -> dict:
    """What the site actually offers, and how much demand it speaks to.

    Deliberately reported as capability, not inventory: the count is here to be
    read alongside the demand it addresses, never as a figure to grow on its own.
    """
    live = trajectory.measure(connection)
    return {
        "useful_pages_live": int(live["published_pages"]),
        "families_admitted": int(_one(
            connection, "SELECT COUNT(*) FROM page_families WHERE status='admitted'")),
        "families_built": int(_one(
            connection, "SELECT COUNT(*) FROM page_families WHERE status='built'")),
        "families_refused": int(_one(
            connection, "SELECT COUNT(*) FROM page_families WHERE status='refused'")),
        "families_launched_this_week": int(_one(
            connection,
            "SELECT COUNT(*) FROM page_families WHERE status='built' AND updated_at>=?",
            (since,))),
        "addressable_demand_impressions": int(live["addressable_demand"]),
        "addressable_demand_note": (
            "search demand the site is visible to, measured from Search Console. "
            "Not total market demand: no keyword-volume source is connected, and a "
            "made-up figure next to measured ones would be worse than none."),
    }


def google(connection: sqlite3.Connection) -> dict:
    live = trajectory.measure(connection)
    clicks = _one(connection, "SELECT COALESCE(SUM(gsc_clicks), 0) FROM metrics_daily")
    return {
        "indexed_pages": int(live["indexed_pages"]),
        "pages_with_impressions": int(live["pages_with_impressions"]),
        "pages_with_traffic": int(live["pages_with_traffic"]),
        "ranking_queries": int(live["ranking_queries"]),
        "queries_top_50": int(live["queries_top_50"]),
        "queries_top_20": int(live["queries_top_20"]),
        "queries_top_10": int(live["queries_top_10"]),
        "impressions": int(live["monthly_impressions"]),
        "clicks": int(clicks),
    }


def authority(connection: sqlite3.Connection, since: str) -> dict:
    return {
        "referring_domains": int(_one(
            connection,
            "SELECT COUNT(DISTINCT placement_url) FROM placements WHERE status='live'")),
        "placements_live": int(_one(
            connection, "SELECT COUNT(*) FROM placements WHERE status='live'")),
        "placements_unverified": int(_one(
            connection, "SELECT COUNT(*) FROM placements WHERE status='unverified'")),
        "outreach_sent_total": int(_one(connection, "SELECT COUNT(*) FROM outreach")),
        "outreach_sent_this_week": int(_one(
            connection, "SELECT COUNT(*) FROM outreach WHERE sent_at>=?", (since,))),
        "outreach_replies": int(_one(
            connection, "SELECT COUNT(*) FROM outreach WHERE response IS NOT NULL")),
    }


def usage(connection: sqlite3.Connection) -> dict:
    live = trajectory.measure(connection)
    return {
        "organic_sessions_per_day": round(live["organic_sessions_measured"], 2),
        "pageviews_per_session": trajectory.pageviews_per_session(connection),
        "pageviews_per_day_all_sources": int(live["daily_pageviews"]),
        "tool_starts": int(live["tool_starts"]),
        "pdf_downloads": int(live["pdf_downloads"]),
    }


def velocity(connection: sqlite3.Connection, since: str) -> dict:
    runs = {row["outcome"]: int(row["n"]) for row in connection.execute(
        "SELECT outcome, COUNT(*) n FROM claude_runs WHERE started_at>=? GROUP BY outcome",
        (since,))}
    succeeded = runs.get("changed", 0) + runs.get("no_action", 0)
    return {
        "useful_launches_this_week": int(_one(
            connection,
            "SELECT COUNT(*) FROM page_candidates WHERE status='shipped' AND shipped_at>=?",
            (since,))),
        "autonomous_runs_succeeded": succeeded,
        "autonomous_runs_refused_or_failed": sum(runs.values()) - succeeded,
        "run_outcomes": runs,
        "claude_spend_usd_this_week": round(_one(
            connection, "SELECT COALESCE(SUM(cost_usd), 0) FROM claude_runs WHERE started_at>=?",
            (since,)), 2),
        "spend_note": ("list-price estimate reported by the CLI, not an amount billed: "
                       "these runs meter against the Max subscription"),
        "open_escalations": int(_one(
            connection, "SELECT COUNT(*) FROM escalations WHERE resolved_at IS NULL")),
    }


def target_gap(connection: sqlite3.Connection) -> dict:
    """The only row that matters, and the one it is most tempting to soften."""
    requirement = trajectory.required_weekly_growth(connection)
    live = trajectory.measure(connection)
    per_session = trajectory.pageviews_per_session(connection)
    run_rate = live["organic_sessions_measured"] * 30 * per_session
    required = trajectory.TARGET_PAGEVIEWS
    weekly = float(requirement["weekly_growth_required"].rstrip("%")) / 100.0
    if weekly <= BREAKOUT_CEILING:
        status = "ON_BREAKOUT_TRAJECTORY"
    elif weekly <= POSSIBLE_CEILING:
        status = "POSSIBLE_BUT_BEHIND"
    else:
        status = "STRUCTURALLY_BEHIND"
    return {
        "current_monthly_pageview_run_rate": int(run_rate),
        "run_rate_required_at_day_90": required,
        "target_band": f"{trajectory.TARGET_PAGEVIEWS_LOW:,}-"
                       f"{trajectory.TARGET_PAGEVIEWS_HIGH:,}",
        "weekly_growth_required_from_here": requirement["weekly_growth_required"],
        "weeks_remaining": requirement["weeks_remaining"],
        "trajectory_status": status,
        "verdict": _verdict(status, requirement),
    }


def _verdict(status: str, requirement: dict) -> str:
    rate = requirement["weekly_growth_required"]
    weeks = requirement["weeks_remaining"]
    if status == "ON_BREAKOUT_TRAJECTORY":
        return (f"{rate} weekly compounding for {weeks} weeks is within what a young "
                "site launching genuinely useful tools sustains. Keep going.")
    if status == "POSSIBLE_BUT_BEHIND":
        return (f"{rate} weekly for {weeks} weeks is above the comfortable rate but not "
                "outside what a step change in surface area and authority produces. It "
                "needs that step change, not more of the same.")
    return (f"{rate} weekly compounding for {weeks} weeks is not a rate this strategy "
            "produces. Reaching the band would need something the current plan does not "
            "contain -- a channel that is not search, or a launch that is not incremental. "
            "Saying otherwise would be a forecast rather than a measurement.")


def build(connection: sqlite3.Connection, *, weeks_back: int = 1) -> dict:
    since, _ = _week_bounds(weeks_back)
    week = trajectory.current_week()
    gap = target_gap(connection)
    return {
        "experiment": trajectory.EXPERIMENT,
        "generated_at": utc_now(),
        "week": week, "of": trajectory.WEEKS,
        "week_ending": trajectory.week_ending(week).isoformat(),
        "days_remaining": gap["weeks_remaining"] * 7,
        "search_surface": search_surface(connection, since),
        "google": google(connection),
        "authority": authority(connection, since),
        "usage": usage(connection),
        "velocity": velocity(connection, since),
        "target_gap": gap,
        "attainment": trajectory.attainment(connection),
        "intensity": trajectory.intensity(connection),
        "objective": ("useful search coverage x search demand x ranking potential x "
                      "authority x product usefulness. Page count is not in it."),
    }


def publish(connection: sqlite3.Connection, *, weeks_back: int = 1) -> dict:
    """Build the scoreboard and escalate only when the verdict has hardened."""
    board = build(connection, weeks_back=weeks_back)
    status = board["target_gap"]["trajectory_status"]
    if status == "STRUCTURALLY_BEHIND" and board["week"] >= 4:
        record_escalation(
            connection, kind="trajectory_structurally_behind", severity="warning",
            subject=f"Week {board['week']}: {status}",
            detail=board["target_gap"]["verdict"],
            fingerprint="trajectory_structurally_behind")
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--weeks-back", type=int, default=1)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="Print the scoreboard without side effects")
    commands.add_parser("publish", help="Build it and escalate a hardened verdict")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    result = (publish if args.command == "publish" else build)(
        connection, weeks_back=args.weeks_back)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
