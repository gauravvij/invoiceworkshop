#!/usr/bin/env python3
"""The 90-day growth experiment: targets, measurement, and intensity.

The objective is 300,000-700,000 monthly pageviews within 90 days. This module
exists to make the gap between that and reality a number rather than an opinion,
every week, without anyone asking.

Working backward from the midpoint:

    500,000 pageviews/month
      / measured pageviews per session  -> sessions needed per month
      / 30 days                          -> sessions needed per day
    from today's ORGANIC baseline        -> the multiple required
    over the weeks remaining             -> the weekly compounding rate

Every input is measured. In particular the baseline is organic sessions only:
all traffic so far is direct and unassigned, so counting it would understate
what the target demands by two orders of magnitude.

That number is the honest headline and it is computed here rather than asserted,
so it moves when the baseline moves. Sessions are the destination, but in the
first weeks they round to zero and steer nothing, so attainment is measured
early against leading indicators and shifts to sessions as they start to exist.

Every one of those leading indicators is an OUTCOME, never a production count.
Page count in particular is not among them and must not be: traffic does not
scale with pages, a target expressed in pages is a standing instruction to
manufacture pages, and fifty tools that rank beat nine hundred that do not. The
metrics that steer are the ones a page cannot satisfy merely by existing --
queries the site ranks for, how many of those reach the top 20 and top 10,
impressions earned, pages that actually earn impressions, referring domains,
sessions. Pages published and pages indexed are still measured and reported,
because they explain the others, but they carry no target and no weight.

Intensity escalates when the trajectory is behind. What escalation raises is
*production quota*: how many qualified families and pages get built, how much
discovery runs, how many reasoning runs are allowed. It never lowers the quality
gate. Being behind target is a reason to build more of what genuinely helps
someone, and never a reason to publish something that does not -- that route
leads to a scaled-content penalty, which is not a slower path to the target but
the end of it.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone

from growth_common import apply_schema, connect_db, database_path, record_escalation, utc_now

EXPERIMENT = "90day-2026Q4"
START_DATE = date(2026, 9, 2)
WEEKS = 13

# The band the owner set, and the midpoint the plan is built against.
TARGET_PAGEVIEWS_LOW = 300_000
TARGET_PAGEVIEWS_HIGH = 700_000
TARGET_PAGEVIEWS = 500_000
# Fallback only. The real figure is measured from analytics below, because
# assuming a friendly ratio quietly shrinks the target: at 1.0 pageviews per
# session, half a million pageviews needs half a million sessions, not 370,000.
PAGEVIEWS_PER_SESSION_DEFAULT = 1.2

# Terminal leading indicators consistent with that much traffic. Each one is
# something the market does in response to the work, so none of them can be
# satisfied by publishing. There is deliberately no page-count entry here: an
# earlier version carried one and it turned every week into an argument for
# more pages rather than better ones.
TERMINAL = {
    "ranking_queries": 4_000,
    "queries_top_20": 900,
    "queries_top_10": 400,
    "monthly_impressions": 1_400_000,
    "pages_with_impressions": 220,
    "referring_domains": 120,
}

# What each metric is worth when scoring attainment. Sessions are the goal but
# say nothing in week 2, so the ranking footprint carries the early weeks.
WEIGHTS = {
    "ranking_queries": 0.15,
    "queries_top_20": 0.15,
    "queries_top_10": 0.15,
    "monthly_impressions": 0.20,
    "pages_with_impressions": 0.10,
    "referring_domains": 0.10,
    "daily_sessions": 0.15,
}

# Measured and reported every week, never targeted and never weighted. They
# explain movement in the metrics above; on their own they are vanity.
DIAGNOSTIC_ONLY = ("published_pages", "indexed_pages", "addressable_demand",
                   "pages_with_traffic", "tool_starts", "pdf_downloads",
                   "daily_pageviews")

# Quotas are CEILINGS, never quotas to fill. `pages_per_week` is the most that
# may be built in a week, not an amount owed; a week that builds two excellent
# things at intensity 4 has done better than one that builds thirty adequate
# ones, and nothing here should be read as asking for the thirty.
INTENSITY = {
    1: {"name": "baseline", "claude_runs_per_day": 1, "pages_per_week": 2,
        "families_per_week": 0, "deep_discovery_per_week": 3, "budget_usd_per_day": 5},
    2: {"name": "elevated", "claude_runs_per_day": 2, "pages_per_week": 6,
        "families_per_week": 1, "deep_discovery_per_week": 3, "budget_usd_per_day": 12},
    3: {"name": "aggressive", "claude_runs_per_day": 4, "pages_per_week": 15,
        "families_per_week": 2, "deep_discovery_per_week": 7, "budget_usd_per_day": 30},
    4: {"name": "maximum", "claude_runs_per_day": 6, "pages_per_week": 30,
        "families_per_week": 3, "deep_discovery_per_week": 7, "budget_usd_per_day": 60},
    5: {"name": "saturation", "claude_runs_per_day": 8, "pages_per_week": 50,
        "families_per_week": 4, "deep_discovery_per_week": 7, "budget_usd_per_day": 100},
}

# Attainment bands that move intensity. Deliberately asymmetric: intensity rises
# fast when behind and falls one step at a time, because thrashing the quota
# every week produces worse work than holding a level.
ESCALATION = ((0.15, 5), (0.40, 4), (0.70, 3), (1.00, 2))


def week_ending(week: int) -> date:
    return START_DATE + timedelta(weeks=week)


def current_week(today: date | None = None) -> int:
    days = ((today or datetime.now(timezone.utc).date()) - START_DATE).days
    return max(0, min(WEEKS, days // 7))


def pageviews_per_session(connection: sqlite3.Connection) -> float:
    """Measured, not assumed. Currently about 1.0: visitors land on one tool
    page and use it, which makes the pageview target harder than a friendlier
    ratio would suggest."""
    row = connection.execute(
        """SELECT SUM(pageviews) p, SUM(sessions) s FROM ga4_acquisition
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ga4_acquisition)
              AND pageviews > 0"""
    ).fetchone()
    if row and row["s"] and row["p"]:
        return max(1.0, round(float(row["p"]) / float(row["s"]), 2))
    return PAGEVIEWS_PER_SESSION_DEFAULT


def _baseline(connection: sqlite3.Connection) -> dict:
    """Where the experiment actually starts. Measured, not assumed.

    Sessions here are ORGANIC sessions. Every visit so far has been direct or
    unassigned, and Search Console has recorded no clicks at all, so the honest
    organic baseline is zero. A floor of 1 keeps the ratio arithmetic defined;
    it does not pretend the traffic exists.
    """
    sessions = connection.execute(
        """SELECT AVG(daily) FROM (
             SELECT date, SUM(sessions) daily FROM ga4_acquisition
              WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ga4_acquisition)
                AND default_channel_group='Organic Search'
              GROUP BY date ORDER BY date DESC LIMIT 7)"""
    ).fetchone()[0]
    impressions = connection.execute(
        "SELECT COALESCE(SUM(gsc_impressions), 0) FROM metrics_daily"
    ).fetchone()[0]
    published = connection.execute(
        "SELECT COUNT(DISTINCT url) FROM page_content_stats"
    ).fetchone()[0]
    indexed = connection.execute(
        """SELECT COUNT(*) FROM index_diagnosis
            WHERE diagnosed_at=(SELECT MAX(diagnosed_at) FROM index_diagnosis)
              AND index_state='indexed'"""
    ).fetchone()[0]
    footprint = connection.execute(
        """SELECT COUNT(DISTINCT query) queries,
                  COUNT(DISTINCT CASE WHEN position <= 50 THEN query END) top50,
                  COUNT(DISTINCT CASE WHEN position <= 20 THEN query END) top20,
                  COUNT(DISTINCT CASE WHEN position <= 10 THEN query END) top10,
                  COUNT(DISTINCT CASE WHEN impressions > 0 THEN page END) pages_seen,
                  COUNT(DISTINCT CASE WHEN clicks > 0 THEN page END) pages_clicked,
                  COALESCE(SUM(impressions), 0) demand
             FROM gsc_query_facts
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_query_facts)"""
    ).fetchone()
    domains = connection.execute(
        "SELECT COUNT(DISTINCT placement_url) FROM placements WHERE status='live'"
    ).fetchone()[0]
    usage = connection.execute(
        """SELECT COALESCE(SUM(tool_starts), 0) starts,
                  COALESCE(SUM(pdf_downloads), 0) pdfs,
                  COALESCE(SUM(pageviews), 0) views
             FROM ga4_acquisition
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ga4_acquisition)"""
    ).fetchone()
    return {
        # Targeted. Each is something the market did, not something we published.
        "daily_sessions": max(1.0, float(sessions or 0)),
        "monthly_impressions": float(impressions or 1),
        "ranking_queries": float(footprint["queries"] or 1),
        "queries_top_20": float(footprint["top20"] or 0),
        "queries_top_10": float(footprint["top10"] or 0),
        "pages_with_impressions": float(footprint["pages_seen"] or 0),
        "referring_domains": float(domains or 0),
        # Reported only. Never scored; see DIAGNOSTIC_ONLY.
        "organic_sessions_measured": float(sessions or 0),
        "queries_top_50": float(footprint["top50"] or 0),
        "pages_with_traffic": float(footprint["pages_clicked"] or 0),
        # Search demand the site is actually visible to. Not total market
        # demand: no keyword-volume source is connected, and inventing one
        # would put a made-up number next to measured ones.
        "addressable_demand": float(footprint["demand"] or 0),
        "published_pages": float(published or 9),
        "indexed_pages": float(indexed or 1),
        "tool_starts": float(usage["starts"] or 0),
        "pdf_downloads": float(usage["pdfs"] or 0),
        "daily_pageviews": float(usage["views"] or 0),
    }


def required_weekly_growth(connection: sqlite3.Connection) -> dict:
    """The compounding rate the target implies, from today's real baseline."""
    baseline = _baseline(connection)
    terminal_sessions = TARGET_PAGEVIEWS / pageviews_per_session(connection) / 30.0
    start = max(1.0, baseline["daily_sessions"])
    factor = terminal_sessions / start
    weeks_left = max(1, WEEKS - current_week())
    weekly = factor ** (1.0 / weeks_left)
    return {
        "baseline_daily_organic_sessions": round(baseline["organic_sessions_measured"], 2),
        "baseline_used_for_arithmetic": round(start, 2),
        "pageviews_per_session_measured": pageviews_per_session(connection),
        "terminal_daily_sessions": round(terminal_sessions, 1),
        "multiple_required": round(factor, 1),
        "weeks_remaining": weeks_left,
        "weekly_growth_required": f"{(weekly - 1) * 100:.0f}%",
        "note": ("This is what the target arithmetically demands. It is reported "
                 "every week whether or not it is being met, because a plan that "
                 "quietly restates its own target is worth nothing."),
    }


