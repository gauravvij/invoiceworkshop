#!/usr/bin/env python3
"""Policy-level authorization for routine Level-1A outreach.

The owner signs a POLICY once instead of signing every recipient. The executor
then checks each candidate action against that policy deterministically, and
anything falling outside it stays blocked and is escalated.

This deliberately does not widen what may be said. Messages still render from
the frozen code allowlist and versioned claims; the policy governs *which
prospects may be contacted without an individual signature*, not what the email
contains. An action that would not have passed the per-action gates still fails
them.

Signing reuses the existing Ed25519 trust anchor. No new trust boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from growth_common import apply_schema, connect_db, database_path, utc_now
from growth_level1a_admin import (
    APPROVAL_DIR,
    NAMESPACE,
    ApprovalError,
    verify_signature,
)

POLICY_VERSION = 2

# The policy the owner is asked to sign. Everything here is machine-checkable:
# no clause depends on judgement at execution time.
POLICY: dict = {
    "policy_version": POLICY_VERSION,
    "channel": "verified_public_business_email",
    "purpose": "relevant resource or tool suggestion",
    # A publicly published business address is not automatically contactable
    # everywhere. Three regimes are handled explicitly and everything else goes
    # to a person; the layer can block a send and can never authorise one that
    # the quality gates would have refused.
    "jurisdiction_layer": {
        "supported": ["US", "UK", "CA"],
        "everything_else": "REVIEW",
        "unknown_jurisdiction": "REVIEW",
        "evidence_read_from_the_targets_own_pages": True,
        "US": {
            "accurate_from_and_reply_to_identity": True,
            "non_deceptive_subject": True,
            "sender_identified_in_the_message": True,
            "working_opt_out": True,
            "physical_postal_address": True,
            "postal_address_never_invented": True,
            "suppression_honoured": True,
            "blocked_until_identity_configured": True,
        },
        "UK": {
            "corporate_subscriber": "eligible",
            "sole_trader_or_individual_subscriber": "REVIEW",
            "status_not_established": "REVIEW",
        },
        "CA": {
            "basis": "implied consent through conspicuous publication",
            "address_published_by_the_organization_itself": True,
            "no_statement_refusing_unsolicited_messages": True,
            "message_relevant_to_the_recipients_business_role": True,
            "source_url_and_observation_timestamp_stored": True,
            "any_condition_unevidenced": "REVIEW",
        },
        "published_refusal_is_honoured_in_every_jurisdiction": True,
        "not_legal_advice_a_conservative_execution_gate": True,
    },
    "recipient_requirements": {
        "must_be_published_by_target_organization": True,
        "must_be_organization_address": True,
        "must_be_verified_against_current_source": True,
        "max_verification_age_days": 7,
        "guessed_addresses_forbidden": True,
        "personal_addresses_forbidden": True,
        "forbidden_local_parts": ["ceo", "founder", "owner", "president", "director"],
    },
    "prospect_requirements": {
        "must_pass_the_jurisdiction_layer": True,
        "must_be_in_reviewed_code_allowlist": True,
        "must_have_real_source_page": True,
        "must_pass_page_verification": True,
        "must_not_be_suppressed": True,
        "must_not_be_previously_contacted_at_organization_level": True,
        "must_not_require_account": True,
        "must_not_require_payment": True,
        "must_not_be_vendor_content": True,
        "must_not_be_own_domain": True,
    },
    "message_constraints": {
        "template_families": ["human_resource", "human_roundup"],
        "claims_from_versioned_registry_only": True,
        "exactly_one_target_url": True,
        "target_url_must_be_canonical": True,
        "attachments": False,
        "arbitrary_links": False,
        "forbidden_terminology": ["seo", "backlink", "dofollow", "link exchange", "reciprocal"],
        "payment_or_reciprocal_offers": False,
    },
    "volume": {"max_new_organizations_per_day": 3, "max_total_messages_per_day": 5},
    "followups": {"maximum": 1, "wait_business_days": 5,
                  "stop_on": ["reply", "bounce", "decline", "unsubscribe", "suppression", "placement"]},
    "execution_class": "level1a_email",
    "form_outbound": False,
    "community_posting": False,
    "account_creation": False,
    "paid_placement": False,
    "level_1b": False,
    "escalate_instead": [
        "paid placement", "partnership", "reciprocal arrangement", "founder interview",
        "journalist request needing a human identity", "guest article", "account creation",
        "community identity or posting", "legal or compliance question",
        "anything requiring personal representation",
    ],
}


def policy_hash(policy: dict | None = None) -> str:
    payload = json.dumps(policy or POLICY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signing_payload(policy: dict | None = None) -> str:
    """Readable payload: the owner should see the rules they are authorising."""
    policy = policy or POLICY
    lines = [
        f"{NAMESPACE}:approve-policy:v1",
        f"policy_version={policy['policy_version']}",
        f"policy_hash={policy_hash(policy)}",
        f"channel={policy['channel']}",
        f"max_new_organizations_per_day={policy['volume']['max_new_organizations_per_day']}",
        f"max_total_messages_per_day={policy['volume']['max_total_messages_per_day']}",
        f"followups_maximum={policy['followups']['maximum']}",
        f"followup_wait_business_days={policy['followups']['wait_business_days']}",
        f"template_families={','.join(policy['message_constraints']['template_families'])}",
        f"form_outbound={policy['form_outbound']}",
        f"community_posting={policy['community_posting']}",
        f"account_creation={policy['account_creation']}",
        f"paid_placement={policy['paid_placement']}",
        f"level_1b={policy['level_1b']}",
        "",
        "Under this policy the executor may contact a prospect WITHOUT an individual",
        "signature only when every requirement below holds. Anything else escalates.",
        "",
    ]
    lines += ["", "JURISDICTION LAYER (can block a send; can never authorise one):"]
    for key, value in sorted(policy["jurisdiction_layer"].items()):
        if isinstance(value, dict):
            lines.append(f"  [{key}]")
            for inner, setting in sorted(value.items()):
                lines.append(f"    {inner}={setting}")
        else:
            lines.append(f"  {key}={value}")
    lines.append("")
    for group in ("recipient_requirements", "prospect_requirements", "message_constraints"):
        lines.append(f"[{group}]")
        for key, value in sorted(policy[group].items()):
            lines.append(f"  {key}={value}")
    return "\n".join(lines) + "\n"


def store(connection: sqlite3.Connection, policy: dict | None = None) -> str:
    policy = policy or POLICY
    digest = policy_hash(policy)
    connection.execute(
        """INSERT INTO outreach_policy (version, policy_json, policy_hash, signed, active, created_at)
           VALUES (?, ?, ?, 0, 0, ?)
           ON CONFLICT(version) DO UPDATE SET
             policy_json=excluded.policy_json, policy_hash=excluded.policy_hash""",
        (policy["policy_version"], json.dumps(policy, sort_keys=True), digest, utc_now()),
    )
    connection.commit()
    return digest


def active_policy(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute(
        "SELECT * FROM outreach_policy WHERE active=1 AND signed=1 ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    policy = json.loads(row["policy_json"])
    if policy_hash(policy) != row["policy_hash"]:
        raise ApprovalError("stored policy does not match its recorded hash")
    return {"policy": policy, "version": row["version"], "hash": row["policy_hash"],
            "signer": row["signer_fingerprint"]}


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------

def admit(connection: sqlite3.Connection, action_id: int) -> dict:
    """Decide whether one action may proceed under the signed policy.

    Returns a full check breakdown either way. This never sends: it only says
    whether the per-action owner signature can be waived.
    """
    from growth_level1a import CANONICAL_TARGETS, PILOT, load_action

    active = active_policy(connection)
    now = utc_now()
    if not active:
        result = {"admitted": False, "reason": "no signed active outreach policy", "checks": {}}
        _record(connection, action_id, 0, "", result, now)
        return result

    policy = active["policy"]
    action = load_action(connection, action_id)
    recipient = (action["recipient"] or "").lower()
    local = recipient.split("@")[0] if "@" in recipient else ""
    allow = {item["organization"] for item in PILOT}

    checks = {
        "execution_class_is_email": action["execution_class"] == policy["execution_class"],
        "in_reviewed_code_allowlist": action["organization"] in allow,
        "not_suppressed": action["suppression_state"] == "active",
        "prospect_qualified": action["prospect_status"] == "qualified",
        "second_pass_passed": bool(action["second_pass_pass"]),
        "no_account_required": not action["requires_account"],
        "no_payment_required": not action["requires_payment"],
        "recipient_present": bool(recipient) and "@" in recipient,
        "recipient_not_personal": local not in policy["recipient_requirements"]["forbidden_local_parts"],
        "template_family_allowed": action["template_id"] in policy["message_constraints"]["template_families"],
        "target_url_canonical": action["target_url"] in CANONICAL_TARGETS,
        "followup_limit_matches_policy": int(action["max_followups"]) <= policy["followups"]["maximum"],
        "attachments_disabled": not action["attachments_allowed"],
        "payment_disabled": not action["payment_allowed"],
    }

    # Page verification must be current, not merely once-true.
    expires = action["verification_expires_at"]
    checks["page_verification_current"] = bool(expires and expires > now)

    # The jurisdiction layer. A prospect with no assessment is not assumed fine:
    # an unassessed recipient is exactly the case this exists to catch.
    assessment = connection.execute(
        """SELECT c.verdict, c.jurisdiction, c.reasons FROM outreach_compliance c
             JOIN level1a_actions a ON a.prospect_id = c.prospect_id
            WHERE a.id = ?""", (action_id,)).fetchone()
    checks["compliance_assessed"] = assessment is not None
    checks["compliance_eligible"] = bool(assessment and assessment["verdict"] == "ELIGIBLE")

    # One organization, one contact — checked at organization level, not address.
    already = connection.execute(
        """SELECT 1 FROM level1a_action_audit aa JOIN level1a_actions a ON a.id=aa.action_id
            WHERE lower(a.organization)=lower(?) AND aa.mode='live'
              AND aa.validation_result='passed' AND aa.attempt_number=0 LIMIT 1""",
        (action["organization"],),
    ).fetchone()
    checks["organization_not_previously_contacted"] = not already

    suppressed = connection.execute(
        "SELECT 1 FROM level1a_suppressions WHERE suppression_key=?", (recipient,)
    ).fetchone()
    checks["recipient_not_suppressed"] = not suppressed

    failed = [name for name, ok in checks.items() if not ok]
    result = {
        "admitted": not failed,
        "reason": None if not failed else "failed policy checks: " + ", ".join(failed),
        "checks": checks,
        "compliance": ({"verdict": assessment["verdict"],
                        "jurisdiction": assessment["jurisdiction"],
                        "reasons": assessment["reasons"]} if assessment else
                       {"verdict": "UNASSESSED",
                        "reasons": "no jurisdiction assessment on record for this "
                                   "prospect, so nothing about its route is settled"}),
        "policy_version": active["version"],
        "policy_hash": active["hash"],
    }
    _record(connection, action_id, active["version"], active["hash"], result, now)
    return result


def _record(connection, action_id, version, digest, result, now) -> None:
    connection.execute(
        """INSERT INTO policy_admissions
             (action_id, policy_version, policy_hash, admitted, checks_json, refusal_reason, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (action_id, version, digest, 1 if result["admitted"] else 0,
         json.dumps(result.get("checks", {}), sort_keys=True), result.get("reason"), now),
    )
    connection.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_show(args) -> None:
    print(json.dumps({"policy": POLICY, "policy_hash": policy_hash()}, indent=2, sort_keys=True))


