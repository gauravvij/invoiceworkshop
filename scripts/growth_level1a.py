#!/usr/bin/env python3
"""Deterministic, restricted Level-1A outreach preparation and execution.

There is intentionally no interface accepting an arbitrary recipient, subject, or body.
Every message is rendered from a database-approved action and versioned claim.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlsplit

from growth_common import apply_schema, connect_db, fetch_public_url, normalize_public_url, utc_now
from growth_level1a_transport import FormTransport, ValidatedDelivery, ZohoMailTransport

FROM_ADDRESS = "hello@invoiceworkshop.com"
FROM_NAME = "InvoiceWorkshop"
FORBIDDEN_PATTERNS = (
    r"\bbest\b", r"\bleading\b", r"\bnumber\s*one\b", r"#\s*1\b",
    r"\bsafest\b", r"\bguarantee(?:d|s)?\b", r"\bcompliant\b",
    r"\bcompliance\b", r"\bcertified\b", r"\bendorsed\b", r"\busers?\b",
    r"\bDA\s*\d+\b", r"\bDR\s*\d+\b", r"\bdofollow\b", r"\bfollowed link\b",
    r"\bbacklink\b", r"\blink exchange\b", r"\breciprocal\b",
)
PAYMENT_PATTERNS = (r"\bsponsor(?:ed|ship)?\b", r"\bpaid placement\b", r"\bpurchase\b", r"\bpayment\b", r"\bfee\b")
EMAIL_PATTERN = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.I)
URL_PATTERN = re.compile(r"https?://[^\s<>\])]+")
CLAIMS = (
    (
        "free_no_signup_local", 1,
        "InvoiceWorkshop is free to use, requires no signup for its core document tools, and saves workspace data locally in the browser.",
        "README.md:3-15; src/lib/storage/database.ts; docs/PRODUCT_PRINCIPLES.md",
    ),
    (
        "browser_pdf_privacy", 1,
        "InvoiceWorkshop creates PDFs in the browser, and document contents are not uploaded to InvoiceWorkshop application servers.",
        "src/lib/documents/pdf.ts; src/pages/privacy/index.astro; tests/e2e/privacy.spec.ts",
    ),
    (
        "reusable_workflows", 1,
        "InvoiceWorkshop supports saved customers and reusable items, plus conversion between supported estimate, quotation, work-order, proforma, and invoice workflows.",
        "src/components/workspace/DocumentWorkspace.tsx; src/lib/documents/conversions.ts; tests/e2e/invoice.spec.ts",
    ),
    (
        "unbranded_documents", 1,
        "Downloaded customer documents do not include InvoiceWorkshop branding or a watermark.",
        "src/lib/documents/pdf.ts; tests/e2e/invoice.spec.ts",
    ),
)
TEMPLATES = (
    (
        "short_resource", 1, "resource_suggestion", "{subject_value}", "{opening_value}",
        "{fit_value}", "{close_value}", 900,
    ),
    (
        "short_directory", 1, "directory_submission", "{subject_value}", "{opening_value}",
        "{fit_value}", "{close_value}", 900,
    ),
)

PILOT = (
    {
        "domain": "freelancethings.co",
        "organization": "Freelance Things",
        "external_page_url": "https://www.freelancethings.co/official-information",
        "verified_contact_route": "https://www.freelancethings.co/official-information",
        "contact_kind": "form",
        "recipient": None,
        "form_handler": None,
        "action_type": "resource_suggestion",
        "target_url": "https://invoiceworkshop.com/invoice-template/",
        "allowed_intent": "Suggest a practical invoicing resource for independent freelancers.",
        "claims": ["free_no_signup_local"],
        "relevance": ["freelance", "resource", "submit"],
        "template_id": "short_resource",
        "subject": "InvoiceWorkshop — invoicing resource for freelancers",
        "opening": "Hello Freelance Things team,",
        "fit": "The invoice template may be useful to freelancers who want to prepare client invoices without opening another hosted account: https://invoiceworkshop.com/invoice-template/",
        "close": "Please include it only if it meets your resource standards.",
        "title": "Freelance Things official information",
        "excerpt": "Curated tools and resources for freelancers with an on-page resource-submission route.",
    },
    {
        "domain": "ledgerco.ca",
        "organization": "LedgerCo",
        "external_page_url": "https://ledgerco.ca/resources/",
        "verified_contact_route": "https://ledgerco.ca/contact/",
        "contact_kind": "email",
        "recipient": "info@ledgerco.ca",
        "form_handler": None,
        "action_type": "resource_suggestion",
        "target_url": "https://invoiceworkshop.com/invoice-template/",
        "allowed_intent": "Suggest a companion resource for LedgerCo's small-business resource library.",
        "claims": ["browser_pdf_privacy"],
        "relevance": ["invoice", "resource", "business"],
        "template_id": "short_resource",
        "subject": "Possible companion resource for your invoice-template library",
        "opening": "Hello LedgerCo team,",
        "fit": "Your library already includes invoice and bookkeeping resources. This invoice template may be a useful optional companion: https://invoiceworkshop.com/invoice-template/",
        "close": "If it does not meet your resource standards, no response or inclusion is expected.",
        "title": "LedgerCo resources",
        "excerpt": "A small-business accounting resource hub with invoice, bookkeeping, and receivables resources.",
    },
    {
        "domain": "business-software.com",
        "organization": "Business-Software.com",
        "external_page_url": "https://www.business-software.com/add-your-product/",
        "verified_contact_route": "https://www.business-software.com/add-your-product/",
        "contact_kind": "form",
        "recipient": None,
        "form_handler": None,
        "action_type": "directory_submission",
        "target_url": "https://invoiceworkshop.com/",
        "allowed_intent": "Submit a factual product record to a legitimate free business-software directory.",
        "claims": ["reusable_workflows"],
        "relevance": ["software", "product", "financial"],
        "template_id": "short_directory",
        "subject": "InvoiceWorkshop product listing",
        "opening": "InvoiceWorkshop is a browser-based business-document workspace.",
        "fit": "It fits the financial-management category and is available at https://invoiceworkshop.com/",
        "close": "Please list it only if it meets the directory's editorial standards.",
        "title": "Add your product to Business-Software.com",
        "excerpt": "A no-cost, editorially reviewed product-submission page with a financial-management category.",
    },
)


@dataclass(frozen=True)
class RenderedMessage:
    action_id: int
    attempt_number: int
    subject: str
    body: str
    message_hash: str


class ValidationError(RuntimeError):
    pass


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def initialize(db: str | Path | None = None) -> sqlite3.Connection:
    connection = connect_db(db)
    apply_schema(connection)
    return connection


def seed_reference_data(connection: sqlite3.Connection) -> None:
    now = utc_now()
    connection.executemany(
        """INSERT INTO level1a_claims
             (claim_key, version, canonical_text, evidence_ref, active, created_at)
           VALUES (?, ?, ?, ?, 1, ?)
           ON CONFLICT(claim_key, version) DO UPDATE SET
             canonical_text=excluded.canonical_text, evidence_ref=excluded.evidence_ref""",
        [(*claim, now) for claim in CLAIMS],
    )
    connection.executemany(
        """INSERT INTO level1a_templates
             (template_id, version, action_type, subject_template, opening_template,
              fit_template, close_template, max_body_characters, active, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
           ON CONFLICT(template_id, version) DO UPDATE SET
             subject_template=excluded.subject_template,
             opening_template=excluded.opening_template,
             fit_template=excluded.fit_template,
             close_template=excluded.close_template,
             max_body_characters=excluded.max_body_characters""",
        [(*template, now) for template in TEMPLATES],
    )
    connection.commit()


def _ensure_directory_prospect(connection: sqlite3.Connection, now: str) -> int:
    page = "https://www.business-software.com/add-your-product/"
    row = connection.execute("SELECT id FROM prospects WHERE domain=? AND page_url=?", ("business-software.com", page)).fetchone()
    if row:
        prospect_id = int(row["id"])
        connection.execute(
            """UPDATE prospects SET status='qualified', rejection_reason=NULL,
                      external_action_approved=0, approved_by=NULL, approved_at=NULL,
                      updated_at=? WHERE id=?""",
            (now, prospect_id),
        )
    else:
        cursor = connection.execute(
            """INSERT INTO prospects (
                 domain, page_url, prospect_type, opportunity_score, risk, why_fit,
                 audience, contact_method, requires_account, requires_payment,
                 link_type, source_url, status, notes, discovered_at, updated_at)
               VALUES (?, ?, 'directory', 80, 'medium', ?, ?, ?, 0, 0,
                       'editorial', ?, 'qualified', ?, ?, ?)""",
            (
                "business-software.com", page,
                "The public page accepts no-cost, editorially reviewed business-software listings and includes financial management.",
                "People comparing business and financial-management software.", page, page,
                "Re-reviewed deterministically for the Level-1A pilot after an earlier model pass did not retain it; CAPTCHA means no generic automated submission is allowed.",
                now, now,
            ),
        )
        prospect_id = int(cursor.lastrowid)
    connection.execute(
        """INSERT INTO prospect_qualification (
             prospect_id, channel, page_evidence, outbound_resources, target_url,
             proposed_action, confidence, second_pass_pass, review_reason, reviewed_at)
           VALUES (?, 'directory', ?, '[]', 'https://invoiceworkshop.com/', ?,
                   'medium', 1, ?, ?)
           ON CONFLICT(prospect_id) DO UPDATE SET
             page_evidence=excluded.page_evidence, target_url=excluded.target_url,
             proposed_action=excluded.proposed_action, confidence=excluded.confidence,
             second_pass_pass=1, review_reason=excluded.review_reason,
             reviewed_at=excluded.reviewed_at""",
        (
            prospect_id,
            "The page states that product submission is free, editorially reviewed, and offers a financial-management category.",
            "Submit a factual InvoiceWorkshop listing without paid or reciprocal terms.",
            "Useful as a comparison-directory record without SEO value; live form automation remains unavailable.", now,
        ),
    )
    return prospect_id


def seed_pilot(connection: sqlite3.Connection) -> list[int]:
    seed_reference_data(connection)
    now = utc_now()
    _ensure_directory_prospect(connection, now)
    action_ids: list[int] = []
    for item in PILOT:
        prospect = connection.execute(
            """SELECT p.id, p.status, p.requires_account, p.requires_payment,
                      q.second_pass_pass
                 FROM prospects p JOIN prospect_qualification q ON q.prospect_id=p.id
                WHERE p.domain=? AND p.page_url=?""",
            (item["domain"], item["external_page_url"]),
        ).fetchone()
        if not prospect or prospect["status"] != "qualified" or prospect["second_pass_pass"] != 1:
            raise ValidationError(f"pilot prospect is not evidence-qualified: {item['domain']}")
        if prospect["requires_account"] or prospect["requires_payment"]:
            raise ValidationError(f"pilot prospect requires an account or payment: {item['domain']}")
        values = {
            "prospect_id": int(prospect["id"]), "organization": item["organization"],
            "external_page_url": normalize_public_url(item["external_page_url"]),
            "verified_contact_route": normalize_public_url(item["verified_contact_route"]),
            "contact_kind": item["contact_kind"], "recipient": item["recipient"],
            "form_handler": item["form_handler"], "action_type": item["action_type"],
            "target_url": normalize_public_url(item["target_url"]), "allowed_intent": item["allowed_intent"],
            "claims": _json(item["claims"]), "forbidden": _json(list(FORBIDDEN_PATTERNS)),
            "relevance": _json(item["relevance"]), "template_id": item["template_id"],
            "subject": item["subject"], "opening": item["opening"], "fit": item["fit"],
            "close": item["close"], "title": item["title"], "excerpt": item["excerpt"],
            "now": now,
        }
        connection.execute(
            """INSERT INTO level1a_actions (
                 prospect_id, organization, external_page_url, verified_contact_route,
                 contact_kind, recipient, form_handler, action_type, target_url,
                 allowed_intent, allowed_claim_keys_json, forbidden_claims_json,
                 relevance_terms_json, template_id, template_version, subject_value,
                 opening_value, fit_value, close_value, max_followups,
                 attachments_allowed, payment_allowed, external_action_approved,
                 message_approved, suppression_state, page_title, page_excerpt,
                 created_at, updated_at)
               VALUES (:prospect_id, :organization, :external_page_url,
                 :verified_contact_route, :contact_kind, :recipient, :form_handler,
                 :action_type, :target_url, :allowed_intent, :claims, :forbidden,
                 :relevance, :template_id, 1, :subject, :opening, :fit, :close,
                 2, 0, 0, 0, 0, 'active', :title, :excerpt, :now, :now)
               ON CONFLICT(prospect_id, action_type, verified_contact_route) DO UPDATE SET
                 organization=excluded.organization, external_page_url=excluded.external_page_url,
                 contact_kind=excluded.contact_kind, recipient=excluded.recipient,
                 form_handler=excluded.form_handler, target_url=excluded.target_url,
                 allowed_intent=excluded.allowed_intent,
                 allowed_claim_keys_json=excluded.allowed_claim_keys_json,
                 forbidden_claims_json=excluded.forbidden_claims_json,
                 relevance_terms_json=excluded.relevance_terms_json,
                 template_id=excluded.template_id, template_version=excluded.template_version,
                 subject_value=excluded.subject_value, opening_value=excluded.opening_value,
                 fit_value=excluded.fit_value, close_value=excluded.close_value,
                 page_title=excluded.page_title, page_excerpt=excluded.page_excerpt,
                 updated_at=excluded.updated_at""",
            values,
        )
        row = connection.execute(
            "SELECT id FROM level1a_actions WHERE prospect_id=? AND action_type=? AND verified_contact_route=?",
            (values["prospect_id"], values["action_type"], values["verified_contact_route"]),
        ).fetchone()
        action_ids.append(int(row["id"]))
    connection.commit()
    return action_ids


def load_action(connection: sqlite3.Connection, action_id: int) -> sqlite3.Row:
    row = connection.execute(
        """SELECT a.*, p.domain, p.status AS prospect_status, p.requires_account,
                  p.requires_payment, p.page_url AS prospect_page_url,
                  p.contact_method AS prospect_contact_method,
                  q.second_pass_pass, t.subject_template, t.opening_template,
                  t.fit_template, t.close_template, t.max_body_characters,
                  t.active AS template_active
             FROM level1a_actions a
             JOIN prospects p ON p.id=a.prospect_id
             JOIN prospect_qualification q ON q.prospect_id=p.id
             JOIN level1a_templates t ON t.template_id=a.template_id
                  AND t.version=a.template_version
            WHERE a.id=?""",
        (action_id,),
    ).fetchone()
    if not row:
        raise ValidationError("unknown Level-1A action")
    return row


def render_message(connection: sqlite3.Connection, action: sqlite3.Row, attempt_number: int = 0) -> RenderedMessage:
    if attempt_number < 0 or attempt_number > int(action["max_followups"]):
        raise ValidationError("attempt exceeds the approved follow-up limit")
    claim_keys = json.loads(action["allowed_claim_keys_json"])
    claims: list[str] = []
    for key in claim_keys:
        claim = connection.execute(
            "SELECT canonical_text FROM level1a_claims WHERE claim_key=? AND active=1 ORDER BY version DESC LIMIT 1",
            (key,),
        ).fetchone()
        if not claim:
            raise ValidationError(f"inactive or unknown approved claim: {key}")
        claims.append(str(claim["canonical_text"]))
    values = dict(action)
    subject = str(action["subject_template"]).format_map(values).strip()
    opening = str(action["opening_template"]).format_map(values).strip()
    fit = str(action["fit_template"]).format_map(values).strip()
    close = str(action["close_template"]).format_map(values).strip()
    if attempt_number:
        opening = "Hello again — this is a brief follow-up." if attempt_number == 1 else "Hello again — this is the final follow-up."
        close = "No response is needed if this is not relevant." if attempt_number == 1 else "No further follow-up will be sent if this is not relevant."
    body = f"{opening}\n\n{' '.join(claims)}\n\n{fit}\n\n{close}\n\nInvoiceWorkshop\n{FROM_ADDRESS}"
    digest = _sha256(subject + "\n\n" + body)
    return RenderedMessage(int(action["id"]), attempt_number, subject, body, digest)


def _valid_email(value: str | None) -> bool:
    if not value or "\n" in value or "\r" in value:
        return False
    display, parsed = parseaddr(value)
    return not display and parsed == value and bool(EMAIL_PATTERN.fullmatch(value))


def _business_days_between(earlier: datetime, later: datetime) -> int:
    count = 0
    day = earlier.date()
    while day < later.date():
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def _validate_frozen_manifest(action: sqlite3.Row) -> None:
    source = next((item for item in PILOT if item["organization"] == action["organization"]), None)
    if not source:
        raise ValidationError("organization is absent from the reviewed code allowlist")
    expected = {
        "external_page_url": normalize_public_url(source["external_page_url"]),
        "verified_contact_route": normalize_public_url(source["verified_contact_route"]),
        "contact_kind": source["contact_kind"], "recipient": source["recipient"],
        "form_handler": source["form_handler"], "action_type": source["action_type"],
        "target_url": normalize_public_url(source["target_url"]),
        "allowed_intent": source["allowed_intent"],
        "allowed_claim_keys_json": _json(source["claims"]),
        "relevance_terms_json": _json(source["relevance"]),
        "template_id": source["template_id"], "template_version": 1,
        "subject_value": source["subject"], "opening_value": source["opening"],
        "fit_value": source["fit"], "close_value": source["close"],
    }
    for key, value in expected.items():
        if action[key] != value:
            raise ValidationError(f"action manifest differs from reviewed allowlist field: {key}")


def _validate_text(action: sqlite3.Row, rendered: RenderedMessage) -> None:
    combined = rendered.subject + "\n" + rendered.body
    if len(rendered.subject) > 120 or len(rendered.body) > int(action["max_body_characters"]):
        raise ValidationError("message exceeds the approved length")
    for pattern in json.loads(action["forbidden_claims_json"]):
        if re.search(pattern, combined, re.I):
            raise ValidationError(f"forbidden claim or outreach language matched: {pattern}")
    for pattern in PAYMENT_PATTERNS:
        if re.search(pattern, combined, re.I):
            raise ValidationError(f"payment or sponsorship language matched: {pattern}")
    urls = [url.rstrip(".,;") for url in URL_PATTERN.findall(combined)]
    if urls != [action["target_url"]]:
        raise ValidationError("message must contain exactly the one approved InvoiceWorkshop target URL")
    body_without_url = combined.replace(action["target_url"], "")
    if re.search(r"(?:\b\d{2,}\b|\b\d+(?:\.\d+)?%|\b\d+[kKmM]\+?\b)", body_without_url):
        raise ValidationError("unapproved numeric or volume claim")
    if "attach" in combined.lower():
        raise ValidationError("attachment language is not permitted")


def verify_public_page(action: sqlite3.Row, *, fetcher=fetch_public_url) -> dict[str, object]:
    response = fetcher(str(action["external_page_url"]))
    try:
        status = int(response.status_code)
        if status < 200 or status >= 400:
            raise ValidationError(f"prospect page returned HTTP {status}")
        text = html.unescape(re.sub(r"<[^>]+>", " ", response.text or ""))
        normalized = re.sub(r"\s+", " ", text).lower()
        matched = [term for term in json.loads(action["relevance_terms_json"]) if term.lower() in normalized]
        if len(matched) < 2:
            raise ValidationError("prospect page no longer has enough approved relevance evidence")
        return {"status": status, "matched_terms": matched, "final_url": str(getattr(response, "url", action["external_page_url"]))}
    finally:
        close = getattr(response, "close", None)
        if close:
            close()


def validate_action(
    connection: sqlite3.Connection,
    action: sqlite3.Row,
    rendered: RenderedMessage,
    *,
    live: bool,
    now: datetime | None = None,
    verify_page: bool = True,
    fetcher=fetch_public_url,
) -> None:
    now = now or datetime.now(timezone.utc)
    if action["prospect_status"] != "qualified" or action["second_pass_pass"] != 1:
        raise ValidationError("prospect is not currently evidence-qualified")
    if action["requires_account"] or action["requires_payment"]:
        raise ValidationError("prospect requires an account or payment")
    if action["attachments_allowed"] or action["payment_allowed"]:
        raise ValidationError("manifest attempts to permit an attachment or payment")
    if action["suppression_state"] != "active":
        raise ValidationError(f"action is suppressed: {action['suppression_state']}")
    if action["template_active"] != 1:
        raise ValidationError("message template is inactive")
    if action["external_page_url"] != action["prospect_page_url"]:
        raise ValidationError("action/prospect page mismatch")
    if action["verified_contact_route"] != action["prospect_contact_method"]:
        raise ValidationError("action/prospect contact-route mismatch")
    if action["contact_kind"] == "email" and not _valid_email(action["recipient"]):
        raise ValidationError("recipient email is malformed")
    if action["contact_kind"] == "form" and action["recipient"] is not None:
        raise ValidationError("form action must not contain an email recipient")
    duplicate_org = connection.execute(
        """SELECT 1 FROM level1a_action_audit aa JOIN level1a_actions a ON a.id=aa.action_id
            WHERE lower(a.organization)=lower(?) AND aa.mode='live'
              AND aa.validation_result='passed' AND aa.attempt_number=? AND a.id<>? LIMIT 1""",
        (action["organization"], rendered.attempt_number, action["id"]),
    ).fetchone()
    if duplicate_org:
        raise ValidationError("another route for this organization has already been contacted")
    suppression_key = (action["recipient"] or action["domain"]).lower()
    if connection.execute("SELECT 1 FROM level1a_suppressions WHERE suppression_key=?", (suppression_key,)).fetchone():
        raise ValidationError("recipient or organization is on the suppression list")
    if connection.execute("SELECT 1 FROM level1a_replies WHERE action_id=? LIMIT 1", (action["id"],)).fetchone():
        raise ValidationError("a reply was received; follow-up sequence is stopped")
    if connection.execute(
        "SELECT 1 FROM placements WHERE prospect_id=? AND (status='live' OR link_present=1) LIMIT 1",
        (action["prospect_id"],),
    ).fetchone():
        raise ValidationError("a placement was recorded; follow-up sequence is stopped")
    if connection.execute("SELECT 1 FROM outreach WHERE prospect_id=? LIMIT 1", (action["prospect_id"],)).fetchone():
        raise ValidationError("legacy outreach history shows this prospect was already contacted")
    previous = connection.execute(
        """SELECT attempt_number, started_at FROM level1a_action_audit
            WHERE action_id=? AND mode='live' AND validation_result='passed'
            ORDER BY attempt_number DESC LIMIT 1""",
        (action["id"],),
    ).fetchone()
    if rendered.attempt_number == 0 and previous:
        raise ValidationError("initial action was already sent")
    if rendered.attempt_number:
        if not previous or int(previous["attempt_number"]) != rendered.attempt_number - 1:
            raise ValidationError("follow-up sequence is incomplete")
        earlier = datetime.fromisoformat(str(previous["started_at"]).replace("Z", "+00:00"))
        wait_days = 4 if rendered.attempt_number == 1 else 7
        if _business_days_between(earlier, now) < wait_days:
            raise ValidationError("follow-up interval has not elapsed")
    _validate_frozen_manifest(action)
    _validate_text(action, rendered)
    expected_rendering = render_message(connection, action, rendered.attempt_number)
    if rendered != expected_rendering:
        raise ValidationError("rendered message differs from the deterministic approved template")
    if verify_page:
        verify_public_page(action, fetcher=fetcher)
        expires = now + timedelta(days=7)
        connection.execute(
            "UPDATE level1a_actions SET last_verified_at=?, verification_expires_at=?, updated_at=? WHERE id=?",
            (now.isoformat(), expires.isoformat(), now.isoformat(), action["id"]),
        )
    if live:
        if action["contact_kind"] == "form" and not action["form_handler"]:
            raise ValidationError("no allowlisted site-specific form handler is installed")
        if os.environ.get("LEVEL1_OUTBOUND_ENABLED", "false").lower() != "true":
            raise ValidationError("environment kill switch LEVEL1_OUTBOUND_ENABLED is false")
        setting = connection.execute("SELECT value FROM level1a_settings WHERE key='outbound_enabled'").fetchone()
        if not setting or setting["value"].lower() != "true":
            raise ValidationError("database outbound kill switch is false")
        if not action["external_action_approved"] or not action["message_approved"]:
            raise ValidationError("action and exact message have not received owner approval")
        approved_hashes = json.loads(action["approved_message_hashes_json"])
        if rendered.message_hash not in approved_hashes:
            raise ValidationError("rendered message differs from the owner-approved message")
        today = now.date().isoformat()
        total = connection.execute(
            "SELECT COUNT(*) FROM level1a_action_audit WHERE mode='live' AND validation_result='passed' AND substr(started_at,1,10)=?",
            (today,),
        ).fetchone()[0]
        new = connection.execute(
            "SELECT COUNT(*) FROM level1a_action_audit WHERE mode='live' AND validation_result='passed' AND attempt_number=0 AND substr(started_at,1,10)=?",
            (today,),
        ).fetchone()[0]
        total_cap = int(connection.execute("SELECT value FROM level1a_settings WHERE key='daily_total_cap'").fetchone()[0])
        new_cap = int(connection.execute("SELECT value FROM level1a_settings WHERE key='daily_new_cap'").fetchone()[0])
        if total >= total_cap or (rendered.attempt_number == 0 and new >= new_cap):
            raise ValidationError("daily Level-1A cap reached")


def _record_audit(
    connection: sqlite3.Connection, action: sqlite3.Row, rendered: RenderedMessage,
    *, mode: str, result: str, reason: str | None = None,
    provider_id: str | None = None, side_effects: str = "none",
    delivery_state: str | None = None,
) -> str:
    now = utc_now()
    message_id = f"l1a-{action['id']}-{rendered.attempt_number}-{rendered.message_hash[:16]}-{_sha256(now)[:8]}"
    connection.execute(
        """INSERT INTO level1a_action_audit (
             action_id, message_id, attempt_number, mode, started_at, finished_at,
             subject, body, recipient_or_route, source_page, target_url,
             message_hash, validation_result, rejection_reason, provider_response_id,
             delivery_state, reply_state, suppression_state, external_side_effects)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
        (
            action["id"], message_id, rendered.attempt_number, mode, now, now,
            rendered.subject, rendered.body, action["recipient"] or action["verified_contact_route"],
            action["external_page_url"], action["target_url"], rendered.message_hash,
            result, reason, provider_id, delivery_state or ("submitted" if provider_id else "none"),
            action["suppression_state"], side_effects,
        ),
    )
    connection.commit()
    return message_id


