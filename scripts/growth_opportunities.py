#!/usr/bin/env python3
"""Unified growth-opportunity model.

The job of this module is to let different KINDS of growth action compete on one
scale, so that improving a page which is gaining impressions can correctly
outrank emailing another mediocre resource page — and so that the reverse is
also possible when the evidence says so.

Three things it deliberately does NOT do:

* It does not treat page length as an objective. Google states no preferred word
  count, and this site has no evidence that longer pages rank better. Word count
  is recorded as diagnostic context; what generates a page-improvement
  opportunity is *missing user value* — an unanswered query the page already
  surfaces for, a missing worked example, a missing comparison between the
  documents users confuse.
* It does not read every unindexed URL as a content problem. The four index
  states have different causes and only one of them implicates the page itself.
  See `diagnose_index`.
* It does not report point estimates it cannot support. With a handful of
  lifetime impressions, "45.9 versus 24.3" is false precision. Values carry an
  uncertainty range and are grouped into broad priority bands; measured signal
  progressively outweighs the prior as traffic accumulates.

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

# Canonical routes, read from the page data rather than restated here.
# The site now adds pages by adding entries to `generators`, so a hardcoded list
# would silently stop measuring every page added after it was written.
_GENERATORS = Path(__file__).resolve().parents[1] / "src" / "content" / "generators.ts"
# Not every tool page is a `generators` entry. A tool with its own interactive
# island -- the progress draw schedule -- is a hand-written route, and reading
# only `generators` measured the site as if it did not exist. Both sources are
# read, because "what pages exist" has two of them.
_PAGES = Path(__file__).resolve().parents[1] / "src" / "pages"
# Routes that exist but are not tools: legal and contact pages carry no growth
# opportunity and would only dilute every per-page ranking they appeared in.
_NON_TOOL_ROUTES = frozenset({"/about/", "/privacy/", "/terms/", "/contact/", "/404/"})
_FALLBACK = (
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


def canonical_routes() -> tuple[str, ...]:
    """Every tool page, taken from the source of truth for what exists."""
    try:
        text = _GENERATORS.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK
    paths = re.findall(r"^\s*path:\s*'(/[a-z0-9/-]*)'", text, re.M)
    if not paths:
        return _FALLBACK
    paths.extend(_standalone_routes())
    seen, routes = set(), []
    for path in paths:
        url = "https://invoiceworkshop.com" + path
        if url not in seen:
            seen.add(url)
            routes.append(url)
    return tuple(routes)


def _standalone_routes() -> list[str]:
    """Tool pages that are their own .astro file rather than a data entry."""
    routes = []
    try:
        for page in sorted(_PAGES.glob("*/index.astro")):
            name = page.parent.name
            # `[slug]` is the dynamic route that renders the `generators`
            # entries; it is a template, not a page, and counting it would put a
            # literal "[slug]" URL into every ranking and every crawl.
            if name.startswith("["):
                continue
            route = f"/{name}/"
            if route not in _NON_TOOL_ROUTES:
                routes.append(route)
    except OSError:
        return []
    return routes


CANONICAL = canonical_routes()

# Which allocation channel each opportunity type belongs to. The weekly
# reallocation moves weight between these, and the weight is applied here, so a
# channel that repeatedly fails actually loses ranking ground.
CHANNEL_OF = {
    "NEW_SEARCH_LANDING_ASSET": "product_led_seo",
    "SERP_GAP": "product_led_seo",
    "AI_SEARCH_VISIBILITY_OPPORTUNITY": "product_led_seo",
    "SEO_PAGE_IMPROVEMENT": "page_improvement",
    "CONTENT_REFRESH": "page_improvement",
    "TECHNICAL_SEO": "technical_seo",
    "INTERNAL_LINKING": "technical_seo",
    "RESOURCE_OUTREACH": "distribution",
    "DIRECTORY_DISTRIBUTION": "distribution",
    "COMMUNITY_OPPORTUNITY": "distribution",
    "BACKLINK_GAP": "distribution",
    "LINKABLE_ASSET": "linkable_assets",
    "PRODUCT_UTILITY": "utility_development",
    "CTR_IMPROVEMENT": "ctr",
}

# Enough lifetime impressions that measured signal deserves to lead. Below it,
# estimates are shrunk toward the prior and reported as ranges. This is a
# judgement, not a statistic, and it is written down so it can be argued with.
EVIDENCE_MATURE_IMPRESSIONS = 500

# Words that carry no page-specific meaning, so their absence from a page proves
# nothing about whether the page answers a query.
STOPWORDS = frozenset(
    "a an and are as at be best by can do for free from generator how i in is it "
    "make me my near new of on online or template templates that the to top up us "
    "use what when where which who with without you your".split()
)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def ctr_at(position: float | None) -> float:
    """Rough click-through by rank. Only used to separate "position 80 earns
    nothing" from "position 8 earns something", not to model a curve."""
    if position is None or position <= 0:
        return 0.0
    for limit, rate in ((1.5, 0.28), (3, 0.15), (5, 0.08), (10, 0.03), (20, 0.01), (50, 0.002)):
        if position <= limit:
            return rate
    return 0.0005


