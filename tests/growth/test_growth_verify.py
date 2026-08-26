from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_verify import page_links_to, same_target  # noqa: E402


class PlacementLinkTests(unittest.TestCase):
    def test_finds_real_anchor_and_resolves_relative_url(self):
        html = '<p>Useful: <a href="/invoice-template/?source=list">Invoice tool</a></p>'
        self.assertTrue(
            page_links_to(
                html,
                "https://invoiceworkshop.com/resources/",
                "https://invoiceworkshop.com/invoice-template/",
            )
        )

    def test_ignores_plain_text_and_script_content(self):
        html = """
        <p>https://invoiceworkshop.com/</p>
        <script>const url = 'https://invoiceworkshop.com/';</script>
        <a href="https://example.com/">Different site</a>
        """
        self.assertFalse(
            page_links_to(html, "https://example.org/list", "https://invoiceworkshop.com/")
        )

    def test_target_match_ignores_www_query_and_trailing_slash_only(self):
        self.assertTrue(
            same_target(
                "https://www.invoiceworkshop.com/invoice-template/?ref=editorial",
                "https://invoiceworkshop.com/invoice-template/",
            )
        )
        self.assertFalse(
            same_target(
                "https://invoiceworkshop.com/proforma-invoice-generator/",
                "https://invoiceworkshop.com/",
            )
        )


if __name__ == "__main__":
    unittest.main()
