#!/usr/bin/env python3
"""Verify real read-only GSC and GA4 access; never changes Google state."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta

from growth_common import BASE_URL
from growth_google import GoogleReadClient, GoogleReadError

DEFAULT_SITE = "sc-domain:invoiceworkshop.com"
DEFAULT_PROPERTY = "551485207"


def verify(client: GoogleReadClient, site: str, property_id: str) -> dict:
    result: dict = {"credential": str(client.credential_path), "gsc": {}, "ga4": {}, "ok": False}

    sites = client.list_gsc_sites().get("siteEntry", [])
    match = next((entry for entry in sites if entry.get("siteUrl") == site), None)
    if not match:
        visible = [entry.get("siteUrl") for entry in sites]
        raise GoogleReadError(f"GSC property {site} is not visible; visible properties: {visible}")
    end = date.today()
    start = end - timedelta(days=15)
    performance = client.query_gsc(
        site,
        {
            "startDate": str(start),
            "endDate": str(end),
            "dimensions": ["date"],
            "rowLimit": 25,
            "type": "web",
        },
    )
    sitemap_rows = client.list_sitemaps(site).get("sitemap", [])
    inspection = client.inspect_url(site, BASE_URL + "/")
    index = inspection.get("inspectionResult", {}).get("indexStatusResult", {})
    result["gsc"] = {
        "property": site,
        "permission": match.get("permissionLevel"),
        "performance_rows": len(performance.get("rows", [])),
        "sitemaps": [
            {"path": row.get("path"), "errors": row.get("errors"), "warnings": row.get("warnings")}
            for row in sitemap_rows
        ],
        "homepage_index": {
            "verdict": index.get("verdict"),
            "coverage_state": index.get("coverageState"),
            "indexing_state": index.get("indexingState"),
        },
    }

    property_name = f"properties/{property_id}"
    summaries = client.account_summaries().get("accountSummaries", [])
    found = None
    account = None
    for summary in summaries:
        for candidate in summary.get("propertySummaries", []):
            if candidate.get("property") == property_name:
                found = candidate
                account = summary
                break
    if not found:
        visible = [
            candidate.get("property")
            for summary in summaries
            for candidate in summary.get("propertySummaries", [])
        ]
        raise GoogleReadError(f"GA4 property {property_name} is not visible; visible properties: {visible}")

    streams = client.list_data_streams(property_id).get("dataStreams", [])
    report = client.run_ga_report(
        property_id,
        {
            "dateRanges": [{"startDate": str(start), "endDate": str(end)}],
            "metrics": [{"name": "sessions"}],
            "limit": 1,
        },
    )
    result["ga4"] = {
        "account": account.get("account"),
        "account_name": account.get("displayName"),
        "property": property_name,
        "property_name": found.get("displayName"),
        "report_rows": len(report.get("rows", [])),
        "streams": [
            {
                "name": stream.get("name"),
                "measurement_id": stream.get("webStreamData", {}).get("measurementId"),
                "default_uri": stream.get("webStreamData", {}).get("defaultUri"),
            }
            for stream in streams
        ],
    }
    result["ok"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=os.environ.get("GSC_SITE", DEFAULT_SITE))
    parser.add_argument("--property-id", default=os.environ.get("GA4_PROPERTY_ID", DEFAULT_PROPERTY))
    args = parser.parse_args()
    try:
        output = verify(GoogleReadClient(), args.site, args.property_id)
        print(json.dumps(output, indent=2, sort_keys=True))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2, sort_keys=True))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