def evidence_maturity(connection: sqlite3.Connection) -> float:
    """How far to trust measured signal over priors, from 0 to 1.

    Ten lifetime impressions cannot support a confident estimate of anything.
    As impressions accumulate this rises and the measured component of a score
    progressively outweighs the assumption behind it.
    """
    total = connection.execute(
        "SELECT COALESCE(SUM(gsc_impressions), 0) FROM metrics_daily"
    ).fetchone()[0]
    return min(1.0, float(total or 0) / EVIDENCE_MATURE_IMPRESSIONS)


def _latest_metrics(connection: sqlite3.Connection) -> dict:
    row = connection.execute(
        """SELECT date, gsc_impressions, gsc_clicks, gsc_avg_position,
                  ga_sessions, ga_tool_starts, ga_pdf_downloads
             FROM metrics_daily WHERE gsc_impressions IS NOT NULL
            ORDER BY date DESC LIMIT 1"""
    ).fetchone()
    return dict(row) if row else {}


def _index_rows(connection: sqlite3.Connection) -> dict[str, dict]:
    latest = connection.execute("SELECT MAX(date) FROM index_state").fetchone()[0]
    if not latest:
        return {}
    return {
        row["url"]: dict(row)
        for row in connection.execute("SELECT * FROM index_state WHERE date=?", (latest,))
    }


