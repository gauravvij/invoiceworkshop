from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_indexnow as indexnow  # noqa: E402
from growth_common import apply_schema, connect_db  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect_db(str(Path(self.temp.name) / "growth.db"))
        apply_schema(self.connection)
        self.pages = {
            "https://invoiceworkshop.com/": (200, b"<html>home</html>"),
            "https://invoiceworkshop.com/receipt-generator/": (200, b"<html>receipt</html>"),
        }
        self.posted = []

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _get(self, url):
        if url == indexnow.SITEMAP:
            locs = "".join(f"<loc>{u}</loc>" for u in self.pages)
            return 200, f"<urlset>{locs}</urlset>".encode()
        return self.pages.get(url, (404, b""))

    def _submit(self, *, status=200, **kwargs):
        class Response:
            def __init__(self, code):
                self.status = code

            def read(self):
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(request, timeout=None):
            if getattr(request, "data", None):
                self.posted.append(request)
                return Response(status)
            raise AssertionError("unexpected GET through the submit path")

        with mock.patch.object(indexnow, "_get", self._get), \
             mock.patch.object(indexnow.urllib.request, "urlopen", urlopen):
            return indexnow.submit(self.connection, **kwargs)


class SubmissionTests(Fixture):
    def test_a_first_run_submits_every_live_sitemap_url(self):
        result = self._submit()
        self.assertEqual(result["submitted"], 2)

    def test_an_unchanged_url_is_not_submitted_twice(self):
        self._submit()
        again = self._submit()
        self.assertEqual(again["submitted"], 0)
        self.assertIn("nothing changed", again["outcome"])

    def test_a_changed_page_is_resubmitted(self):
        self._submit()
        self.pages["https://invoiceworkshop.com/"] = (200, b"<html>home, rewritten</html>")
        again = self._submit()
        self.assertEqual(again["submitted"], 1)
        self.assertEqual(again["urls"], ["https://invoiceworkshop.com/"])

    def test_a_url_that_is_not_returning_200_is_never_submitted(self):
        self.pages["https://invoiceworkshop.com/receipt-generator/"] = (500, b"boom")
        result = self._submit()
        self.assertEqual(result["submitted"], 1)
        self.assertNotIn("https://invoiceworkshop.com/receipt-generator/", result["urls"])

    def test_a_rejected_batch_is_not_recorded_so_it_retries(self):
        rejected = self._submit(status=422)
        self.assertEqual(rejected["submitted"], 0)
        retried = self._submit(status=200)
        self.assertEqual(retried["submitted"], 2)

    def test_a_dry_run_posts_nothing(self):
        result = self._submit(dry_run=True)
        self.assertEqual(result["outcome"], "dry run")
        self.assertEqual(self.posted, [])
        self.assertEqual(len(result["would_submit"]), 2)


class CoverageTests(Fixture):
    def _coverage(self, pages):
        with mock.patch.object(indexnow, "_get", lambda url: pages.get(url, (200, b""))):
            return indexnow.coverage(self.connection)

    def test_a_zero_result_is_recorded_because_zero_is_the_baseline(self):
        result = self._coverage({q: (200, b"nothing here") for q in indexnow.COVERAGE.values()})
        self.assertEqual(result["engines"]["bing"]["urls_seen"], 0)
        rows = list(self.connection.execute("SELECT engine, urls_seen FROM search_coverage"))
        self.assertIn(("bing", 0), [tuple(r) for r in rows])

    def test_found_urls_are_counted_once_each(self):
        body = (b"https://invoiceworkshop.com/receipt-generator/ "
                b"https://invoiceworkshop.com/receipt-generator/ "
                b"https://invoiceworkshop.com/credit-note-generator/")
        result = self._coverage({q: (200, body) for q in indexnow.COVERAGE.values()})
        self.assertEqual(result["engines"]["bing"]["urls_seen"], 2)

    def test_a_blocked_query_is_an_error_not_a_zero(self):
        pages = {q: (202, b"") for q in indexnow.COVERAGE.values()}
        result = self._coverage(pages)
        self.assertIn("error", result["engines"]["bing"])
        self.assertEqual(list(self.connection.execute("SELECT * FROM search_coverage")), [])


class SitemapTests(Fixture):
    class FakeClient:
        def __init__(self, has, submitted=None):
            self.has = has
            self.submitted = submitted if submitted is not None else has
            self.calls = []

        def sitemap_state(self, site, sm):
            return {"urls_google_has": self.has}

        def submit_sitemap(self, site, sm):
            self.calls.append((site, sm))
            self.has = self.submitted
            return {"urls_google_has": self.has}

    def _sitemap(self, client, **kwargs):
        import growth_google
        with mock.patch.object(indexnow, "_get", self._get), \
             mock.patch.object(growth_google, "GoogleSitemapClient", lambda *a, **k: client):
            return indexnow.sitemap(self.connection, **kwargs)

    def test_a_stale_google_copy_is_resubmitted(self):
        # The real case: Google held 13 URLs while the live sitemap listed 22.
        client = self.FakeClient(has=1, submitted=2)
        result = self._sitemap(client)
        self.assertEqual(result["action"], "resubmitted")
        self.assertEqual(len(client.calls), 1)

    def test_a_current_google_copy_is_left_alone(self):
        client = self.FakeClient(has=2)
        result = self._sitemap(client)
        self.assertIn("none", result["action"])
        self.assertEqual(client.calls, [])

    def test_force_resubmits_even_when_current(self):
        client = self.FakeClient(has=2)
        self._sitemap(client, force=True)
        self.assertEqual(len(client.calls), 1)


class KeyTests(unittest.TestCase):
    def test_the_key_file_the_protocol_checks_is_actually_served_from_public(self):
        served = Path(__file__).resolve().parents[2] / "public" / f"{indexnow.KEY}.txt"
        self.assertTrue(served.exists(), f"{served} is missing, so IndexNow cannot verify the host")
        self.assertEqual(served.read_text(encoding="utf-8").strip(), indexnow.KEY)

    def test_the_key_location_points_at_that_file(self):
        self.assertTrue(indexnow.KEY_LOCATION.endswith(f"/{indexnow.KEY}.txt"))


if __name__ == "__main__":
    unittest.main()
