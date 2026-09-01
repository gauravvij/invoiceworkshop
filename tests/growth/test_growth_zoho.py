from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_zoho import FROM_HEADER, REQUIRED_SCOPES, ZohoClient, ZohoError  # noqa: E402


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class ZohoClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "oauth.json"
        self.data = {
            "client_id": "redacted", "client_secret": "redacted",
            "refresh_token": "redacted", "access_token": "redacted",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
            "accounts_base": "https://accounts.zoho.in",
            "mail_api_base": "https://mail.zoho.in/api",
            "scope": sorted(REQUIRED_SCOPES),
        }
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.path.write_text(json.dumps(self.data))
        os.chmod(self.path, 0o600)

    def test_exact_scopes_and_india_endpoints_are_required(self):
        client = ZohoClient(self.path)
        self.assertEqual(set(client.data["scope"]), REQUIRED_SCOPES)
        self.data["scope"].append("ZohoMail.messages.ALL")
        self.write()
        with self.assertRaisesRegex(ZohoError, "exactly"):
            ZohoClient(self.path)

    def test_group_readable_secret_is_rejected(self):
        os.chmod(self.path, 0o640)
        with self.assertRaisesRegex(ZohoError, "mode 600"):
            ZohoClient(self.path)

    def test_account_resolution_pins_exact_mailbox(self):
        payload = {
            "status": {"code": 200},
            "data": [{"accountId": "123", "emailAddress": [{"mailId": "hello@invoiceworkshop.com"}]}],
        }
        with patch("growth_zoho.requests.get", return_value=Response(payload)):
            client = ZohoClient(self.path)
            self.assertEqual(client.resolve_account_id(), "123")
        stored = json.loads(self.path.read_text())
        self.assertEqual(stored["account_id"], "123")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_sends_carry_the_approved_from_display_name(self):
        self.data["account_id"] = "123"
        self.write()
        account = {
            "status": {"code": 200},
            "data": [{"accountId": "123", "emailAddress": [{"mailId": "hello@invoiceworkshop.com"}]}],
        }
        sent = {"status": {"code": 200}, "data": {"messageId": "m1", "threadId": "t1"}}
        captured = {}

        def post(url, **kwargs):
            captured.update(kwargs.get("json") or {})
            return Response(sent)

        with patch("growth_zoho.requests.get", return_value=Response(account)), \
                patch("growth_zoho.requests.post", side_effect=post):
            client = ZohoClient(self.path)
            client.send_plaintext(recipient="owner@example.com", subject="s", body="b")
            self.assertEqual(captured["fromAddress"], "InvoiceWorkshop <hello@invoiceworkshop.com>")
            captured.clear()
            client.reply_plaintext(
                message_id="m0", recipient="owner@example.com", subject="s", body="b"
            )
            self.assertEqual(captured["fromAddress"], FROM_HEADER)

    def test_from_header_is_the_exact_approved_identity(self):
        self.assertEqual(FROM_HEADER, "InvoiceWorkshop <hello@invoiceworkshop.com>")


if __name__ == "__main__":
    unittest.main()
