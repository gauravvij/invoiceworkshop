#!/usr/bin/env python3
"""Render a deterministic Level-0 evidence report from the local database."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from growth_common import apply_schema, connect_db, database_path


def rows_as_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def build_report(connection, period: int) -> dict:
    start = (date.today() - timedelta(days=period - 1)).isoformat()
    metrics = rows_as_dicts(connection.execute(
        "SELECT * FROM metrics_daily WHERE date>=? ORDER BY date", (start,)
    ).fetchall())
    sources = rows_as_dicts(connection.execute(
        """SELECT s.* FROM source_snapshots s
           JOIN (SELECT source, MAX(collected_at) latest FROM source_snapshots GROUP BY source) x
             ON x.source=s.source AND x.latest=s.collected_at
           ORDER BY s.source"""
    ).fetchall())
    health = rows_as_dicts(connection.execute(
        """SELECT h.* FROM url_health h
           WHERE h.date=(SELECT MAX(date) FROM url_health) ORDER BY h.url"""
    ).fetchall())
    index = rows_as_dicts(connection.execute(
        """SELECT i.* FROM index_state i
           WHERE i.date=(SELECT MAX(date) FROM index_state) ORDER BY i.url"""
    ).fetchall())
    sitemaps = rows_as_dicts(connection.execute(
        """SELECT s.* FROM sitemap_state s
           WHERE s.date=(SELECT MAX(date) FROM sitemap_state) ORDER BY s.path"""
    ).fetchall())
    prospects = rows_as_dicts(connection.execute(
        """SELECT id, domain, page_url, prospect_type, opportunity_score, risk,
                  why_fit, audience, contact_method, requires_account,
                  requires_payment, link_type, source_url, status,
                  external_action_approved, discovered_at
             FROM prospects ORDER BY opportunity_score DESC, id LIMIT 25"""
    ).fetchall())
    breakdowns = {}
    for dimension in ("query", "page", "country", "device"):
        breakdowns[dimension] = rows_as_dicts(connection.execute(
            """SELECT value, clicks, impressions, ctr, position, window_start, window_end
                 FROM gsc_breakdowns
                WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_breakdowns)
                  AND dimension=?
                ORDER BY impressions DESC, clicks DESC LIMIT 25""",
            (dimension,),
        ).fetchall())

    anomalies = []
    for row in health:
        if row["status"] is None or row["status"] >= 400 or row["error"]:
            anomalies.append({"type": "url_health", "url": row["url"], "detail": row["error"] or row["status"]})
    for row in index:
        if row["error"] or row["verdict"] != "PASS":
            anomalies.append({"type": "index_state", "url": row["url"], "detail": row["error"] or row["coverage_state"]})
    for row in sources:
        if row["status"] not in {"ok", "empty"}:
            anomalies.append({"type": "source", "source": row["source"], "detail": row["error"] or row["status"]})
    outreach_count = connection.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]
    approved_count = connection.execute("SELECT COUNT(*) FROM prospects WHERE external_action_approved=1").fetchone()[0]
    if outreach_count:
        anomalies.append({"type": "policy", "detail": f"Level 0 database contains {outreach_count} outreach rows"})
    if approved_count:
        anomalies.append({"type": "policy", "detail": f"Level 0 database contains {approved_count} externally approved prospects"})

    totals = {
        "gsc_clicks": sum(row["gsc_clicks"] or 0 for row in metrics),
        "gsc_impressions": sum(row["gsc_impressions"] or 0 for row in metrics),
        "ga_sessions": sum(row["ga_sessions"] or 0 for row in metrics),
        "ga_users": sum(row["ga_users"] or 0 for row in metrics),
        "ga_pageviews": sum(row["ga_pageviews"] or 0 for row in metrics),
        "ga_tool_starts": sum(row["ga_tool_starts"] or 0 for row in metrics),
        "ga_pdf_downloads": sum(row["ga_pdf_downloads"] or 0 for row in metrics),
        "ga_returning": sum(row["ga_returning"] or 0 for row in metrics),
    }
    return {
        "period": {"start": start, "end": date.today().isoformat(), "days": period},
        "totals": totals,
        "daily_metrics": metrics,
        "latest_sources": sources,
        "latest_health": health,
        "latest_index_state": index,
        "latest_sitemaps": sitemaps,
        "gsc_breakdowns": breakdowns,
        "prospect_count": connection.execute("SELECT COUNT(*) FROM prospects").fetchone()[0],
        "top_prospects": prospects,
        "placement_count": connection.execute("SELECT COUNT(*) FROM placements").fetchone()[0],
        "outreach_count": outreach_count,
        "anomalies": anomalies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--period", type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.period <= 90:
        parser.error("--period must be between 1 and 90")
    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    print(json.dumps(build_report(connection, args.period), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
