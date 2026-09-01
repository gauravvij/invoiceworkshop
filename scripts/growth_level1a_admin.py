#!/usr/bin/env python3
"""Owner-only Level-1A approval controls, gated by an off-server Ed25519 key.

The server holds a public verification key and nothing else. Approvals are
produced on the owner's own machine with `ssh-keygen -Y sign`, which ships with
macOS and every modern Linux, so no library needs installing on either side and
no private key ever reaches this host.

Flow:

  1. server:  approval-request --action-id 22      -> writes a readable payload
  2. owner:   ssh-keygen -Y sign -f <key> -n invoiceworkshop-level1a <payload>
  3. server:  approve-action --action-id 22 --signature-file <payload>.sig

The payload is regenerated from live database state at verification time and
names the recipient, target URL, approval hash and every message hash. Change
any of them and the regenerated payload no longer matches what was signed, so a
signature cannot be replayed onto a different action, message or recipient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from growth_common import utc_now
from growth_level1a import export_manifest, initialize, load_action, render_message

NAMESPACE = "invoiceworkshop-level1a"
PAYLOAD_VERSION = "v2"
DEFAULT_ALLOWED_SIGNERS = Path(
    "/home/azureuser/.config/invoiceworkshop/level1_owner_allowed_signers"
)
DEFAULT_IDENTITY = "owner"
APPROVAL_DIR = Path("/home/azureuser/.config/invoiceworkshop/approvals")


class ApprovalError(SystemExit):
    pass


# ---------------------------------------------------------------------------
# Canonical payloads. Readable on purpose: the owner should be able to see
# exactly what they are signing before they sign it.
# ---------------------------------------------------------------------------

def action_payload(connection, action_id: int) -> tuple[str, str, list[str]]:
    action = load_action(connection, action_id)
    hashes = [
        render_message(connection, action, attempt).message_hash
        for attempt in range(int(action["max_followups"]) + 1)
    ]
    approval_hash = hashlib.sha256(
        json.dumps(hashes, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    lines = [
        f"{NAMESPACE}:approve-action:{PAYLOAD_VERSION}",
        f"action_id={action_id}",
        f"organization={action['organization']}",
        f"execution_class={action['execution_class']}",
        f"contact_kind={action['contact_kind']}",
        f"recipient={action['recipient'] or action['verified_contact_route']}",
        f"external_page_url={action['external_page_url']}",
        f"target_url={action['target_url']}",
        f"max_followups={action['max_followups']}",
        f"approval_hash={approval_hash}",
    ]
    lines += [f"message_hash[{index}]={value}" for index, value in enumerate(hashes)]
    return "\n".join(lines) + "\n", approval_hash, hashes


def manifest_payload(connection) -> tuple[str, str]:
    manifest = export_manifest(connection, "level1a_email")
    lines = [
        f"{NAMESPACE}:activate:{PAYLOAD_VERSION}",
        f"manifest_hash={manifest['manifest_hash']}",
        f"sender={manifest['sender']}",
        f"action_count={len(manifest['actions'])}",
    ]
    for item in sorted(manifest["actions"], key=lambda row: row["action_id"]):
        lines.append(
            f"action[{item['action_id']}]={item['organization']}|{item['recipient']}"
            f"|{item['target_url']}|{item['approval_hash']}"
        )
    return "\n".join(lines) + "\n", manifest["manifest_hash"]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _allowed_signers() -> Path:
    configured = os.environ.get("LEVEL1_OWNER_ALLOWED_SIGNERS", "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_ALLOWED_SIGNERS
    if not path.is_file():
        raise ApprovalError(
            f"owner public key is not installed at {path}. Run: "
            "growth_level1a_admin.py install-owner-key --public-key '<ssh-ed25519 ...>'"
        )
    return path


def _record(connection, *, scope: str, action_id: int | None, target_hash: str,
            payload: str, verified: bool, identity: str, fingerprint: str,
            detail: str, method: str = "ed25519_sshsig") -> None:
    connection.execute(
        """INSERT INTO level1a_approval_audit
             (scope, action_id, target_hash, payload_sha256, method, signer_identity,
              key_fingerprint, verified, detail, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (scope, action_id, target_hash,
         hashlib.sha256(payload.encode("utf-8")).hexdigest(), method, identity,
         fingerprint, 1 if verified else 0, detail[:500], utc_now()),
    )
    connection.commit()


def verify_signature(payload: str, signature_path: Path, identity: str) -> tuple[bool, str, str]:
    """Verify an SSHSIG over the exact payload. Returns (ok, fingerprint, detail)."""
    if shutil.which("ssh-keygen") is None:
        raise ApprovalError("ssh-keygen is required to verify owner approvals")
    if not signature_path.is_file():
        raise ApprovalError(f"signature file not found: {signature_path}")
    allowed = _allowed_signers()
    with tempfile.NamedTemporaryFile("w", suffix=".approval", delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", identity,
             "-n", NAMESPACE, "-s", str(signature_path)],
            stdin=temporary.open("rb"), capture_output=True, text=True, timeout=30,
        )
    finally:
        temporary.unlink(missing_ok=True)
    output = (result.stdout + result.stderr).strip()
    fingerprint = ""
    for token in output.split():
        if token.startswith("SHA256:"):
            fingerprint = token
            break
    return result.returncode == 0, fingerprint, output


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_install_owner_key(args: argparse.Namespace) -> None:
    key = args.public_key.strip()
    if not key.startswith("ssh-ed25519 "):
        raise ApprovalError("only an ssh-ed25519 public key is accepted")
    if len(key.split()) < 2:
        raise ApprovalError("public key looks malformed")
    if "PRIVATE KEY" in key or key.startswith("-----"):
        raise ApprovalError("that is a private key; install only the .pub value")
    path = DEFAULT_ALLOWED_SIGNERS
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fields = key.split()
    line = f"{args.identity} {fields[0]} {fields[1]}\n"
    path.write_text(line, encoding="utf-8")
    path.chmod(0o600)
    print(json.dumps({
        "status": "installed", "allowed_signers": str(path),
        "identity": args.identity, "key_type": fields[0],
        "note": "public verification key only; no private key is stored on this host",
    }, indent=2))


