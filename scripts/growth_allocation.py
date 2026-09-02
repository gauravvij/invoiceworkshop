#!/usr/bin/env python3
"""Weekly effort reallocation across growth channels.

This is the part of the loop that closes. Each week it looks at what each
channel actually produced, moves the channel's weight, and that weight feeds
directly into `growth_opportunities.expected_growth_value`. A channel that keeps
failing therefore loses ranking ground and stops being worked on, without anyone
reading a report and deciding to act.

Two rules keep it honest:

* A weight only moves on a completed cohort of at least `min_sample` attempts.
  Below that the decision is recorded as `insufficient_evidence` and nothing
  changes. This is what stops one impression from being read as a trend.
* Weights are bounded. A failing channel is reduced, never zeroed, because a
  channel with no attempts can never produce the evidence that would revive it.

Read-only against the outside world: it reads the growth database and writes
weights and decisions back to it. It sends nothing and publishes nothing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from growth_common import apply_schema, connect_db, database_path, utc_now

CHANNELS = (
    "product_led_seo", "page_improvement", "technical_seo", "distribution",
    "linkable_assets", "utility_development", "ctr",
)

# How many completed attempts a channel needs before its outcomes are allowed to
# move anything. Distribution is higher because a single unanswered email says
# almost nothing, and because the cost of wrongly abandoning outreach is high.
MIN_SAMPLE = {
    "distribution": 10,
    "page_improvement": 2,
    "technical_seo": 2,
    "product_led_seo": 2,
    "linkable_assets": 1,
    "utility_development": 1,
    "ctr": 2,
}

WEIGHT_FLOOR, WEIGHT_CEILING = 0.2, 1.6
REDUCE_FACTOR, INCREASE_FACTOR = 0.7, 1.2

# The calibration cohort: how many organizations must finish their initial and
# follow-up cycle before the email channel is judged at all.
CALIBRATION_COHORT_MIN = 10
CALIBRATION_COHORT_TARGET = 15


def ensure_channels(connection: sqlite3.Connection) -> None:
    now = utc_now()
    for channel in CHANNELS:
        connection.execute(
            """INSERT INTO channel_allocation (channel, weight, min_sample, updated_at)
               VALUES (?, 1.0, ?, ?)
               ON CONFLICT(channel) DO UPDATE SET min_sample=excluded.min_sample""",
            (channel, MIN_SAMPLE[channel], now),
        )
    connection.commit()


# ---------------------------------------------------------------------------
# What each channel actually produced
# ---------------------------------------------------------------------------

def _experiment_outcomes(connection: sqlite3.Connection, action_types: tuple[str, ...]) -> dict:
    """Concluded experiments only. An experiment past its evaluation date with no
    conclusion is counted as an attempt awaiting judgement, not as a failure."""
    placeholders = ",".join("?" * len(action_types))
    rows = connection.execute(
        f"""SELECT outcome, evaluate_after, conclusion FROM growth_experiments
             WHERE action_type IN ({placeholders})""",
        action_types,
    ).fetchall()
    concluded = [row for row in rows if row["outcome"]]
    return {
        "attempts": len(concluded),
        "wins": sum(1 for row in concluded if row["outcome"] == "positive"),
        "running": len(rows) - len(concluded),
    }


def outreach_cohort(connection: sqlite3.Connection) -> dict:
    """Delivery, reply and placement outcomes for the approved outreach cohort.

    "Completed" means the organization has had its initial message and either a
    follow-up or a terminal event (reply, bounce, suppression). Judging a
    prospect that was emailed yesterday would be judging nothing.
    """
    approved = connection.execute(
        """SELECT id, organization, prospect_id, max_followups, suppression_state
             FROM level1a_actions
            WHERE execution_class='level1a_email' AND external_action_approved=1
              AND message_approved=1"""
    ).fetchall()
    classes = {
        row["id"]: row["prospect_type"]
        for row in connection.execute(
            """SELECT a.id AS id, p.prospect_type AS prospect_type
                 FROM level1a_actions a JOIN prospects p ON p.id=a.prospect_id"""
        )
    }

    by_class: dict[str, dict] = {}
    totals = {"cohort": len(approved), "completed": 0, "sent": 0, "delivered": 0,
              "bounced": 0, "replies": 0, "positive": 0, "placements": 0}
    for action in approved:
        sends = connection.execute(
            """SELECT attempt_number, delivery_state FROM level1a_action_audit
                WHERE action_id=? AND mode='live' AND external_side_effects='email_sent'
                ORDER BY attempt_number""",
            (action["id"],),
        ).fetchall()
        replies = connection.execute(
            "SELECT COUNT(*) FROM level1a_replies WHERE action_id=?", (action["id"],)
        ).fetchone()[0]
        positive = connection.execute(
            """SELECT COUNT(*) FROM level1a_replies
                WHERE action_id=? AND classification IN ('positive','information_requested')""",
            (action["id"],),
        ).fetchone()[0]
        placements = connection.execute(
            """SELECT COUNT(*) FROM placements p JOIN level1a_actions a ON a.prospect_id=p.prospect_id
                WHERE a.id=? AND p.status='live'""",
            (action["id"],),
        ).fetchone()[0]
        delivered = sum(1 for s in sends if s["delivery_state"] in ("submitted", "delivered"))
        bounced = sum(1 for s in sends if s["delivery_state"] == "bounced")

        # A cycle is complete once the follow-up has gone out, or once something
        # terminal happened that means no follow-up ever will.
        terminal = bool(replies or bounced or action["suppression_state"] != "active")
        complete = bool(sends) and (terminal or len(sends) > int(action["max_followups"] or 0))

        totals["sent"] += len(sends)
        totals["delivered"] += delivered
        totals["bounced"] += bounced
        totals["replies"] += replies
        totals["positive"] += positive
        totals["placements"] += placements
        totals["completed"] += int(complete)

        bucket = by_class.setdefault(
            classes.get(action["id"]) or "unknown",
            {"cohort": 0, "completed": 0, "sent": 0, "replies": 0, "positive": 0, "placements": 0},
        )
        bucket["cohort"] += 1
        bucket["completed"] += int(complete)
        bucket["sent"] += len(sends)
        bucket["replies"] += replies
        bucket["positive"] += positive
        bucket["placements"] += placements

    totals["by_class"] = by_class
    return totals


def calibrate_outreach(connection: sqlite3.Connection, *, record: bool = True) -> dict:
    """Judge the email channel once, on the calibration cohort, then recommend.

    This is the one-time decision the owner asked for: it exists so outreach
    stops needing per-prospect approval, in whichever direction the evidence
    points.
    """
    cohort = outreach_cohort(connection)
    completed = cohort["completed"]
    sent, delivered, bounced = cohort["sent"], cohort["delivered"], cohort["bounced"]
    replies, positive, placements = cohort["replies"], cohort["positive"], cohort["placements"]

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 3) if denominator else 0.0

    if completed < CALIBRATION_COHORT_MIN:
        recommendation = "CONTINUE_CALIBRATION"
        rationale = (
            f"{completed} of at least {CALIBRATION_COHORT_MIN} organizations have completed "
            f"their initial and follow-up cycle (target {CALIBRATION_COHORT_TARGET}). "
            "Judging the channel now would be judging noise."
        )
    elif rate(delivered, sent) < 0.8:
        recommendation = "MODIFY_POLICY_TEMPLATES"
        rationale = (f"Only {rate(delivered, sent):.0%} of {sent} messages were accepted for "
                     f"delivery ({bounced} bounced). Fix deliverability and contact-route "
                     "verification before judging the offer itself.")
    elif placements >= 2 or (positive >= 2 and rate(positive, completed) >= 0.15):
        recommendation = "SIGN_POLICY_AND_AUTONOMIZE"
        rationale = (f"{placements} placement(s) and {positive} positive repl(ies) from "
                     f"{completed} completed cycles. The channel works well enough that "
                     "per-prospect approval is now the bottleneck rather than the safeguard.")
    elif replies == 0 and completed >= CALIBRATION_COHORT_TARGET:
        recommendation = "STOP_CHANNEL"
        rationale = (f"{completed} completed cycles produced zero replies of any kind. "
                     "Continuing would be sending mail to people who have shown they do "
                     "not want it.")
    elif positive == 0 and placements == 0:
        recommendation = "REDUCE_EMAIL_ALLOCATION"
        rationale = (f"{replies} repl(ies), none positive, and no placements from "
                     f"{completed} completed cycles. Keep the channel open at lower "
                     "volume; spend the effort where it converts.")
    else:
        recommendation = "MODIFY_POLICY_TEMPLATES"
        rationale = (f"{positive} positive of {replies} repl(ies) across {completed} cycles: "
                     "some signal, not enough to widen. Adjust targeting or copy and "
                     "re-measure.")

    result = {
        "cohort_size": cohort["cohort"], "completed": completed,
        "sent": sent, "delivered": delivered, "bounced": bounced,
        "replies": replies, "positive_replies": positive, "placements": placements,
        "delivery_rate": rate(delivered, sent),
        "reply_rate": rate(replies, completed),
        "positive_reply_rate": rate(positive, completed),
        "placement_rate": rate(placements, completed),
        "by_class": cohort["by_class"],
        "recommendation": recommendation, "rationale": rationale,
    }
    if record:
        connection.execute(
            """INSERT INTO outreach_calibration
                 (evaluated_at, cohort_size, completed, sent, delivered, bounced, replies,
                  positive_replies, placements, by_class_json, recommendation, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (utc_now(), cohort["cohort"], completed, sent, delivered, bounced, replies,
             positive, placements, json.dumps(cohort["by_class"], sort_keys=True),
             recommendation, rationale),
        )
        connection.commit()
    return result


