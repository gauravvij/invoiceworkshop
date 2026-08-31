#!/usr/bin/env python3
"""Cheap deterministic discovery, filtering, fetching, and shortlisting."""

from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from growth_common import (
    apply_schema,
    canonical_domain,
    connect_db,
    database_path,
    fetch_public_url,
    normalize_public_url,
    utc_now,
)
from growth_research_policy import (
    CHANNEL_QUERIES,
    SEARCHES_PER_SCHEDULED_RUN,
    SEARCH_RESULTS_PER_QUERY,
    SHORTLIST_MAX,
)

BING_RSS = "https://www.bing.com/search"
CONTACT_HINT = re.compile(
    r"(?:contact|submit|suggest|editorial|write[- ]?for[- ]?us|contribut|pitch|get[- ]?featured)",
    re.I,
)
NOISE = re.compile(
    r"(?:buy backlinks?|link building service|\bda\s*[0-9]+|\bdr\s*[0-9]+|seo directory|"
    r"submit.*(?:hundreds|thousands).*directories)",
    re.I,
)
DISQUALIFY_PAGE = re.compile(
    r"(?:backlink required|reciprocal link|paid listing|pay to submit|buy a listing|"
    r"sponsored placement only)",
    re.I,
)
BLOCKED_DOMAINS = {
    "bing.com", "google.com", "facebook.com", "instagram.com", "linkedin.com",
    "pinterest.com", "tiktok.com", "youtube.com", "x.com", "twitter.com",
    "abill.io", "bill.com", "freshbooks.com", "invoiceninja.com", "invoicey.io",
    "paypal.com", "paymoapp.com", "quickbooks.intuit.com", "stripe.com",
    "waveapps.com", "xero.com", "zoho.com", "buildern.com", "flowlu.com",
    "joist.com", "support.construction", "tallysolutions.com",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._href: str | None = None
        self._anchor: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._anchor).strip()))
            self._href = None
            self._anchor = []

    def handle_data(self, data):
        if self._ignored:
            return
        value = " ".join(data.split())
        if value:
            self.text.append(value)
            if self._href:
                self._anchor.append(value)


def _blocked(domain: str) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in BLOCKED_DOMAINS)


