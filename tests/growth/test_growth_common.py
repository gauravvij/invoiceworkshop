from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import canonical_domain, normalize_public_url  # noqa: E402


class PublicUrlTests(unittest.TestCase):
    def test_normalizes_public_url_and_removes_fragment(self):
        self.assertEqual(
            normalize_public_url("https://WWW.Example.com/path?q=1#private"),
            "https://www.example.com/path?q=1",
        )
        self.assertEqual(canonical_domain("https://www.example.com/page"), "example.com")

    def test_rejects_unsafe_urls(self):
        unsafe = (
            "file:///etc/passwd",
            "https://user:password@example.com/",
            "http://localhost/",
            "http://sub.localhost/",
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "https://example.com:8443/",
        )
        for value in unsafe:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_public_url(value)

    @patch("growth_common.socket.getaddrinfo")
    def test_rejects_hostname_resolving_to_private_address(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.5", 443))]
        with self.assertRaisesRegex(ValueError, "private or reserved"):
            normalize_public_url("https://example.com/", resolve_dns=True)

    @patch("growth_common.socket.getaddrinfo")
    def test_accepts_hostname_resolving_to_public_address(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        self.assertEqual(
            normalize_public_url("https://example.com", resolve_dns=True),
            "https://example.com/",
        )


if __name__ == "__main__":
    unittest.main()


class IndexationMetricTests(unittest.TestCase):
    """One canonical indexation metric, derived from coverageState.

    A report once said 0 URLs were indexed while five were. Two things caused it:
    Google's sitemap `contents[].indexed` counter, which it no longer populates,
    and `verdict == "PASS"` standing in for "indexed" over a frozen list of nine
    URLs that no longer described the site.
    """

    def _row(self, coverage, verdict="NEUTRAL", crawled=None):
        return {"coverage_state": coverage, "verdict": verdict, "last_crawl_time": crawled}

    def test_the_four_states_are_the_only_answers(self):
        from growth_opportunities import classify_index
        cases = {
            "Submitted and indexed": "indexed",
            "URL is unknown to Google": "unknown",
            "Discovered - currently not indexed": "discovered_not_crawled",
            "Crawled - currently not indexed": "crawled_not_indexed",
        }
        for coverage, expected in cases.items():
            verdict = "PASS" if expected == "indexed" else "NEUTRAL"
            crawled = "2026-09-01T00:00:00Z" if "Crawled" in coverage else None
            self.assertEqual(
                classify_index(self._row(coverage, verdict, crawled)), expected, coverage)

    def test_a_page_google_has_never_fetched_is_not_crawled_not_indexed(self):
        from growth_opportunities import classify_index
        # The distinction the whole diagnosis rests on: nothing has read the
        # page, so the content cannot be why it is missing.
        self.assertEqual(
            classify_index(self._row("Discovered - currently not indexed", crawled=None)),
            "discovered_not_crawled")

    def test_indexation_counts_every_state_and_nothing_twice(self):
        from growth_daily_monitor import _indexation
        rows = [self._row("Submitted and indexed", "PASS"),
                self._row("Submitted and indexed", "PASS"),
                self._row("Discovered - currently not indexed"),
                self._row("URL is unknown to Google")]
        counts = _indexation(rows)
        self.assertEqual(counts, {"indexed": 2, "crawled_not_indexed": 0,
                                  "discovered_not_crawled": 1, "unknown": 1})
        self.assertEqual(sum(counts.values()), len(rows))

    def test_inspection_covers_the_whole_sitemap_not_a_frozen_subset(self):
        from growth_common import PRIORITY_URLS
        from growth_measure import _routes_to_inspect
        routes = _routes_to_inspect()
        self.assertGreater(len(routes), len(PRIORITY_URLS))
        # /about/ is indexed and was outside both the old list and canonical_routes().
        self.assertIn("https://invoiceworkshop.com/about/", routes)

    def test_the_deprecated_sitemap_counter_is_not_read(self):
        import inspect

        import growth_indexnow
        source = inspect.getsource(growth_indexnow)
        self.assertNotIn('contents.get("indexed"', source)