def channel_evidence(connection: sqlite3.Connection) -> dict[str, dict]:
    """One evidence record per channel: attempts, wins and what counted."""
    calibration = calibrate_outreach(connection, record=False)
    # Distribution is judged on completed outreach cycles, and a "win" is a
    # placement or a positive reply — not a message sent.
    distribution = {
        "attempts": calibration["completed"],
        "wins": calibration["placements"] + calibration["positive_replies"],
        "detail": (f"{calibration['completed']} completed cycles, "
                   f"{calibration['placements']} placements, "
                   f"{calibration['positive_replies']} positive replies "
                   f"(calibration says {calibration['recommendation']})"),
    }

    pages = _experiment_outcomes(connection, ("page_improvement", "content_gap", "content_refresh"))
    pages["detail"] = (f"{pages['attempts']} concluded page experiments, {pages['wins']} positive, "
                       f"{pages['running']} still inside their evaluation window")

    # Technical work is judged on whether URLs it was responsible for actually
    # became indexed, and only where the constraint was ours to fix.
    fixable = connection.execute(
        """SELECT COUNT(*) FROM index_diagnosis d
            WHERE d.diagnosed_at=(SELECT MAX(diagnosed_at) FROM index_diagnosis)
              AND d.blocking_checks<>''"""
    ).fetchone()[0]
    indexed = connection.execute(
        """SELECT COUNT(*) FROM index_diagnosis d
            WHERE d.diagnosed_at=(SELECT MAX(diagnosed_at) FROM index_diagnosis)
              AND d.index_state='indexed'"""
    ).fetchone()[0]
    waiting = connection.execute(
        """SELECT COUNT(*) FROM index_diagnosis d
            WHERE d.diagnosed_at=(SELECT MAX(diagnosed_at) FROM index_diagnosis)
              AND d.blocking_checks='' AND d.index_state<>'indexed'"""
    ).fetchone()[0]
    technical = {
        "attempts": fixable, "wins": 0,
        "detail": (f"{indexed} indexed, {fixable} URLs with a fixable prerequisite, "
                   f"{waiting} correctly published and simply not yet crawled "
                   "(nothing to fix; rewriting these would be churn)"),
    }

    ctr = _experiment_outcomes(connection, ("ctr",))
    ctr["detail"] = f"{ctr['attempts']} concluded CTR experiments, {ctr['wins']} positive"
    product = _experiment_outcomes(connection, ("product_led_seo", "new_landing_asset"))
    product["detail"] = f"{product['attempts']} concluded product-led experiments, {product['wins']} positive"
    assets = _experiment_outcomes(connection, ("linkable_asset",))
    assets["detail"] = f"{assets['attempts']} concluded asset experiments, {assets['wins']} positive"
    utility = _experiment_outcomes(connection, ("product_utility",))
    utility["detail"] = f"{utility['attempts']} concluded utility experiments, {utility['wins']} positive"

    return {
        "distribution": distribution,
        "page_improvement": pages,
        "technical_seo": technical,
        "ctr": ctr,
        "product_led_seo": product,
        "linkable_assets": assets,
        "utility_development": utility,
    }