def _curve(start: float, end: float, week: int) -> float:
    """Compounding path from start to end across the experiment."""
    if week <= 0:
        return start
    ratio = max(end, 1.0) / max(start, 0.5)
    return max(start, 0.5) * (ratio ** (min(week, WEEKS) / WEEKS))


def plan(connection: sqlite3.Connection, *, rebuild: bool = False) -> dict:
    """Write the weekly targets once. They are not adjusted to fit results."""
    existing = connection.execute(
        "SELECT COUNT(*) FROM growth_targets WHERE experiment=?", (EXPERIMENT,)
    ).fetchone()[0]
    if existing and not rebuild:
        return {"status": "already planned", "rows": existing,
                **reconcile_metrics(connection)}
    if rebuild:
        connection.execute("DELETE FROM growth_targets WHERE experiment=?", (EXPERIMENT,))

    baseline = _baseline(connection)
    terminal_sessions = TARGET_PAGEVIEWS / pageviews_per_session(connection) / 30.0
    ends = {**TERMINAL, "daily_sessions": terminal_sessions}
    rationale = {
        "daily_sessions": f"{TARGET_PAGEVIEWS:,} pageviews/month at "
                          f"{pageviews_per_session(connection)} measured pageviews "
                          "per session, over 30 days",
        "ranking_queries": "the breadth of the ranking footprint the destination "
                           "traffic implies, however many pages produce it",
        "queries_top_20": "queries on page two or better, where impressions begin",
        "queries_top_10": "queries on page one, where the clicks actually are",
        "pages_with_impressions": "pages the market found worth showing; a page that "
                                  "earns none never counts, however many exist",
        "monthly_impressions": "the destination sessions at a realistic blended CTR",
        "referring_domains": "authority needed for a young domain to rank the head terms",
    }
    rows = 0
    for week in range(WEEKS + 1):
        for metric, end in ends.items():
            target = _curve(baseline.get(metric, 1.0), end, week)
            connection.execute(
                """INSERT INTO growth_targets
                     (experiment, week, week_ending, metric, target, rationale)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(experiment, week, metric) DO UPDATE SET target=excluded.target""",
                (EXPERIMENT, week, week_ending(week).isoformat(), metric,
                 round(target, 2), rationale.get(metric, "")),
            )
            rows += 1
        connection.execute(
            """INSERT INTO growth_targets
                 (experiment, week, week_ending, metric, target, rationale)
               VALUES (?, ?, ?, 'monthly_pageviews', ?, ?)
               ON CONFLICT(experiment, week, metric) DO UPDATE SET target=excluded.target""",
            (EXPERIMENT, week, week_ending(week).isoformat(),
             round(_curve(baseline["daily_sessions"], terminal_sessions, week)
                   * 30 * pageviews_per_session(connection), 0),
             "sessions on the planned curve, converted to pageviews"),
        )
        rows += 1
    connection.commit()
    return {"status": "planned", "rows": rows, "experiment": EXPERIMENT,
            "requirement": required_weekly_growth(connection)}


