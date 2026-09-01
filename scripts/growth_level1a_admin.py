#!/usr/bin/env python3
"""Owner-only Level-1A approval controls; keep the signing key outside the repo."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

from growth_common import utc_now
from growth_level1a import export_manifest, initialize, load_action, render_message


def _owner_key() -> bytes:
    configured = os.environ.get("LEVEL1_OWNER_APPROVAL_KEY_FILE", "").strip()
    if not configured:
        raise SystemExit("LEVEL1_OWNER_APPROVAL_KEY_FILE is not configured")
    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        raise SystemExit("LEVEL1_OWNER_APPROVAL_KEY_FILE is not a readable file")
    key = path.read_bytes().strip()
    if len(key) < 32:
        raise SystemExit("owner approval key must contain at least 32 bytes")
    return key


def _verify(payload: str, signature: str) -> None:
    expected = hmac.new(_owner_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise SystemExit("invalid owner approval signature")


def cmd_approve(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    action = load_action(connection, args.action_id)
    hashes = [render_message(connection, action, attempt).message_hash for attempt in range(int(action["max_followups"]) + 1)]
    approval_hash = hashlib.sha256(json.dumps(hashes, separators=(",", ":")).encode("utf-8")).hexdigest()
    if approval_hash != args.approval_hash:
        raise SystemExit("approval hash does not match the current deterministic message set")
    _verify(f"approve-action:{args.action_id}:{args.approval_hash}", args.signature)
    now = utc_now()
    connection.execute(
        """UPDATE level1a_actions SET external_action_approved=1, message_approved=1,
                  approved_message_hash=?, approved_message_hashes_json=?,
                  approved_by='owner-hmac', approved_at=?, updated_at=?
            WHERE id=?""",
        (hashes[0], json.dumps(hashes, separators=(",", ":")), now, now, args.action_id),
    )
    connection.commit()
    print(json.dumps({"action_id": args.action_id, "status": "approved", "approval_hash": args.approval_hash, "message_hashes": hashes}))


def cmd_activate(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    manifest = export_manifest(connection, "level1a_email")
    if manifest["manifest_hash"] != args.manifest_hash:
        raise SystemExit("manifest hash does not match the current action set")
    _verify(f"activate-level1a:{args.manifest_hash}", args.signature)
    for item in manifest["actions"]:
        if not item["external_action_approved"] or not item["message_approved"]:
            raise SystemExit(f"action {item['action_id']} is not fully approved")
    connection.execute(
        """UPDATE level1a_settings SET value=CASE
                 WHEN key IN ('outbound_enabled','email_outbound_enabled') THEN 'true'
                 ELSE 'false' END, updated_at=?
             WHERE key IN ('outbound_enabled','email_outbound_enabled','form_outbound_enabled')""",
        (utc_now(),),
    )
    connection.commit()
    print(json.dumps({
        "status": "email_database_switch_enabled", "environment_switch_required": True,
        "form_outbound_enabled": False,
    }))


def cmd_deactivate(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    connection.execute(
        """UPDATE level1a_settings SET value='false', updated_at=?
             WHERE key IN ('outbound_enabled','email_outbound_enabled','form_outbound_enabled')""",
        (utc_now(),),
    )
    connection.commit()
    print(json.dumps({"status": "disabled"}))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db")
    commands = root.add_subparsers(dest="command", required=True)
    approve = commands.add_parser("approve-action")
    approve.add_argument("--action-id", type=int, required=True)
    approve.add_argument("--approval-hash", required=True)
    approve.add_argument("--signature", required=True)
    approve.set_defaults(handler=cmd_approve)
    activate = commands.add_parser("activate")
    activate.add_argument("--manifest-hash", required=True)
    activate.add_argument("--signature", required=True)
    activate.set_defaults(handler=cmd_activate)
    commands.add_parser("deactivate").set_defaults(handler=cmd_deactivate)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