def dry_run_action(connection: sqlite3.Connection, action_id: int, *, fetcher=fetch_public_url) -> dict[str, object]:
    action = load_action(connection, action_id)
    rendered = render_message(connection, action)
    try:
        validate_action(connection, action, rendered, live=False, fetcher=fetcher)
    except ValidationError as error:
        message_id = _record_audit(connection, action, rendered, mode="dry_run", result="rejected", reason=str(error))
        return {"action_id": action_id, "message_id": message_id, "status": "rejected", "reason": str(error), "external_side_effects": "none"}
    message_id = _record_audit(connection, action, rendered, mode="dry_run", result="review_ready")
    return {
        "action_id": action_id, "message_id": message_id, "status": "review_ready",
        "organization": action["organization"], "route": action["recipient"] or action["verified_contact_route"],
        "contact_kind": action["contact_kind"], "subject": rendered.subject, "body": rendered.body,
        "message_hash": rendered.message_hash, "external_side_effects": "none",
    }


def execute_action(connection: sqlite3.Connection, action_id: int, attempt_number: int = 0) -> dict[str, object]:
    action = load_action(connection, action_id)
    rendered = render_message(connection, action, attempt_number)
    try:
        validate_action(connection, action, rendered, live=True)
    except ValidationError as error:
        _record_audit(
            connection, action, rendered, mode="live", result="rejected",
            reason=str(error), side_effects="none",
        )
        raise
    delivery = ValidatedDelivery.from_validator(
        action_id=action_id, message_id=rendered.message_hash,
        recipient=action["recipient"] or action["verified_contact_route"],
        subject=rendered.subject, body=rendered.body,
    )
    transport = ZohoMailTransport() if action["contact_kind"] == "email" else FormTransport()
    try:
        provider_id = transport.send(delivery)
    except Exception as error:
        _record_audit(
            connection, action, rendered, mode="live", result="rejected",
            reason=f"transport failure: {type(error).__name__}: {error}",
            side_effects="unknown", delivery_state="unknown",
        )
        raise
    message_id = _record_audit(
        connection, action, rendered, mode="live", result="passed",
        provider_id=provider_id,
        side_effects="email_sent" if action["contact_kind"] == "email" else "form_submitted",
    )
    return {"action_id": action_id, "message_id": message_id, "status": "sent", "provider_id": provider_id}


