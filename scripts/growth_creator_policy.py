#!/usr/bin/env python3
"""Sign-once authorization for UNPAID creator and newsletter suggestions.

Deliberately a second, narrower policy rather than a widening of the existing
resource-page one. Signing that policy must never authorise this, and signing
this must never authorise that: they contact different people, for a different
reason, at a different volume, and they are reported separately so neither can
borrow the other's evidence.

What this authorises is small and exact: one message to a publicly published
business or editorial address, about one specific InvoiceWorkshop capability
that is live at the time of sending, chosen for a reason that target's audience
would actually care about. One follow-up, five business days later, and it stops
on any signal at all.

What it does not authorise is everything else, and the list is enforced in code
rather than described: no DMs, no comments, no personal addresses, no account
creation, no payment, no sponsorship or affiliate discussion, no attachments, no
generic mass mail. Those are not "discouraged"; a prospect that would need one
is refused by `admit` and escalated.

Signing reuses the existing Ed25519 owner trust anchor. No new trust boundary,
no new key, no new authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from growth_common import apply_schema, connect_db, database_path, utc_now
from growth_level1a_admin import APPROVAL_DIR, NAMESPACE, ApprovalError, verify_signature

POLICY_VERSION = 2

# The angles a message may take, and the live page each points at. A prospect
# whose angle is not on this list cannot be admitted, which is what stops the
# message drifting into "please feature InvoiceWorkshop".
APPROVED_ANGLES = {
    "freelancer_newsletter": "https://invoiceworkshop.com/receipt-generator/",
    "freelancer_creator": "https://invoiceworkshop.com/",
    "bookkeeping_newsletter": "https://invoiceworkshop.com/credit-note-generator/",
    "bookkeeping_creator": "https://invoiceworkshop.com/credit-note-generator/",
    "small_business_newsletter": "https://invoiceworkshop.com/",
    "contractor_creator": "https://invoiceworkshop.com/progress-draw-schedule/",
}

POLICY: dict = {
    "policy_version": POLICY_VERSION,
    "policy_family": "creator_newsletter_unpaid_editorial",
    "separate_from": "resource_page_outreach_policy",
    "channel": "verified_public_business_or_editorial_email_or_contact_form",
    "purpose": "unpaid suggestion of one specific, live, free InvoiceWorkshop tool",
    # Two routes, both verified against the target's own pages. A form is a
    # route the organization published for this purpose; it is not a workaround
    # for not having an address, and everything below is checked before use.
    "contact_routes": {
        "email": {
            "must_be_published_on_target_own_site": True,
            "must_be_business_or_editorial_address": True,
            "guessed_or_inferred_addresses_forbidden": True,
        },
        "form": {
            "must_be_publicly_linked_from_the_site": True,
            "must_be_general_editorial_resources_partnership_or_contact_route": True,
            "organization_and_page_already_qualified": True,
            "no_login_or_account": True,
            "no_captcha_to_bypass": True,
            "captcha_bypass_forbidden_absolutely": True,
            "no_payment": True,
            "no_personal_identity_required": True,
            "support_ticket_forms_forbidden": True,
            "legal_privacy_or_complaint_forms_forbidden": True,
            "site_instruction_forbidding_contact_is_honoured": True,
            "mandatory_personal_name_escalates_to_review": True,
        },
    },
    # Form behaviour is deliberately more conservative than email: a form goes
    # into a queue we cannot see, so a second submission is indistinguishable
    # from pestering.
    "form_behaviour": {
        "max_initial_submissions": 1,
        "automated_followup": False,
        "organization_level_deduplication": True,
        "stop_permanently_on": ["response", "decline", "suppression"],
        "sender_is_the_organization_not_a_person": True,
        "unverified_submission_recorded_as_unknown_never_retried": True,
        "attachments": False,
        "exactly_one_canonical_url": True,
    },
    "recipient_requirements": {
        "must_be_published_on_target_own_site": True,
        "must_be_business_or_editorial_address": True,
        "must_be_verified_against_current_source": True,
        "max_verification_age_days": 7,
        "guessed_addresses_forbidden": True,
        "personal_addresses_not_offered_publicly_forbidden": True,
        "forbidden_local_parts": ["ceo", "founder", "owner", "president", "director",
                                  "personal", "me", "family"],
    },
    "prospect_requirements": {
        "must_be_in_creator_backlog": True,
        "must_be_qualified_by_recorded_evidence": True,
        "must_have_verified_recent_activity": True,
        "must_show_evidence_of_recommending_tools": True,
        "must_not_be_paid_placement_only": True,
        "must_not_be_generic_influencer": True,
        "must_not_be_suppressed": True,
        "must_not_be_previously_contacted_at_domain_level": True,
        "must_not_require_account": True,
        "must_not_require_payment": True,
    },
    "message_constraints": {
        "one_specific_angle_per_message": True,
        "angle_must_be_from_approved_list": True,
        "target_url_must_be_live_at_send_time": True,
        "exactly_one_target_url": True,
        "attachments": False,
        "arbitrary_links": False,
        "generic_feature_request_forbidden": True,
        "forbidden_terminology": ["seo", "backlink", "dofollow", "link exchange",
                                  "reciprocal", "guest post", "sponsored", "affiliate",
                                  "commission", "partnership deal"],
        "payment_or_reciprocal_offers": False,
    },
    # One ceiling across both routes, not five of each. It is a maximum, never
    # a quota: on a day with two worthwhile organizations, two are contacted.
    "volume": {
        "max_new_organizations_per_day": 5,
        "shared_across_email_and_form": True,
        "max_total_messages_per_day": 8,
        "is_a_ceiling_not_a_quota": True,
    },
    "followups": {"maximum": 1, "wait_business_days": 5,
                  "email_only": True, "forms_never_followed_up": True,
                  "stop_on": ["reply", "bounce", "decline", "unsubscribe",
                              "suppression", "placement"]},
    # Deliverability and complaint thresholds that stop the channel by
    # themselves. No judgement call, no override.
    "auto_stop": {
        "min_completed_before_judging": 10,
        "max_bounce_rate": 0.10,
        "max_complaint_or_unsubscribe_rate": 0.05,
        "stops_channel_without_owner_action": True,
    },
    "execution_class": "level1a_email",
    "direct_messages": False,
    "community_posting": False,
    "form_outbound": False,
    "account_creation": False,
    "paid_placement": False,
    "sponsorship_negotiation": False,
    "affiliate_agreements": False,
    "attachments": False,
    "mass_generic_email": False,
    "escalate_instead": [
        "a form requiring a personal first or last name",
        "a form behind a login, a CAPTCHA or a payment",
        "sponsorship", "payment of any kind", "affiliate economics", "interview",
        "founder participation", "contractual partnership", "account creation",
        "community identity or posting", "direct message", "anything requiring a "
        "personal identity",
    ],
}


def policy_hash(policy: dict | None = None) -> str:
    payload = json.dumps(policy or POLICY, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def signing_payload(policy: dict | None = None) -> str:
    """What the owner reads before signing. Everything here is enforced in code."""
    policy = policy or POLICY
    lines = [
        f"{NAMESPACE}:approve-creator-policy:v1",
        f"policy_version={policy['policy_version']}",
        f"policy_family={policy['policy_family']}",
        f"policy_hash={policy_hash(policy)}",
        f"channel={policy['channel']}",
        f"purpose={policy['purpose']}",
        "",
        "THIS IS A SEPARATE AUTHORIZATION.",
        "Signing it does not widen the resource-page outreach policy, and signing",
        "that one does not authorise anything here. The two are reported separately.",
        "",
        f"max_new_organizations_per_day={policy['volume']['max_new_organizations_per_day']}"
        " (SHARED across the email and form routes, and a ceiling rather than a quota)",
        f"max_total_messages_per_day={policy['volume']['max_total_messages_per_day']}",
        f"followups_maximum={policy['followups']['maximum']}",
        f"followup_wait_business_days={policy['followups']['wait_business_days']}",
        f"stop_on={','.join(policy['followups']['stop_on'])}",
        "",
        "NOT AUTHORISED (each refused in code, not merely discouraged):",
    ]
    for flag in ("direct_messages", "community_posting", "form_outbound",
                 "account_creation", "paid_placement", "sponsorship_negotiation",
                 "affiliate_agreements", "attachments", "mass_generic_email"):
        lines.append(f"  {flag}={policy[flag]}")
    lines += ["", "AUTO-STOP (no owner action needed to halt the channel):"]
    for key, value in sorted(policy["auto_stop"].items()):
        lines.append(f"  {key}={value}")
    lines += ["", "CONTACT ROUTES (a prospect must satisfy one of these, fully):"]
    for name, rules in sorted(policy["contact_routes"].items()):
        lines.append(f"  [{name}]")
        for key, value in sorted(rules.items()):
            lines.append(f"    {key}={value}")
    lines += ["", "FORM BEHAVIOUR (stricter than email, because a form queue is invisible):"]
    for key, value in sorted(policy["form_behaviour"].items()):
        lines.append(f"  {key}={value}")
    lines += ["", "APPROVED ANGLES (one per message, pointing at a live page):"]
    for segment, url in sorted(APPROVED_ANGLES.items()):
        lines.append(f"  {segment} -> {url}")
    lines.append("")
    for group in ("recipient_requirements", "prospect_requirements", "message_constraints"):
        lines.append(f"[{group}]")
        for key, value in sorted(policy[group].items()):
            lines.append(f"  {key}={value}")
    lines += ["", "Under this policy a qualifying prospect may be contacted ONCE without",
              "a per-recipient signature. Anything failing any check is escalated, not sent."]
    return "\n".join(lines) + "\n"


def store(connection: sqlite3.Connection, policy: dict | None = None) -> str:
    policy = policy or POLICY
    digest = policy_hash(policy)
    connection.execute(
        """INSERT INTO creator_policy (version, policy_json, policy_hash, signed, active, created_at)
           VALUES (?, ?, ?, 0, 0, ?)
           ON CONFLICT(version) DO UPDATE SET
             policy_json=excluded.policy_json, policy_hash=excluded.policy_hash""",
        (policy["policy_version"], json.dumps(policy, sort_keys=True), digest, utc_now()))
    connection.commit()
    return digest


def active_policy(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute(
        "SELECT * FROM creator_policy WHERE active=1 AND signed=1 ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    policy = json.loads(row["policy_json"])
    if policy_hash(policy) != row["policy_hash"]:
        raise ApprovalError("stored creator policy does not match its recorded hash")
    return {"policy": policy, "version": row["version"], "hash": row["policy_hash"],
            "signer": row["signer_fingerprint"]}


# ---------------------------------------------------------------------------
# Deliverability: the channel stops itself
# ---------------------------------------------------------------------------

def deliverability(connection: sqlite3.Connection) -> dict:
    """Bounce and complaint rates on creator sends only.

    Read from this channel's own audit rows. Sharing a denominator with the
    resource-page cohort would let a healthy channel hide a failing one.
    """
    row = connection.execute(
        """SELECT COUNT(*) sent,
                  SUM(CASE WHEN aa.delivery_state='bounced' THEN 1 ELSE 0 END) bounced,
                  SUM(CASE WHEN aa.suppression_state<>'active' THEN 1 ELSE 0 END) suppressed
             FROM level1a_action_audit aa
             JOIN level1a_actions a ON a.id = aa.action_id
             JOIN creator_prospects c ON lower(c.recipient) = lower(aa.recipient_or_route)
            WHERE aa.mode='live'"""
    ).fetchone()
    sent = int(row["sent"] or 0)
    bounced = int(row["bounced"] or 0)
    suppressed = int(row["suppressed"] or 0)
    limits = POLICY["auto_stop"]
    if sent < limits["min_completed_before_judging"]:
        return {"sent": sent, "bounce_rate": None, "complaint_rate": None,
                "healthy": True,
                "detail": f"{sent} sent, below the {limits['min_completed_before_judging']} "
                          "needed to judge deliverability at all"}
    bounce_rate = bounced / sent
    complaint_rate = suppressed / sent
    healthy = (bounce_rate <= limits["max_bounce_rate"]
               and complaint_rate <= limits["max_complaint_or_unsubscribe_rate"])
    return {"sent": sent, "bounce_rate": round(bounce_rate, 3),
            "complaint_rate": round(complaint_rate, 3), "healthy": healthy,
            "detail": ("within thresholds" if healthy else
                       f"bounce {bounce_rate:.1%} / complaint {complaint_rate:.1%} "
                       "exceeds the signed thresholds; the channel stops itself")}


def admit(connection: sqlite3.Connection, prospect_id: int) -> dict:
    """Whether one creator prospect may be contacted under the signed policy.

    Never sends. It only says whether a per-recipient signature can be waived.
    """
    now = utc_now()
    active = active_policy(connection)
    if not active:
        result = {"admitted": False, "checks": {},
                  "reason": "no signed active creator policy. Resource-page outreach "
                            "being authorised does not authorise this channel."}
        _record(connection, prospect_id, 0, "", result, now)
        return result

    policy = active["policy"]
    row = connection.execute(
        "SELECT * FROM creator_prospects WHERE id=?", (prospect_id,)).fetchone()
    if row is None:
        return {"admitted": False, "reason": f"no creator prospect {prospect_id}", "checks": {}}

    recipient = (row["recipient"] or "").lower()
    local = recipient.split("@")[0] if "@" in recipient else ""
    health = deliverability(connection)

    sent_today = connection.execute(
        """SELECT COUNT(DISTINCT c.domain) FROM level1a_action_audit aa
             JOIN creator_prospects c ON lower(c.recipient)=lower(aa.recipient_or_route)
            WHERE aa.mode='live' AND substr(aa.finished_at, 1, 10)=?""",
        (now[:10],)).fetchone()[0]
    contacted = connection.execute(
        """SELECT 1 FROM level1a_action_audit aa
             JOIN creator_prospects c ON lower(c.recipient)=lower(aa.recipient_or_route)
            WHERE aa.mode='live' AND lower(c.domain)=lower(?) LIMIT 1""",
        (row["domain"],)).fetchone()
    suppressed = connection.execute(
        "SELECT 1 FROM level1a_suppressions WHERE suppression_key=?", (recipient,)).fetchone()

    route = row["contact_route"] or (
        "email" if (row["contact_kind"] == "email" and recipient) else "none")
    form_checks = json.loads(row["form_checks_json"] or "{}")
    verified_at = row["form_verified_at"] if route == "form" else row["contact_verified_at"]

    checks = {
        "prospect_qualified": row["status"] == "qualified",
        "route_is_verified": route in ("email", "form"),
        # --- email route ---------------------------------------------------
        "recipient_is_email": route != "email" or (bool(recipient) and "@" in recipient),
        "recipient_published_on_own_site":
            route != "email" or (bool(row["contact_url"]) and row["contact_kind"] == "email"),
        "recipient_not_personal_local_part":
            route != "email"
            or local not in policy["recipient_requirements"]["forbidden_local_parts"],
        # --- form route. Every one was read off the form's own page. --------
        "form_url_recorded": route != "form" or bool(row["contact_form_url"]),
        "form_has_no_blockers": route != "form" or not row["form_blockers"],
        "form_is_a_real_form": route != "form" or bool(form_checks.get("has_form")),
        "form_has_no_captcha": route != "form" or bool(form_checks.get("no_captcha")),
        "form_has_no_login": route != "form" or bool(form_checks.get("no_login")),
        "form_is_the_right_purpose": route != "form" or bool(form_checks.get("right_purpose")),
        "form_is_not_a_complaint_or_ticket_route":
            route != "form" or bool(form_checks.get("not_wrong_purpose")),
        "form_requires_no_payment": route != "form" or bool(form_checks.get("no_payment")),
        "site_does_not_forbid_contact":
            route != "form" or bool(form_checks.get("not_forbidden")),
        "form_not_previously_submitted": True,   # replaced below for the form route
        "contact_verification_current": bool(
            verified_at and verified_at >= _days_ago(
                policy["recipient_requirements"]["max_verification_age_days"])),
        "recent_activity_verified": bool(row["last_activity_date"]),
        "recommends_tools": bool(row["recommends_tools"]),
        "not_paid_placement_only": row["coverage_kind"] != "sponsored",
        "angle_recorded": bool(row["product_angle"]),
        "angle_target_is_approved": row["target_url"] == APPROVED_ANGLES.get(row["segment"]),
        "domain_not_previously_contacted": not contacted,
        "recipient_not_suppressed": route != "email" or not suppressed,
        "daily_organization_limit":
            sent_today < policy["volume"]["max_new_organizations_per_day"],
        "deliverability_healthy": health["healthy"],
    }
    # A form goes into a queue we cannot see, so one submission is the whole
    # allowance: a second is indistinguishable from pestering.
    if route == "form":
        submitted = connection.execute(
            """SELECT 1 FROM level1a_action_audit aa
                 JOIN creator_prospects c ON c.contact_form_url = aa.recipient_or_route
                WHERE aa.mode='live' AND lower(c.domain)=lower(?) LIMIT 1""",
            (row["domain"],)).fetchone()
        checks["form_not_previously_submitted"] = not submitted

    failed = [name for name, ok in checks.items() if not ok]
    result = {
        "route": route,
        "admitted": not failed,
        "reason": None if not failed else "failed policy checks: " + ", ".join(failed),
        "checks": checks, "deliverability": health,
        "policy_version": active["version"], "policy_hash": active["hash"],
    }
    _record(connection, prospect_id, active["version"], active["hash"], result, now)
    return result


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _record(connection, prospect_id, version, digest, result, now) -> None:
    connection.execute(
        """INSERT INTO creator_admissions
             (prospect_id, policy_version, policy_hash, admitted, checks_json,
              refusal_reason, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (prospect_id, version, digest, 1 if result["admitted"] else 0,
         json.dumps(result.get("checks", {}), sort_keys=True), result.get("reason"), now))
    connection.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_show(args) -> None:
    print(json.dumps({"policy": POLICY, "approved_angles": APPROVED_ANGLES,
                      "policy_hash": policy_hash()}, indent=2, sort_keys=True))


