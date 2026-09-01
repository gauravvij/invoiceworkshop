#!/usr/bin/env python3
"""Aggressive, deterministic backlink opportunity discovery.

Pipeline: broad search pool -> cheap filter -> dedupe against CRM/history ->
page extraction -> rule-based qualification -> scoring -> tiering.

The engine is read-only against the outside world. It performs HTTP GETs and
nothing else: it never submits a form, posts, authenticates, purchases, or
sends mail. Promotion to an actionable prospect still leaves every Level-1A
outbound gate closed.

External page content is untrusted data. It is measured against rules and
never interpreted as an instruction.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import requests

from growth_backlink_policy import (
    ACCOUNT_PATTERNS,
    SELF_DOMAIN,
    VENDOR_CTA_PATTERNS,
    VENDOR_CTA_THRESHOLD,
    VENDOR_PRODUCT_PATTERNS,
    OFF_TOPIC_PATTERNS,
    CRAWL_MAX_LINKS_PER_SEED,
    CRAWL_SEEDS,
    CRAWL_SKIP_PATH,
    ACTIONABLE_LINK_REASONS,
    BLOCKED_DOMAINS,
    CAPTCHA_PATTERNS,
    CHANNEL_QUERIES,
    COMMUNITY_CHANNEL,
    COMMUNITY_DOMAINS,
    COMPETITORS,
    ESCALATION_CHANNEL,
    EXTRACT_LIMIT,
    PAID_PATTERNS,
    RECIPROCAL_PATTERNS,
    SCORE_CEILINGS,
    SEARCH_RESULTS_PER_QUERY,
    SPAM_PATTERNS,
    TIER_A_MIN,
    TIER_B_MIN,
    TIER_C_MIN,
    classify_link_reason,
    target_for,
)
from growth_search_providers import SearchProviderError, get_provider
from growth_common import (
    apply_schema,
    canonical_domain,
    connect_db,
    database_path,
    normalize_public_url,
    utc_now,
)

USER_AGENT = "InvoiceWorkshop-Level0/1.0 (+https://invoiceworkshop.com/)"
# Some hosts return 403 to any unfamiliar agent. A second, ordinary browser
# string is tried before a page is written off; nothing else about the request
# changes and it stays a plain read-only GET.
BROKEN_LINK_CHECKS_PER_PAGE = 12
FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36"
)
CONTACT_HINT = re.compile(
    r"(?:contact|submit|suggest|editorial|guidelines|write[- ]?for[- ]?us|contribut|pitch|about)",
    re.I,
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
ASSET_EMAIL_RE = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|css|js)$", re.I)

SPAM_RE = re.compile("|".join(SPAM_PATTERNS), re.I)
PAID_RE = re.compile("|".join(PAID_PATTERNS), re.I)
RECIPROCAL_RE = re.compile("|".join(RECIPROCAL_PATTERNS), re.I)
ACCOUNT_RE = re.compile("|".join(ACCOUNT_PATTERNS), re.I)
CAPTCHA_RE = re.compile("|".join(CAPTCHA_PATTERNS), re.I)
OFF_TOPIC_RE = re.compile("|".join(OFF_TOPIC_PATTERNS), re.I)
VENDOR_CTA_RE = re.compile("|".join(VENDOR_CTA_PATTERNS), re.I)
VENDOR_PRODUCT_RE = re.compile("|".join(VENDOR_PRODUCT_PATTERNS), re.I)

# Signals used by the cheap pre-fetch filter.
RESOURCE_HINT = re.compile(
    r"(?:resource|tool|template|guide|checklist|library|directory|roundup|"
    r"best|list|links|downloads)", re.I
)
AUDIENCE_HINT = re.compile(
    r"(?:freelance|self[- ]employed|small business|smb|solopreneur|contractor|"
    r"construction|trades|consultant|bookkeep|account|creator|agency|entrepreneur)", re.I
)
INVOICE_HINT = re.compile(
    r"(?:invoic|billing|quotation|quote|estimate|work order|purchase order|"
    r"proforma|get(?:ting)? paid|receivable)", re.I
)


class PageParser(HTMLParser):
    """Minimal extractor: visible text, links, and the title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self.title = ""
        self._href: str | None = None
        self._anchor: list[str] = []
        self._ignored = 0
        self._in_title = False
        self.meta_robots = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._ignored += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href = attributes.get("href")
            self._anchor = []
        elif tag == "meta" and (attributes.get("name") or "").lower() == "robots":
            self.meta_robots = (attributes.get("content") or "").lower()

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "template"} and self._ignored:
            self._ignored -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor).strip()))
            self._href = None

    def handle_data(self, data):
        if self._ignored:
            return
        if self._in_title:
            self.title += data
        stripped = data.strip()
        if stripped:
            self.text.append(stripped)
            if self._href is not None:
                self._anchor.append(stripped)

    @property
    def body_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text))


def initialize(db: str | None = None) -> sqlite3.Connection:
    connection = connect_db(database_path(db))
    apply_schema(connection)
    return connection


def dedupe_key(page_url: str) -> str:
    """Collapse www/non-www and trailing slashes so one page is stored once."""
    split = urlsplit(page_url)
    return f"{canonical_domain(page_url)}{split.path.rstrip('/').lower()}"


def blocked(domain: str) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in BLOCKED_DOMAINS)


def is_community(domain: str) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in COMMUNITY_DOMAINS)


# ---------------------------------------------------------------------------
# Stage 1 — broad discovery
# ---------------------------------------------------------------------------

_PROVIDER: object | None = None


def provider():
    """The configured search provider. Never falls back to another source."""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = get_provider()
    return _PROVIDER