def classify_reply(text: str, *, bounced: bool = False) -> tuple[str, bool, str]:
    normalized = re.sub(r"\s+", " ", text).lower()
    if bounced:
        return "bounce", False, "suppress"
    if re.search(r"\b(unsubscribe|remove me|stop emailing|opt out)\b", normalized):
        return "unsubscribe", False, "suppress"
    if re.search(r"\b(not interested|no thank|decline|do not contact)\b", normalized):
        return "decline", False, "suppress"
    if re.search(r"\b(sponsor|paid|payment|fee|rate card)\b", normalized):
        return "payment_requested", True, "escalate"
    if re.search(r"\b(author|byline|headshot|writing sample|contributor)\b", normalized):
        return "editorial_author_required", True, "escalate"
    if re.search(r"\b(partner|partnership|affiliate|revenue share|reciprocal)\b", normalized):
        return "partnership", True, "escalate"
    if re.search(r"\b(legal|lawyer|attorney|compliance|regulation|privacy complaint)\b", normalized):
        return "legal_compliance", True, "escalate"
    if re.search(r"\b(yes|looks useful|we will review|added|included|interested)\b", normalized):
        return "positive", False, "stop_followups"
    if "?" in text or re.search(r"\b(please provide|more information|tell us)\b", normalized):
        return "information_requested", True, "draft_factual_response_for_review"
    return "ambiguous", True, "escalate"