def _health(connection: sqlite3.Connection) -> dict[str, int]:
    latest = connection.execute("SELECT MAX(date) FROM url_health").fetchone()[0]
    if not latest:
        return {}
    return {
        row["url"]: int(row["status"] or 0)
        for row in connection.execute(
            "SELECT url, status FROM url_health WHERE date=?", (latest,)
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


# ---------------------------------------------------------------------------
# Measurement of the built site
# ---------------------------------------------------------------------------

def _dist(root: Path | None = None) -> Path:
    return Path(root or Path(__file__).resolve().parents[1] / "dist")


def _page_file(url: str, root: Path) -> Path:
    path = url.replace("https://invoiceworkshop.com", "").strip("/")
    return root / (path + "/index.html") if path else root / "index.html"


def visible_text(html: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def page_texts(root: Path | None = None) -> dict[str, str]:
    """Rendered text per canonical page, or {} when the site is not built.

    A missing build yields no gaps rather than invented ones: the model must
    never claim a page is deficient on evidence it does not have.
    """
    base = _dist(root)
    texts = {}
    for url in CANONICAL:
        target = _page_file(url, base)
        if target.is_file():
            texts[url] = visible_text(target.read_text(encoding="utf-8", errors="ignore"))
    return texts


def sitemap_urls(root: Path | None = None) -> set[str]:
    sitemap = _dist(root) / "sitemap.xml"
    if not sitemap.is_file():
        return set()
    return set(re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8")))


def measure_pages(connection: sqlite3.Connection, dist: Path | None = None) -> dict:
    """Measure page structure from the built site. Facts, not estimates.

    `words` is recorded because it is useful when reading a diagnosis; nothing
    in the model rewards raising it.
    """
    root = _dist(dist)
    now = utc_now()
    inbound: dict[str, int] = {url: 0 for url in CANONICAL}
    raw: dict[str, str] = {}
    for url in CANONICAL:
        target = _page_file(url, root)
        if target.is_file():
            raw[url] = target.read_text(encoding="utf-8", errors="ignore")
    for html in raw.values():
        for path in set(re.findall(r'href="(/(?:[a-z0-9-]+/)?)"', html)):
            full = "https://invoiceworkshop.com" + path
            if full in inbound:
                inbound[full] += 1

    measured = {}
    for url, html in raw.items():
        text = visible_text(html)
        features = {
            # A generator page without a worked example makes the reader do the
            # arithmetic in their head to check the tool is doing it right.
            "worked_example": 'class="doc-table"' in html,
            # These documents are routinely confused for one another; a page
            # that never says which is which leaves that job undone.
            "comparison": 'class="term-list"' in html,
            "canonical_self": f'rel="canonical" href="{url}"' in html,
            "h1_count": len(re.findall(r"<h1", html, re.I)),
        }
        connection.execute(
            """INSERT INTO page_content_stats
                 (url, measured_at, words, headings, bytes, internal_out, internal_in, features_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url, measured_at) DO UPDATE SET
                 words=excluded.words, features_json=excluded.features_json,
                 internal_in=excluded.internal_in""",
            (url, now, len(text.split()), len(re.findall(r"<h2", html, re.I)), len(html),
             len(set(re.findall(r'href="(/(?:[a-z0-9-]+/)?)"', html))), inbound[url],
             json.dumps(features, sort_keys=True)),
        )
        measured[url] = {"words": len(text.split()), **features, "internal_in": inbound[url]}
    connection.commit()
    return measured


def _page_stats(connection: sqlite3.Connection) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    try:
        rows = connection.execute(
            """SELECT * FROM page_content_stats s
                WHERE measured_at=(SELECT MAX(measured_at) FROM page_content_stats
                                    WHERE url=s.url)"""
        )
    except sqlite3.Error:
        return stats
    for row in rows:
        entry = dict(row)
        try:
            entry["features"] = json.loads(entry.get("features_json") or "{}")
        except json.JSONDecodeError:
            entry["features"] = {}
        stats[entry["url"]] = entry
    return stats


# ---------------------------------------------------------------------------
# Index diagnosis
# ---------------------------------------------------------------------------

def classify_index(row: dict) -> str:
    """Which of the four index states a URL is actually in.

    The distinction that matters most: "Discovered - currently not indexed" with
    no crawl time means Google has never fetched the page. Whatever is wrong, it
    is not the content — nothing has read it.
    """
    coverage = (row.get("coverage_state") or "").lower()
    crawled = bool(row.get("last_crawl_time"))
    if row.get("verdict") == "PASS" and "indexed" in coverage and "not indexed" not in coverage:
        return "indexed"
    if "unknown" in coverage:
        return "unknown"
    if "discovered" in coverage and not crawled:
        return "discovered_not_crawled"
    if crawled or "crawled" in coverage:
        return "crawled_not_indexed"
    return "discovered_not_crawled"


CONSTRAINT_OF = {
    "indexed": "none",
    "discovered_not_crawled": "crawl_scheduling",
    "unknown": "discovery_signals",
    "crawled_not_indexed": "content_quality",
}


def readiness(url: str, *, health: dict[str, int], sitemap: set[str],
              stats: dict[str, dict]) -> dict[str, bool]:
    """Everything under our control that must be true before waiting is the
    right answer."""
    page = stats.get(url, {})
    features = page.get("features", {})
    return {
        "returns_200": health.get(url) == 200,
        "in_sitemap": url in sitemap if sitemap else True,
        "self_canonical": bool(features.get("canonical_self", True)),
        "single_h1": int(features.get("h1_count", 1) or 0) == 1,
        "internally_linked": int(page.get("internal_in", 0) or 0) >= 2,
    }


def diagnose_index(connection: sqlite3.Connection, *, dist: Path | None = None) -> list[dict]:
    """Record why each canonical URL is or is not indexed, and record when the
    honest answer is that there is nothing to do but wait."""
    now = utc_now()
    today = now[:10]
    health = _health(connection)
    sitemap = sitemap_urls(dist)
    stats = _page_stats(connection)
    rows = _index_rows(connection)
    out = []
    for url in CANONICAL:
        row = rows.get(url)
        if not row:
            continue
        state = classify_index(row)
        ready = readiness(url, health=health, sitemap=sitemap, stats=stats)
        blocking = sorted(name for name, ok in ready.items() if not ok)
        # `diagnosed_at` is a date, so this counts whole days in the current
        # state. It is what tells a stalled URL apart from a new one.
        first_seen = connection.execute(
            """SELECT MIN(diagnosed_at) FROM index_diagnosis
                WHERE url=? AND index_state=?""",
            (url, state),
        ).fetchone()[0] or today
        days = (datetime.fromisoformat(today).date()
                - datetime.fromisoformat(first_seen).date()).days

        if state == "indexed":
            recommended = "none: indexed"
        elif blocking:
            recommended = "fix readiness: " + ", ".join(blocking)
        elif state == "discovered_not_crawled":
            recommended = ("wait: Google has the URL and has not fetched it. The page has "
                           "never been read, so its content cannot be the cause. Build "
                           "authority; do not rewrite.")
        elif state == "unknown":
            recommended = ("wait and improve discovery signals: sitemap and internal links "
                           "are already in place, so the remaining lever is external "
                           "discovery, not another edit.")
        else:
            recommended = ("crawled and declined: differentiation is genuinely implicated "
                           "here, so a content or product gap is worth investigating.")

        entry = {
            "url": url, "index_state": state,
            "coverage_state": row.get("coverage_state") or "",
            "last_crawl_time": row.get("last_crawl_time"),
            "constraint_kind": CONSTRAINT_OF[state],
            "ready": ready, "blocking_checks": blocking,
            "recommended": recommended, "days_in_state": days,
        }
        connection.execute(
            """INSERT INTO index_diagnosis
                 (url, diagnosed_at, index_state, coverage_state, last_crawl_time,
                  constraint_kind, ready_json, blocking_checks, recommended,
                  first_seen_state, days_in_state)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url, diagnosed_at) DO UPDATE SET
                 index_state=excluded.index_state, recommended=excluded.recommended,
                 blocking_checks=excluded.blocking_checks,
                 days_in_state=excluded.days_in_state""",
            (url, today, state, entry["coverage_state"], entry["last_crawl_time"],
             entry["constraint_kind"], json.dumps(ready, sort_keys=True),
             ",".join(blocking), recommended, first_seen, days),
        )
        out.append(entry)
    connection.commit()
    return out


# ---------------------------------------------------------------------------
# Generators. Each returns opportunity dicts; none of them act.
# ---------------------------------------------------------------------------

def from_indexing(connection: sqlite3.Connection, context: dict) -> list[dict]:
    """An opportunity only where something is actually broken or actually
    declined. A URL that is correctly published and simply has not been crawled
    yet produces a diagnosis, not work."""
    out = []
    for entry in context["diagnosis"]:
        state = entry["index_state"]
        if state == "indexed":
            continue
        if entry["blocking_checks"]:
            out.append({
                "opportunity_key": f"index-readiness:{entry['url']}",
                "opportunity_type": "TECHNICAL_SEO",
                "title": f"Fix indexing prerequisites on {_route(entry['url'])}",
                "target_url": entry["url"],
                "evidence": (f"{entry['coverage_state']}; failing checks: "
                             f"{', '.join(entry['blocking_checks'])}"),
                "evidence_strength": "strong",
                "expected_upside": 60, "feasibility": 0.8, "intent_quality": 0.9,
                "authority_benefit": 0.0, "confidence": 0.7,
                "effort_days": 0.25, "time_to_impact_days": 21,
                "reversible": 1, "risk": "low", "execution_tier": "AUTO",
                "basis": "measured",
            })
            continue
        if state == "crawled_not_indexed":
            out.append({
                "opportunity_key": f"index-quality:{entry['url']}",
                "opportunity_type": "SEO_PAGE_IMPROVEMENT",
                "title": f"Investigate why Google declined to index {_route(entry['url'])}",
                "target_url": entry["url"],
                "evidence": (f"{entry['coverage_state']}; crawled "
                             f"{entry['last_crawl_time']}; all readiness checks pass"),
                "evidence_strength": "strong",
                "expected_upside": 60, "feasibility": 0.4, "intent_quality": 0.9,
                "authority_benefit": 0.0, "confidence": 0.4,
                "effort_days": 1.0, "time_to_impact_days": 45,
                "reversible": 1, "risk": "low", "execution_tier": "REVIEW",
                "basis": "measured",
            })
    return out


def from_content_gaps(connection: sqlite3.Connection, context: dict) -> list[dict]:
    """Page improvements justified by missing user value, never by length.

    Three kinds of evidence, in descending order of how much they prove:

    1. The page already surfaces for a query whose distinctive terms appear
       nowhere on it. That is a demonstrated, unmet sub-intent.
    2. The page has no worked example. On a document generator, an example with
       the arithmetic shown is what lets a reader confirm the tool did the right
       thing before trusting it with a customer's invoice.
    3. The page never distinguishes itself from the documents it is routinely
       confused with, which is the question these visitors actually arrive with.
    """
    stats = context["stats"]
    texts = context["texts"]
    index = {entry["url"]: entry["index_state"] for entry in context["diagnosis"]}
    by_page: dict[str, list[dict]] = {}
    for fact in context["facts"]:
        by_page.setdefault(fact["page"], []).append(fact)

    out = []
    for url in CANONICAL:
        page = stats.get(url)
        text = texts.get(url)
        if not page or text is None:
            continue  # not built and not measured: claim nothing
        features = page.get("features", {})
        lowered = text.lower()
        facts = by_page.get(url, [])
        impressions = sum(int(f["impressions"] or 0) for f in facts)
        indexed = index.get(url) == "indexed"

        gaps: list[str] = []
        unmet: list[str] = []
        for fact in facts:
            missing = [
                term for term in re.findall(r"[a-z]{3,}", (fact["query"] or "").lower())
                if term not in STOPWORDS and term not in lowered
            ]
            if missing:
                unmet.append(f"'{fact['query']}' (missing: {', '.join(missing)})")
        if unmet:
            gaps.append("unanswered surfaced query: " + "; ".join(unmet))
        if not features.get("worked_example"):
            gaps.append("no worked example showing the document and its arithmetic")
        if not features.get("comparison"):
            gaps.append("no comparison with the documents this one is confused with")
        if not gaps:
            continue

        # A demonstrated unmet query is worth much more than a structural gap on
        # a page nobody has ever seen.
        measured = bool(unmet) or (indexed and impressions > 0)
        out.append({
            "opportunity_key": f"gap:{url}",
            "opportunity_type": "SEO_PAGE_IMPROVEMENT",
            "title": f"Close user-value gaps on {_route(url)}",
            "target_url": url,
            "target_query": (facts[0]["query"] if facts else None),
            "evidence": (f"{len(gaps)} gap(s): " + " | ".join(gaps)
                         + f" [context: {page['words']} words, indexed={indexed}, "
                           f"impressions={impressions}]"),
            "evidence_strength": "strong" if unmet else "moderate" if indexed else "weak",
            "current_impressions": impressions,
            "current_clicks": sum(int(f["clicks"] or 0) for f in facts),
            "expected_upside": 90 if unmet else 45 if indexed else 20,
            "feasibility": 0.6 if indexed else 0.3,
            "intent_quality": 0.9,
            "authority_benefit": 0.1,
            "confidence": 0.5 if unmet else 0.35,
            "effort_days": 0.5,
            "time_to_impact_days": 45,
            "reversible": 1, "risk": "low", "execution_tier": "AUTO",
            "basis": "measured" if measured else "prior",
        })
    return out


def from_ctr(connection: sqlite3.Connection, context: dict) -> list[dict]:
    """Only worth raising once a page has impressions AND a rankable position."""
    out = []
    for fact in context["facts"]:
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
            "basis": "measured",
        })
    return out


def from_emerging_queries(connection: sqlite3.Connection, context: dict) -> list[dict]:
    """Queries the site is already surfacing for are the cheapest to pursue."""
    out = []
    for fact in context["facts"]:
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
            "basis": "measured" if impressions >= 3 else "prior",
        })
    return out