def search(query: str, limit: int = SEARCH_RESULTS_PER_QUERY) -> list[dict]:
    return provider().search(query, limit)


def channel_plan(connection: sqlite3.Connection, channels: list[str] | None,
                 queries_per_channel: int) -> list[tuple[str, str]]:
    """Rotate queries per channel, weighted by measured channel performance."""
    selected = channels or list(CHANNEL_QUERIES)
    plan: list[tuple[str, str]] = []
    for channel in selected:
        pool = CHANNEL_QUERIES.get(channel, ())
        if not pool:
            continue
        row = connection.execute(
            "SELECT runs, effort_weight FROM backlink_channel_stats WHERE channel=?", (channel,)
        ).fetchone()
        runs = int(row["runs"]) if row else 0
        weight = float(row["effort_weight"]) if row else 1.0
        count = max(1, min(len(pool), round(queries_per_channel * weight)))
        # Deterministic rotation: a channel does not re-run the same queries.
        start = (runs * count) % len(pool)
        plan.extend((channel, pool[(start + offset) % len(pool)]) for offset in range(count))
    return plan


def cheap_filter(channel: str, title: str, snippet: str, page_url: str) -> tuple[bool, str]:
    """Reject before spending an HTTP fetch. Returns (keep, reason)."""
    text = f"{title} {snippet} {page_url}"
    domain = canonical_domain(page_url)
    if not domain or not page_url.startswith("http"):
        return False, "unusable url"
    if SPAM_RE.search(text):
        return False, "spam signal"
    if blocked(domain):
        return False, "blocked or competitor domain"
    if channel == COMMUNITY_CHANNEL:
        return (True, "") if is_community(domain) else (False, "not a community platform")
    if is_community(domain):
        return False, "community domain outside the community channel"
    if channel == "unlinked_mention":
        return True, ""
    path = urlsplit(page_url).path.strip("/")
    if not path:
        return False, "homepage rather than a specific page"
    signals = sum((
        bool(RESOURCE_HINT.search(text)),
        bool(AUDIENCE_HINT.search(text)),
        bool(INVOICE_HINT.search(text)),
    ))
    if signals < 2:
        return False, "insufficient topical signal"
    return True, ""


def discover(connection: sqlite3.Connection, run_id: int, channels: list[str] | None,
             queries_per_channel: int) -> dict:
    now = utc_now()
    plan = channel_plan(connection, channels, queries_per_channel)
    raw = filtered = duplicates = rejected = requests_made = 0
    errors: list[str] = []
    seen_pages = {
        dedupe_key(row["page_url"]) for row in connection.execute(
            "SELECT page_url FROM backlink_opportunities"
        )
    } | {
        dedupe_key(row["page_url"]) for row in connection.execute("SELECT page_url FROM prospects")
    } | {
        dedupe_key(row["thread_url"]) for row in connection.execute(
            "SELECT thread_url FROM community_opportunities"
        )
    }
    per_channel: dict[str, dict[str, int]] = {}
    for channel, query in plan:
        bucket = per_channel.setdefault(channel, {"raw": 0, "kept": 0, "duplicates": 0, "rejected": 0})
        try:
            rows = search(query)
            requests_made += 1
        except SearchProviderError as error:
            # Recorded, never swallowed by switching to a weaker source.
            errors.append(f"{channel}: search provider failed: {error}")
            continue
        except Exception as error:  # transient network/parse failure
            errors.append(f"{channel}: {type(error).__name__}")
            continue
        for row in rows:
            raw += 1
            bucket["raw"] += 1
            try:
                page_url = normalize_public_url(row["page_url"])
            except Exception:
                rejected += 1
                bucket["rejected"] += 1
                continue
            domain = canonical_domain(page_url)
            evidence = row.get("content") or row.get("snippet") or ""
            keep, reason = cheap_filter(channel, row["title"], evidence, page_url)
            if not keep:
                rejected += 1
                bucket["rejected"] += 1
                continue
            key = dedupe_key(page_url)
            if key in seen_pages:
                duplicates += 1
                bucket["duplicates"] += 1
                continue
            seen_pages.add(key)
            filtered += 1
            bucket["kept"] += 1
            if channel == COMMUNITY_CHANNEL:
                connection.execute(
                    """INSERT INTO community_opportunities
                         (platform, thread_url, title, question_summary, discovered_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(thread_url) DO NOTHING""",
                    (domain, page_url, row["title"][:400], row["snippet"][:1200], now, now),
                )
                continue
            connection.execute(
                """INSERT INTO backlink_opportunities
                     (domain, page_url, channel, discovery_run_id, title, page_evidence,
                      target_url, discovered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain, page_url) DO NOTHING""",
                (
                    domain, page_url, channel, run_id, row["title"][:400],
                    evidence[:1500],
                    target_for(f"{row['title']} {evidence} {page_url}"),
                    now, now,
                ),
            )
    connection.commit()
    return {
        "provider": provider().name,
        "queries_run": len(plan), "raw": raw, "filtered": filtered,
        "duplicates": duplicates, "rejected": rejected,
        "http_requests": requests_made, "per_channel": per_channel, "errors": errors,
    }


