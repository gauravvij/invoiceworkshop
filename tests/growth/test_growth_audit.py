from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_audit as audit  # noqa: E402


class SampleTests(unittest.TestCase):
    def test_a_tool_page_is_a_candidate(self):
        ok, _ = audit._is_candidate("https://example-invoices.com/invoice-generator")
        self.assertTrue(ok)

    def test_an_app_store_listing_is_not_a_tool(self):
        ok, why = audit._is_candidate("https://play.google.com/store/apps/details?id=x")
        self.assertFalse(ok)
        self.assertIn("not a tool host", why)

    def test_an_article_about_tools_is_not_a_tool(self):
        ok, why = audit._is_candidate("https://vendor.com/blog/best-invoice-generators")
        self.assertFalse(ok)
        self.assertIn("article path", why)

    def test_a_search_engine_redirect_is_not_a_tool_page(self):
        # One of these was drawn into the first frame and measured as if it were
        # a product. It is a wrapper, and nobody can visit it twice.
        ok, why = audit._is_candidate("https://www.google.com/goto?url=CAESzwEB6zsw")
        self.assertFalse(ok)
        self.assertIn("redirect", why)


class RowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _row(self, **evidence):
        base = {"fields_filled": 5, "canary_left_the_browser": False,
                "canary_left_to_third_party": False, "canary_destinations": [],
                "leaked_fields": [], "third_party_domains": [], "login_form_present": False}
        base.update(evidence)
        return audit._row({"domain": "example.com", "url": "https://example.com/"},
                          base, self.folder)

    def test_an_unmeasured_tool_is_not_recorded_as_passing(self):
        # The difference the whole study rests on: we could not tell, which is
        # not the same as it did not happen.
        row = self._row(canary_left_the_browser=None, canary_left_to_third_party=None)
        self.assertEqual(row["typed_data_left_the_browser"], "unmeasured")
        self.assertEqual(row["sent_to_an_unrelated_domain"], "unmeasured")

    def test_a_first_party_send_is_not_reported_as_a_third_party_send(self):
        row = self._row(canary_left_the_browser=True, canary_left_to_third_party=False,
                        canary_destinations=[{"domain": "example.com", "first_party": True}])
        self.assertEqual(row["typed_data_left_the_browser"], "yes")
        self.assertEqual(row["sent_to_an_unrelated_domain"], "no")

    def test_a_differently_named_domain_of_the_same_tool_is_not_an_outsider(self):
        # invoicesimple.com posts to getinvoicesimple.com. Publishing that as
        # "sent to a third party" would be a false accusation.
        self.assertTrue(audit.same_operator("invoicesimple.com", "getinvoicesimple.com"))
        self.assertFalse(audit.same_operator("invoicesimple.com", "intercom.io"))
        self.assertFalse(audit.same_operator("xero.com", "unifyintent.com"))

    def test_an_outside_recipient_is_named(self):
        row = self._row(canary_left_the_browser=True,
                        canary_destinations=[{"domain": "intercom.io", "first_party": False}])
        self.assertEqual(row["sent_to_an_unrelated_domain"], "yes")
        self.assertEqual(row["unrelated_recipients"], "intercom.io")

    def test_the_leaking_field_is_named(self):
        row = self._row(canary_left_the_browser=True,
                        leaked_fields=[{"type": "email", "name": "newsletter_email",
                                        "placeholder": "", "label": ""}])
        self.assertEqual(row["fields_that_left"], "newsletter_email")

    def test_a_missing_claim_file_is_unmeasured_rather_than_no(self):
        self.assertEqual(self._row()["claims_local_processing"], "unmeasured")


class DatasetTests(unittest.TestCase):
    """The publisher's own tool must not be inside its own percentages."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.saved = (audit.DATA, audit.FRAME, audit.MEASUREMENTS, audit.ROOT)
        audit.ROOT = root
        audit.DATA = root / "data" / "audit"
        audit.FRAME = audit.DATA / "frame.json"
        audit.MEASUREMENTS = audit.DATA / "measurements"
        audit.DATA.mkdir(parents=True)
        candidates = [
            {"domain": "a.com", "url": "https://a.com/", "is_publisher_own_tool": False},
            {"domain": "b.com", "url": "https://b.com/", "is_publisher_own_tool": False},
            {"domain": "invoiceworkshop.com", "url": "https://invoiceworkshop.com/",
             "is_publisher_own_tool": True},
        ]
        audit.FRAME.write_text(json.dumps({
            "drawn_on": "2026-09-05T00:00:00Z", "queries": ["q"], "candidates": candidates}))
        for domain, left in (("a.com", True), ("b.com", False), ("invoiceworkshop.com", False)):
            folder = audit.MEASUREMENTS / domain
            folder.mkdir(parents=True)
            (folder / "evidence.json").write_text(json.dumps({
                "fields_filled": 4, "canary_left_the_browser": left,
                "canary_left_to_third_party": left, "canary_destinations": [],
                "leaked_fields": [], "third_party_domains": ["x.com"] * 3,
                "login_form_present": False}))

    def tearDown(self):
        audit.DATA, audit.FRAME, audit.MEASUREMENTS, audit.ROOT = self.saved
        self.temp.cleanup()

    def test_headline_counts_exclude_the_publishers_own_tool(self):
        summary = audit.dataset()
        self.assertEqual(summary["third_party_tools"], 2)
        self.assertEqual(summary["measurable"], 2)
        self.assertEqual(summary["typed_data_left_the_browser"], 1)
        self.assertEqual(summary["kept_in_the_browser"], 1)

    def test_the_csv_still_lists_the_publishers_own_tool(self):
        audit.dataset()
        csv_text = (audit.ROOT / "public" / "research"
                    / "free-invoice-generator-audit-2026.csv").read_text()
        self.assertIn("invoiceworkshop.com", csv_text)
        self.assertIn("publisher_own_tool", csv_text)


class HarnessTests(unittest.TestCase):
    """The domain parser, exercised in the runtime that actually uses it."""

    def _registrable(self, url: str) -> str:
        out = subprocess.run(
            ["node", "-e",
             "const {registrable}=require('./scripts/audit_domain.cjs');"
             "console.log(registrable(process.argv[1]));", url],
            capture_output=True, text=True, timeout=30, cwd=str(SCRIPTS.parent))
        return out.stdout.strip()

    def test_a_two_label_domain_is_itself(self):
        self.assertEqual(self._registrable("https://plaininvoice.com/x"), "plaininvoice.com")

    def test_a_subdomain_reduces_to_its_registrable_domain(self):
        self.assertEqual(self._registrable("https://api.unifyintent.com/v1"), "unifyintent.com")

    def test_a_multi_part_suffix_is_not_mistaken_for_the_domain(self):
        # "tools.rounded.com.au" read as "com.au" turned a tool posting to its
        # own server into a tool posting to a stranger.
        self.assertEqual(self._registrable("https://tools.rounded.com.au/"), "rounded.com.au")
        self.assertEqual(self._registrable("https://poundkit.co.uk/a"), "poundkit.co.uk")


if __name__ == "__main__":
    unittest.main()
