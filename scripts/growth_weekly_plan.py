#!/usr/bin/env python3
"""Create and audit a deterministic Level-0 weekly evidence plan."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from growth_common import ROOT, apply_schema, connect_db, database_path
from growth_report import build_report

REQUIRED_DOCS = (
    "docs/SEO_STRATEGY.md",
    "docs/PRE_GROWTH_QA.md",
    "docs/SEARCH_BASELINE.md",
    "docs/PRODUCT_PRINCIPLES.md",
)
SAFE_DOMAIN = re.compile(r"^[a-z0-9.-]+$")


def _job_log(db: str | None, arguments: list[str], *, expected_codes: set[int]) -> dict:
    command = [sys.executable, str(ROOT / "scripts" / "growth_job_log.py")]
    if db:
        command.extend(("--db", db))
    command.extend(arguments)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode not in expected_codes:
        raise RuntimeError(f"growth job audit exited {completed.returncode}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("growth job audit returned invalid JSON") from error


def _source(report: dict, name: str) -> dict:
    for item in report["latest_sources"]:
        if item["source"] == name:
            return item
    raise ValueError(f"missing {name} source snapshot")


def validate_report(report: dict) -> dict[str, dict]:
    sources = {name: _source(report, name) for name in ("gsc", "ga4")}
    for name, source in sources.items():
        if source["status"] not in {"ok", "empty"} or source.get("error"):
            raise ValueError(f"latest {name} source snapshot is not successful")
    if not report["latest_health"]:
        raise ValueError("latest URL health evidence is missing")
    if not report["latest_index_state"]:
        raise ValueError("latest index evidence is missing")
    return sources


def _route(url: str) -> str:
    return urlsplit(url).path or "/"


def _safe_top_prospects(report: dict, limit: int = 3) -> list[str]:
    rendered = []
    for item in report["top_prospects"]:
        domain = str(item["domain"]).lower()
        if not SAFE_DOMAIN.fullmatch(domain):
            continue
        rendered.append(f"{domain} (score {int(item['opportunity_score'])})")
        if len(rendered) == limit:
            break
    return rendered


def render_plan(report: dict, generated_on: str) -> str:
    sources = validate_report(report)
    period = report["period"]
    totals = report["totals"]
    indexed = [row for row in report["latest_index_state"] if row["verdict"] == "PASS"]
    pending = [row for row in report["latest_index_state"] if row["verdict"] != "PASS"]
    healthy = [
        row for row in report["latest_health"]
        if row["status"] is not None and 200 <= row["status"] < 400 and not row["error"]
    ]
    source_line = ", ".join(
        f"{name.upper()} {sources[name]['status']} ({int(sources[name]['row_count'])} rows)"
        for name in ("gsc", "ga4")
    )
    indexed_routes = ", ".join(f"`{_route(row['url'])}`" for row in indexed) or "none"
    pending_routes = ", ".join(
        f"`{_route(row['url'])}` ({row['coverage_state'] or row['verdict'] or 'unknown'})"
        for row in pending
    ) or "none"
    prospects = ", ".join(_safe_top_prospects(report)) or "none"
    breakdown_counts = ", ".join(
        f"{name}={len(report['gsc_breakdowns'][name])}"
        for name in ("query", "page", "country", "device")
    )
    sitemap_ok = sum(
        1 for row in report["latest_sitemaps"]
        if not row["error"] and not row["errors"] and not row["warnings"]
    )
    ga_sessions = sum(row["ga_sessions"] or 0 for row in report["daily_metrics"])

    return f"""# InvoiceWorkshop Level-0 weekly plan — {generated_on}

Report period: {period['start']} through {period['end']} ({period['days']} calendar days).
Stored daily metric rows in that period: {len(report['daily_metrics'])}.
Latest persisted source evidence used: {source_line}.

## Observed evidence