def crawl_seeds(connection: sqlite3.Connection, run_id: int,
                seeds: list[tuple[str, str]] | None = None) -> dict:
    """Discover resource pages by reading known hubs rather than searching.

    Keyword search cannot reach a specific organisation's resource section
    through an endpoint that ignores `site:`. Reading the hub directly can.
    """
    now = utc_now()
    chosen = seeds or list(CRAWL_SEEDS)
    seen = {dedupe_key(row["page_url"]) for row in connection.execute(
        "SELECT page_url FROM backlink_opportunities"
    )} | {dedupe_key(row["page_url"]) for row in connection.execute("SELECT page_url FROM prospects")}
    added = visited = skipped = 0
    errors: list[str] = []
    for channel, seed in chosen:
        try:
            status, body = fetch(seed)
            visited += 1
        except Exception as error:
            errors.append(f"{canonical_domain(seed)}: {type(error).__name__}")
            continue
        if status != 200 or not body:
            errors.append(f"{canonical_domain(seed)}: HTTP {status}")
            continue
        parser = PageParser()
        try:
            parser.feed(body)
        except Exception:
            pass
        host = urlsplit(seed).netloc
        kept = 0
        for href, anchor in parser.links:
            if kept >= CRAWL_MAX_LINKS_PER_SEED:
                break
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(seed, href)
            split = urlsplit(absolute)
            if split.scheme not in {"http", "https"} or split.netloc != host:
                continue
            path = split.path.lower()
            if not path.strip("/") or any(skip in path for skip in CRAWL_SKIP_PATH):
                continue
            label = f"{anchor} {path}"
            if not (RESOURCE_HINT.search(label) or INVOICE_HINT.search(label)):
                continue
            try:
                page_url = normalize_public_url(absolute)
            except Exception:
                continue
            domain = canonical_domain(page_url)
            key = dedupe_key(page_url)
            if blocked(domain) or is_community(domain) or key in seen:
                skipped += 1
                continue
            seen.add(key)
            connection.execute(
                """INSERT INTO backlink_opportunities
                     (domain, page_url, channel, discovery_run_id, title, page_evidence,
                      target_url, discovered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, '', ?, ?, ?)
                   ON CONFLICT(domain, page_url) DO NOTHING""",
                (domain, page_url, channel, run_id, (anchor or "")[:400],
                 target_for(label), now, now),
            )
            added += 1
            kept += 1
    connection.commit()
    return {"seeds": len(chosen), "visited": visited, "added": added,
            "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Stage 2 — page extraction
# ---------------------------------------------------------------------------

def fetch(url: str) -> tuple[int, str]:
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=25, allow_redirects=True
    )
    if response.status_code in {401, 403, 406, 429}:
        response = requests.get(
            url, headers={"User-Agent": FALLBACK_USER_AGENT}, timeout=25, allow_redirects=True
        )
    return response.status_code, response.text if response.ok else ""


def find_contact_route(page_url: str, parser: PageParser) -> tuple[str | None, str, str | None]:
    """Return (contact_url, contact_kind, recipient) using same-site evidence only."""
    host = urlsplit(page_url).netloc
    emails = [
        address for address in EMAIL_RE.findall(parser.body_text)
        if not ASSET_EMAIL_RE.search(address)
        and canonical_domain(page_url).split(".")[0] in address.split("@")[-1].lower()
    ]
    if emails:
        return page_url, "email", sorted(set(emails), key=len)[0].lower()
    for href, anchor in parser.links:
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        if urlsplit(absolute).netloc != host:
            continue
        if CONTACT_HINT.search(anchor) or CONTACT_HINT.search(urlsplit(absolute).path):
            kind = "editorial_guidelines" if re.search(
                r"guideline|write-for-us|contribut", absolute, re.I
            ) else "form"
            return normalize_public_url(absolute), kind, None
    for href, _ in parser.links:
        if href and href.startswith("mailto:"):
            address = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.fullmatch(address):
                return page_url, "email", address
    return None, "unknown", None


def _record_fetch_failure(connection: sqlite3.Connection, row: sqlite3.Row,
                          reason: str, now: str) -> None:
    """One failure defers the page to the next cycle; two retires it."""
    attempts = int(row["fetch_attempts"]) + 1
    if attempts >= 2:
        connection.execute(
            """UPDATE backlink_opportunities
                  SET fetch_attempts=?, rejection_reason=?, tier='reject', updated_at=?
                WHERE id=?""",
            (attempts, reason, now, row["id"]),
        )
    else:
        connection.execute(
            "UPDATE backlink_opportunities SET fetch_attempts=?, updated_at=? WHERE id=?",
            (attempts, now, row["id"]),
        )


def extract(connection: sqlite3.Connection, limit: int = EXTRACT_LIMIT) -> dict:
    now = utc_now()
    rows = connection.execute(
        """SELECT * FROM backlink_opportunities
            WHERE extracted_at IS NULL AND rejection_reason IS NULL AND fetch_attempts < 2
            ORDER BY fetch_attempts, id LIMIT ?""",
        (limit,),
    ).fetchall()
    extracted = failed = 0
    requests_made = 0
    for row in rows:
        try:
            status, body = fetch(row["page_url"])
            requests_made += 1
        except Exception as error:
            _record_fetch_failure(connection, row, f"fetch failed: {type(error).__name__}", now)
            failed += 1
            continue
        if status != 200 or not body:
            _record_fetch_failure(connection, row, f"page returned HTTP {status}", now)
            failed += 1
            continue
        parser = PageParser()
        try:
            parser.feed(body)
        except Exception:
            pass
        text = parser.body_text[:200_000]
        contact_url, contact_kind, recipient = find_contact_route(row["page_url"], parser)
        connection.execute(
            """UPDATE backlink_opportunities
                  SET title=?, page_evidence=?, contact_route=?, contact_kind=?,
                      recipient=?, target_url=?, requires_account=?, requires_payment=?,
                      vendor_content=?, extracted_at=?, updated_at=?
                WHERE id=?""",
            (
                (parser.title.strip() or row["title"])[:400],
                text[:1500],
                contact_url, contact_kind, recipient,
                target_for(f"{parser.title} {text[:4000]} {row['page_url']}"),
                1 if ACCOUNT_RE.search(text) else 0,
                1 if PAID_RE.search(text) else 0,
                # Judged on the full page: vendor CTAs usually sit well past the
                # 1,500 characters kept as evidence.
                1 if _is_vendor_content(text) else 0,
                now, now, row["id"],
            ),
        )
        extracted += 1
    connection.commit()
    return {"extracted": extracted, "failed": failed, "http_requests": requests_made}