def reconcile_metrics(connection: sqlite3.Connection) -> dict:
    """Bring the stored plan in line with the metric set, without touching a
    target that is still in it.

    When a metric stops being an objective its rows are dropped, and when one is
    added its rows are computed from the current baseline. Rows for metrics that
    survive the change are left exactly as written. That distinction matters:
    moving a target a metric is already being judged against would make a bad
    week look better, which is the one thing this file must never do.
    """
    wanted = set(TERMINAL) | {"daily_sessions", "monthly_pageviews"}
    present = {row["metric"] for row in connection.execute(
        "SELECT DISTINCT metric FROM growth_targets WHERE experiment=?", (EXPERIMENT,))}
    dropped = sorted(present - wanted)
    added = sorted(wanted - present)
    if not dropped and not added:
        return {"retargeted": False}
    for metric in dropped:
        connection.execute(
            "DELETE FROM growth_targets WHERE experiment=? AND metric=?",
            (EXPERIMENT, metric))
    if added:
        baseline = _baseline(connection)
        for metric in added:
            for week in range(WEEKS + 1):
                connection.execute(
                    """INSERT INTO growth_targets
                         (experiment, week, week_ending, metric, target, rationale)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(experiment, week, metric) DO NOTHING""",
                    (EXPERIMENT, week, week_ending(week).isoformat(), metric,
                     round(_curve(baseline.get(metric, 0.0), TERMINAL[metric], week), 2),
                     "added when the objective moved from page count to demand"))
    connection.commit()
    return {"retargeted": True, "metrics_dropped": dropped, "metrics_added": added,
            "note": ("Targets for metrics that stayed in the objective were not "
                     "recomputed. Only metrics that left or joined it changed.")}


