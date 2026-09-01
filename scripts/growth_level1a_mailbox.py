#!/usr/bin/env python3
"""Restricted inbound polling for replies to sent Level-1A email actions."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from email.utils import parseaddr

from growth_common import utc_now
from growth_level1a import initialize, record_reply
from growth_zoho import ZohoClient

BOUNCE_SENDERS = ("mailer-daemon", "postmaster")
BOUNCE_SUBJECT = re.compile(r"\b(undeliverable|delivery (?:status|failure|failed)|mail delivery failed|returned mail|failure notice)\b", re.I)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _email(value: str) -> str:
    return parseaddr(html.unescape(value or ""))[1].lower()


def _subject(value: str) -> str:
    return re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", html.unescape(value or ""), flags=re.I).strip().lower()


def _plain(value: str) -> str:
    without_markup = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_markup).strip()[:50_000]


def _authentication_state(headers: dict[str, object]) -> str:
    blob = json.dumps(headers, separators=(",", ":")).lower()
    passed = {name: bool(re.search(rf"\b{name}\s*[=:]\s*pass\b", blob)) for name in ("spf", "dkim", "dmarc")}
    failed = any(re.search(rf"\b{name}\s*[=:]\s*(?:fail|softfail|temperror|permerror)\b", blob) for name in ("spf", "dkim", "dmarc"))
    if passed["dmarc"] or (passed["spf"] and passed["dkim"]):
        return "pass"
    return "fail" if failed else "unverified"


def _received_iso(message: dict[str, object]) -> str:
    raw = str(message.get("receivedTime") or message.get("sentDateInGMT") or "0")
    try:
        stamp = int(raw) / 1000
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return utc_now()


def _eligible_sent(connection) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(
        """SELECT aa.action_id, aa.subject, aa.provider_response_id,
                  aa.provider_thread_id, a.recipient, a.organization
             FROM level1a_action_audit aa
             JOIN level1a_actions a ON a.id=aa.action_id
            WHERE aa.mode='live' AND aa.validation_result='passed'
              AND aa.delivery_state IN ('submitted','delivered','unknown')
              AND a.execution_class='level1a_email'
              AND a.suppression_state='active'
            ORDER BY aa.id DESC"""
    )]


def _match(message: dict[str, object], sent: list[dict[str, object]]) -> tuple[dict[str, object] | None, str | None]:
    thread = str(message.get("threadId") or "")
    sender = _email(str(message.get("fromAddress") or ""))
    subject = _subject(str(message.get("subject") or ""))
    for row in sent:
        if thread and row.get("provider_thread_id") and thread == str(row["provider_thread_id"]):
            return row, "thread_id"
    for row in sent:
        if sender == str(row["recipient"]).lower() and subject == _subject(str(row["subject"])):
            return row, "sender_and_subject"
    return None, None


def bootstrap(connection, client: ZohoClient) -> dict[str, object]:
    messages = client.list_messages(limit=50)
    maximum = max((int(str(item.get("receivedTime") or "0")) for item in messages), default=0)
    connection.execute(
        """INSERT INTO level1a_mail_poll_state(key,value,updated_at)
           VALUES ('received_watermark_ms',?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (str(maximum), utc_now()),
    )
    connection.commit()
    return {"status": "bootstrapped", "messages_examined": len(messages), "content_read": 0, "watermark_ms": maximum}