# ---------------------------------------------------------------------------
# Stage 3 — rule-based qualification, scoring (Part D) and tiering (Part E)
# ---------------------------------------------------------------------------

def hard_reject(text: str, domain: str, requires_payment: int,
                vendor_content: int = 0) -> str | None:
    if domain == SELF_DOMAIN or domain.endswith("." + SELF_DOMAIN):
        return "InvoiceWorkshop's own site"
    if SPAM_RE.search(text):
        return "Part K spam signal on the page"
    if blocked(domain):
        return "blocked or competitor domain"
    if RECIPROCAL_RE.search(text):
        return "requires a reciprocal link"
    if requires_payment or PAID_RE.search(text):
        return "paid or sponsored placement"
    if OFF_TOPIC_RE.search(text):
        return "page subject is unrelated to business billing"
    if vendor_content or _is_vendor_content(text):
        return "competitor or vendor content marketing"
    return None


def _is_vendor_content(text: str) -> bool:
    """A site selling its own invoicing product is not a placement opportunity."""
    if not INVOICE_HINT.search(text):
        return False
    ctas = len(set(match.group(0).lower() for match in VENDOR_CTA_RE.finditer(text)))
    return ctas >= VENDOR_CTA_THRESHOLD or bool(VENDOR_PRODUCT_RE.search(text))


def score_opportunity(row: sqlite3.Row) -> dict[str, int]:
    text = f"{row['title']} {row['page_evidence']}".lower()
    url = str(row["page_url"]).lower()
    combined = f"{text} {url}"

    # Topical relevance (25): does the page already talk about our subject?
    relevance = 0
    relevance += 10 if INVOICE_HINT.search(combined) else 0
    relevance += 6 if re.search(r"template|checklist|form", combined) else 0
    relevance += 5 if re.search(r"resource|tool", combined) else 0
    relevance += 4 if re.search(r"free", combined) else 0

    # Actual audience fit (20): are these the people who need this?
    audience = 0
    for pattern, points in (
        (r"freelance|self[- ]employed|solopreneur|independent (?:worker|contractor)", 8),
        (r"small business|smb|entrepreneur|sole trader", 6),
        (r"contractor|construction|trades|builder", 6),
        (r"bookkeep|account(?:ant|ing)|consultant", 5),
    ):
        if re.search(pattern, combined):
            audience += points
    audience = min(audience, SCORE_CEILINGS["audience"])

    # Editorial legitimacy (15): does this read like a real publication?
    legitimacy = 0
    legitimacy += 6 if row["contact_kind"] in {"email", "form", "editorial_guidelines"} else 0
    legitimacy += 4 if re.search(r"about|editor|team|author", combined) else 0
    legitimacy += 5 if not re.search(r"submit your (?:link|site|url)|free directory", combined) else 0
    legitimacy = min(legitimacy, SCORE_CEILINGS["legitimacy"])

    # Exact resource fit (15): would we genuinely improve this specific page?
    resource_fit = 0
    if re.search(r"resource|tools|downloads|library|roundup|best|list", combined):
        resource_fit += 7
    if INVOICE_HINT.search(combined):
        resource_fit += 5
    if row["opportunity_type"] in {"broken_replacement", "unlinked_mention"}:
        resource_fit += 3
    resource_fit = min(resource_fit, SCORE_CEILINGS["resource_fit"])

    # Likelihood of placement (10).
    likelihood = 0
    likelihood += 4 if row["contact_kind"] == "email" else 2 if row["contact_kind"] != "unknown" else 0
    likelihood += 3 if not row["requires_account"] else 0
    likelihood += 3 if row["opportunity_type"] in {"broken_replacement", "unlinked_mention"} else 0
    likelihood = min(likelihood, SCORE_CEILINGS["likelihood"])

    # Referral traffic potential (10): would a real person click through?
    referral = 0
    referral += 5 if re.search(r"resource|tools|template|guide", combined) else 0
    referral += 3 if AUDIENCE_HINT.search(combined) else 0
    referral += 2 if re.search(r"2025|2026|updated", combined) else 0
    referral = min(referral, SCORE_CEILINGS["referral"])

    # SEO/link value (5) — deliberately the smallest component.
    seo = 0
    path_depth = len([part for part in urlsplit(url).path.split("/") if part])
    seo += 3 if path_depth <= 3 else 1
    seo += 2 if re.search(r"\.(?:org|edu|gov)(?:/|$)", url) else 0
    seo = min(seo, SCORE_CEILINGS["seo"])

    parts = {
        "relevance": min(relevance, SCORE_CEILINGS["relevance"]),
        "audience": audience, "legitimacy": legitimacy, "resource_fit": resource_fit,
        "likelihood": likelihood, "referral": referral, "seo": seo,
    }
    parts["total"] = sum(parts.values())
    return parts


def second_pass(row: sqlite3.Row, parts: dict[str, int]) -> tuple[bool, str]:
    """If search engines did not exist, would this contact still make sense?"""
    if parts["audience"] < 6:
        return False, "audience is not plausibly served by an invoicing tool"
    if parts["resource_fit"] < 7:
        return False, "the page is not a resource InvoiceWorkshop would improve"
    if row["contact_kind"] == "unknown":
        return False, "no public contact or submission route was found on the site"
    return True, "the page serves an audience that bills clients and already collects practical resources"