def record_reply(
    connection: sqlite3.Connection, action_id: int, provider_message_id: str,
    text: str, *, bounced: bool = False,
) -> dict[str, object]:
    load_action(connection, action_id)
    classification, escalation, automated = classify_reply(text, bounced=bounced)
    now = utc_now()
    connection.execute(
        """INSERT INTO level1a_replies (
             action_id, provider_message_id, received_at, classification,
             requires_escalation, automated_action, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (action_id, provider_message_id, now, classification, int(escalation), automated, _sha256(text)),
    )
    if classification in {"decline", "unsubscribe", "bounce"}:
        state = {"decline": "declined", "unsubscribe": "unsubscribed", "bounce": "bounced"}[classification]
        action = load_action(connection, action_id)
        key = (action["recipient"] or action["domain"]).lower()
        connection.execute("UPDATE level1a_actions SET suppression_state=?, updated_at=? WHERE id=?", (state, now, action_id))
        connection.execute(
            """INSERT INTO level1a_suppressions
                 (suppression_key, organization, recipient, state, reason, permanent, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(suppression_key) DO UPDATE SET state=excluded.state, reason=excluded.reason""",
            (key, action["organization"], action["recipient"], state, f"reply classified as {classification}", now),
        )
    connection.commit()
    return {"classification": classification, "requires_escalation": escalation, "automated_action": automated}


def export_manifest(connection: sqlite3.Connection) -> dict[str, object]:
    actions = []
    for action in connection.execute("SELECT id FROM level1a_actions ORDER BY id"):
        row = load_action(connection, int(action["id"]))
        renderings = [render_message(connection, row, attempt) for attempt in range(int(row["max_followups"]) + 1)]
        rendered = renderings[0]
        approval_hash = _sha256(_json([item.message_hash for item in renderings]))
        actions.append({
            "action_id": row["id"], "prospect_id": row["prospect_id"],
            "organization": row["organization"], "page": row["external_page_url"],
            "contact_route": row["verified_contact_route"], "contact_kind": row["contact_kind"],
            "recipient": row["recipient"], "action_type": row["action_type"],
            "target_url": row["target_url"], "intent": row["allowed_intent"],
            "claim_keys": json.loads(row["allowed_claim_keys_json"]),
            "forbidden_claims": json.loads(row["forbidden_claims_json"]),
            "template": f"{row['template_id']}@{row['template_version']}",
            "max_followups": row["max_followups"], "attachments_allowed": False,
            "payment_allowed": False, "external_action_approved": bool(row["external_action_approved"]),
            "message_approved": bool(row["message_approved"]), "message_hash": rendered.message_hash,
            "approval_hash": approval_hash,
            "subject": rendered.subject, "body": rendered.body,
            "approved_messages": [
                {"attempt": item.attempt_number, "message_hash": item.message_hash,
                 "subject": item.subject, "body": item.body}
                for item in renderings
            ],
            "suppression_state": row["suppression_state"],
            "last_verified_at": row["last_verified_at"],
        })
    payload: dict[str, object] = {
        "level": "1A", "outbound_enabled": False,
        "sender": f"{FROM_NAME} <{FROM_ADDRESS}>", "actions": actions,
    }
    payload["manifest_hash"] = _sha256(_json(payload))
    return payload


def cmd_seed(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    print(json.dumps({"action_ids": seed_pilot(connection), "status": "seeded_disabled"}, indent=2))


def cmd_manifest(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    seed_pilot(connection)
    print(json.dumps(export_manifest(connection), indent=2, sort_keys=True))


def cmd_dry_run(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    action_ids = seed_pilot(connection)
    selected = [args.action_id] if args.action_id else action_ids
    print(json.dumps([dry_run_action(connection, action_id) for action_id in selected], indent=2, sort_keys=True))


def cmd_execute(args: argparse.Namespace) -> None:
    connection = initialize(args.db)
    print(json.dumps(execute_action(connection, args.action_id, args.attempt), indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db", help="Override GROWTH_DB_PATH")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-pilot").set_defaults(handler=cmd_seed)
    commands.add_parser("manifest").set_defaults(handler=cmd_manifest)
    dry = commands.add_parser("dry-run")
    dry.add_argument("--action-id", type=int)
    dry.set_defaults(handler=cmd_dry_run)
    execute = commands.add_parser("execute", help="Execute only a pre-approved database action")
    execute.add_argument("--action-id", type=int, required=True)
    execute.add_argument("--attempt", type=int, default=0, choices=(0, 1, 2))
    execute.set_defaults(handler=cmd_execute)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
