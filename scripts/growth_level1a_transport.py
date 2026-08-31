#!/usr/bin/env python3
"""Restricted Level-1A transports. This module has no general-purpose send CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


_VALIDATED = object()


@dataclass(frozen=True)
class ValidatedDelivery:
    action_id: int
    message_id: str
    from_address: str
    from_name: str
    recipient: str
    subject: str
    body: str
    _capability: object

    @classmethod
    def from_validator(
        cls, *, action_id: int, message_id: str, recipient: str, subject: str, body: str
    ) -> "ValidatedDelivery":
        return cls(
            action_id=action_id,
            message_id=message_id,
            from_address="hello@invoiceworkshop.com",
            from_name="InvoiceWorkshop",
            recipient=recipient,
            subject=subject,
            body=body,
            _capability=_VALIDATED,
        )


def _read_secret_file(variable: str) -> str:
    path_value = os.environ.get(variable, "").strip()
    if not path_value:
        raise RuntimeError(f"{variable} is not configured")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{variable} does not identify a readable file")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"{variable} file is empty")
    return value


class ZohoMailTransport:
    """Zoho Mail API adapter which accepts only validator-created deliveries."""

    def send(self, delivery: ValidatedDelivery) -> str:
        if delivery._capability is not _VALIDATED:
            raise RuntimeError("delivery did not originate from the Level-1A validator")
        if delivery.from_address != "hello@invoiceworkshop.com" or delivery.from_name != "InvoiceWorkshop":
            raise RuntimeError("sender identity is not the approved mailbox identity")

        account_id = os.environ.get("ZOHO_MAIL_ACCOUNT_ID", "").strip()
        if not account_id.isdigit():
            raise RuntimeError("ZOHO_MAIL_ACCOUNT_ID is not configured")
        access_token = _read_secret_file("ZOHO_MAIL_ACCESS_TOKEN_FILE")
        api_base = os.environ.get("ZOHO_MAIL_API_BASE", "https://mail.zoho.in/api").rstrip("/")

        import requests

        response = requests.post(
            f"{api_base}/accounts/{account_id}/messages",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "InvoiceWorkshop-Level1A/1.0",
            },
            data=json.dumps({
                "fromAddress": delivery.from_address,
                "toAddress": delivery.recipient,
                "subject": delivery.subject,
                "content": delivery.body,
                "mailFormat": "plaintext",
                "askReceipt": "no",
            }),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        provider_id = str(payload.get("data", {}).get("messageId") or payload.get("data", {}).get("mailId") or "")
        if not provider_id:
            raise RuntimeError("Zoho accepted the request without returning a message identifier")
        return provider_id


class FormTransport:
    """No generic form submission is permitted; allowlisted handlers are separate work."""

    def send(self, _delivery: ValidatedDelivery) -> str:
        raise RuntimeError("no allowlisted site-specific Level-1A form handler is installed")
