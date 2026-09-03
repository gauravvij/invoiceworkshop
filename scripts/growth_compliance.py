#!/usr/bin/env python3
"""Jurisdiction-aware eligibility for unattended outreach.

A publicly published business email address is not automatically contactable
everywhere. Three regimes are treated explicitly here and everything else is
sent to a person:

  US   commercial email must identify the sender accurately, carry an honest
       subject, offer a working opt-out and include a physical postal address.
       We do not have one configured, so US sends are blocked on the owner
       rather than sent without it.

  UK   the rules differ by who the recipient is. An incorporated organization
       is a corporate subscriber; a sole trader or ordinary partnership is
       treated as an individual and is not sent to unattended. Unknown is
       unknown, and unknown means a person looks at it.

  CA   consent may be implied where a business has conspicuously published an
       address, the publication carries no statement refusing unsolicited
       messages, and the message relates to that person's role. All three are
       evidenced from the page, with the URL and the date, or the send does not
       happen.

Everything else -- and anything the evidence does not settle -- is REVIEW.

This is an execution gate, not legal advice, and it is deliberately built to
fail towards a human. Every verdict here can block a send; none can authorise
one that the existing quality gates would have refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3

from growth_common import (
    apply_schema,
    canonical_domain,
    connect_db,
    database_path,
    record_escalation,
    utc_now,
)

# ---------------------------------------------------------------------------
# Jurisdiction
# ---------------------------------------------------------------------------

# Country-coded domains say it outright. Generic TLDs say nothing at all, which
# is why the page evidence below exists.
CCTLD = {
    ".uk": "UK", ".co.uk": "UK", ".org.uk": "UK", ".ac.uk": "UK", ".gov.uk": "UK",
    ".ca": "CA", ".us": "US",
}

US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
CA_PROVINCES = "AB BC MB NB NL NS NT NU ON PE QC SK YT".split()

US_ADDRESS = re.compile(
    r"\b(?:" + "|".join(US_STATES) + r")\.?\s+\d{5}(?:-\d{4})?\b")
CA_ADDRESS = re.compile(
    r"\b(?:" + "|".join(CA_PROVINCES) + r")\.?\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", re.I)
UK_POSTCODE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b")
UK_REGISTERED = re.compile(
    r"registered (?:in|office) (?:in )?(?:england|wales|scotland|northern ireland)|"
    r"\bcompany (?:number|no\.?|reg(?:istration)?\.? no\.?)\s*[:.]?\s*\d{6,8}\b|"
    r"\bregistered charity (?:number|no\.?)\b", re.I)
UK_PHONE = re.compile(r"\+44\s?\(?0?\)?\s?\d|\b0(?:1|2|3|7|8)\d{2,4}\s?\d{3,4}\s?\d{3,4}\b")
CA_MARKER = re.compile(r"\bcanada\b|\bcanadian\b", re.I)
US_MARKER = re.compile(r"\bunited states\b|\bu\.s\.a?\.\b|\bUSA\b")

# Entity shape. UK treats an incorporated body differently from a sole trader,
# and the suffix is the most reliable public signal of which one it is.
CORPORATE = re.compile(
    r"\b(?:Ltd\.?|Limited|PLC|LLP|LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|"
    r"Corporation|GmbH|Pty|Co\.?,? Ltd|Association|Institute|Foundation|"
    r"Society|Council|Chamber|Federation|Union|University|College)\b")
# Self-description, not subject matter. An earlier version matched the word
# "freelancer" anywhere on the page, which labelled a freelancers' union, an
# authors' guild and a design association as sole traders because their pages
# are about freelancers. What matters is whether the publisher says it is one.
SOLE_TRADER = re.compile(
    r"\b(?:I am a (?:sole trader|sole proprietor|freelance\w*|independent \w+)|"
    r"I'm a (?:sole trader|freelance\w*|independent \w+)|"
    r"sole trader|sole proprietorship|sole proprietor|"
    r"trading as\b|(?<![a-z])t/a\b|"
    r"(?:this|my) (?:is a )?one[- ]person (?:business|studio|practice)|"
    r"(?:run|owned and run) by (?:me|one person))\b", re.I)

# A published refusal. Honoured as written, whatever the jurisdiction.
NO_UNSOLICITED = re.compile(
    r"\b(?:no unsolicited|do not send unsolicited|unsolicited (?:email|e-mail|"
    r"messages?|pitches|submissions|commercial)[^.]{0,40}(?:not|never|will be "
    r"(?:deleted|ignored|reported))|no cold (?:email|outreach|calls?)|"
    r"no marketing (?:email|e-mail|messages)|do not contact (?:us|me) "
    r"(?:with|about|regarding) (?:offers|products|services|marketing)|"
    r"no solicitation)\b", re.I)


def classify_jurisdiction(domain: str, text: str) -> tuple[str, str]:
    """Best-evidenced jurisdiction, with the evidence that decided it."""
    host = (domain or "").lower()
    for suffix, code in sorted(CCTLD.items(), key=lambda item: -len(item[0])):
        if host.endswith(suffix):
            return code, f"country-coded domain {suffix}"

    # Structured data first: it is a statement rather than an inference.
    for match in JSONLD_COUNTRY.finditer(text):
        code = COUNTRY_CODE.get(match.group(1).strip().lower())
        if code:
            return code, f"structured data states addressCountry \"{match.group(1)}\""

    signals: list[tuple[str, str]] = []
    if UK_REGISTERED.search(text):
        signals.append(("UK", "the page states a UK company or charity registration"))
    if UK_POSTCODE.search(text) and UK_PHONE.search(text):
        signals.append(("UK", "a UK postcode and a UK telephone number on the page"))
    if CA_ADDRESS.search(text):
        signals.append(("CA", "a Canadian province and postal code on the page"))
    elif CA_MARKER.search(text) and not US_ADDRESS.search(text):
        signals.append(("CA", "the page identifies itself as Canadian"))
    if US_ADDRESS.search(text):
        signals.append(("US", "a US state and ZIP code on the page"))
    elif US_MARKER.search(text):
        signals.append(("US", "the page identifies itself as US-based"))

    # Two regimes claiming the same page is not evidence, it is a coin toss.
    codes = {code for code, _ in signals}
    if len(codes) == 1:
        code = codes.pop()
        return code, "; ".join(why for _, why in signals)
    if len(codes) > 1:
        return "UNKNOWN", ("conflicting location evidence (" +
                           ", ".join(sorted(codes)) + "), so it is not settled")
    return "UNKNOWN", "no location evidence on the page"


def classify_entity(text: str, title: str = "") -> tuple[str, str]:
    """Corporate body, sole trader/individual, or not established.

    An explicit incorporation or constitution takes precedence: a page can
    mention sole traders while being published by a limited company or a
    professional association, and the publisher is who the rule is about.
    """
    incorporated = CORPORATE.search(f"{title} {text}")
    if incorporated:
        return "corporate", f"incorporated or constituted body ({incorporated.group(0)})"
    sole = SOLE_TRADER.search(text)
    if sole:
        return "sole_trader_or_individual", (
            f"the publisher describes itself as \"{sole.group(0)}\"")
    return "unknown", "no incorporation or trading-status evidence on the page"


# ---------------------------------------------------------------------------
# Sender identity: what a compliant message needs from us
# ---------------------------------------------------------------------------

def sender_identity(connection: sqlite3.Connection) -> dict:
    row = connection.execute("SELECT * FROM sender_identity WHERE id=1").fetchone()
    identity = dict(row) if row else {}
    from growth_level1a import FROM_ADDRESS, FROM_NAME
    identity.setdefault("from_name", FROM_NAME)
    identity.setdefault("from_address", FROM_ADDRESS)
    identity["from_name"] = identity.get("from_name") or FROM_NAME
    identity["from_address"] = identity.get("from_address") or FROM_ADDRESS
    identity["reply_to"] = identity.get("reply_to") or identity["from_address"]
    missing = [field for field in ("postal_address", "optout_line")
               if not (identity.get(field) or "").strip()]
    identity["missing"] = missing
    identity["complete"] = not missing
    return identity


def us_message_requirements(connection: sqlite3.Connection) -> dict:
    """What a US-covered message must carry, and whether we can carry it.

    The postal address is not invented. If it is not configured, US recipients
    are blocked and the gap is reported as an owner blocker.
    """
    identity = sender_identity(connection)
    checks = {
        "accurate_from_identity": bool(identity["from_name"] and identity["from_address"]),
        "reply_to_present": bool(identity["reply_to"]),
        "sender_identified_in_body": True,   # the templates sign off as InvoiceWorkshop
        "opt_out_mechanism": "optout_line" not in identity["missing"],
        "postal_address": "postal_address" not in identity["missing"],
        "suppression_honoured": True,        # enforced by the existing suppression table
    }
    return {"checks": checks, "satisfied": all(checks.values()),
            "missing": identity["missing"], "identity": identity}


# ---------------------------------------------------------------------------
# The assessment
# ---------------------------------------------------------------------------

def assess_row(connection: sqlite3.Connection, prospect: sqlite3.Row,
               page_text: str, title: str = "") -> dict:
    """One prospect, one verdict, with the reason spelled out either way."""
    domain = canonical_domain(prospect["page_url"] or "") or prospect["domain"]
    jurisdiction, jurisdiction_why = classify_jurisdiction(domain, page_text)
    entity, entity_why = classify_entity(page_text, title)
    refuses = bool(NO_UNSOLICITED.search(page_text))
    # The address lives on the action, not on the prospect: `contact_method`
    # holds the route URL. Reading it there reported every recipient as having
    # no address, which made the Canadian publication test unanswerable.
    recipient = _recipient_for(connection, prospect["id"])
    published = bool(recipient) and recipient.lower() in page_text.lower()

    reasons: list[str] = []
    verdict = "ELIGIBLE"

    # Honoured everywhere, before anything else is considered.
    if refuses:
        return _finish(connection, prospect, domain, recipient, jurisdiction,
                       jurisdiction_why, entity, entity_why, published, refuses,
                       True, "REJECT",
                       ["the page states in writing that unsolicited messages are not "
                        "wanted, which is honoured whatever the jurisdiction allows"])

    if jurisdiction == "US":
        requirements = us_message_requirements(connection)
        if not requirements["satisfied"]:
            verdict = "REVIEW"
            reasons.append(
                "US commercial email must carry a physical postal address and a working "
                "opt-out. Missing: " + ", ".join(requirements["missing"]) +
                ". The address is not invented, so this waits on the owner")
    elif jurisdiction == "UK":
        if entity == "corporate":
            pass
        elif entity == "sole_trader_or_individual":
            verdict = "REVIEW"
            reasons.append(
                "the recipient reads as a sole trader or individual subscriber rather "
                "than a corporate body, and there is no established lawful route for "
                "unsolicited marketing email to one unattended")
        else:
            verdict = "REVIEW"
            reasons.append(
                "corporate status is not established, and the UK rule turns on it, so "
                "this is not settled well enough to send unattended")
    elif jurisdiction == "CA":
        missing = []
        if not published:
            missing.append("the address is not visibly published on this page by the "
                           "organization itself")
        if not (prospect["why_fit"] or "").strip():
            missing.append("no recorded relevance to the recipient's business role")
        if missing:
            verdict = "REVIEW"
            reasons.append(
                "Canadian implied consent through conspicuous publication needs all of "
                "its conditions evidenced, and these are not: " + "; ".join(missing))
    else:
        verdict = "REVIEW"
        reasons.append(
            f"jurisdiction is {jurisdiction} ({jurisdiction_why}). No verified rule "
            "profile exists for it, and guessing at one country's rules from another's "
            "is not something this system does")

    if not recipient or "@" not in recipient:
        verdict = "REVIEW"
        reasons.append("no verified email address extracted for this organization, so "
                       "there is no route to assess")

    return _finish(connection, prospect, domain, recipient, jurisdiction,
                   jurisdiction_why, entity, entity_why, published, refuses,
                   bool((prospect["why_fit"] or "").strip()), verdict,
                   reasons or ["every condition for this jurisdiction is evidenced"])


def _recipient_for(connection: sqlite3.Connection, prospect_id: int) -> str:
    """The verified email address for this organization, if one was extracted."""
    row = connection.execute(
        """SELECT recipient FROM level1a_actions
            WHERE prospect_id=? AND contact_kind='email'
              AND recipient IS NOT NULL AND recipient <> ''
            ORDER BY id DESC LIMIT 1""", (prospect_id,)).fetchone()
    return (row["recipient"] or "").strip().lower() if row else ""


def _finish(connection, prospect, domain, recipient, jurisdiction, jurisdiction_why,
            entity, entity_why, published, refuses, relevant, verdict, reasons) -> dict:
    now = utc_now()
    connection.execute(
        """INSERT INTO outreach_compliance
             (prospect_id, domain, recipient, jurisdiction, jurisdiction_evidence,
              entity_type, entity_evidence, address_published_by_org,
              no_unsolicited_statement, relevant_to_role, evidence_source_url,
              evidence_observed_at, verdict, reasons, assessed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(prospect_id) DO UPDATE SET
             recipient=excluded.recipient, jurisdiction=excluded.jurisdiction,
             jurisdiction_evidence=excluded.jurisdiction_evidence,
             entity_type=excluded.entity_type, entity_evidence=excluded.entity_evidence,
             address_published_by_org=excluded.address_published_by_org,
             no_unsolicited_statement=excluded.no_unsolicited_statement,
             relevant_to_role=excluded.relevant_to_role,
             evidence_source_url=excluded.evidence_source_url,
             evidence_observed_at=excluded.evidence_observed_at,
             verdict=excluded.verdict, reasons=excluded.reasons,
             assessed_at=excluded.assessed_at""",
        (prospect["id"], domain, recipient, jurisdiction, jurisdiction_why,
         entity, entity_why, int(published), int(refuses), int(relevant),
         prospect["page_url"], now, verdict, "; ".join(reasons), now))
    connection.commit()
    return {"prospect_id": prospect["id"], "domain": domain, "jurisdiction": jurisdiction,
            "entity_type": entity, "verdict": verdict, "reasons": reasons,
            "evidence": {"jurisdiction": jurisdiction_why, "entity": entity_why,
                         "address_published_by_org": published,
                         "no_unsolicited_statement": refuses,
                         "source_url": prospect["page_url"], "observed_at": now}}


# Structured data states the country outright and is not affected by how a
# footer is laid out. Read before the prose, because it is the better evidence.
JSONLD_COUNTRY = re.compile(r'"addressCountry"\s*:\s*(?:"|\{[^}]*"name"\s*:\s*")([^"]{2,40})"', re.I)
JSONLD_REGION = re.compile(r'"addressRegion"\s*:\s*"([^"]{2,40})"', re.I)
COUNTRY_CODE = {
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
    "gb": "UK", "uk": "UK", "united kingdom": "UK", "england": "UK", "scotland": "UK",
    "wales": "UK", "northern ireland": "UK", "great britain": "UK",
    "ca": "CA", "can": "CA", "canada": "CA",
}

# Where an organization's legal identity and address actually live. A contact
# form rarely carries either; a privacy policy almost always does.
EVIDENCE_PATHS = ("/", "/privacy", "/privacy-policy", "/about", "/about-us",
                  "/contact", "/contact-us", "/terms")
MAX_EVIDENCE_PAGES = 4


def _site_evidence(page_url: str) -> tuple[str, str]:
    """Text from the contact page plus the site root.

    A postal address almost never sits on a contact form; it sits in the footer
    of the home page. Reading only the page we found reported eleven of eighteen
    organizations as being of unknown jurisdiction while their address was one
    request away, and "unknown" here means a person has to look at it.
    """
    from urllib.parse import urlsplit

    from growth_backlink_engine import PageParser, fetch as http_fetch

    texts, titles = [], []
    parts = urlsplit(page_url)
    base = f"{parts.scheme}://{parts.netloc}"
    candidates = [page_url] + [base + path for path in EVIDENCE_PATHS]
    read = 0
    for url in dict.fromkeys(candidates):
        if read >= MAX_EVIDENCE_PAGES:
            break
        try:
            status, body = http_fetch(url)
        except Exception:
            continue
        if status != 200 or not body:
            continue
        read += 1
        parser = PageParser()
        parser.feed(body)
        # The raw body carries structured data the text extractor strips out,
        # and that is where the country is usually stated unambiguously.
        for match in JSONLD_COUNTRY.finditer(body):
            texts.append(f"addressCountry {match.group(1)}")
        for match in JSONLD_REGION.finditer(body):
            texts.append(f"addressRegion {match.group(1)}")
        texts.append(parser.body_text)
        titles.append(parser.title)
    return "\n".join(texts), " ".join(titles)


def assess_all(connection: sqlite3.Connection, limit: int = 50) -> dict:
    """Read each qualified prospect's own pages and assess it."""
    results = []
    rows = connection.execute(
        "SELECT * FROM prospects WHERE status='qualified' ORDER BY id LIMIT ?",
        (limit,)).fetchall()
    for prospect in rows:
        text, title = _site_evidence(prospect["page_url"])
        if not text:
            results.append(_finish(
                connection, prospect,
                canonical_domain(prospect["page_url"] or "") or prospect["domain"],
                _recipient_for(connection, prospect["id"]),
                "UNKNOWN", "the page could not be read", "unknown",
                "the page could not be read", False, False, False, "REVIEW",
                ["the page could not be read, so neither jurisdiction nor recipient "
                 "type could be established"]))
            continue
        results.append(assess_row(connection, prospect, text, title))

    counts: dict[str, int] = {}
    for row in results:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    identity = sender_identity(connection)
    if identity["missing"]:
        record_escalation(
            connection, kind="sender_identity_incomplete", severity="warning",
            subject="Outreach is missing " + " and ".join(identity["missing"])
                    + ", which US-covered messages require",
            detail=("A compliant commercial message needs a physical postal address and "
                    "a working opt-out. Neither is invented here, so every US recipient "
                    "stays REVIEW until the owner supplies them. Configure with "
                    "growth_compliance.py set-identity."),
            fingerprint="sender_identity_incomplete")
    return {"assessed": len(results), "counts": counts, "results": results,
            "sender_identity": {"complete": identity["complete"],
                                "missing": identity["missing"]},
            "external_side_effects": "read-only GET of each prospect's own page"}


def eligible(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT c.prospect_id, c.domain, c.recipient, c.jurisdiction, c.entity_type
             FROM outreach_compliance c WHERE c.verdict='ELIGIBLE'
            ORDER BY c.prospect_id""")]


def report(connection: sqlite3.Connection) -> dict:
    rows = [dict(row) for row in connection.execute(
        """SELECT prospect_id, domain, jurisdiction, entity_type, verdict, reasons
             FROM outreach_compliance ORDER BY verdict, jurisdiction, domain""")]
    counts: dict[str, int] = {}
    by_jurisdiction: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
        by_jurisdiction[row["jurisdiction"]] = by_jurisdiction.get(row["jurisdiction"], 0) + 1
    return {"counts": counts, "by_jurisdiction": by_jurisdiction, "rows": rows,
            "sender_identity": sender_identity(connection)}


def set_identity(connection: sqlite3.Connection, **fields) -> dict:
    """Owner-supplied sender details. Nothing here is guessed or defaulted."""
    now = utc_now()
    current = connection.execute("SELECT * FROM sender_identity WHERE id=1").fetchone()
    merged = dict(current) if current else {
        "legal_name": "", "from_name": "", "from_address": "", "reply_to": "",
        "postal_address": "", "optout_line": "", "configured_by": ""}
    merged.update({k: v for k, v in fields.items() if v is not None})
    connection.execute(
        """INSERT INTO sender_identity
             (id, legal_name, from_name, from_address, reply_to, postal_address,
              optout_line, configured_by, updated_at)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             legal_name=excluded.legal_name, from_name=excluded.from_name,
             from_address=excluded.from_address, reply_to=excluded.reply_to,
             postal_address=excluded.postal_address, optout_line=excluded.optout_line,
             configured_by=excluded.configured_by, updated_at=excluded.updated_at""",
        (merged["legal_name"], merged["from_name"], merged["from_address"],
         merged["reply_to"], merged["postal_address"], merged["optout_line"],
         merged.get("configured_by", ""), now))
    connection.commit()
    from growth_common import resolve_escalation
    if sender_identity(connection)["complete"]:
        resolve_escalation(connection, "sender_identity_incomplete")
    return sender_identity(connection)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("assess", help="Assess every qualified prospect")
    run.add_argument("--limit", type=int, default=50)
    commands.add_parser("report", help="Verdicts, jurisdictions and the reasons")
    commands.add_parser("eligible", help="Prospects the layer clears for unattended send")
    commands.add_parser("identity", help="The sender details messages would carry")
    setter = commands.add_parser("set-identity", help="Record owner-supplied sender details")
    for field in ("legal-name", "from-name", "from-address", "reply-to",
                  "postal-address", "optout-line", "configured-by"):
        setter.add_argument("--" + field)
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "assess":
        result = assess_all(connection, args.limit)
    elif args.command == "eligible":
        result = {"eligible": eligible(connection)}
    elif args.command == "identity":
        result = sender_identity(connection)
    elif args.command == "set-identity":
        result = set_identity(
            connection, legal_name=args.legal_name, from_name=args.from_name,
            from_address=args.from_address, reply_to=args.reply_to,
            postal_address=args.postal_address, optout_line=args.optout_line,
            configured_by=args.configured_by)
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
