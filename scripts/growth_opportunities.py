#!/usr/bin/env python3
"""Unified growth-opportunity model.

The job of this module is to let different KINDS of growth action compete on one
scale, so that improving a page which is gaining impressions can correctly
outrank emailing another mediocre resource page — and so that the reverse is
also possible when the evidence says so.

Scores are deliberately coarse. They exist to order work, not to look precise.
Everything is derived from evidence already in the growth database: Search
Console, GA4, URL inspection, the backlink pipeline and the outreach ledger.

Read-only against the outside world. Generating opportunities never sends,
publishes or changes the site.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from growth_common import apply_schema, connect_db, database_path, utc_now

# Canonical routes. The architecture is frozen, so an opportunity may only ever
# point at one of these.
CANONICAL = (
    "https://invoiceworkshop.com/",
    "https://invoiceworkshop.com/invoice-template/",
    "https://invoiceworkshop.com/construction-invoice-template/",
    "https://invoiceworkshop.com/contractor-invoice-template/",
    "https://invoiceworkshop.com/proforma-invoice-generator/",
    "https://invoiceworkshop.com/quotation-generator/",
    "https://invoiceworkshop.com/estimate-generator/",
    "https://invoiceworkshop.com/work-order-generator/",
    "https://invoiceworkshop.com/purchase-order-generator/",
)

# Rough click-through by rank. Used only to turn "position 80" into "no traffic"
# and "position 8" into "some traffic" without pretending to model a curve.
def ctr_at(position: float | None) -> float:
    if position is None or position <= 0:
        return 0.0
    for limit, rate in ((1.5, 0.28), (3, 0.15), (5, 0.08), (10, 0.03), (20, 0.01), (50, 0.002)):
        if position <= limit:
            return rate
    return 0.0005


# A thin page is a ranking and indexing liability on a young domain. Word counts
# come from the built output, so this is measured rather than assumed.
THIN_WORDS = 1000


def expected_growth_value(row: dict) -> float:
    """Coarse expected value: upside x confidence x intent, discounted by effort.

    Deliberately simple and inspectable. Unknown inputs score conservatively —
    a missing number never inflates a score.
    """
    upside = float(row.get("expected_upside") or 0)
    confidence = float(row.get("confidence") or 0.3)
    intent = float(row.get("intent_quality") or 0.5)
    feasibility = float(row.get("feasibility") or 0.3)
    authority = float(row.get("authority_benefit") or 0.0)
    effort = max(0.25, float(row.get("effort_days") or 1.0))
    time_to_impact = max(7, int(row.get("time_to_impact_days") or 30))

    # Authority is worth something even when direct traffic upside is nil: on a
    # new domain it is the constraint on everything else.
    value = (upside * intent * feasibility) + (authority * 40)
    value *= confidence
    # Slower payoffs are discounted, but never to zero.
    value *= 30.0 / time_to_impact
    return round(value / effort, 2)


def _latest_metrics(connection: sqlite3.Connection) -> dict:
    row = connection.execute(
        """SELECT date, gsc_impressions, gsc_clicks, gsc_avg_position,
                  ga_sessions, ga_tool_starts, ga_pdf_downloads
             FROM metrics_daily WHERE gsc_impressions IS NOT NULL
            ORDER BY date DESC LIMIT 1"""
    ).fetchone()
    return dict(row) if row else {}


def _index_state(connection: sqlite3.Connection) -> dict[str, dict]:
    latest = connection.execute(
        "SELECT MAX(date) FROM index_state"
    ).fetchone()[0]
    if not latest:
        return {}
    return {
        row["url"]: dict(row)
        for row in connection.execute(
            "SELECT * FROM index_state WHERE date=?", (latest,)
        )
    }


def _query_facts(connection: sqlite3.Connection) -> list[dict]:
    latest = connection.execute("SELECT MAX(snapshot_date) FROM gsc_query_facts").fetchone()[0]
    if not latest:
        return []
    return [
        dict(row)
        for row in connection.execute(
            """SELECT query, page, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
                      AVG(position) AS position
                 FROM gsc_query_facts WHERE snapshot_date=?
                GROUP BY query, page ORDER BY impressions DESC""",
            (latest,),
        )
    ]


def measure_pages(connection: sqlite3.Connection, dist: Path | None = None) -> dict:
    """Measure content depth from the built site. Facts, not estimates."""
    root = Path(dist or Path(__file__).resolve().parents[1] / "dist")
    now = utc_now()
    measured = {}
    for url in CANONICAL:
        path = url.replace("https://invoiceworkshop.com", "").strip("/")
        target = root / (path + "/index.html") if path else root / "index.html"
        if not target.is_file():
            continue
        html = target.read_text(encoding="utf-8", errors="ignore")
        body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", body)
        words = len(re.sub(r"\s+", " ", text).split())
        headings = len(re.findall(r"<h2", html, re.I))
        internal = len(set(re.findall(r'href="(/[a-z0-9-]*/)"', html)))
        connection.execute(
            """INSERT INTO page_content_stats (url, measured_at, words, headings, bytes, internal_out)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(url, measured_at) DO UPDATE SET words=excluded.words""",
            (url, now, words, headings, len(html), internal),
        )
        measured[url] = words
    connection.commit()
    return measured


def _page_words(connection: sqlite3.Connection) -> dict[str, int]:
    """Latest measured word count per canonical page."""
    words: dict[str, int] = {}
    try:
        for row in connection.execute(
            """SELECT url, words FROM page_content_stats s
                WHERE measured_at=(SELECT MAX(measured_at) FROM page_content_stats
                                    WHERE url=s.url)"""
        ):
            words[row["url"]] = int(row["words"] or 0)
    except sqlite3.Error:
        pass
    return words


# ---------------------------------------------------------------------------
# Generators. Each returns opportunity dicts; none of them act.
# ---------------------------------------------------------------------------

def from_indexing(connection: sqlite3.Connection) -> list[dict]:
    """Unindexed canonical pages: nothing else can work until these are in."""
    out = []
    for url, row in _index_state(connection).items():
        if url not in CANONICAL:
            continue
        coverage = (row.get("coverage_state") or "").lower()
        if row.get("verdict") == "PASS" and "indexed" in coverage:
            continue
        unknown = "unknown" in coverage
        out.append({
            "opportunity_key": f"index:{url}",
            "opportunity_type": "TECHNICAL_SEO",
            "title": f"Get {url.replace('https://invoiceworkshop.com','') or '/'} indexed",
            "target_url": url,
            "evidence": f"URL inspection reports: {row.get('coverage_state')}",
            "evidence_strength": "strong",
            # An unindexed page earns nothing at all, so the upside is whatever
            # the page would plausibly earn once it ranks at all.
            "expected_upside": 40 if unknown else 60,
            "feasibility": 0.35 if unknown else 0.5,
            "intent_quality": 0.9,
            "authority_benefit": 0.0,
            "confidence": 0.45,
            "effort_days": 0.5,
            "time_to_impact_days": 30,
            "reversible": 1, "risk": "low",
            "execution_tier": "AUTO",
        })
    return out


def from_thin_pages(connection: sqlite3.Connection, words: dict[str, int]) -> list[dict]:
    """Thin canonical pages that already draw impressions are the best targets."""
    facts = _query_facts(connection)
    by_page: dict[str, dict] = {}
    for fact in facts:
        page = fact["page"]
        entry = by_page.setdefault(page, {"impressions": 0, "clicks": 0, "position": [], "queries": []})
        entry["impressions"] += int(fact["impressions"] or 0)
        entry["clicks"] += int(fact["clicks"] or 0)
        if fact["position"]:
            entry["position"].append(float(fact["position"]))
        entry["queries"].append(fact["query"])
    index = _index_state(connection)
    out = []
    for url in CANONICAL:
        count = words.get(url)
        if count is None or count >= THIN_WORDS:
            continue
        seen = by_page.get(url, {})
        impressions = int(seen.get("impressions") or 0)
        positions = seen.get("position") or []
        position = sum(positions) / len(positions) if positions else None
        indexed = (index.get(url, {}).get("verdict") == "PASS")
        # Evidence is strongest where the page is indexed AND already surfacing.
        strength = "strong" if (indexed and impressions) else "moderate" if indexed else "weak"
        out.append({
            "opportunity_key": f"depth:{url}",
            "opportunity_type": "SEO_PAGE_IMPROVEMENT",
            "title": f"Deepen thin page {url.replace('https://invoiceworkshop.com','') or '/'} ({count} words)",
            "target_url": url,
            "target_query": (seen.get("queries") or [None])[0],
            "evidence": (
                f"{count} words vs {THIN_WORDS} target; indexed={indexed}; "
                f"impressions={impressions}; avg position={round(position,1) if position else 'n/a'}"
            ),
            "evidence_strength": strength,
            "current_impressions": impressions,
            "current_clicks": int(seen.get("clicks") or 0),
            "current_position": position,
            "expected_upside": 120 if (indexed and impressions) else 60 if indexed else 25,
            "feasibility": 0.6 if indexed else 0.3,
            "intent_quality": 0.9,
            "authority_benefit": 0.1,
            "confidence": 0.5 if indexed else 0.3,
            "effort_days": 0.5,
            "time_to_impact_days": 45,
            "reversible": 1, "risk": "low",
            "execution_tier": "AUTO",
        })
    return out


def from_ctr(connection: sqlite3.Connection) -> list[dict]:
    """Only worth raising once a page has impressions AND a rankable position."""
    out = []
    for fact in _query_facts(connection):
        impressions = int(fact["impressions"] or 0)
        position = float(fact["position"] or 0)
        clicks = int(fact["clicks"] or 0)
        # Below roughly page 2 there is no CTR problem to fix, only a ranking one.
        if impressions < 50 or position > 20 or clicks:
            continue
        out.append({
            "opportunity_key": f"ctr:{fact['page']}:{fact['query']}",
            "opportunity_type": "CTR_IMPROVEMENT",
            "title": f"Improve SERP CTR for '{fact['query']}'",
            "target_url": fact["page"], "target_query": fact["query"],
            "evidence": f"{impressions} impressions at position {round(position,1)} with {clicks} clicks",
            "evidence_strength": "strong",
            "current_impressions": impressions, "current_clicks": clicks,
            "current_position": position,
            "expected_upside": int(impressions * ctr_at(position)),
            "feasibility": 0.7, "intent_quality": 0.9, "confidence": 0.5,
            "effort_days": 0.25, "time_to_impact_days": 21,
            "reversible": 1, "risk": "low", "execution_tier": "AUTO",
        })
    return out


def from_emerging_queries(connection: sqlite3.Connection) -> list[dict]:
    """Queries the site is already surfacing for are the cheapest to pursue."""
    out = []
    for fact in _query_facts(connection):
        impressions = int(fact["impressions"] or 0)
        if impressions < 1:
            continue
        position = float(fact["position"] or 0)
        out.append({
            "opportunity_key": f"query:{fact['query']}",
            "opportunity_type": "SERP_GAP",
            "title": f"Pursue emerging query '{fact['query']}'",
            "target_url": fact["page"], "target_query": fact["query"],
            "evidence": f"{impressions} impressions at avg position {round(position,1)}",
            "evidence_strength": "moderate" if impressions >= 3 else "weak",
            "current_impressions": impressions,
            "current_position": position,
            # Real demand exists but the site is far off the first page, so the
            # realistic near-term upside is small.
            "expected_upside": 30 if position <= 40 else 10,
            "feasibility": 0.35 if position <= 40 else 0.2,
            "intent_quality": 0.95,
            "authority_benefit": 0.0,
            "confidence": 0.35,
            "effort_days": 1.0, "time_to_impact_days": 60,
            "reversible": 1, "risk": "low", "execution_tier": "REVIEW",
        })
    return out


def from_backlink_pipeline(connection: sqlite3.Connection) -> list[dict]:
    """Outreach competes on the same scale as everything else, not above it."""
    rows = connection.execute(
        """SELECT domain, page_url, target_url, tier, total_score, contact_kind, recipient,
                  tool_link_count
             FROM backlink_opportunities WHERE tier IN ('A','B')
            ORDER BY total_score DESC LIMIT 25"""
    ).fetchall()
    contacted = {
        row["domain"] for row in connection.execute(
            "SELECT DISTINCT domain FROM prospects WHERE status='qualified'"
        )
    }
    out = []
    for row in rows:
        if row["domain"] in contacted:
            continue
        tools = int(row["tool_link_count"] or -1)
        # Placement probability drives this, not the SEO score.
        placement = 0.25 if tools >= 3 else 0.15 if tools >= 1 else 0.05
        out.append({
            "opportunity_key": f"outreach:{row['domain']}",
            "opportunity_type": "RESOURCE_OUTREACH",
            "title": f"Resource outreach to {row['domain']}",
            "target_url": row["target_url"],
            "evidence": (
                f"Tier {row['tier']} score {row['total_score']}, links to {tools} third-party tools, "
                f"contact route {row['contact_kind']}"
            ),
            "evidence_strength": "moderate" if tools >= 1 else "weak",
            # One editorial link on a young domain is worth little traffic
            # directly; its value is almost entirely authority.
            "expected_upside": 5,
            "feasibility": placement,
            "intent_quality": 0.4,
            "authority_benefit": 0.35 if tools >= 3 else 0.2,
            "confidence": 0.4,
            "effort_days": 0.2,
            "time_to_impact_days": 90,
            "reversible": 1, "risk": "low",
            "execution_tier": "AUTO" if row["contact_kind"] == "email" else "REVIEW",
        })
    return out


def from_linkable_assets(connection: sqlite3.Connection) -> list[dict]:
    """Assets that earn citations without asking. Seeded from real page demand."""
    seeds = [
        ("retainage-calculator", "Construction retainage & progress-draw calculator",
         "https://invoiceworkshop.com/construction-invoice-template/",
         "Construction billing is the only cluster with query impressions so far, and "
         "retainage is the hardest part of it to compute by hand.", 0.55, 2.0, 0.4),
        ("payment-terms-reference", "Payment terms reference (net terms, late-payment rules)",
         "https://invoiceworkshop.com/invoice-template/",
         "Late payment is the single most cited freelancer problem in the pages our own "
         "outreach research surfaced; a factual reference is citable without inventing data.",
         0.45, 1.5, 0.3),
        ("invoice-numbering-guide", "Invoice numbering schemes utility",
         "https://invoiceworkshop.com/invoice-template/",
         "The product already generates numbering sequences, so the utility is close to "
         "existing functionality.", 0.35, 1.0, 0.2),
    ]
    out = []
    for key, title, target, evidence, feasibility, effort, authority in seeds:
        out.append({
            "opportunity_key": f"asset:{key}",
            "opportunity_type": "LINKABLE_ASSET",
            "title": title, "target_url": target,
            "evidence": evidence, "evidence_strength": "moderate",
            "expected_upside": 60, "feasibility": feasibility,
            "intent_quality": 0.6, "authority_benefit": authority,
            "confidence": 0.35, "effort_days": effort, "time_to_impact_days": 90,
            "reversible": 1, "risk": "low", "execution_tier": "REVIEW",
        })
    return out


GENERATORS = (
    ("indexing", lambda c, w: from_indexing(c)),
    ("thin_pages", from_thin_pages),
    ("ctr", lambda c, w: from_ctr(c)),
    ("emerging_queries", lambda c, w: from_emerging_queries(c)),
    ("backlinks", lambda c, w: from_backlink_pipeline(c)),
    ("linkable_assets", lambda c, w: from_linkable_assets(c)),
)


def refresh(connection: sqlite3.Connection, words: dict[str, int] | None = None) -> dict:
    now = utc_now()
    if words is None:
        measure_pages(connection)
        words = _page_words(connection)
    counts: dict[str, int] = {}
    for name, generator in GENERATORS:
        rows = generator(connection, words)
        counts[name] = len(rows)
        for row in rows:
            row["expected_growth_value"] = expected_growth_value(row)
            connection.execute(
                """INSERT INTO growth_opportunities (
                     opportunity_key, opportunity_type, title, target_url, target_query,
                     evidence, evidence_strength, current_impressions, current_clicks,
                     current_position, demand_estimate, feasibility, intent_quality,
                     expected_upside, authority_benefit, effort_days, confidence,
                     time_to_impact_days, reversible, risk, expected_growth_value,
                     execution_tier, first_seen_at, updated_at)
                   VALUES (:opportunity_key, :opportunity_type, :title, :target_url, :target_query,
                     :evidence, :evidence_strength, :current_impressions, :current_clicks,
                     :current_position, :demand_estimate, :feasibility, :intent_quality,
                     :expected_upside, :authority_benefit, :effort_days, :confidence,
                     :time_to_impact_days, :reversible, :risk, :expected_growth_value,
                     :execution_tier, :now, :now)
                   ON CONFLICT(opportunity_key) DO UPDATE SET
                     title=excluded.title, evidence=excluded.evidence,
                     evidence_strength=excluded.evidence_strength,
                     current_impressions=excluded.current_impressions,
                     current_clicks=excluded.current_clicks,
                     current_position=excluded.current_position,
                     expected_upside=excluded.expected_upside,
                     feasibility=excluded.feasibility, confidence=excluded.confidence,
                     expected_growth_value=excluded.expected_growth_value,
                     execution_tier=excluded.execution_tier,
                     updated_at=excluded.updated_at""",
                {
                    "demand_estimate": None, "target_query": None,
                    "current_impressions": None, "current_clicks": None,
                    "current_position": None, **row, "now": now,
                },
            )
    connection.commit()
    return {"generated": counts, "total": sum(counts.values()), "external_side_effects": "none"}


def ranked(connection: sqlite3.Connection, limit: int = 10, tier: str | None = None) -> list[dict]:
    clause = " AND execution_tier=?" if tier else ""
    args = [tier, limit] if tier else [limit]
    return [
        dict(row)
        for row in connection.execute(
            f"""SELECT * FROM growth_opportunities
                 WHERE state='open'{clause}
                 ORDER BY expected_growth_value DESC, evidence_strength DESC LIMIT ?""",
            args,
        )
    ]


def record_experiment(connection: sqlite3.Connection, *, opportunity_key: str | None,
                      hypothesis: str, action: str, action_type: str,
                      target_url: str | None, target_query: str | None,
                      baseline: dict, expected: str, days: int = 30) -> int:
    now = datetime.now(timezone.utc)
    cursor = connection.execute(
        """INSERT INTO growth_experiments (
             opportunity_key, hypothesis, action, action_type, target_url, target_query,
             started_at, evaluate_after, baseline_json, expected_outcome,
             attribution_note, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (opportunity_key, hypothesis, action, action_type, target_url, target_query,
         now.isoformat(), (now + timedelta(days=days)).date().isoformat(),
         json.dumps(baseline, sort_keys=True), expected,
         "Do not attribute a ranking change to this action alone; other actions "
         "and normal index volatility overlap the same window.", now.isoformat()),
    )
    connection.commit()
    return int(cursor.lastrowid)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("refresh", help="Rebuild opportunities from current evidence")
    commands.add_parser("measure", help="Measure content depth from the built site")
    show = commands.add_parser("top", help="Show the highest expected-value opportunities")
    show.add_argument("--limit", type=int, default=10)
    show.add_argument("--tier")
    commands.add_parser("experiments", help="List experiments and their evaluation dates")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "refresh":
        result = refresh(connection)
    elif args.command == "measure":
        result = {"measured": measure_pages(connection)}
    elif args.command == "top":
        result = {"opportunities": ranked(connection, args.limit, args.tier)}
    else:
        result = {"experiments": [
            dict(row) for row in connection.execute(
                "SELECT * FROM growth_experiments ORDER BY id DESC LIMIT 25"
            )
        ]}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