def search_rss(query: str, limit: int = SEARCH_RESULTS_PER_QUERY) -> list[dict]:
    response = requests.get(
        BING_RSS,
        params={"q": query, "format": "rss"},
        headers={"User-Agent": "InvoiceWorkshop-Level0/1.0 (+https://invoiceworkshop.com/)"},
        timeout=20,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    results = []
    for item in root.findall("./channel/item")[:limit]:
        results.append({
            "title": html.unescape(item.findtext("title") or "").strip(),
            "page_url": html.unescape(item.findtext("link") or "").strip(),
            "snippet": html.unescape(item.findtext("description") or "").strip(),
        })
    return results


def heuristic_score(channel: str, title: str, snippet: str, page_url: str) -> int:
    text = f"{title} {snippet} {page_url}".lower()
    if NOISE.search(text):
        return -100
    score = 20
    for term in ("resource", "tools", "guide", "library", "checklist", "template", "invoice"):
        score += 6 if term in text else 0
    for term in {
        "freelancer": ("freelance", "independent worker", "creator"),
        "small_business": ("small business", "entrepreneur", "smb"),
        "accounting": ("accounting", "bookkeeping", "accountant"),
        "contractor": ("contractor", "construction", "trades"),
        "directory": ("directory", "discover", "submit"),
        "editorial": ("best", "roundup", "review"),
        "community": ("community", "forum", "discussion"),
        "linkable_asset": ("checklist", "reference", "example"),
        "competitor_gap": ("invoice", "quotation", "work order", "estimate"),
    }.get(channel, ()):
        score += 10 if term in text else 0
    path = urlsplit(page_url).path.rstrip("/")
    if path:
        score += 8
    return min(score, 100)


def persist_results(connection, channel: str, query: str, rows: list[dict]) -> dict:
    added = duplicates = rejected = 0
    now = utc_now()
    for row in rows:
        try:
            page_url = normalize_public_url(row["page_url"])
            domain = canonical_domain(page_url)
            score = heuristic_score(channel, row["title"], row["snippet"], page_url)
            if _blocked(domain) or score < 35:
                rejected += 1
                continue
            if connection.execute(
                "SELECT 1 FROM prospects WHERE domain=? AND page_url=?", (domain, page_url)
            ).fetchone():
                duplicates += 1
                continue
            cursor = connection.execute(
                """INSERT INTO research_candidates
                   (domain, page_url, channel, query_theme, title, snippet,
                    heuristic_score, discovered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain, page_url) DO NOTHING""",
                (
                    domain, page_url, channel, query, row["title"][:500],
                    row["snippet"][:2000], score, now, now,
                ),
            )
            if cursor.rowcount:
                added += 1
            else:
                duplicates += 1
        except (KeyError, TypeError, ValueError):
            rejected += 1
    connection.commit()
    return {"added": added, "duplicates": duplicates, "rejected": rejected}


def import_vetted(connection, path: str) -> dict:
    """Seed public candidates already checked by a human, without qualifying them."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("vetted candidate file must contain a JSON list")
    added = updated = rejected = 0
    now = utc_now()
    for raw in payload:
        try:
            if not isinstance(raw, dict) or raw.get("channel") not in CHANNEL_QUERIES:
                raise ValueError("invalid candidate or channel")
            page_url = normalize_public_url(str(raw["page_url"]))
            contact_url = normalize_public_url(str(raw["contact_url"]))
            domain = canonical_domain(page_url)
            contact_domain = canonical_domain(contact_url)
            if _blocked(domain) or not (
                domain == contact_domain
                or domain.endswith("." + contact_domain)
                or contact_domain.endswith("." + domain)
            ):
                raise ValueError("blocked domain or cross-site contact route")
            if not CONTACT_HINT.search(urlsplit(contact_url).path) and contact_url != page_url:
                raise ValueError("contact URL is not an explicit route")
            if connection.execute(
                "SELECT 1 FROM prospects WHERE domain=? AND page_url=?", (domain, page_url)
            ).fetchone():
                rejected += 1
                continue
            existing = connection.execute(
                "SELECT id, state FROM research_candidates WHERE domain=? AND page_url=?",
                (domain, page_url),
            ).fetchone()
            values = (
                str(raw["channel"]), str(raw.get("query_theme") or "human-vetted sprint")[:500],
                str(raw.get("title") or "")[:500], str(raw.get("snippet") or "")[:2000],
                contact_url, max(80, min(int(raw.get("heuristic_score", 90)), 100)), now,
            )
            if existing:
                if existing["state"] in {"qualified", "rejected"}:
                    rejected += 1
                    continue
                connection.execute(
                    """UPDATE research_candidates SET channel=?, query_theme=?, title=?, snippet=?,
                              contact_url=?, heuristic_score=?, state='queued', rejection_reason=NULL,
                              updated_at=? WHERE id=?""",
                    (*values, existing["id"]),
                )
                updated += 1
            else:
                connection.execute(
                    """INSERT INTO research_candidates
                       (domain, page_url, channel, query_theme, title, snippet, contact_url,
                        heuristic_score, discovered_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (domain, page_url, *values[:-1], now, now),
                )
                added += 1
        except (KeyError, TypeError, ValueError):
            rejected += 1
    connection.commit()
    return {"added": added, "updated": updated, "rejected": rejected}


def discover(connection, channels: list[str], searches_per_channel: int = 1) -> dict:
    totals = {"queries": 0, "results": 0, "added": 0, "duplicates": 0, "rejected": 0}
    errors = []
    for channel in channels:
        for query in CHANNEL_QUERIES[channel][:searches_per_channel]:
            try:
                rows = search_rss(query)
                outcome = persist_results(connection, channel, query, rows)
                totals["queries"] += 1
                totals["results"] += len(rows)
                for key in ("added", "duplicates", "rejected"):
                    totals[key] += outcome[key]
            except Exception as error:
                errors.append(f"{channel}: {type(error).__name__}: {error}")
    return {**totals, "errors": errors, "external_side_effects": "none"}


def scheduled_channels(connection, run_id: int) -> list[str]:
    channels = list(CHANNEL_QUERIES)
    channel_count = len(channels)
    order = {channel: index for index, channel in enumerate(channels)}
    counts = defaultdict(int)
    for row in connection.execute(
        "SELECT channel, COUNT(*) count FROM research_candidates WHERE state='queued' GROUP BY channel"
    ):
        counts[row["channel"]] = int(row["count"])
    channels.sort(key=lambda item: (counts[item], (order[item] - run_id) % channel_count))
    return channels[:SEARCHES_PER_SCHEDULED_RUN]


def _contact_url(page_url: str, parser: PageParser) -> str | None:
    domain = canonical_domain(page_url)
    candidates = []
    if CONTACT_HINT.search(urlsplit(page_url).path):
        candidates.append((page_url, "page route"))
    for href, label in parser.links:
        if not CONTACT_HINT.search(f"{href} {label}"):
            continue
        try:
            target = normalize_public_url(urljoin(page_url, href))
            if canonical_domain(target) == domain:
                candidates.append((target, label))
        except ValueError:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: ("contact" not in item[0].lower(), len(item[0])))
    return candidates[0][0]