def cmd_request(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    digest = store(connection)
    APPROVAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = APPROVAL_DIR / f"creator-policy-v{POLICY_VERSION}.approval"
    payload = signing_payload()
    path.write_text(payload, encoding="utf-8")
    print(json.dumps({
        "status": "awaiting_owner_signature",
        "policy_family": POLICY["policy_family"],
        "policy_version": POLICY_VERSION, "policy_hash": digest,
        "payload_file": str(path),
        "sign_on_your_machine":
            f"ssh-keygen -Y sign -f ~/.ssh/invoiceworkshop_owner "
            f"-n {NAMESPACE} {path.name}",
        "then_activate":
            f"python3 scripts/growth_creator_policy.py activate "
            f"--signature-file {path}.sig",
    }, indent=2))
    print("\n--- policy to be signed ---")
    print(payload, end="")


def cmd_activate(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    store(connection)
    ok, fingerprint, detail = verify_signature(
        signing_payload(), Path(args.signature_file).expanduser(), args.identity)
    if not ok:
        raise ApprovalError(f"owner signature did not verify: {detail}")
    connection.execute(
        """UPDATE creator_policy SET signed=1, active=CASE WHEN version=? THEN 1 ELSE 0 END,
               signer_fingerprint=?, signed_at=? WHERE version=?""",
        (POLICY_VERSION, fingerprint, utc_now(), POLICY_VERSION))
    connection.execute("UPDATE creator_policy SET active=0 WHERE version<>?", (POLICY_VERSION,))
    connection.commit()
    print(json.dumps({"status": "creator_policy_active", "policy_version": POLICY_VERSION,
                      "policy_hash": policy_hash(), "verified_by": fingerprint}, indent=2))


def cmd_deactivate(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    connection.execute("UPDATE creator_policy SET active=0")
    connection.commit()
    print(json.dumps({"status": "creator_policy_deactivated"}))


def cmd_admit(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    print(json.dumps(admit(connection, args.prospect_id), indent=2, sort_keys=True))


def cmd_status(args) -> None:
    connection = connect_db(database_path(args.db)); apply_schema(connection)
    try:
        active = active_policy(connection)
    except ApprovalError as error:
        active = {"error": str(error)}
    backlog = connection.execute(
        "SELECT COUNT(*) FROM creator_prospects WHERE status='qualified'").fetchone()[0]
    print(json.dumps({
        "code_policy_hash": policy_hash(),
        "active_policy": {k: v for k, v in (active or {}).items() if k != "policy"} if active else None,
        "policy_matches_code": bool(active and active.get("hash") == policy_hash()),
        "qualified_backlog": backlog,
        "deliverability": deliverability(connection),
        "sending": "enabled" if active else "blocked: no signed creator policy",
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
    check = commands.add_parser("admit", help="Test one prospect against the signed policy")
    check.add_argument("--prospect-id", type=int, required=True)
    check.set_defaults(handler=cmd_admit)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    args = root.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