def cmd_request(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    digest = store(connection)
    APPROVAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = APPROVAL_DIR / f"outreach-policy-v{POLICY_VERSION}.approval"
    payload = signing_payload()
    path.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "status": "awaiting_owner_signature", "policy_version": POLICY_VERSION,
        "policy_hash": digest, "payload_file": str(path),
        "sign_on_your_machine":
            f"ssh-keygen -Y sign -f ~/.ssh/invoiceworkshop_owner -n {NAMESPACE} {path.name}",
    }, indent=2))
    print("\n--- policy to be signed ---")
    print(payload, end="")


def cmd_activate(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    store(connection)
    ok, fingerprint, detail = verify_signature(
        signing_payload(), Path(args.signature_file).expanduser(), args.identity
    )
    if not ok:
        raise ApprovalError(f"owner signature did not verify: {detail}")
    connection.execute(
        """UPDATE outreach_policy SET signed=1, active=CASE WHEN version=? THEN 1 ELSE 0 END,
               signer_fingerprint=?, signed_at=? WHERE version=?""",
        (POLICY_VERSION, fingerprint, utc_now(), POLICY_VERSION),
    )
    connection.execute("UPDATE outreach_policy SET active=0 WHERE version<>?", (POLICY_VERSION,))
    connection.commit()
    print(json.dumps({"status": "policy_active", "policy_version": POLICY_VERSION,
                      "policy_hash": policy_hash(), "verified_by": fingerprint}, indent=2))


def cmd_deactivate(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    connection.execute("UPDATE outreach_policy SET active=0")
    connection.commit()
    print(json.dumps({"status": "policy_deactivated"}))


def cmd_admit(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    print(json.dumps(admit(connection, args.action_id), indent=2, sort_keys=True))


def cmd_status(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    active = None
    try:
        active = active_policy(connection)
    except ApprovalError as error:
        active = {"error": str(error)}
    print(json.dumps({
        "code_policy_hash": policy_hash(),
        "active_policy": {k: v for k, v in (active or {}).items() if k != "policy"} if active else None,
        "policy_matches_code": bool(active and active.get("hash") == policy_hash()),
    }, indent=2, sort_keys=True))


def main() -> None:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("show").set_defaults(handler=cmd_show)
    commands.add_parser("request", help="Emit the policy for owner signature").set_defaults(handler=cmd_request)
    activate = commands.add_parser("activate", help="Verify the owner signature and activate")
    activate.add_argument("--signature-file", required=True)
    activate.add_argument("--identity", default="owner")
    activate.set_defaults(handler=cmd_activate)
    commands.add_parser("deactivate").set_defaults(handler=cmd_deactivate)
    check = commands.add_parser("admit", help="Test one action against the signed policy")
    check.add_argument("--action-id", type=int, required=True)
    check.set_defaults(handler=cmd_admit)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    args = root.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