def from_backlink_pipeline(connection: sqlite3.Connection, context: dict) -> list[dict]:
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
            "basis": "prior",
        })
    return out


def from_linkable_assets(connection: sqlite3.Connection, context: dict) -> list[dict]:
    """Assets that could earn citations without asking.

    "Calculators earn links" is not a reason to build a calculator. Each seed
    carries the SERP check that was actually run against it, and an asset that
    lost that check stays here as a recorded rejection rather than being
    re-proposed every morning.

    Checked 2026-09-02 with the authenticated search provider:

    * retainage calculator — SERP is Procore, PlanHub, SubcontractorHub, Rabbet
      and a 50-state Subtrade calculator. A standalone page would be a new thin
      URL against far stronger domains. REJECTED as a new URL; the one genuinely
      under-served part (retainage accumulating across draws) was added to the
      existing construction page instead, where it needs no new URL and lands on
      the only cluster with impressions.
    * payment-terms reference — SERP is Stripe, Sage, Bill.com and a dozen
      near-identical net-30 guides. No differentiation available. REJECTED.
    * invoice numbering — same picture: Stripe plus seven interchangeable
      guides. REJECTED.
    """
    # Kept as evidence so the rejections are visible and can be revisited when
    # the domain is strong enough for the answer to change.
    rejected = {
        "retainage-calculator": (
            "Rejected 2026-09-02 as a standalone asset: SERP held by Procore, PlanHub, "
            "SubcontractorHub, Rabbet and a 50-state calculator. The differentiated part "
            "(cumulative retainage across draws) shipped inside "
            "/construction-invoice-template/ instead."),
        "payment-terms-reference": (
            "Rejected 2026-09-02: SERP held by Stripe, Sage and Bill.com with equivalent "
            "coverage. Nothing we could add that those pages do not already say."),
        "invoice-numbering-guide": (
            "Rejected 2026-09-02: SERP is Stripe plus seven interchangeable guides. No "
            "utility or accuracy advantage available."),
    }
    for key, reason in rejected.items():
        connection.execute(
            """UPDATE growth_opportunities SET state='dismissed', dismissed_reason=?
                WHERE opportunity_key=? AND state<>'done'""",
            (reason, f"asset:{key}"),
        )
    connection.commit()
    return []