def qualify(connection: sqlite3.Connection) -> dict:
    """Score, tier, and keep at most one live opportunity per referring domain.

    The objective is referring domains, not pages, so a second page on a domain
    already represented is demoted rather than counted again.
    """
    now = utc_now()
    rows = connection.execute(
        """SELECT * FROM backlink_opportunities
            WHERE rejection_reason IS NULL AND extracted_at IS NOT NULL
            ORDER BY id"""
    ).fetchall()
    claimed_domains = {
        row["domain"] for row in connection.execute(
            "SELECT domain FROM prospects WHERE status IN ('qualified','new')"
        )
    }

    # Pass 1: score every extracted page independently.
    scored: list[tuple[sqlite3.Row, dict, str, str]] = []
    for row in rows:
        text = f"{row['title']} {row['page_evidence']}"
        reason = hard_reject(
            text, str(row["domain"]), int(row["requires_payment"]),
            int(row["vendor_content"] or 0),
        )
        if reason:
            connection.execute(
                """UPDATE backlink_opportunities
                      SET tier='reject', rejection_reason=?, total_score=0, updated_at=?
                    WHERE id=?""",
                (reason, now, row["id"]),
            )
            continue
        parts = score_opportunity(row)
        passed, why = second_pass(row, parts)
        subject = f"{row['title']} {row['page_evidence']} {row['page_url']}"
        on_subject = bool(INVOICE_HINT.search(subject))
        if not passed or parts["total"] < TIER_C_MIN:
            tier = "reject"
        elif str(row["domain"]) in claimed_domains:
            tier, why = "C", "domain is already represented in the CRM"
        elif parts["total"] >= TIER_A_MIN and on_subject \
                and row["contact_kind"] in {"email", "form", "editorial_guidelines"} \
                and not row["requires_payment"] and not row["requires_account"]:
            tier = "A"
        elif parts["total"] >= TIER_B_MIN and on_subject:
            tier = "B"
        elif not on_subject and parts["total"] >= TIER_B_MIN:
            tier, why = "C", "page does not itself cover invoicing or getting paid"
        else:
            tier = "C"
        scored.append((row, parts, tier, why))

    # Pass 2: one referring domain yields at most one A/B opportunity.
    best: dict[str, int] = {}
    for row, parts, tier, _ in scored:
        if tier in {"A", "B"}:
            domain = str(row["domain"])
            if domain not in best or parts["total"] > best[domain]:
                best[domain] = parts["total"]
    kept: set[str] = set()
    counts = {"reviewed": len(rows), "A": 0, "B": 0, "C": 0, "reject": 0}
    for row, parts, tier, why in scored:
        domain = str(row["domain"])
        if tier in {"A", "B"}:
            if domain in kept or parts["total"] < best.get(domain, 0):
                tier, why = "C", "another page on this domain scores higher"
            else:
                kept.add(domain)
        connection.execute(
            """UPDATE backlink_opportunities
                  SET score_relevance=?, score_audience=?, score_legitimacy=?,
                      score_resource_fit=?, score_likelihood=?, score_referral=?,
                      score_seo=?, total_score=?, tier=?, second_pass_pass=?,
                      second_pass_reason=?, rejection_reason=?, updated_at=?
                WHERE id=?""",
            (
                parts["relevance"], parts["audience"], parts["legitimacy"],
                parts["resource_fit"], parts["likelihood"], parts["referral"],
                parts["seo"], parts["total"], tier, 1 if tier != "reject" else 0, why,
                why if tier == "reject" else None, now, row["id"],
            ),
        )
        counts[tier] += 1
    counts["reject"] = counts["reviewed"] - counts["A"] - counts["B"] - counts["C"]
    connection.commit()
    return counts


def vendor_audit(connection: sqlite3.Connection) -> dict:
    """Promotion gate: judge the *site*, not just the article.

    A vendor's article page often carries no call to action even though the
    site sells competing invoicing software. Before an opportunity is offered
    for outreach, check the domain root once and flag the whole domain.
    """
    now = utc_now()
    domains = [
        row["domain"] for row in connection.execute(
            """SELECT DISTINCT domain FROM backlink_opportunities
                WHERE tier IN ('A','B') AND vendor_content=0"""
        )
    ]
    flagged, checked, failed = 0, 0, 0
    for domain in domains:
        try:
            status, body = fetch(f"https://{domain}/")
            checked += 1
        except Exception:
            failed += 1
            continue
        if status != 200 or not body:
            failed += 1
            continue
        parser = PageParser()
        try:
            parser.feed(body)
        except Exception:
            pass
        if _is_vendor_content(parser.body_text):
            connection.execute(
                """UPDATE backlink_opportunities
                      SET vendor_content=1, tier='reject',
                          rejection_reason='competitor or vendor content marketing',
                          updated_at=? WHERE domain=?""",
                (now, domain),
            )
            flagged += 1
    connection.commit()
    return {"domains_checked": checked, "flagged_as_vendor": flagged,
            "unreachable": failed, "external_side_effects": "none"}


# ---------------------------------------------------------------------------
# Channel 3 — broken/outdated tool verification
# ---------------------------------------------------------------------------

