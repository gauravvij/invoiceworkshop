from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_search_providers as providers  # noqa: E402
from growth_search_providers import (  # noqa: E402
    AnySearchProvider,
    BingRssProvider,
    SearchProviderError,
    SearchQuotaExhausted,
    get_provider,
)


class Response:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SelectionTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("BACKLINK_SEARCH_PROVIDER", None)

    def test_anysearch_is_the_default(self):
        self.assertEqual(get_provider().name, "anysearch")

    def test_provider_is_configurable_by_environment(self):
        os.environ["BACKLINK_SEARCH_PROVIDER"] = "bing_rss"
        self.assertEqual(get_provider().name, "bing_rss")

    def test_unknown_provider_is_an_explicit_error(self):
        with self.assertRaisesRegex(SearchProviderError, "unknown search provider"):
            get_provider("brave")

    def test_registry_is_open_for_another_provider(self):
        self.assertIn("anysearch", providers.PROVIDERS)
        self.assertIn("bing_rss", providers.PROVIDERS)


class AnySearchTests(unittest.TestCase):
    def setUp(self):
        self.provider = AnySearchProvider()
        self.provider.min_interval_seconds = 0

    def _payload(self, rows):
        return {"code": 0, "message": "success", "data": {"results": rows, "metadata": {}}}

    def test_results_are_normalized(self):
        payload = self._payload([{
            "title": "Freelancer Resources",
            "url": "https://example.org/resources/",
            "snippet": "Invoicing tools",
            "content": "Longer body text about invoicing tools",
        }])
        with patch("growth_search_providers.requests.post", return_value=Response(payload)):
            rows = self.provider.search("freelancer resources invoice")
        self.assertEqual(rows, [{
            "title": "Freelancer Resources",
            "page_url": "https://example.org/resources/",
            "snippet": "Invoicing tools",
            "content": "Longer body text about invoicing tools",
        }])

    def test_content_falls_back_to_snippet(self):
        payload = self._payload([{"title": "T", "url": "https://example.org/a/", "snippet": "S"}])
        with patch("growth_search_providers.requests.post", return_value=Response(payload)):
            rows = self.provider.search("q")
        self.assertEqual(rows[0]["content"], "S")

    def test_rows_without_a_url_are_dropped(self):
        payload = self._payload([{"title": "T", "url": "", "snippet": "S"}])
        with patch("growth_search_providers.requests.post", return_value=Response(payload)):
            self.assertEqual(self.provider.search("q"), [])

    def test_limit_is_respected(self):
        payload = self._payload([
            {"title": f"T{i}", "url": f"https://example.org/{i}/", "snippet": "s"}
            for i in range(20)
        ])
        with patch("growth_search_providers.requests.post", return_value=Response(payload)):
            self.assertEqual(len(self.provider.search("q", limit=5)), 5)

    def test_error_code_is_surfaced(self):
        payload = {"code": 42, "message": "nope", "data": {}}
        with patch("growth_search_providers.requests.post", return_value=Response(payload)):
            with self.assertRaisesRegex(SearchProviderError, "code 42"):
                self.provider.search("q")

    def test_transport_failure_raises_rather_than_returning_empty(self):
        with patch("growth_search_providers.requests.post", side_effect=OSError("boom")), \
                patch("growth_search_providers.time.sleep"):
            with self.assertRaisesRegex(SearchProviderError, "anysearch request failed"):
                self.provider.search("q")

    def test_quota_refusal_is_surfaced_with_its_status(self):
        for status in (401, 402, 403):
            with patch("growth_search_providers.requests.post",
                       return_value=Response({}, status_code=status)):
                with self.assertRaises(SearchQuotaExhausted) as caught:
                    self.provider.search("q")
            self.assertIn(str(status), str(caught.exception))

    def test_credentials_offered_by_the_provider_are_never_adopted(self):
        """A 402 body may hand back an auto-provisioned account. Ignore it."""
        offered = {
            "code": -1,
            "message": ("Your account and API key have been automatically generated. "
                        "Use the API key below to continue.\nusername=as_auto_x\n"
                        "password=hunter2\napi_key=as_sk_deadbeef"),
        }
        with patch("growth_search_providers.requests.post",
                   return_value=Response(offered, status_code=402)):
            with self.assertRaises(SearchQuotaExhausted):
                self.provider.search("q")
        # The offer must not have been read into the client's credentials.
        self.assertIsNone(self.provider.api_key)
        self.assertNotIn("Authorization", self.provider._headers())

    def test_quota_error_is_not_retried_into_a_generic_failure(self):
        calls = []

        def post(*args, **kwargs):
            calls.append(1)
            return Response({}, status_code=402)

        with patch("growth_search_providers.requests.post", side_effect=post):
            with self.assertRaises(SearchQuotaExhausted):
                self.provider.search("q")
        self.assertEqual(len(calls), 1)

    def test_api_key_is_optional_and_sent_when_present(self):
        self.assertNotIn("Authorization", AnySearchProvider(api_key=None)._headers())
        self.assertEqual(
            AnySearchProvider(api_key="secret")._headers()["Authorization"], "Bearer secret"
        )


class NoSilentFallbackTests(unittest.TestCase):
    def test_engine_does_not_fall_back_to_another_provider(self):
        source = (SCRIPTS / "growth_backlink_engine.py").read_text(encoding="utf-8")
        # The engine must never name a concrete provider or reach for a second one.
        self.assertNotIn("BingRssProvider", source)
        self.assertNotIn("bing.com", source)
        self.assertIn("SearchProviderError", source)

    def test_a_provider_failure_is_recorded_not_swallowed(self):
        source = (SCRIPTS / "growth_backlink_engine.py").read_text(encoding="utf-8")
        self.assertIn("search provider failed", source)

    def test_bing_is_flagged_as_not_honouring_operators(self):
        self.assertFalse(BingRssProvider.honours_operators)


if __name__ == "__main__":
    unittest.main()