GENERATORS = (
    ("indexing", from_indexing),
    ("content_gaps", from_content_gaps),
    ("ctr", from_ctr),
    ("emerging_queries", from_emerging_queries),
    ("backlinks", from_backlink_pipeline),
    ("linkable_assets", from_linkable_assets),
)


def _route(url: str) -> str:
    return url.replace("https://invoiceworkshop.com", "") or "/"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def expected_growth_value(row: dict, *, weight: float = 1.0) -> float:
    """Coarse expected value: usefulness x realistic upside x confidence / effort.

    Deliberately simple and inspectable. Unknown inputs score conservatively —
    a missing number never inflates a score. The channel weight is applied here
    so that weekly reallocation actually changes what gets done.
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
    return round(weight * value / effort, 2)


def value_range(point: float, row: dict, maturity: float) -> tuple[float, float]:
    """An honest interval around a number the evidence cannot pin down.

    Two things widen it: low confidence in the opportunity itself, and a site
    with too little traffic for any measured input to mean much. A `prior`-based
    row is widened further because nothing has been observed at all.
    """
    confidence = float(row.get("confidence") or 0.3)
    spread = (1.0 - confidence) * (1.0 - 0.6 * maturity)
    if row.get("basis") != "measured":
        spread = min(1.0, spread + 0.2)
    return round(point * max(0.0, 1 - spread), 2), round(point * (1 + 2 * spread), 2)


def assign_bands(rows: list[dict]) -> list[dict]:
    """Group into three broad priority bands rather than implying an exact order.

    Bands are ratios to the strongest opportunity, not thresholds on the number
    itself, because the number is coarse and the site has nowhere near enough
    traffic to defend a decimal. Two opportunities in the same band are not
    separable on this evidence, and the reported range says how far from
    separable they are.
    """
    ordered = sorted(rows, key=lambda r: r["expected_growth_value"], reverse=True)
    best = ordered[0]["expected_growth_value"] if ordered else 0.0
    for row in ordered:
        point = row["expected_growth_value"]
        if best <= 0:
            row["priority_band"] = 3
        elif point >= 0.5 * best:
            row["priority_band"] = 1
        elif point >= 0.2 * best:
            row["priority_band"] = 2
        else:
            row["priority_band"] = 3
    return ordered


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def _weights(connection: sqlite3.Connection) -> dict[str, float]:
    try:
        return {
            row["channel"]: float(row["weight"])
            for row in connection.execute("SELECT channel, weight FROM channel_allocation")
        }
    except sqlite3.Error:
        return {}


def refresh(connection: sqlite3.Connection, *, dist: Path | None = None) -> dict:
    now = utc_now()
    measure_pages(connection, dist)
    context = {
        "stats": _page_stats(connection),
        "texts": page_texts(dist),
        "facts": _query_facts(connection),
        "diagnosis": diagnose_index(connection, dist=dist),
    }
    maturity = evidence_maturity(connection)
    weights = _weights(connection)

    collected: list[dict] = []
    counts: dict[str, int] = {}
    for name, generator in GENERATORS:
        rows = generator(connection, context)
        counts[name] = len(rows)
        for row in rows:
            channel = CHANNEL_OF.get(row["opportunity_type"], "page_improvement")
            row["channel"] = channel
            row.setdefault("basis", "prior")
            point = expected_growth_value(row, weight=weights.get(channel, 1.0))
            row["expected_growth_value"] = point
            low, high = value_range(point, row, maturity)
            row["value_low"], row["value_high"] = low, high
            collected.append(row)

    # An opportunity the evidence no longer supports must stop competing for
    # attention. It is dismissed rather than deleted so the history stays
    # readable, and it comes back automatically if the evidence returns.
    keys = [row["opportunity_key"] for row in collected]
    placeholders = ",".join("?" * len(keys)) if keys else "''"
    connection.execute(
        f"""UPDATE growth_opportunities
              SET state='dismissed',
                  dismissed_reason=COALESCE(dismissed_reason,
                                            'no longer supported by evidence'),
                  updated_at=?
            WHERE state='open' AND opportunity_key NOT IN ({placeholders})""",
        [now, *keys],
    )

    for row in assign_bands(collected):
        connection.execute(
            """INSERT INTO growth_opportunities (
                 opportunity_key, opportunity_type, title, target_url, target_query,
                 evidence, evidence_strength, current_impressions, current_clicks,
                 current_position, demand_estimate, feasibility, intent_quality,
                 expected_upside, authority_benefit, effort_days, confidence,
                 time_to_impact_days, reversible, risk, expected_growth_value,
                 value_low, value_high, priority_band, basis, channel,
                 execution_tier, first_seen_at, updated_at)
               VALUES (:opportunity_key, :opportunity_type, :title, :target_url, :target_query,
                 :evidence, :evidence_strength, :current_impressions, :current_clicks,
                 :current_position, :demand_estimate, :feasibility, :intent_quality,
                 :expected_upside, :authority_benefit, :effort_days, :confidence,
                 :time_to_impact_days, :reversible, :risk, :expected_growth_value,
                 :value_low, :value_high, :priority_band, :basis, :channel,
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
                 value_low=excluded.value_low, value_high=excluded.value_high,
                 priority_band=excluded.priority_band, basis=excluded.basis,
                 channel=excluded.channel,
                 execution_tier=excluded.execution_tier,
                 state=CASE WHEN growth_opportunities.state='dismissed' THEN 'open'
                            ELSE growth_opportunities.state END,
                 dismissed_reason=NULL,
                 updated_at=excluded.updated_at""",
            {
                "demand_estimate": None, "target_query": None,
                "current_impressions": None, "current_clicks": None,
                "current_position": None, **row, "now": now,
            },
        )
    connection.commit()
    return {
        "generated": counts, "total": len(collected),
        "evidence_maturity": round(maturity, 3),
        "channel_weights": weights,
        "index_states": {e["url"]: e["index_state"] for e in context["diagnosis"]},
        "external_side_effects": "none",
    }


def ranked(connection: sqlite3.Connection, limit: int = 10, tier: str | None = None) -> list[dict]:
    clause = " AND execution_tier=?" if tier else ""
    args = [tier, limit] if tier else [limit]
    return [
        dict(row)
        for row in connection.execute(
            f"""SELECT * FROM growth_opportunities
                 WHERE state='open'{clause}
                 ORDER BY priority_band ASC, expected_growth_value DESC LIMIT ?""",
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
    commands.add_parser("measure", help="Measure page structure from the built site")
    commands.add_parser("diagnose", help="Classify why each canonical URL is not indexed")
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
    elif args.command == "diagnose":
        measure_pages(connection)
        result = {"diagnosis": diagnose_index(connection),
                  "evidence_maturity": round(evidence_maturity(connection), 3)}
    elif args.command == "top":
        result = {
            "evidence_maturity": round(evidence_maturity(connection), 3),
            "note": ("Values are coarse and carry ranges. Compare bands, not decimals: "
                     "opportunities in the same band are not separable on this evidence."),
            "opportunities": ranked(connection, args.limit, args.tier),
        }
    else:
        result = {"experiments": [
            dict(row) for row in connection.execute(
                "SELECT * FROM growth_experiments ORDER BY id DESC LIMIT 25"
            )
        ]}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
