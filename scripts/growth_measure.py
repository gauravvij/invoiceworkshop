#!/usr/bin/env python3
"""Collect read-only GSC, GA4, sitemap, index, and URL-health evidence."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

from growth_common import (
    PRIORITY_URLS,
    apply_schema,
    connect_db,
    database_path,
    fetch_public_url,
    normalize_public_url,
    utc_now,
)
from growth_google import GoogleReadClient

DEFAULT_SITE = "sc-domain:invoiceworkshop.com"
DEFAULT_PROPERTY = "551485207"
EVENT_COLUMNS = {
    "tool_started": "ga_tool_starts",
    "pdf_downloaded": "ga_pdf_downloads",
    "returning_workspace_loaded": "ga_returning",
}


def ga_date(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def upsert_metric(connection, metric_date: str, fields: dict, collected_at: str) -> None:
    allowed = {
        "gsc_impressions", "gsc_clicks", "gsc_ctr", "gsc_avg_position",
        "ga_sessions", "ga_users", "ga_pageviews", "ga_tool_starts",
        "ga_pdf_downloads", "ga_returning",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown metric fields: {sorted(unknown)}")
    columns = ["date", *fields, "collected_at"]
    values = [metric_date, *[fields[column] for column in fields], collected_at]
    updates = ", ".join(f"{column}=excluded.{column}" for column in [*fields, "collected_at"])
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO metrics_daily ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}",
        values,
    )


def record_snapshot(connection, collected_at: str, source: str, start: str | None,
                    end: str | None, status: str, rows: int, totals: dict,
                    error: str | None = None) -> None:
    connection.execute(
        """INSERT INTO source_snapshots
           (collected_at, source, window_start, window_end, status, row_count, totals_json, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (collected_at, source, start, end, status, rows, json.dumps(totals, sort_keys=True), error),
    )