def cmd_approval_request(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    APPROVAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.action_id:
        payload, target_hash, hashes = action_payload(connection, args.action_id)
        path = APPROVAL_DIR / f"action-{args.action_id}.approval"
        extra = {"action_id": args.action_id, "approval_hash": target_hash,
                 "message_hashes": hashes}
    else:
        payload, target_hash = manifest_payload(connection)
        path = APPROVAL_DIR / "activate.approval"
        extra = {"manifest_hash": target_hash}
    path.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "status": "awaiting_owner_signature", "payload_file": str(path),
        **extra,
        "sign_on_your_machine": (
            f"ssh-keygen -Y sign -f ~/.ssh/invoiceworkshop_owner -n {NAMESPACE} {path.name}"
        ),
    }, indent=2))
    print("\n--- payload to be signed ---")
    print(payload, end="")


def cmd_approve_action(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    payload, approval_hash, hashes = action_payload(connection, args.action_id)
    ok, fingerprint, detail = verify_signature(
        payload, Path(args.signature_file).expanduser(), args.identity
    )
    _record(connection, scope="action", action_id=args.action_id,
            target_hash=approval_hash, payload=payload, verified=ok,
            identity=args.identity, fingerprint=fingerprint, detail=detail)
    if not ok:
        raise ApprovalError(f"owner signature did not verify: {detail}")
    now = utc_now()
    connection.execute(
        """UPDATE level1a_actions SET external_action_approved=1, message_approved=1,
                  approved_message_hash=?, approved_message_hashes_json=?,
                  approved_by=?, approved_at=?, updated_at=?
            WHERE id=?""",
        (hashes[0], json.dumps(hashes, separators=(",", ":")),
         f"owner-ed25519:{fingerprint}" if fingerprint else "owner-ed25519",
         now, now, args.action_id),
    )
    connection.commit()
    print(json.dumps({
        "action_id": args.action_id, "status": "approved",
        "approval_hash": approval_hash, "message_hashes": hashes,
        "verified_by": fingerprint or "ed25519", "method": "ed25519_sshsig",
    }, indent=2))


def cmd_activate(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    payload, manifest_hash = manifest_payload(connection)
    ok, fingerprint, detail = verify_signature(
        payload, Path(args.signature_file).expanduser(), args.identity
    )
    _record(connection, scope="manifest", action_id=None, target_hash=manifest_hash,
            payload=payload, verified=ok, identity=args.identity,
            fingerprint=fingerprint, detail=detail)
    if not ok:
        raise ApprovalError(f"owner signature did not verify: {detail}")
    manifest = export_manifest(connection, "level1a_email")
    for item in manifest["actions"]:
        if not item["external_action_approved"] or not item["message_approved"]:
            raise ApprovalError(f"action {item['action_id']} is not fully approved")
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
        "form_outbound_enabled": False, "verified_by": fingerprint or "ed25519",
    }, indent=2))


def cmd_deactivate(args: argparse.Namespace) -> None:
    """Turning outbound OFF needs no signature; stopping is always allowed."""
    connection = initialize(args.db)
    connection.execute(
        """UPDATE level1a_settings SET value='false', updated_at=?
             WHERE key IN ('outbound_enabled','email_outbound_enabled','form_outbound_enabled')""",
        (utc_now(),),
    )
    connection.commit()
    print(json.dumps({"status": "disabled"}))


def cmd_status(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    allowed = DEFAULT_ALLOWED_SIGNERS
    installed = allowed.is_file()
    rows = [dict(row) for row in connection.execute(
        """SELECT scope, action_id, target_hash, method, signer_identity,
                  key_fingerprint, verified, recorded_at
             FROM level1a_approval_audit ORDER BY id DESC LIMIT 10"""
    )]
    print(json.dumps({
        "owner_key_installed": installed,
        "allowed_signers": str(allowed) if installed else None,
        "key_type": allowed.read_text().split()[1] if installed else None,
        "namespace": NAMESPACE,
        "private_key_on_server": False,
        "recent_verifications": rows,
    }, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db")
    commands = root.add_subparsers(dest="command", required=True)

    install = commands.add_parser("install-owner-key", help="Install the owner public key")
    install.add_argument("--public-key", required=True)
    install.add_argument("--identity", default=DEFAULT_IDENTITY)
    install.set_defaults(handler=cmd_install_owner_key)

    request = commands.add_parser("approval-request", help="Emit a payload for the owner to sign")
    request.add_argument("--action-id", type=int)
    request.set_defaults(handler=cmd_approval_request)

    approve = commands.add_parser("approve-action", help="Verify an owner signature and approve")
    approve.add_argument("--action-id", type=int, required=True)
    approve.add_argument("--signature-file", required=True)
    approve.add_argument("--identity", default=DEFAULT_IDENTITY)
    approve.set_defaults(handler=cmd_approve_action)

    activate = commands.add_parser("activate", help="Verify an owner signature and enable email outbound")
    activate.add_argument("--signature-file", required=True)
    activate.add_argument("--identity", default=DEFAULT_IDENTITY)
    activate.set_defaults(handler=cmd_activate)

    commands.add_parser("deactivate", help="Disable outbound (no signature required)").set_defaults(
        handler=cmd_deactivate
    )
    commands.add_parser("status", help="Show approval-gate state").set_defaults(handler=cmd_status)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