def verify_broken_links(connection: sqlite3.Connection, limit: int = 20) -> dict:
    """Confirm a referenced tool is actually dead before qualifying the page."""
    now = utc_now()
    rows = connection.execute(
        """SELECT * FROM backlink_opportunities
            WHERE channel='broken_replacement' AND broken_url IS NULL
              AND extracted_at IS NOT NULL AND rejection_reason IS NULL
            ORDER BY id LIMIT ?""",
        (limit,),
    ).fetchall()
    confirmed = unconfirmed = 0
    for row in rows:
        try:
            status, body = fetch(row["page_url"])
        except Exception:
            continue
        parser = PageParser()
        try:
            parser.feed(body)
        except Exception:
            pass
        host = urlsplit(row["page_url"]).netloc
        broken_url = evidence = None
        # Bound the probing: a link-heavy resource page can carry dozens of
        # outbound tool links, and each HEAD carries its own timeout.
        checked = 0
        for href, anchor in parser.links:
            if checked >= BROKEN_LINK_CHECKS_PER_PAGE:
                break
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(row["page_url"], href)
            if urlsplit(absolute).netloc in {"", host}:
                continue
            if not INVOICE_HINT.search(f"{anchor} {absolute}"):
                continue
            checked += 1
            try:
                response = requests.head(
                    absolute, headers={"User-Agent": USER_AGENT}, timeout=8, allow_redirects=True
                )
                code = response.status_code
                if code in {405, 403}:  # some hosts reject HEAD
                    code = requests.get(
                        absolute, headers={"User-Agent": USER_AGENT}, timeout=12
                    ).status_code
            except Exception as error:
                broken_url, evidence = absolute, f"request failed: {type(error).__name__}"
                break
            if code >= 400:
                broken_url, evidence = absolute, f"HTTP {code}"
                break
        if broken_url:
            connection.execute(
                """UPDATE backlink_opportunities
                      SET broken_url=?, broken_evidence=?, opportunity_type='broken_replacement',
                          updated_at=? WHERE id=?""",
                (broken_url, evidence, now, row["id"]),
            )
            confirmed += 1
        else:
            connection.execute(
                """UPDATE backlink_opportunities
                      SET tier='reject', rejection_reason='no dead outbound tool link confirmed',
                          updated_at=? WHERE id=?""",
                (now, row["id"]),
            )
            unconfirmed += 1
    connection.commit()
    return {"confirmed": confirmed, "unconfirmed": unconfirmed}


# ---------------------------------------------------------------------------
# Channel 1 — competitor gap dataset
# ---------------------------------------------------------------------------

def competitor_gap(connection: sqlite3.Connection, competitors: list[str] | None = None,
                   per_competitor: int = 2) -> dict:
    now = utc_now()
    targets = competitors or list(COMPETITORS[:6])
    recorded = actionable = 0
    for competitor in targets:
        queries = (
            f'"{competitor}" resources tools -site:{competitor}',
            f'"{competitor}" "recommended" OR "we use" -site:{competitor}',
        )[:per_competitor]
        for query in queries:
            try:
                rows = search(query)
            except Exception:
                continue
            for row in rows:
                try:
                    url = normalize_public_url(row["page_url"])
                except Exception:
                    continue
                domain = canonical_domain(url)
                if blocked(domain):
                    continue
                reason = classify_link_reason(f"{row['title']} {row['snippet']}")
                is_actionable = 1 if reason in ACTIONABLE_LINK_REASONS else 0
                cursor = connection.execute(
                    """INSERT INTO competitor_pages
                         (competitor, referring_url, referring_domain, anchor, link_reason,
                          actionable, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(competitor, referring_url) DO UPDATE SET
                         last_seen_at=excluded.last_seen_at, link_reason=excluded.link_reason,
                         actionable=excluded.actionable""",
                    (competitor, url, domain, row["title"][:300], reason, is_actionable, now, now),
                )
                if cursor.rowcount:
                    recorded += 1
                actionable += is_actionable
    connection.commit()
    return {"recorded": recorded, "actionable": actionable, "competitors": len(targets)}


# ---------------------------------------------------------------------------
# Part J — channel performance and effort reallocation
# ---------------------------------------------------------------------------

def update_channel_stats(connection: sqlite3.Connection, per_channel: dict) -> dict:
    now = utc_now()
    adjustments = {}
    for channel, bucket in per_channel.items():
        qualified = connection.execute(
            """SELECT COUNT(*) FROM backlink_opportunities
                WHERE channel=? AND tier IN ('A','B')""",
            (channel,),
        ).fetchone()[0]
        tier_a = connection.execute(
            "SELECT COUNT(*) FROM backlink_opportunities WHERE channel=? AND tier='A'",
            (channel,),
        ).fetchone()[0]
        row = connection.execute(
            "SELECT * FROM backlink_channel_stats WHERE channel=?", (channel,)
        ).fetchone()
        previous_qualified = int(row["qualified"]) if row else 0
        barren = int(row["barren_streak"]) if row else 0
        weight = float(row["effort_weight"]) if row else 1.0
        gained = qualified - previous_qualified
        if gained <= 0:
            barren += 1
        else:
            barren = 0
        # Part J: throttle barren channels, reward producing ones. Bounded so a
        # channel is never fully switched off by automation alone.
        if barren >= 3:
            weight = max(0.25, round(weight - 0.25, 2))
        elif gained >= 2:
            weight = min(2.5, round(weight + 0.25, 2))
        adjustments[channel] = {"gained": gained, "barren_streak": barren, "effort_weight": weight}
        connection.execute(
            """INSERT INTO backlink_channel_stats
                 (channel, runs, raw_discovered, qualified, tier_a, rejected,
                  barren_streak, effort_weight, last_run_at, updated_at)
               VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(channel) DO UPDATE SET
                 runs=runs+1,
                 raw_discovered=raw_discovered+excluded.raw_discovered,
                 qualified=excluded.qualified, tier_a=excluded.tier_a,
                 rejected=rejected+excluded.rejected,
                 barren_streak=excluded.barren_streak,
                 effort_weight=excluded.effort_weight,
                 last_run_at=excluded.last_run_at, updated_at=excluded.updated_at""",
            (channel, bucket.get("raw", 0), qualified, tier_a, bucket.get("rejected", 0),
             barren, weight, now, now),
        )
    connection.commit()
    return adjustments