def measure(connection: sqlite3.Connection) -> dict:
    """Where the experiment actually is, from evidence already collected."""
    live = _baseline(connection)
    live["monthly_pageviews"] = round(
        live["organic_sessions_measured"] * 30 * pageviews_per_session(connection), 0)
    return live


def intensity(connection: sqlite3.Connection) -> dict:
    row = connection.execute("SELECT * FROM intensity_state WHERE id=1").fetchone()
    if row is None:
        now = utc_now()
        connection.execute(
            """INSERT INTO intensity_state (id, level, since, reason, updated_at)
               VALUES (1, 1, ?, 'experiment not yet started', ?)""", (now, now))
        connection.commit()
        return {"level": 1, "since": now, "reason": "experiment not yet started",
                **INTENSITY[1]}
    return {"level": int(row["level"]), "since": row["since"], "reason": row["reason"],
            **INTENSITY[int(row["level"])]}


def _set_intensity(connection: sqlite3.Connection, level: int, reason: str) -> None:
    now = utc_now()
    connection.execute(
        """INSERT INTO intensity_state (id, level, since, reason, updated_at)
           VALUES (1, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET level=excluded.level, since=excluded.since,
             reason=excluded.reason, updated_at=excluded.updated_at""",
        (level, now, reason, now))
    connection.commit()


