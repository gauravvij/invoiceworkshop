#!/usr/bin/env python3
"""Restricted Level-1A transports. This module has no general-purpose send CLI."""

from __future__ import annotations

from dataclasses import dataclass

from growth_zoho import ZohoClient


_VALIDATED = object()


class PreSendTransportError(RuntimeError):
    """A transport precondition failed before a message-create request."""


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


@dataclass(frozen=True)
class TransportResult:
    message_id: str
    thread_id: str = ""


class ZohoMailTransport:
    """Zoho Mail API adapter which accepts only validator-created deliveries."""

    def send(self, delivery: ValidatedDelivery) -> TransportResult:
        if delivery._capability is not _VALIDATED:
            raise RuntimeError("delivery did not originate from the Level-1A validator")
        if delivery.from_address != "hello@invoiceworkshop.com" or delivery.from_name != "InvoiceWorkshop":
            raise RuntimeError("sender identity is not the approved mailbox identity")

        try:
            client = ZohoClient()
            identity = client.send_identity()
        except Exception as error:
            raise PreSendTransportError(f"Zoho pre-send verification failed: {type(error).__name__}") from error
        if identity["display_name"] != "InvoiceWorkshop" or not identity["enabled"]:
            raise PreSendTransportError("Zoho send identity must be enabled with display name InvoiceWorkshop")
        result = client.send_plaintext(
            recipient=delivery.recipient, subject=delivery.subject, body=delivery.body
        )
        return TransportResult(result["message_id"], result["thread_id"])


class FormTransport:
    """No generic form submission is permitted; allowlisted handlers are separate work."""

    def send(self, _delivery: ValidatedDelivery) -> TransportResult:
        raise PreSendTransportError("no allowlisted site-specific Level-1A form handler is installed")
