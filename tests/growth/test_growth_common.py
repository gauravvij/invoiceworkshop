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