def attainment(connection: sqlite3.Connection, week: int | None = None) -> dict:
    """How far along the planned curve the experiment actually is."""
    week = current_week() if week is None else week
    targets = {row["metric"]: float(row["target"]) for row in connection.execute(
        "SELECT metric, target FROM growth_targets WHERE experiment=? AND week=?",
        (EXPERIMENT, week))}
    if not targets:
        return {"week": week, "attainment": 0.0, "detail": {},
                "note": "no plan for this week"}
    actual = measure(connection)
    detail, score, weight_used = {}, 0.0, 0.0
    for metric, weight in WEIGHTS.items():
        target = targets.get(metric)
        if not target:
            continue
        got = float(actual.get(metric, 0))
        ratio = min(1.5, got / target) if target > 0 else 0.0
        detail[metric] = {"target": round(target, 1), "actual": round(got, 1),
                          "ratio": round(ratio, 3)}
        score += weight * ratio
        weight_used += weight
    return {"week": week, "week_ending": week_ending(week).isoformat(),
            "attainment": round(score / weight_used, 3) if weight_used else 0.0,
            "detail": detail}


# The demand-side outcomes the floor reads. Both are things the market does, so
# neither can be closed by publishing; the floor cannot become an argument for
# page count no matter how far behind the experiment falls.
FLOOR_METRICS = ("ranking_queries", "monthly_impressions")


def structural_floor(connection: sqlite3.Connection) -> tuple[int, str]:
    """Minimum intensity implied by distance from the demand the target needs.

    The weekly curve is exponential, so early weeks are easy to "meet" while
    still being nowhere near the destination: a plan whose week-one bar is
    trivially cleared scores full marks and tells you nothing. This floor looks
    at the destination directly, so a structural shortfall raises production
    immediately instead of after a month of passing weeks.

    It reads the ranking footprint and impressions rather than the page count.
    That distinction is the whole point: a floor keyed to pages says "publish
    more" in every situation including the ones where publishing more is the
    problem, whereas a floor keyed to demand says "earn more", which is
    satisfied by better work as readily as by more of it.
    """
    live = measure(connection)
    shares = {metric: float(live.get(metric, 0)) / TERMINAL[metric]
              for metric in FLOOR_METRICS}
    binding = min(shares, key=shares.get)
    share = shares[binding]
    label = binding.replace("_", " ")
    for threshold, level in ((0.25, 4), (0.50, 3), (0.75, 2)):
        if share < threshold:
            return level, (
                f"{live.get(binding, 0):,.0f} {label} against the {TERMINAL[binding]:,} the "
                f"target implies ({share:.1%}). Structural shortfall on demand, so "
                f"intensity floors at {level} regardless of the weekly curve. What that "
                f"buys is more qualified work, never a lower bar or a larger page count.")
    return 1, "demand is broadly where the target needs it"