def fetch_candidate(row) -> dict:
    response = fetch_public_url(row["page_url"], timeout=20)
    if response.status_code >= 400:
        raise ValueError(f"HTTP {response.status_code}")
    parser = PageParser()
    parser.feed(response.text[:1_000_000])
    text = " ".join(parser.text)
    if len(text) < 200:
        raise ValueError("page did not expose enough readable evidence")
    if DISQUALIFY_PAGE.search(text):
        raise ValueError("page requires payment, sponsorship, or a reciprocal link")
    contact_url = row["contact_url"] or _contact_url(row["page_url"], parser)
    if not contact_url:
        raise ValueError("no explicit same-site contact/editorial/submission route")
    contact_text = text
    if contact_url != row["page_url"]:
        contact_response = fetch_public_url(contact_url, timeout=20)
        if contact_response.status_code >= 400:
            raise ValueError(f"contact route HTTP {contact_response.status_code}")
        contact_parser = PageParser()
        contact_parser.feed(contact_response.text[:1_000_000])
        contact_text = " ".join(contact_parser.text)
        if len(contact_text) < 100:
            raise ValueError("contact route did not expose enough readable evidence")
    contact_route_verified = bool(CONTACT_HINT.search(
        f"{urlsplit(contact_url).path} {contact_text}"
    ))
    if not contact_route_verified:
        raise ValueError("contact/submission evidence was not present on the contact route")
    return {
        "candidate_id": int(row["id"]),
        "channel": row["channel"],
        "page_url": row["page_url"],
        "contact_url": contact_url,
        "title": row["title"],
        "search_snippet": row["snippet"],
        "heuristic_score": int(row["heuristic_score"]),
        "page_excerpt": text[:3500],
        "contact_excerpt": contact_text[:1800],
        "contact_route_verified": contact_route_verified,
    }


def _diverse_rows(connection, limit: int) -> list:
    rows = connection.execute(
        """SELECT * FROM research_candidates WHERE state='queued'
           ORDER BY heuristic_score DESC, id"""
    ).fetchall()
    selected = []
    seen_channels = set()
    for row in rows:
        if row["channel"] not in seen_channels:
            selected.append(row)
            seen_channels.add(row["channel"])
        if len(selected) == limit:
            return selected
    selected_ids = {row["id"] for row in selected}
    selected.extend(row for row in rows if row["id"] not in selected_ids)
    return selected[:limit]


def prepare_shortlist(connection, limit: int = SHORTLIST_MAX) -> dict:
    shortlisted = []
    deferred = 0
    for row in _diverse_rows(connection, limit * 3):
        if len(shortlisted) >= limit:
            break
        try:
            evidence = fetch_candidate(row)
            connection.execute(
                """UPDATE research_candidates SET state='shortlisted', contact_url=?,
                          updated_at=? WHERE id=?""",
                (evidence["contact_url"], utc_now(), row["id"]),
            )
            shortlisted.append(evidence)
        except Exception as error:
            deferred += 1
            connection.execute(
                """UPDATE research_candidates SET state='deferred', rejection_reason=?,
                          updated_at=? WHERE id=?""",
                (f"deterministic prefilter: {type(error).__name__}: {error}"[:1000], utc_now(), row["id"]),
            )
        connection.commit()
    return {"shortlist": shortlisted, "deferred": deferred, "external_side_effects": "none"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--channel", action="append", choices=sorted(CHANNEL_QUERIES))
    parser.add_argument("--searches-per-channel", type=int, default=1, choices=(1, 2))
    parser.add_argument("--shortlist", type=int, default=0, choices=range(0, SHORTLIST_MAX + 1))
    parser.add_argument("--import-vetted", metavar="JSON_FILE")
    args = parser.parse_args()
    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    channels = list(CHANNEL_QUERIES) if args.all else (args.channel or [])
    result = discover(connection, channels, args.searches_per_channel) if channels else {}
    if args.import_vetted:
        result["vetted_import"] = import_vetted(connection, args.import_vetted)
    if args.shortlist:
        result["qualification_input"] = prepare_shortlist(connection, args.shortlist)
    connection.close()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