# ---------------------------------------------------------------------------
# Part F — placement verification
# ---------------------------------------------------------------------------

def verify_placements(connection: sqlite3.Connection, limit: int = 50) -> dict:
    now = utc_now()
    rows = connection.execute(
        "SELECT * FROM placements ORDER BY COALESCE(verified_at,'') LIMIT ?", (limit,)
    ).fetchall()
    checked = live = lost = 0
    for row in rows:
        try:
            status, body = fetch(row["placement_url"])
        except Exception:
            connection.execute(
                """UPDATE placements SET consecutive_failures=consecutive_failures+1,
                       status='suspect', verified_at=? WHERE id=?""",
                (now, row["id"]),
            )
            continue
        checked += 1
        parser = PageParser()
        try:
            parser.feed(body)
        except Exception:
            pass
        target = str(row["link_target"])
        present = 0
        rel = anchor = ""
        surrounding = ""
        for href, text in parser.links:
            if href and target.rstrip("/") in urljoin(row["placement_url"], href).rstrip("/"):
                present, anchor = 1, text
                break
        if present:
            index = parser.body_text.find(anchor) if anchor else -1
            if index >= 0:
                surrounding = parser.body_text[max(0, index - 160):index + 160]
            rel_match = re.search(
                r'<a[^>]+href="[^"]*%s[^"]*"[^>]*rel="([^"]+)"' % re.escape(urlsplit(target).path),
                body, re.I,
            )
            rel = rel_match.group(1).lower() if rel_match else "follow"
        indexable = 0 if "noindex" in (parser.meta_robots or "") else 1
        connection.execute(
            """INSERT INTO placement_observations
                 (placement_id, observed_at, http_status, indexable, link_present,
                  rel, anchor, surrounding_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], now, status, indexable, present, rel, anchor[:300], surrounding[:600]),
        )
        connection.execute(
            """UPDATE placements SET link_present=?, rel=?, anchor=?, last_http_status=?,
                   status=?, consecutive_failures=?, verified_at=? WHERE id=?""",
            (
                present, rel or row["rel"], anchor[:300] or row["anchor"], status,
                "live" if present and status == 200 else "dead" if status >= 400 else "suspect",
                0 if present else int(row["consecutive_failures"]) + 1,
                now, row["id"],
            ),
        )
        live += present
        lost += 0 if present else 1
    connection.commit()
    return {"checked": checked, "live": live, "missing": lost}


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------

def start_run(connection: sqlite3.Connection, mode: str, channels: list[str] | None) -> int:
    cursor = connection.execute(
        """INSERT INTO backlink_discovery_runs (started_at, mode, channels_json)
           VALUES (?, ?, ?)""",
        (utc_now(), mode, json.dumps(channels or list(CHANNEL_QUERIES))),
    )
    connection.commit()
    return int(cursor.lastrowid)


def finish_run(connection: sqlite3.Connection, run_id: int, **fields) -> None:
    allowed = {
        "raw_discovered", "filtered", "duplicates", "extracted", "reviewed", "qualified",
        "rejected", "llm_reviewed", "tokens_used", "tool_calls", "http_requests",
        "cost_usd", "status", "errors_json",
    }
    sets = ", ".join(f"{key}=?" for key in fields if key in allowed)
    values = [fields[key] for key in fields if key in allowed]
    connection.execute(
        f"UPDATE backlink_discovery_runs SET finished_at=?, {sets} WHERE id=?",
        [utc_now(), *values, run_id],
    )
    connection.commit()


def cycle(connection: sqlite3.Connection, mode: str, channels: list[str] | None,
          queries_per_channel: int, extract_limit: int) -> dict:
    run_id = start_run(connection, mode, channels)
    found = discover(connection, run_id, channels, queries_per_channel)
    crawled = crawl_seeds(connection, run_id) if mode in {"deep", "accelerated"} else {
        "seeds": 0, "visited": 0, "added": 0, "skipped": 0, "errors": []
    }
    pulled = extract(connection, extract_limit)
    broken = verify_broken_links(connection)
    counts = qualify(connection)
    audit = vendor_audit(connection)
    if audit["flagged_as_vendor"]:
        counts = qualify(connection)
    adjustments = update_channel_stats(connection, found["per_channel"])
    http_total = found["http_requests"] + pulled["http_requests"]
    finish_run(
        connection, run_id,
        raw_discovered=found["raw"] + crawled["visited"],
        filtered=found["filtered"] + crawled["added"],
        duplicates=found["duplicates"], extracted=pulled["extracted"],
        reviewed=counts["reviewed"], qualified=counts["A"] + counts["B"],
        rejected=counts["reject"], llm_reviewed=0, tokens_used=0,
        tool_calls=found["queries_run"] + pulled["extracted"],
        http_requests=http_total + crawled["visited"],
        status="partial" if found["errors"] else "success",
        errors_json=json.dumps(found["errors"]),
    )
    return {
        "run_id": run_id, "mode": mode, "provider": provider().name,
        "discovery": found, "crawl": crawled,
        "extraction": pulled,
        "broken_links": broken, "qualification": counts, "vendor_audit": audit,
        "channel_adjustments": adjustments, "http_requests": http_total,
        "external_side_effects": "none",
    }


def report(connection: sqlite3.Connection, limit: int = 20) -> dict:
    rows = connection.execute(
        """SELECT domain, page_url, channel, title, contact_route, contact_kind, recipient,
                  target_url, opportunity_type, total_score, tier, second_pass_reason,
                  broken_url, broken_evidence
             FROM backlink_opportunities
            WHERE tier IN ('A','B')
            ORDER BY CASE tier WHEN 'A' THEN 0 ELSE 1 END, total_score DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    community = connection.execute(
        """SELECT platform, thread_url, title, question_summary, state
             FROM community_opportunities ORDER BY id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    tiers = dict(connection.execute(
        "SELECT tier, COUNT(*) FROM backlink_opportunities GROUP BY tier"
    ).fetchall())
    channels = [dict(row) for row in connection.execute(
        """SELECT channel, runs, raw_discovered, qualified, tier_a, barren_streak, effort_weight
             FROM backlink_channel_stats ORDER BY qualified DESC, channel"""
    )]
    return {
        "tiers": tiers, "channels": channels,
        "opportunities": [dict(row) for row in rows],
        "community_opportunities": [dict(row) for row in community],
        "external_side_effects": "none",
    }


def evaluate(connection: sqlite3.Connection, period_days: int = 7) -> dict:
    """Part I/J: tie distribution outcomes back to search and product signals."""
    channels = [dict(row) for row in connection.execute(
        """SELECT channel, runs, raw_discovered, qualified, tier_a, rejected,
                  contacted, replies, placements, referral_sessions,
                  barren_streak, effort_weight
             FROM backlink_channel_stats ORDER BY qualified DESC, channel"""
    )]
    productive = [row["channel"] for row in channels if row["qualified"] > 0]
    barren = [row["channel"] for row in channels if row["barren_streak"] >= 3]

    search_signal = [dict(row) for row in connection.execute(
        """SELECT date, gsc_impressions, gsc_clicks, gsc_avg_position,
                  ga_sessions, ga_tool_starts, ga_pdf_downloads
             FROM metrics_daily ORDER BY date DESC LIMIT ?""",
        (period_days,),
    )]
    per_page = [dict(row) for row in connection.execute(
        """SELECT p.link_target AS target_url,
                  COUNT(DISTINCT CASE WHEN p.link_present=1 THEN
                    substr(p.placement_url, 1, instr(p.placement_url || '/', '/')) END) AS referring_domains,
                  COUNT(*) AS placements,
                  SUM(CASE WHEN p.status='live' THEN 1 ELSE 0 END) AS live
             FROM placements p GROUP BY p.link_target"""
    )]
    pipeline = dict(connection.execute(
        "SELECT tier, COUNT(*) FROM backlink_opportunities GROUP BY tier"
    ).fetchall())
    return {
        "period_days": period_days,
        "pipeline_by_tier": pipeline,
        "channels": channels,
        "productive_channels": productive,
        "channels_to_throttle": barren,
        "target_page_outcomes": per_page,
        "search_and_product_signal": search_signal,
        "note": (
            "Placement-to-ranking correlation needs live placements; none exist yet, "
            "so no causal claim can be made from this data."
        ),
        "external_side_effects": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("cycle", help="Run a full read-only discovery cycle")
    run.add_argument("--mode", choices=("daily", "deep", "accelerated", "manual"), default="daily")
    run.add_argument("--channels", nargs="*")
    run.add_argument("--queries-per-channel", type=int, default=2)
    run.add_argument("--extract-limit", type=int, default=EXTRACT_LIMIT)

    commands.add_parser("qualify", help="Re-score and re-tier extracted opportunities")
    commands.add_parser("vendor-audit", help="Check A/B domains' own sites for vendor CTAs")
    gap = commands.add_parser("competitor-gap", help="Refresh the competitor-gap dataset")
    gap.add_argument("--competitors", nargs="*")
    placements = commands.add_parser("verify-placements", help="Re-verify recorded placements")
    placements.add_argument("--limit", type=int, default=50)
    shown = commands.add_parser("report", help="Show the current opportunity pipeline")
    shown.add_argument("--limit", type=int, default=20)
    weekly = commands.add_parser("evaluate", help="Weekly channel and outcome evaluation")
    weekly.add_argument("--period", type=int, default=7)
    crawl = commands.add_parser("crawl", help="Search-independent seed-hub crawl")
    crawl.add_argument("--mode", default="manual")
    crawl.add_argument("--expand", action="store_true",
                       help="Use already-extracted resource pages as second-level seeds")
    crawl.add_argument("--limit", type=int, default=40)

    args = parser.parse_args()
    connection = initialize(args.db)
    if args.command == "cycle":
        result = cycle(connection, args.mode, args.channels, args.queries_per_channel, args.extract_limit)
    elif args.command == "qualify":
        result = qualify(connection)
    elif args.command == "vendor-audit":
        result = vendor_audit(connection)
    elif args.command == "competitor-gap":
        result = competitor_gap(connection, args.competitors)
    elif args.command == "verify-placements":
        result = verify_placements(connection, args.limit)
    elif args.command == "evaluate":
        result = evaluate(connection, args.period)
    elif args.command == "crawl":
        run_id = start_run(connection, args.mode, ["crawl"])
        seeds = None
        if args.expand:
            seeds = [
                (row["channel"], row["page_url"])
                for row in connection.execute(
                    """SELECT channel, page_url FROM backlink_opportunities
                        WHERE extracted_at IS NOT NULL AND tier='C'
                          AND second_pass_reason NOT LIKE 'page does not%'
                        ORDER BY total_score DESC LIMIT ?""",
                    (args.limit,),
                )
            ]
        result = crawl_seeds(connection, run_id, seeds)
        finish_run(connection, run_id, status="success", filtered=result["added"])
    else:
        result = report(connection, args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