- GA4 stored-row totals: {ga_sessions} sessions, {totals['ga_users']} users, {totals['ga_pageviews']} pageviews, {totals['ga_tool_starts']} tool starts, {totals['ga_pdf_downloads']} PDF downloads, and {totals['ga_returning']} returning workspace loads.
- GSC stored-row totals: {totals['gsc_clicks']} clicks and {totals['gsc_impressions']} impressions. Breakdown row counts: {breakdown_counts}. Empty search evidence is recorded without treating it as an indexation result or incident.
- Priority URL inspection: {len(indexed)} of {len(report['latest_index_state'])} pass. Indexed: {indexed_routes}.
- Other recorded index states: {pending_routes}. These states do not establish a technical cause.
- URL health: {len(healthy)} of {len(report['latest_health'])} checks are healthy. Sitemap rows without reported errors or warnings: {sitemap_ok} of {len(report['latest_sitemaps'])}.
- Research CRM: {report['prospect_count']} prospects; current top three evidence scores: {prospects}. Placements: {report['placement_count']}; outreach: {report['outreach_count']}.

## Continue

- Continue the bounded daily collection and read-only prospect research cadence.
- Keep the documented canonical route map, product principles, and SEO architecture frozen while search evidence is absent.
- Review index-state movement as observation only; do not infer causes from `NEUTRAL`, discovered, or unknown states.

## Stop or avoid

- Do not repeat indexing submissions, create doorway/synonym pages, or implement product/SEO changes from this plan.
- Do not send outreach, submit forms or listings, create accounts, post, pay, or mutate an external service.
- Do not manufacture query conclusions when GSC query/page/country/device evidence is empty.

## Next research allocation

- Favor public resource pages that explicitly accept relevant tool suggestions and reject backlink sellers, generic SEO directories, pay-to-link pages, and competitors without a credible editorial path.
- Preserve the daily bounds: at most two searches, one extraction call, three unique public pages, and two prospect additions.
- Reassess only when later stored evidence changes; recommendations remain Level-0 and read-only.

## Escalation

- None for indexation or empty GSC data alone. Escalate only a verified collector/authentication failure, unhealthy production URL, sitemap error, policy-row violation, or tripped operation pause.

External side effects: none.
"""


def _read_required_docs() -> list[str]:
    read = []
    for relative in REQUIRED_DOCS:
        content = (ROOT / relative).read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"required document is empty: {relative}")
        read.append(relative)
    return read


def _write_verified(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".weekly-", delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)
    if path.read_text(encoding="utf-8") != content:
        raise RuntimeError("weekly plan verification failed")


def run_weekly(
    *, db: str | None, period: int, hermes_job_id: str, output_dir: Path
) -> dict:
    started = _job_log(
        db,
        ["start", "--job", "weekly", "--hermes-job-id", hermes_job_id],
        expected_codes={0},
    )
    run_id = int(started["run_id"])
    try:
        documents = _read_required_docs()
        connection = connect_db(database_path(db))
        apply_schema(connection)
        report = build_report(connection, period)
        connection.close()
        sources = validate_report(report)
        plan_path = output_dir / f"{date.today().isoformat()}.md"
        _write_verified(plan_path, render_plan(report, date.today().isoformat()))
        finished = _job_log(
            db,
            ["finish", "--run-id", str(run_id), "--status", "success"],
            expected_codes={0},
        )
        result = {
            **finished,
            "plan_path": str(plan_path),
            "documents_read": documents,
            "evidence_rows_used": {
                "gsc": int(sources["gsc"]["row_count"]),
                "ga4": int(sources["ga4"]["row_count"]),
            },
            "report_period": report["period"],
            "priority_urls_recorded": len(report["latest_index_state"]),
            "prospects_total": int(report["prospect_count"]),
        }
        return result
    except Exception as error:
        message = f"weekly_plan: {type(error).__name__}: {error}"[:1000]
        _job_log(
            db,
            [
                "finish", "--run-id", str(run_id), "--status", "failure",
                "--error", message,
            ],
            expected_codes={2},
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--period", type=int, default=7)
    parser.add_argument("--hermes-job-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "plans")
    args = parser.parse_args()
    if not 1 <= args.period <= 90:
        parser.error("--period must be between 1 and 90")
    result = run_weekly(
        db=args.db,
        period=args.period,
        hermes_job_id=args.hermes_job_id,
        output_dir=args.output_dir.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