def collect_gsc(client: GoogleReadClient, connection, site: str, start: str,
                end: str, collected_at: str) -> dict:
    daily = client.query_gsc(site, {
        "startDate": start, "endDate": end, "dimensions": ["date"],
        "rowLimit": 500, "type": "web", "dataState": "final",
    }).get("rows", [])
    totals = {"clicks": 0, "impressions": 0}
    for row in daily:
        values = {
            "gsc_clicks": int(row.get("clicks", 0)),
            "gsc_impressions": int(row.get("impressions", 0)),
            "gsc_ctr": row.get("ctr"),
            "gsc_avg_position": row.get("position"),
        }
        upsert_metric(connection, row["keys"][0], values, collected_at)
        totals["clicks"] += values["gsc_clicks"]
        totals["impressions"] += values["gsc_impressions"]

    snapshot_date = date.today().isoformat()
    breakdown_counts = {}
    for dimension in ("query", "page", "country", "device"):
        rows = client.query_gsc(site, {
            "startDate": start, "endDate": end, "dimensions": [dimension],
            "rowLimit": 250, "type": "web", "dataState": "final",
        }).get("rows", [])
        connection.execute(
            "DELETE FROM gsc_breakdowns WHERE snapshot_date=? AND dimension=?",
            (snapshot_date, dimension),
        )
        for row in rows:
            connection.execute(
                """INSERT INTO gsc_breakdowns
                   (snapshot_date, dimension, value, clicks, impressions, ctr, position, window_start, window_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_date, dimension, row["keys"][0], int(row.get("clicks", 0)),
                    int(row.get("impressions", 0)), row.get("ctr"), row.get("position"),
                    start, end,
                ),
            )
        breakdown_counts[dimension] = len(rows)
    totals["breakdowns"] = breakdown_counts
    record_snapshot(
        connection, collected_at, "gsc", start, end,
        "ok" if daily else "empty", len(daily), totals,
    )
    return totals


def collect_ga4(client: GoogleReadClient, connection, property_id: str,
                start: str, end: str, collected_at: str) -> dict:
    daily = client.run_ga_report(property_id, {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "date"}],
        "metrics": [
            {"name": "sessions"}, {"name": "totalUsers"}, {"name": "screenPageViews"},
        ],
        "limit": 100,
    }).get("rows", [])
    event_rows = client.run_ga_report(property_id, {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "date"}, {"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": {
            "filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": list(EVENT_COLUMNS), "caseSensitive": True},
            }
        },
        "limit": 500,
    }).get("rows", [])

    by_date: dict[str, dict] = defaultdict(dict)
    totals = {"sessions": 0, "users": 0, "pageviews": 0, **{name: 0 for name in EVENT_COLUMNS}}
    for row in daily:
        day = ga_date(row["dimensionValues"][0]["value"])
        values = [int(item.get("value", 0)) for item in row.get("metricValues", [])]
        fields = {
            "ga_sessions": values[0] if len(values) > 0 else 0,
            "ga_users": values[1] if len(values) > 1 else 0,
            "ga_pageviews": values[2] if len(values) > 2 else 0,
        }
        by_date[day].update(fields)
        totals["sessions"] += fields["ga_sessions"]
        totals["users"] += fields["ga_users"]
        totals["pageviews"] += fields["ga_pageviews"]
    for row in event_rows:
        day = ga_date(row["dimensionValues"][0]["value"])
        event = row["dimensionValues"][1]["value"]
        count = int(row["metricValues"][0].get("value", 0))
        if event in EVENT_COLUMNS:
            by_date[day][EVENT_COLUMNS[event]] = count
            totals[event] += count
    for day, fields in by_date.items():
        for column in EVENT_COLUMNS.values():
            fields.setdefault(column, 0)
        upsert_metric(connection, day, fields, collected_at)

    record_snapshot(
        connection, collected_at, "ga4", start, end,
        "ok" if daily else "empty", len(daily), totals,
    )
    return totals


def collect_sitemaps(client: GoogleReadClient, connection, site: str,
                     collected_at: str) -> dict:
    rows = client.list_sitemaps(site).get("sitemap", [])
    today = date.today().isoformat()
    totals = {"count": len(rows), "errors": 0, "warnings": 0}
    for row in rows:
        errors = int(row.get("errors", 0))
        warnings = int(row.get("warnings", 0))
        totals["errors"] += errors
        totals["warnings"] += warnings
        connection.execute(
            """INSERT INTO sitemap_state
               (date, path, collected_at, errors, warnings, last_submitted, last_downloaded, is_pending, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
               ON CONFLICT(date, path) DO UPDATE SET
                 collected_at=excluded.collected_at, errors=excluded.errors,
                 warnings=excluded.warnings, last_submitted=excluded.last_submitted,
                 last_downloaded=excluded.last_downloaded, is_pending=excluded.is_pending,
                 error=NULL""",
            (
                today, row.get("path"), collected_at, errors, warnings,
                row.get("lastSubmitted"), row.get("lastDownloaded"), int(bool(row.get("isPending"))),
            ),
        )
    record_snapshot(connection, collected_at, "sitemap", today, today, "ok", len(rows), totals)
    return totals


def collect_inspections(client: GoogleReadClient, connection, site: str,
                        collected_at: str) -> dict:
    today = date.today().isoformat()
    passed = 0
    errors = []
    for url in PRIORITY_URLS:
        try:
            result = client.inspect_url(site, url).get("inspectionResult", {}).get("indexStatusResult", {})
            verdict = result.get("verdict")
            passed += int(verdict == "PASS")
            connection.execute(
                """INSERT INTO index_state
                   (date, url, inspected_at, verdict, coverage_state, indexing_state,
                    robots_state, fetch_state, last_crawl_time, google_canonical,
                    user_canonical, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(date, url) DO UPDATE SET
                    inspected_at=excluded.inspected_at, verdict=excluded.verdict,
                    coverage_state=excluded.coverage_state, indexing_state=excluded.indexing_state,
                    robots_state=excluded.robots_state, fetch_state=excluded.fetch_state,
                    last_crawl_time=excluded.last_crawl_time,
                    google_canonical=excluded.google_canonical,
                    user_canonical=excluded.user_canonical, error=NULL""",
                (
                    today, url, collected_at, verdict, result.get("coverageState"),
                    result.get("indexingState"), result.get("robotsTxtState"),
                    result.get("pageFetchState"), result.get("lastCrawlTime"),
                    result.get("googleCanonical"), result.get("userCanonical"),
                ),
            )
        except Exception as error:
            errors.append(f"{url}: {error}")
            connection.execute(
                """INSERT INTO index_state (date, url, inspected_at, error)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(date, url) DO UPDATE SET inspected_at=excluded.inspected_at, error=excluded.error""",
                (today, url, collected_at, str(error)),
            )
    status = "ok" if not errors else ("partial" if passed else "failed")
    record_snapshot(
        connection, collected_at, "inspection", today, today, status,
        len(PRIORITY_URLS), {"passed": passed, "checked": len(PRIORITY_URLS)},
        " | ".join(errors) if errors else None,
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    return {"passed": passed, "checked": len(PRIORITY_URLS)}


def collect_health(connection, collected_at: str) -> dict:
    today = date.today().isoformat()
    healthy = 0
    errors = []
    for url in PRIORITY_URLS:
        status = None
        final_url = None
        response_ms = None
        error_text = None
        try:
            response = fetch_public_url(url)
            status = response.status_code
            final_url = normalize_public_url(response.url)
            response_ms = getattr(response, "elapsed_total_ms", None)
            expected_url = normalize_public_url(url)
            if final_url != expected_url:
                error_text = f"unexpected final URL: {final_url}"
                errors.append(f"{url}: {error_text}")
            elif status >= 400:
                error_text = f"HTTP {status}"
                errors.append(f"{url}: {error_text}")
            else:
                healthy += int(200 <= status < 400)
        except Exception as error:
            error_text = str(error)
            errors.append(f"{url}: {error_text}")
        connection.execute(
            """INSERT INTO url_health (date, url, checked_at, status, final_url, response_ms, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, url) DO UPDATE SET checked_at=excluded.checked_at,
                 status=excluded.status, final_url=excluded.final_url,
                 response_ms=excluded.response_ms, error=excluded.error""",
            (today, url, collected_at, status, final_url, response_ms, error_text),
        )
    status = "ok" if not errors else ("partial" if healthy else "failed")
    record_snapshot(
        connection, collected_at, "health", today, today, status,
        len(PRIORITY_URLS), {"healthy": healthy, "checked": len(PRIORITY_URLS)},
        " | ".join(errors) if errors else None,
    )
    if errors:
        raise RuntimeError("; ".join(errors))
    return {"healthy": healthy, "checked": len(PRIORITY_URLS)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--lookback-days", type=int, default=int(os.environ.get("GROWTH_LOOKBACK_DAYS", "28")))
    parser.add_argument("--site", default=os.environ.get("GSC_SITE", DEFAULT_SITE))
    parser.add_argument("--property-id", default=os.environ.get("GA4_PROPERTY_ID", DEFAULT_PROPERTY))
    parser.add_argument("--public-only", action="store_true", help="Skip paused Google operations but retain public URL health")
    args = parser.parse_args()
    if not 7 <= args.lookback_days <= 90:
        parser.error("--lookback-days must be between 7 and 90")

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    collected_at = utc_now()
    connection.execute(
        """UPDATE collection_runs SET finished_at=?, status='failed', errors_json=?
            WHERE status='running'""",
        (
            collected_at,
            json.dumps(["previous collector process ended without a terminal status"]),
        ),
    )
    run = connection.execute(
        "INSERT INTO collection_runs (started_at, status) VALUES (?, 'running')", (collected_at,)
    )
    connection.commit()
    run_id = run.lastrowid
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=args.lookback_days - 1)).isoformat()
    errors = []
    summary = {}

    try:
        summary["health"] = collect_health(connection, collected_at)
        connection.commit()
    except Exception as error:
        errors.append(f"health: {error}")
        connection.commit()

    if args.public_only:
        client = None
        errors.append("google_reads: paused by bounded failure safeguard")
    else:
        try:
            client = GoogleReadClient()
        except Exception as error:
            client = None
            errors.append(f"google_auth: {error}")

    if client:
        for name, collector in (
            ("gsc", lambda: collect_gsc(client, connection, args.site, start, end, collected_at)),
            ("ga4", lambda: collect_ga4(client, connection, args.property_id, start, end, collected_at)),
            ("sitemap", lambda: collect_sitemaps(client, connection, args.site, collected_at)),
            ("inspection", lambda: collect_inspections(client, connection, args.site, collected_at)),
        ):
            try:
                summary[name] = collector()
            except Exception as error:
                errors.append(f"{name}: {error}")
            connection.commit()

    status = "ok" if not errors else ("partial" if summary else "failed")
    connection.execute(
        "UPDATE collection_runs SET finished_at=?, status=?, errors_json=? WHERE id=?",
        (utc_now(), status, json.dumps(errors), run_id),
    )
    connection.commit()
    print(json.dumps({"run_id": run_id, "status": status, "window": [start, end], "summary": summary, "errors": errors}, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