# ---------------------------------------------------------------------------
# Reallocation
# ---------------------------------------------------------------------------

def reallocate(connection: sqlite3.Connection) -> dict:
    """Move channel weights on observed outcomes. This is the decision, not a
    description of one: the new weights are what ranking uses tomorrow."""
    ensure_channels(connection)
    now = utc_now()
    evidence = channel_evidence(connection)
    current = {
        row["channel"]: dict(row)
        for row in connection.execute("SELECT * FROM channel_allocation")
    }
    decisions = []
    for channel in CHANNELS:
        record = current[channel]
        found = evidence.get(channel, {"attempts": 0, "wins": 0, "detail": "no attempts recorded"})
        attempts, wins = int(found["attempts"]), int(found["wins"])
        previous = float(record["weight"])
        minimum = int(record["min_sample"])
        failures = int(record["consecutive_failures"])

        if attempts < minimum:
            decision, weight = "insufficient_evidence", previous
            rationale = (f"{attempts} completed attempt(s) against a minimum sample of "
                         f"{minimum}. Weight unchanged: too little happened to learn from.")
        elif wins == 0:
            failures += 1
            weight = max(WEIGHT_FLOOR, round(previous * REDUCE_FACTOR, 3))
            decision = "reduce" if weight < previous else "hold"
            rationale = (f"{attempts} completed attempt(s), no wins ({failures} consecutive "
                         f"failing review). Weight {previous} -> {weight}; effort moves to "
                         "channels that are producing.")
        elif wins / attempts >= 0.25:
            failures = 0
            weight = min(WEIGHT_CEILING, round(previous * INCREASE_FACTOR, 3))
            decision = "increase" if weight > previous else "hold"
            rationale = (f"{wins} win(s) from {attempts} attempt(s). Weight "
                         f"{previous} -> {weight}.")
        else:
            failures = 0
            decision, weight = "hold", previous
            rationale = (f"{wins} win(s) from {attempts} attempt(s): working, but not well "
                         "enough to take effort from anything else.")

        connection.execute(
            """UPDATE channel_allocation
                  SET weight=?, attempts=?, wins=?, consecutive_failures=?,
                      last_reason=?, updated_at=?
                WHERE channel=?""",
            (weight, attempts, wins, failures, rationale, now, channel),
        )
        connection.execute(
            """INSERT INTO allocation_decisions
                 (decided_at, channel, previous_weight, new_weight, attempts, wins,
                  evidence, decision, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, channel, previous, weight, attempts, wins, found["detail"], decision, rationale),
        )
        decisions.append({
            "channel": channel, "previous_weight": previous, "new_weight": weight,
            "attempts": attempts, "wins": wins, "decision": decision,
            "evidence": found["detail"], "rationale": rationale,
        })
    connection.commit()
    return {"decided_at": now, "decisions": decisions, "external_side_effects": "none"}


def due_experiments(connection: sqlite3.Connection) -> list[dict]:
    """Experiments whose evaluation date has passed and that still have no
    conclusion. Nothing is concluded early; nothing is left unconcluded either."""
    today = datetime.now(timezone.utc).date().isoformat()
    return [
        dict(row)
        for row in connection.execute(
            """SELECT id, opportunity_key, action, action_type, target_url, target_query,
                      started_at, evaluate_after, baseline_json
                 FROM growth_experiments
                WHERE outcome IS NULL AND evaluate_after <= ?
                ORDER BY evaluate_after""",
            (today,),
        )
    ]


def evaluate_due(connection: sqlite3.Connection) -> dict:
    """Conclude every experiment that is due, from measured movement alone."""
    concluded = []
    for experiment in due_experiments(connection):
        baseline = json.loads(experiment["baseline_json"] or "{}")
        url = experiment["target_url"]
        row = connection.execute(
            """SELECT COALESCE(SUM(impressions),0) AS impressions,
                      COALESCE(SUM(clicks),0) AS clicks,
                      AVG(position) AS position
                 FROM gsc_query_facts
                WHERE page=? AND snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_query_facts)""",
            (url,),
        ).fetchone()
        observed = {"impressions": int(row["impressions"]), "clicks": int(row["clicks"]),
                    "position": row["position"]}
        before_impressions = int(baseline.get("impressions") or 0)
        before_position = baseline.get("position")
        improved_position = (
            before_position is not None and observed["position"] is not None
            and observed["position"] < float(before_position) - 5
        )
        if observed["clicks"] > int(baseline.get("clicks") or 0):
            outcome = "positive"
        elif observed["impressions"] > before_impressions or improved_position:
            outcome = "positive"
        elif observed["impressions"] == before_impressions:
            outcome = "neutral"
        else:
            outcome = "negative"
        conclusion = (
            f"Impressions {before_impressions} -> {observed['impressions']}, "
            f"clicks {baseline.get('clicks')} -> {observed['clicks']}, "
            f"position {before_position} -> {observed['position']}. "
            "Single-page observation with no control; treat as weak evidence."
        )
        connection.execute(
            """UPDATE growth_experiments
                  SET observed_json=?, outcome=?, conclusion=?, concluded_at=?, updated_at=?
                WHERE id=?""",
            (json.dumps(observed, sort_keys=True), outcome, conclusion, utc_now(),
             utc_now(), experiment["id"]),
        )
        concluded.append({"id": experiment["id"], "action": experiment["action"],
                          "outcome": outcome, "conclusion": conclusion})
    connection.commit()
    return {"concluded": concluded, "count": len(concluded)}


def status(connection: sqlite3.Connection) -> dict:
    ensure_channels(connection)
    return {
        "channels": [
            dict(row) for row in connection.execute(
                "SELECT * FROM channel_allocation ORDER BY weight DESC, channel"
            )
        ],
        "recent_decisions": [
            dict(row) for row in connection.execute(
                "SELECT * FROM allocation_decisions ORDER BY id DESC LIMIT 14"
            )
        ],
        "experiments_due": len(due_experiments(connection)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Current channel weights and recent decisions")
    commands.add_parser("evidence", help="What each channel has actually produced")
    commands.add_parser("evaluate-experiments", help="Conclude experiments that are due")
    commands.add_parser("reallocate", help="Move channel weights on observed outcomes")
    commands.add_parser("outreach-calibration", help="Judge the outreach cohort and recommend")
    commands.add_parser("weekly", help="Evaluate due experiments, then reallocate")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "status":
        result = status(connection)
    elif args.command == "evidence":
        result = channel_evidence(connection)
    elif args.command == "evaluate-experiments":
        result = evaluate_due(connection)
    elif args.command == "reallocate":
        result = reallocate(connection)
    elif args.command == "outreach-calibration":
        result = calibrate_outreach(connection)
    else:
        result = {
            "experiments": evaluate_due(connection),
            "outreach_calibration": calibrate_outreach(connection),
            "reallocation": reallocate(connection),
        }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