def checkpoint(connection: sqlite3.Connection, *, week: int | None = None) -> dict:
    """Weekly: measure, compare, and move intensity. This is the escalation."""
    week = current_week() if week is None else week
    result = attainment(connection, week)
    before = intensity(connection)["level"]

    wanted = 1
    for threshold, level in ESCALATION:
        if result["attainment"] < threshold:
            wanted = level
            break
    floor, floor_reason = structural_floor(connection)
    wanted = max(wanted, floor)
    # Reported whenever the floor is holding the level, not only when it raises
    # it. A week that "met the curve" while the floor independently demanded the
    # same intensity has not met anything, and the verdict should say so.
    if floor > 1 and floor >= wanted:
        result["structural_floor"] = floor_reason
    # Rises immediately when behind; falls one step at a time, because changing
    # the quota every week produces worse work than holding a level.
    after = wanted if wanted > before else max(wanted, before - 1)

    if after > before:
        verdict = (f"{result['attainment']:.0%} of the week {week} plan. Escalating to "
                   f"intensity {after} ({INTENSITY[after]['name']}): "
                   f"{INTENSITY[after]['pages_per_week']} qualified pages/week, "
                   f"{INTENSITY[after]['claude_runs_per_day']} reasoning runs/day. "
                   "The quality gate is unchanged -- escalation buys more of what "
                   "genuinely helps a user, never a lower bar.")
    elif after < before:
        verdict = (f"{result['attainment']:.0%} of the week {week} plan and ahead of "
                   f"the curve. Easing to intensity {after} ({INTENSITY[after]['name']}).")
    else:
        verdict = (f"{result['attainment']:.0%} of the week {week} plan. Holding "
                   f"intensity {after} ({INTENSITY[after]['name']}).")
    if result.get("structural_floor"):
        verdict += " " + result["structural_floor"]

    if after != before:
        _set_intensity(connection, after, verdict)
    connection.execute(
        """INSERT INTO trajectory_checkpoints
             (experiment, week, checked_at, metrics_json, attainment,
              intensity_before, intensity_after, verdict)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(experiment, week) DO UPDATE SET
             checked_at=excluded.checked_at, metrics_json=excluded.metrics_json,
             attainment=excluded.attainment, intensity_after=excluded.intensity_after,
             verdict=excluded.verdict""",
        (EXPERIMENT, week, utc_now(), json.dumps(result["detail"], sort_keys=True),
         result["attainment"], before, after, verdict))
    connection.commit()

    # Escalating to the ceiling and still being far behind is not a quota
    # problem, and quietly running at maximum forever would hide that.
    queued = 0
    try:
        queued = int(connection.execute(
            """SELECT COUNT(*) FROM page_candidates c JOIN page_families f
                    ON f.family_key=c.family_key
                WHERE c.status='queued' AND f.status IN ('admitted','built')"""
        ).fetchone()[0])
    except sqlite3.Error:
        pass
    if queued < INTENSITY[after]["pages_per_week"]:
        record_escalation(
            connection, kind="surface_queue_short", severity="info",
            subject=f"Qualified page queue ({queued}) is below the weekly ceiling "
                    f"({INTENSITY[after]['pages_per_week']})",
            detail=("Capacity now exceeds the supply of families that can pass the "
                    "admission gate. This is a note, not a shortfall: the ceiling is "
                    "the most that may be built, not an amount owed, and an empty "
                    "queue is a legitimate steady state. The response is more research "
                    "into genuinely differentiated families, never admitting weaker "
                    "ones -- a family whose only difference is wording costs the domain "
                    "more than its pages could ever earn."),
            fingerprint="surface_queue_short")
    if after >= 5 and result["attainment"] < 0.15 and week >= 4:
        record_escalation(
            connection, kind="trajectory_structural_gap", severity="warning",
            subject=f"Week {week}: at maximum intensity and below 15% of plan",
            detail=("Production quota is no longer the constraint. Either the "
                    "target needs restating or the strategy does; more pages at "
                    "this rate will not close a gap this size. "
                    + json.dumps(required_weekly_growth(connection))),
            fingerprint="trajectory_structural_gap")
    return {**result, "intensity_before": before, "intensity_after": after,
            "verdict": verdict, "quotas": INTENSITY[after]}


def status(connection: sqlite3.Connection) -> dict:
    week = current_week()
    return {
        "experiment": EXPERIMENT,
        "target_band": f"{TARGET_PAGEVIEWS_LOW:,}-{TARGET_PAGEVIEWS_HIGH:,} monthly pageviews",
        "week": week, "of": WEEKS, "week_ending": week_ending(week).isoformat(),
        "days_remaining": (week_ending(WEEKS) - datetime.now(timezone.utc).date()).days,
        "requirement": required_weekly_growth(connection),
        "measured_now": measure(connection),
        "attainment": attainment(connection),
        "intensity": intensity(connection),
        "recent_checkpoints": [dict(row) for row in connection.execute(
            """SELECT week, checked_at, attainment, intensity_after, verdict
                 FROM trajectory_checkpoints WHERE experiment=?
                ORDER BY week DESC LIMIT 5""", (EXPERIMENT,))],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="Write the weekly targets, once")
    planner.add_argument("--rebuild", action="store_true")
    commands.add_parser("status", help="Where the experiment is against plan")
    commands.add_parser("measure", help="Current values of every tracked metric")
    check = commands.add_parser("checkpoint", help="Weekly compare and escalate")
    check.add_argument("--week", type=int)
    commands.add_parser("quotas", help="Production quotas at the current intensity")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "plan":
        result = plan(connection, rebuild=args.rebuild)
    elif args.command == "status":
        result = status(connection)
    elif args.command == "measure":
        result = measure(connection)
    elif args.command == "checkpoint":
        result = checkpoint(connection, week=args.week)
    else:
        result = intensity(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
