#!/usr/bin/env python3
"""Least-privilege Zoho India OAuth client for the restricted growth wrappers."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

MAILBOX = "hello@invoiceworkshop.com"
DISPLAY_NAME = "InvoiceWorkshop"
# Zoho emits the From header verbatim from `fromAddress`; the mailbox displayName
# setting only governs webmail compose, so the identity must be spelled out here.
FROM_HEADER = f"{DISPLAY_NAME} <{MAILBOX}>"
REQUIRED_SCOPES = {
    "ZohoMail.accounts.READ",
    "ZohoMail.messages.READ",
    "ZohoMail.messages.CREATE",
}
DEFAULT_SECRET = Path("/home/azureuser/.config/invoiceworkshop/zoho_oauth.json")


class ZohoError(RuntimeError):
    pass


def _contains_mailbox(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_mailbox(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_mailbox(item) for item in value)
    return isinstance(value, str) and value.lower() == MAILBOX


class ZohoClient:
    def __init__(self, secret_path: str | Path | None = None):
        configured = secret_path or os.environ.get("ZOHO_OAUTH_SECRET_FILE") or DEFAULT_SECRET
        self.path = Path(configured).expanduser().resolve()
        if not self.path.is_file():
            raise ZohoError("Zoho OAuth secret file is not configured")
        if self.path.stat().st_mode & 0o077:
            raise ZohoError("Zoho OAuth secret file must have mode 600")
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        scopes = set(self.data.get("scope", []))
        if scopes != REQUIRED_SCOPES:
            raise ZohoError("Zoho OAuth secret does not contain exactly the reviewed least-privilege scopes")
        if self.data.get("accounts_base") != "https://accounts.zoho.in":
            raise ZohoError("Zoho OAuth accounts endpoint is not the India endpoint")
        if self.data.get("mail_api_base") != "https://mail.zoho.in/api":
            raise ZohoError("Zoho Mail API endpoint is not the India endpoint")

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        handle, temporary = tempfile.mkstemp(prefix=".zoho-oauth-", dir=self.path.parent)
        try:
            os.fchmod(handle, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _refresh_if_needed(self) -> None:
        try:
            expires_at = datetime.fromisoformat(str(self.data["expires_at"]))
        except (KeyError, ValueError) as error:
            raise ZohoError("Zoho OAuth secret has no valid expiration timestamp") from error
        if expires_at > datetime.now(timezone.utc) + timedelta(seconds=15):
            return
        response = requests.post(
            self.data["accounts_base"] + "/oauth/v2/token",
            data={
                "client_id": self.data["client_id"],
                "client_secret": self.data["client_secret"],
                "refresh_token": self.data["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        payload = self._payload(response, "OAuth refresh")
        if "access_token" not in payload:
            raise ZohoError("Zoho OAuth refresh returned no access token")
        self.data["access_token"] = payload["access_token"]
        self.data["expires_at"] = (
            datetime.now(timezone.utc)
            + timedelta(seconds=int(payload.get("expires_in", 3600)) - 60)
        ).isoformat()
        self._persist()

    @staticmethod
    def _payload(response: requests.Response, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as error:
            raise ZohoError(f"{operation} failed with HTTP {response.status_code} and non-JSON output") from error
        if response.status_code >= 400:
            safe = {key: payload.get(key) for key in ("error", "error_description", "message") if key in payload}
            raise ZohoError(f"{operation} failed with HTTP {response.status_code}: {safe}")
        status = payload.get("status")
        if isinstance(status, dict) and int(status.get("code", 200)) >= 400:
            raise ZohoError(f"{operation} failed: {status.get('description', 'unknown Zoho error')}")
        return payload

    def _headers(self) -> dict[str, str]:
        self._refresh_if_needed()
        return {
            "Authorization": "Zoho-oauthtoken " + self.data["access_token"],
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "InvoiceWorkshop-Level1A/1.0",
        }

    @property
    def api_base(self) -> str:
        return str(self.data["mail_api_base"]).rstrip("/")

    def resolve_account_id(self) -> str:
        payload = self._payload(
            requests.get(self.api_base + "/accounts", headers=self._headers(), timeout=30),
            "account lookup",
        )
        matches = [row for row in payload.get("data", []) if _contains_mailbox(row)]
        if len(matches) != 1 or not matches[0].get("accountId"):
            raise ZohoError(f"expected exactly one {MAILBOX} account, found {len(matches)}")
        account_id = str(matches[0]["accountId"])
        configured = self.data.get("account_id")
        if configured and str(configured) != account_id:
            raise ZohoError("resolved account ID differs from the pinned account ID")
        if not configured:
            self.data["account_id"] = account_id
            self._persist()
        return account_id

    def send_identity(self) -> dict[str, object]:
        payload = self._payload(
            requests.get(self.api_base + "/accounts", headers=self._headers(), timeout=30),
            "send identity lookup",
        )
        matches = []
        for account in payload.get("data", []):
            for detail in account.get("sendMailDetails", []) if isinstance(account, dict) else []:
                if isinstance(detail, dict) and str(detail.get("fromAddress", "")).lower() == MAILBOX:
                    matches.append(detail)
        if len(matches) != 1:
            raise ZohoError(f"expected one {MAILBOX} send identity, found {len(matches)}")
        return {
            "from_address": MAILBOX,
            "display_name": str(matches[0].get("displayName") or ""),
            "enabled": bool(matches[0].get("status", True)),
        }

    def list_messages(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ZohoError("message list limit must be between 1 and 200")
        account_id = self.resolve_account_id()
        payload = self._payload(
            requests.get(
                f"{self.api_base}/accounts/{account_id}/messages/view",
                headers=self._headers(),
                params={"limit": limit, "includesent": "false", "sortBy": "date", "sortorder": "false"},
                timeout=30,
            ),
            "message list",
        )
        rows = payload.get("data", [])
        return rows if isinstance(rows, list) else []

    def get_message_content(self, folder_id: str, message_id: str) -> str:
        account_id = self.resolve_account_id()
        payload = self._payload(
            requests.get(
                f"{self.api_base}/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/content",
                headers=self._headers(), timeout=30,
            ),
            "message content",
        )
        data = payload.get("data", {})
        if isinstance(data, dict):
            for key in ("content", "messageContent", "htmlContent"):
                if isinstance(data.get(key), str):
                    return data[key]
        if isinstance(data, str):
            return data
        raise ZohoError("message content response contained no readable content")

    def get_message_headers(self, folder_id: str, message_id: str) -> dict[str, Any]:
        account_id = self.resolve_account_id()
        return self._payload(
            requests.get(
                f"{self.api_base}/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/header",
                headers=self._headers(), timeout=30,
            ),
            "message headers",
        )

    def send_plaintext(self, *, recipient: str, subject: str, body: str) -> dict[str, str]:
        account_id = self.resolve_account_id()
        payload = self._payload(
            requests.post(
                f"{self.api_base}/accounts/{account_id}/messages",
                headers=self._headers(),
                json={
                    "fromAddress": FROM_HEADER, "toAddress": recipient,
                    "subject": subject, "content": body, "mailFormat": "plaintext",
                    "askReceipt": "no",
                },
                timeout=30,
            ),
            "message send",
        )
        data = payload.get("data", {}) if isinstance(payload.get("data", {}), dict) else {}
        message_id = str(data.get("messageId") or data.get("mailId") or "")
        if not message_id:
            raise ZohoError("Zoho accepted the send without a message identifier")
        return {"message_id": message_id, "thread_id": str(data.get("threadId") or "")}

    def reply_plaintext(
        self, *, message_id: str, recipient: str, subject: str, body: str
    ) -> dict[str, str]:
        account_id = self.resolve_account_id()
        payload = self._payload(
            requests.post(
                f"{self.api_base}/accounts/{account_id}/messages/{message_id}",
                headers=self._headers(),
                json={
                    "fromAddress": FROM_HEADER, "toAddress": recipient,
                    "subject": subject, "content": body, "action": "reply",
                    "mailFormat": "plaintext", "askReceipt": "no",
                },
                timeout=30,
            ),
            "message reply",
        )
        data = payload.get("data", {}) if isinstance(payload.get("data", {}), dict) else {}
        reply_id = str(data.get("messageId") or data.get("mailId") or "")
        if not reply_id:
            raise ZohoError("Zoho accepted the reply without a message identifier")
        return {"message_id": reply_id, "thread_id": str(data.get("threadId") or "")}