def poll(connection, client: ZohoClient) -> dict[str, object]:
    started = utc_now()
    state = connection.execute(
        "SELECT value FROM level1a_mail_poll_state WHERE key='received_watermark_ms'"
    ).fetchone()
    if not state:
        raise RuntimeError("mail polling must be bootstrapped before it can process replies")
    watermark = int(state["value"])
    messages = client.list_messages(limit=100)
    candidates = [item for item in messages if int(str(item.get("receivedTime") or "0")) >= watermark]
    sent = _eligible_sent(connection)
    examined = matched = bounces = suppressions = 0
    errors: list[str] = []
    maximum = watermark
    for message in sorted(candidates, key=lambda item: int(str(item.get("receivedTime") or "0"))):
        provider_id = str(message.get("messageId") or "")
        if not provider_id:
            continue
        maximum = max(maximum, int(str(message.get("receivedTime") or "0")))
        if connection.execute(
            "SELECT 1 FROM level1a_inbound_audit WHERE provider_message_id=?", (provider_id,)
        ).fetchone():
            continue
        examined += 1
        sender = _email(str(message.get("fromAddress") or ""))
        subject = str(message.get("subject") or "")
        row, method = _match(message, sent)
        bounce_hint = any(token in sender for token in BOUNCE_SENDERS) or bool(BOUNCE_SUBJECT.search(subject))
        content = ""
        if row is None and bounce_hint and sent:
            try:
                content = _plain(client.get_message_content(str(message.get("folderId")), provider_id))
                for candidate in sent:
                    if str(candidate["recipient"]).lower() in content.lower():
                        row, method = candidate, "bounce_recipient"
                        break
            except Exception as error:
                errors.append(f"bounce content read failed for {_hash(provider_id)[:12]}: {type(error).__name__}")
        classification = None
        escalation = None
        content_hash = None
        authentication = "unverified"
        before_state = None
        if row is not None:
            if not content:
                try:
                    content = _plain(client.get_message_content(str(message.get("folderId")), provider_id))
                except Exception as error:
                    errors.append(f"matched content read failed for {_hash(provider_id)[:12]}: {type(error).__name__}")
                    continue
            content_hash = _hash(content)
            matched += 1
            try:
                headers = client.get_message_headers(str(message.get("folderId")), provider_id)
                authentication = _authentication_state(headers)
            except Exception as error:
                errors.append(f"matched header read failed for {_hash(provider_id)[:12]}: {type(error).__name__}")
            if authentication == "pass":
                before = connection.execute(
                    "SELECT suppression_state FROM level1a_actions WHERE id=?", (row["action_id"],)
                ).fetchone()
                before_state = before["suppression_state"]
                result = record_reply(
                    connection, int(row["action_id"]), provider_id, content,
                    bounced=bounce_hint,
                )
                classification = str(result["classification"])
                escalation = int(bool(result["requires_escalation"]))
                if classification == "bounce":
                    bounces += 1
                after = connection.execute(
                    "SELECT suppression_state FROM level1a_actions WHERE id=?", (row["action_id"],)
                ).fetchone()["suppression_state"]
                suppressions += int(after != before_state)
            else:
                classification = "ambiguous"
                escalation = 1
        connection.execute(
            """INSERT INTO level1a_inbound_audit (
                 provider_message_id, provider_thread_id, received_at, sender_hash,
                 subject_hash, matched_action_id, match_method, authentication_state,
                 classification, requires_escalation, content_hash, attachment_ignored,
                 external_content_executed, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                provider_id, str(message.get("threadId") or "") or None,
                _received_iso(message), _hash(sender), _hash(_subject(subject)),
                int(row["action_id"]) if row else None, method, authentication,
                classification, escalation, content_hash,
                int(str(message.get("hasAttachment") or "0") not in {"0", "false", "False", ""}),
                utc_now(),
            ),
        )
    finished = utc_now()
    connection.execute(
        """INSERT INTO level1a_mail_poll_state(key,value,updated_at)
           VALUES ('received_watermark_ms',?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (str(maximum), finished),
    )
    status = "partial" if errors else "success"
    connection.execute(
        """INSERT INTO level1a_mail_poll_runs (
             started_at,finished_at,status,messages_examined,matched_replies,
             bounces_detected,suppressions_updated,errors_json,external_side_effects)
           VALUES (?,?,?,?,?,?,?,?, 'none')""",
        (started, finished, status, examined, matched, bounces, suppressions, json.dumps(errors)),
    )
    connection.commit()
    return {
        "status": status, "messages_examined": examined, "matched_replies": matched,
        "bounces_detected": bounces, "suppressions_updated": suppressions,
        "errors": errors, "external_side_effects": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    parser.add_argument("command", choices=("bootstrap", "poll", "status"))
    args = parser.parse_args()
    connection = initialize(args.db)
    if args.command == "status":
        client = ZohoClient()
        result = {
            "account_id": client.resolve_account_id(),
            "mailbox": "hello@invoiceworkshop.com",
            "messages_listed": len(client.list_messages(limit=10)),
            "poll_bootstrapped": bool(connection.execute(
                "SELECT 1 FROM level1a_mail_poll_state WHERE key='received_watermark_ms'"
            ).fetchone()),
            "external_side_effects": "none",
        }
    elif args.command == "bootstrap":
        result = bootstrap(connection, ZohoClient())
    else:
        result = poll(connection, ZohoClient())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
