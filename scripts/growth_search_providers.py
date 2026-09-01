#!/usr/bin/env python3
"""Pluggable read-only web-search providers for backlink discovery.

Selected with `BACKLINK_SEARCH_PROVIDER`. There is deliberately no fallback
chain: if the configured provider fails, the caller sees the failure. Silently
degrading to a weaker source would quietly poison the CRM with low-quality
candidates, which is exactly how the Bing RSS problem went unnoticed.

Every provider performs read-only HTTP requests and returns normalized rows:
`{"title", "page_url", "snippet", "content"}`.
"""

from __future__ import annotations

import html
import json
import os
import time
import xml.etree.ElementTree as ET
from typing import Protocol

import requests

USER_AGENT = "InvoiceWorkshop-Level0/1.0 (+https://invoiceworkshop.com/)"
DEFAULT_PROVIDER = "anysearch"
DEFAULT_LIMIT = 12


class SearchProviderError(RuntimeError):
    """The configured provider could not answer. Never swallowed silently."""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        ...


class AnySearchProvider:
    """api.anysearch.com — POST /v1/search.

    Anonymous access is supported and an API key is optional; when
    `ANYSEARCH_API_KEY` is present it is sent as a bearer token. Calibration on
    2026-09-01 measured roughly ten results per query with no pagination, so
    breadth comes from many distinct queries rather than deep result pages.
    """

    name = "anysearch"
    endpoint = "https://api.anysearch.com/v1/search"
    # Observed guard is a QPS-style limit of 10 with an immediately-resetting
    # window, so a small spacing keeps requests comfortably inside it.
    min_interval_seconds = 0.4

    def __init__(self, api_key: str | None = None, timeout: int = 45):
        self.api_key = api_key or os.environ.get("ANYSEARCH_API_KEY") or None
        self.timeout = timeout
        self._last_call = 0.0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        gap = time.monotonic() - self._last_call
        if gap < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - gap)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    self.endpoint, headers=self._headers(),
                    json={"query": query}, timeout=self.timeout,
                )
                self._last_call = time.monotonic()
                if response.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as error:
                last_error = error
                time.sleep(1.5 * (attempt + 1))
        else:
            raise SearchProviderError(
                f"anysearch request failed: {type(last_error).__name__}"
            ) from last_error

        if payload.get("code") not in (0, None):
            raise SearchProviderError(f"anysearch returned code {payload.get('code')}")
        rows = (payload.get("data") or {}).get("results") or []
        results = []
        for row in rows[:limit]:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            snippet = (row.get("snippet") or "").strip()
            results.append({
                "title": (row.get("title") or "").strip(),
                "page_url": url,
                "snippet": snippet,
                # `content` is usually a longer echo of the snippet; keeping it
                # gives the cheap filter more text without an extra page fetch.
                "content": (row.get("content") or snippet).strip(),
            })
        return results


class BingRssProvider:
    """Legacy `bing.com/search?format=rss`.

    Retained only so the historical source stays runnable for comparison. It
    was measured on 2026-09-01 to ignore `site:` and quoted-phrase operators
    entirely, so it must never be selected as a silent fallback.
    """

    name = "bing_rss"
    endpoint = "https://www.bing.com/search"
    honours_operators = False

    def __init__(self, timeout: int = 25):
        self.timeout = timeout

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        try:
            response = requests.get(
                self.endpoint, params={"q": query, "format": "rss"},
                headers={"User-Agent": USER_AGENT}, timeout=self.timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as error:
            raise SearchProviderError(f"bing_rss request failed: {type(error).__name__}") from error
        results = []
        for item in root.findall("./channel/item")[:limit]:
            snippet = html.unescape(item.findtext("description") or "").strip()
            results.append({
                "title": html.unescape(item.findtext("title") or "").strip(),
                "page_url": html.unescape(item.findtext("link") or "").strip(),
                "snippet": snippet,
                "content": snippet,
            })
        return results


PROVIDERS = {
    AnySearchProvider.name: AnySearchProvider,
    BingRssProvider.name: BingRssProvider,
    # Brave or another SERP API slots in here without touching the engine.
}


def get_provider(name: str | None = None) -> SearchProvider:
    selected = (name or os.environ.get("BACKLINK_SEARCH_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if selected not in PROVIDERS:
        raise SearchProviderError(
            f"unknown search provider {selected!r}; available: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[selected]()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Probe a configured search provider")
    parser.add_argument("query")
    parser.add_argument("--provider")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    provider = get_provider(args.provider)
    rows = provider.search(args.query, args.limit)
    print(json.dumps({"provider": provider.name, "count": len(rows), "results": rows}, indent=2))


if __name__ == "__main__":
    main()
