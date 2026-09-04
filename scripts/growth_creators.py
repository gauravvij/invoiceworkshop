#!/usr/bin/env python3
"""Creator and newsletter distribution: discovery, verification, qualification.

The resource-page outreach cohort answers "who publishes a list our tool belongs
on". This answers a different question: "whose audience would actually want this
specific thing, and do they ever recommend anything". Those need different
evidence, so they get a different table, a different volume limit and different
reporting -- merging them would let one borrow the other's results.

Nothing here contacts anyone. Discovery, fetching and qualification run
unattended; sending is governed by a separate owner-signed policy in
growth_creator_policy.py, and a qualified prospect sits in the backlog until
that policy exists. The gate is written so that being behind on traffic cannot
lower it: every check is a fact read off the target's own page.

Four things disqualify a target outright, and all four are common:

  * no evidence they have published anything recently -- a dead newsletter has
    no audience regardless of its archive
  * no evidence they ever recommend a tool -- an unpaid suggestion to someone
    who never makes them is a waste of their attention and ours
  * no public business contact route on their own site
  * a following without a subject: "business influencer" is not an audience fit,
    and reach without relevance is the thing this module exists not to chase
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from growth_common import (
    apply_schema,
    canonical_domain,
    public_domain_or_blank,
    connect_db,
    database_path,
    utc_now,
)

# Which live capability each segment's audience would actually care about.
# `target` must be a page that exists: an angle pointing at something unbuilt is
# a promise, and the policy forbids sending one.
SEGMENTS = {
    "freelancer_newsletter": {
        "angle": "the free no-signup invoice-to-receipt workflow: quote, invoice, "
                 "then receipt the payment, with nothing uploaded anywhere",
        "target": "https://invoiceworkshop.com/receipt-generator/",
        "queries": (
            'freelancer newsletter "tools I use" invoicing recommendation',
            '"newsletter for freelancers" resources tools invoicing',
            'freelance business newsletter archive "free tools" invoice',
            '"freelancer resources" newsletter subscribe invoicing tools',
            'freelance newsletter issue archive tools invoicing recommendation',
            'independent worker newsletter "what I am using" tools business admin',
        ),
    },
    "freelancer_creator": {
        "angle": "a free invoice and receipt workflow their audience can use "
                 "without signing up or having a document watermarked",
        "target": "https://invoiceworkshop.com/",
        "queries": (
            'freelancer blog "tools for freelancers" invoicing free no signup',
            '"how to invoice as a freelancer" blog author contact',
            'freelance writer resources page invoicing tools recommended',
            'freelance designer blog "my tools" invoicing client billing free',
            'freelance blog "getting paid" resources invoice tools contact us',
            'freelance consultant website resources page "free tools" clients invoice',
        ),
    },
    "bookkeeping_newsletter": {
        "angle": "a free client-facing paperwork toolkit -- invoices, receipts and "
                 "credit notes -- that a bookkeeper can hand to a client who is "
                 "still emailing Word documents",
        "target": "https://invoiceworkshop.com/credit-note-generator/",
        "queries": (
            'bookkeeping newsletter "for bookkeepers" resources tools',
            'accounting newsletter small business "tools we recommend"',
            '"bookkeeper" newsletter archive client resources invoice template',
            'bookkeeping practice newsletter "resources for clients" free tools',
            'accounting newsletter issue archive "tools" small business clients',
        ),
    },
    "bookkeeping_creator": {
        "angle": "the credit note and receipt workflow, which is where small "
                 "clients most often send the wrong document",
        "target": "https://invoiceworkshop.com/credit-note-generator/",
        "queries": (
            'bookkeeping blog "credit note" vs invoice explained resources',
            'accounting educator blog small business invoicing tools list',
            '"bookkeeping tips" blog resources free tools invoice receipt',
            'bookkeeper blog "client onboarding" resources invoice template free',
            'accounting blog "invoice vs receipt" explained resources contact',
            '"bookkeeping for" blog free resources tools we recommend',
        ),
    },
    "small_business_newsletter": {
        "angle": "a free paperwork workspace covering invoices, estimates, work "
                 "orders, receipts and credit notes, with no account",
        "target": "https://invoiceworkshop.com/",
        "queries": (
            '"small business newsletter" tools resources free recommend',
            'newsletter for small business owners "free tools" archive',
            'solopreneur newsletter resources tools recommendation archive',
            'small business owner newsletter archive issue "tools" free recommend',
            '"main street" OR "local business" newsletter resources tools free',
        ),
    },
    "contractor_creator": {
        "angle": "the construction invoice plus the progress-draw and retainage "
                 "schedule, which is arithmetic their audience gets wrong and "
                 "currently does in a spreadsheet",
        "target": "https://invoiceworkshop.com/progress-draw-schedule/",
        "queries": (
            'construction business blog "progress billing" retainage resources',
            'contractor blog "schedule of values" draw request explained',
            'construction newsletter contractors "tools" resources billing',
            '"for contractors" blog resources invoicing retainage free tool',
            'trade business blog "getting paid" invoicing resources contractors',
            'construction blog "change order" "progress payment" resources tools',
            '"electrician" OR "plumber" business blog invoicing resources tools',
        ),
    },
}

RESULTS_PER_QUERY = 10

# Recency. A newsletter that last published eighteen months ago has an archive,
# not an audience.
MAX_ACTIVITY_AGE_DAYS = 270

# Evidence that this person or publication recommends things at all.
RECOMMENDS = re.compile(
    r"\b(tools i use|tools we use|my favou?rite tools|recommended tools|tool stack|"
    r"resources (?:i|we) recommend|best tools for|tools for (?:freelancers|contractors|"
    r"bookkeepers|small business)|our favou?rite|worth bookmarking|free tools)\b", re.I)

# How their coverage is paid for. Not disqualifying on its own, but a site that
# only runs paid placements will not act on an unpaid suggestion.
SPONSORED = re.compile(r"\b(sponsored|paid partnership|in partnership with|advertorial|"
                       r"this post is sponsored|#ad\b)", re.I)
AFFILIATE = re.compile(r"\b(affiliate link|affiliate commission|commission if you|"
                       r"we may earn|earn a commission|affiliate disclosure)\b", re.I)

# Reach, only where the target states it themselves.
AUDIENCE = re.compile(r"([\d][\d,\.]{2,})\s*\+?\s*(subscribers|readers|members|followers)", re.I)

# Publication dates live in three places and a site uses whichever it likes:
# visible text, a <time datetime=> attribute, or JSON-LD / OpenGraph metadata.
# Reading only the visible text rejected live publications for having their date
# in a machine-readable field, which is the opposite of what the check is for.
META_DATE = re.compile(
    r'(?:datePublished|dateModified|article:published_time|article:modified_time)'
    r'"?\s*[:=]\s*"?\s*(20[12]\d-\d{2}-\d{2})', re.I)
TIME_ATTR = re.compile(r'<time[^>]+datetime="\s*(20[12]\d-\d{2}-\d{2})', re.I)

DATE_PATTERNS = (
    re.compile(r"\b(20[12]\d)-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20[12]\d)\b", re.I),
)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# A following without a subject. Reach with no relevance is exactly what this
# module exists not to chase.
GENERIC_INFLUENCER = re.compile(
    r"\b(business influencer|entrepreneur mindset|hustle|passive income blueprint|"
    r"personal brand coach|grow your following|money mindset|side hustle empire)\b", re.I)

# Places whose "contact" is a platform account rather than the target's own
# published business address.
PLATFORM_HOSTS = ("twitter.com", "x.com", "instagram.com", "facebook.com", "tiktok.com",
                  "linkedin.com", "youtube.com", "reddit.com", "medium.com", "threads.net")


# A site that sells a product has a product's navigation. These paths are what
# separate a company blog from a creator's: nobody's personal newsletter has an
# enterprise page, and a company's content team does not act on an unpaid tool
# suggestion the way an individual publisher does.
COMPANY_PATHS = ("/pricing", "/plans", "/signup", "/sign-up", "/login", "/log-in",
                 "/enterprise", "/request-a-demo", "/book-a-demo", "/integrations",
                 "/customers", "/careers", "/start-free-trial", "/free-trial")
MIN_COMPANY_SIGNALS = 3


def _is_company(page_url: str, links: list) -> tuple[bool, str]:
    """Whether the site is a company rather than a publisher.

    Read from the site's own navigation, so it is a fact about the target and
    not a guess about its size. Three of these together is a product company:
    one on its own could be anything.
    """
    from urllib.parse import urljoin, urlsplit

    host = urlsplit(page_url).netloc
    found = set()
    for href, _anchor in links:
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        if urlsplit(absolute).netloc != host:
            continue
        path = urlsplit(absolute).path.rstrip("/").lower()
        for marker in COMPANY_PATHS:
            if path == marker or path.endswith(marker):
                found.add(marker)
    if len(found) >= MIN_COMPANY_SIGNALS:
        return True, ("the site is a product company, not a publisher: its own navigation "
                      f"carries {', '.join(sorted(found)[:4])}. A company content team does "
                      "not act on an unpaid tool suggestion the way an individual "
                      "publisher does")
    return False, ""


def _is_vendor(page_url: str, title: str, text: str) -> tuple[bool, str]:
    """A company selling its own invoicing product is not a creator.

    Reuses the competitor list and the vendor-content detector the backlink
    engine already applies, because the mistake is the same one: an unpaid tool
    suggestion sent to a competitor's content team, or to a large SaaS vendor
    whose blog exists to sell their own product, is a waste of the contact and
    reads as exactly the kind of mail this policy is written to avoid sending.
    """
    from growth_backlink_engine import _is_vendor_content
    from growth_backlink_policy import BLOCKED_DOMAINS, COMPETITORS

    domain = canonical_domain(page_url)
    for blocked in set(COMPETITORS) | set(BLOCKED_DOMAINS):
        if domain == blocked or domain.endswith("." + blocked):
            return True, f"{domain} sells a competing product"
    # A domain named after the thing we make is making it too. The maintained
    # competitor list only holds the ones already known; this catches the rest,
    # which arrive continuously and are the ones most likely to look like a
    # relevant blog while being a product.
    root = domain.split(".")[0].lower()
    if any(word in root for word in ("invoice", "billing", "receipt", "facture")):
        return True, (f"{domain} is named after an invoicing product, so it is a "
                      "competitor rather than a publisher")
    if _is_vendor_content(text, title):
        return True, ("the page reads as vendor content for the site's own product "
                      "rather than as editorial recommendation")
    return False, ""


# ---------------------------------------------------------------------------
# Contact forms as a second verified route
# ---------------------------------------------------------------------------

# Anti-bot controls. Their presence ends the assessment: a form behind one of
# these is a form the site has decided should be filled in by a person, and
# working around that is not something this system does at any volume.
CAPTCHA_MARKERS = ("recaptcha", "g-recaptcha", "hcaptcha", "h-captcha", "cf-turnstile",
                   "turnstile", "friendlycaptcha", "captcha", "arkoselabs", "funcaptcha")

# A form behind a login is not a public contact route.
LOGIN_MARKERS = ("type=\"password\"", "type='password'", "sign in to continue",
                 "log in to continue", "you must be logged in", "members only")

# Forms that exist for a different purpose. Repurposing a complaint, privacy or
# support-ticket form for an unsolicited suggestion is an abuse of it regardless
# of how polite the message is.
WRONG_PURPOSE = re.compile(
    r"\b(privacy request|data (?:subject|deletion) request|gdpr request|ccpa request|"
    r"file a complaint|complaints? (?:form|procedure)|report abuse|report a problem|"
    r"submit a ticket|support ticket|open a case|dmca|legal notice|whistleblow|"
    r"safeguarding|incident report)\b", re.I)

# The route is right when the page says so.
RIGHT_PURPOSE = re.compile(
    r"\b(contact us|get in touch|general enquir|general inquir|editorial|"
    r"pitch (?:us|a story)|submit a (?:tip|resource|tool|story)|write for us|"
    r"partnership|collaborat|work with (?:us|me)|press|media enquir|"
    r"suggest a (?:tool|resource)|advertis)\b", re.I)

# The site telling us not to. Honoured as written.
FORBIDS_CONTACT = re.compile(
    r"\b(no unsolicited|do not send unsolicited|no cold (?:email|outreach|pitch)|"
    r"we do not accept (?:guest|unsolicited|pitches|submissions)|"
    r"unsolicited (?:pitches|submissions|emails) will be|"
    r"not accepting (?:pitches|submissions|guest)|no vendors|no solicitation|"
    r"please do not contact us (?:about|regarding) (?:products|tools|software))\b", re.I)

# A form demanding a personal first and last name cannot be filled truthfully by
# an organization. That is a REVIEW, not a refusal: a person may legitimately
# put their own name in it, and this system may not put anyone's.
PERSONAL_NAME = re.compile(
    r'name="[^"]*(?:first[_-]?name|last[_-]?name|fname|lname|surname)"[^>]*required|'
    r'required[^>]*name="[^"]*(?:first[_-]?name|last[_-]?name|fname|lname|surname)"', re.I)

# The path a contact route actually lives on. Checked against the URL rather
# than the copy, because almost every page carries the words "contact us".
CONTACT_ROUTE_PATH = re.compile(
    r"/(contact|contact-us|get-in-touch|enquir|inquir|pitch|submit|tips?|"
    r"write-for-us|contribute|partnership|partner-with|collaborat|press|media|"
    r"work-with-(us|me)|advertis|suggest)", re.I)

PAYMENT = re.compile(r"\b(submission fee|listing fee|\$\d+ to submit|paid submission|"
                     r"pay to be featured|sponsored listing fee)\b", re.I)


def verify_form(form_url: str) -> dict:
    """Read a contact form's own page and decide whether it is usable.

    Every condition is a fact on that page. Nothing here works around a control
    the site put up: a CAPTCHA or a login ends the assessment, and a form that
    exists for complaints or support tickets is not repurposed. A site that says
    in writing it does not want unsolicited contact is believed.
    """
    from urllib.parse import urlsplit

    from growth_backlink_engine import PageParser, fetch as http_fetch

    checks = {"fetched": False, "has_form": False, "no_captcha": False,
              "no_login": False, "right_purpose": False, "not_wrong_purpose": False,
              "no_payment": False, "not_forbidden": False}
    blockers: list[str] = []
    try:
        status, body = http_fetch(form_url)
    except Exception:
        status, body = 0, ""
    if status != 200 or not body:
        return {"usable": False, "review": False, "checks": checks,
                "blockers": ["the form page could not be read, so nothing about it "
                             "could be verified"]}
    checks["fetched"] = True
    lowered = body.lower()
    page = PageParser()
    page.feed(body)
    text = page.body_text

    checks["has_form"] = "<form" in lowered or "<textarea" in lowered
    if not checks["has_form"]:
        blockers.append("no form on the page it links to")

    hit = next((marker for marker in CAPTCHA_MARKERS if marker in lowered), None)
    checks["no_captcha"] = hit is None
    if hit:
        blockers.append(f"protected by an anti-bot control ({hit}), which is not "
                        "worked around")

    login = next((marker for marker in LOGIN_MARKERS if marker in lowered), None)
    checks["no_login"] = login is None
    if login:
        blockers.append("behind a login, so it is not a public contact route")

    wrong = WRONG_PURPOSE.search(text)
    checks["not_wrong_purpose"] = wrong is None
    if wrong:
        blockers.append(f"exists for a different purpose ({wrong.group(0)}), and "
                        "repurposing it would be an abuse of it")

    # The URL has to be a contact route, not merely a page that says "contact us"
    # somewhere in its footer. An /about page qualified twice before this, and an
    # about page is not an invitation to write.
    path = urlsplit(form_url).path.lower()
    on_a_contact_route = bool(CONTACT_ROUTE_PATH.search(path))
    checks["right_purpose"] = on_a_contact_route and bool(RIGHT_PURPOSE.search(text))
    if not checks["right_purpose"]:
        blockers.append(
            "the URL is not a contact route" if not on_a_contact_route else
            "the page does not identify itself as a general, editorial or business "
            "contact route")

    pay = PAYMENT.search(text)
    checks["no_payment"] = pay is None
    if pay:
        blockers.append(f"asks for payment ({pay.group(0)})")

    forbidden = FORBIDS_CONTACT.search(text)
    checks["not_forbidden"] = forbidden is None
    if forbidden:
        blockers.append(f"the site says in writing: \"{forbidden.group(0)}\"")

    review = bool(PERSONAL_NAME.search(body)) and not blockers
    return {"usable": not blockers and not review, "review": review, "checks": checks,
            "blockers": blockers,
            "review_reason": ("the form requires a personal first or last name, which "
                              "cannot be answered truthfully as an organization"
                              if review else "")}


def _resolve_contact(page_url: str, parser) -> tuple[str | None, str, str | None]:
    """Find a published business email, following the contact link if there is one.

    The backlink engine's extractor stops at the link because a resource page's
    own body usually carries what it needs. A creator's does not: the address
    lives on /contact, one hop away, and stopping short reported 404 of 405
    candidates as unreachable when most of them publish an address perfectly
    plainly. One hop, same host only, and the address must belong to the target's
    own domain -- a Gmail address on a contact page is a personal address that
    was not offered as a business route.
    """
    from urllib.parse import urlsplit

    from growth_backlink_engine import (
        ASSET_EMAIL_RE, EMAIL_RE, PageParser, fetch as http_fetch, find_contact_route,
    )

    contact_url, kind, recipient = find_contact_route(page_url, parser)
    if kind == "email" and recipient:
        return contact_url, kind, recipient
    if kind not in ("form", "editorial_guidelines") or not contact_url:
        return contact_url, kind, recipient
    if urlsplit(contact_url).netloc != urlsplit(page_url).netloc:
        return contact_url, kind, recipient
    try:
        status, body = http_fetch(contact_url)
    except Exception:
        return contact_url, kind, recipient
    if status != 200 or not body:
        return contact_url, kind, recipient
    page = PageParser()
    page.feed(body)
    root = canonical_domain(contact_url).split(".")[0].lower()
    candidates = [
        address.lower() for address in EMAIL_RE.findall(page.body_text)
        if not ASSET_EMAIL_RE.search(address)
        and root in address.split("@")[-1].lower()
    ]
    for href, _ in page.links:
        if href and href.startswith("mailto:"):
            address = href[7:].split("?")[0].strip().lower()
            if EMAIL_RE.fullmatch(address) and root in address.split("@")[-1].lower():
                candidates.append(address)
    if candidates:
        return contact_url, "email", sorted(set(candidates), key=len)[0]
    return contact_url, kind, recipient


def _provider():
    from growth_backlink_engine import provider
    return provider()


def discover(connection: sqlite3.Connection, segments: list[str] | None = None,
             queries_per_segment: int = 2) -> dict:
    """Search, record candidates. No page is fetched here and nobody is contacted."""
    now = utc_now()
    chosen = segments or list(SEGMENTS)
    found, errors = 0, []
    seen_domains = {row["domain"] for row in connection.execute(
        "SELECT DISTINCT domain FROM creator_prospects")}
    for segment in chosen:
        config = SEGMENTS.get(segment)
        if not config:
            errors.append(f"unknown segment {segment!r}")
            continue
        # Rotate through the pool on the count already stored, so repeated runs
        # widen the search instead of re-reading the same first page.
        offset = connection.execute(
            "SELECT COUNT(*) FROM creator_prospects WHERE segment=?", (segment,)
        ).fetchone()[0]
        pool = config["queries"]
        for index in range(queries_per_segment):
            query = pool[(offset // max(1, RESULTS_PER_QUERY) + index) % len(pool)]
            try:
                results = _provider().search(query, RESULTS_PER_QUERY)
            except Exception as error:  # provider failures must not stop the run
                errors.append(f"{segment}: {error}")
                continue
            for result in results:
                url = (result.get("page_url") or "").strip()
                if not url.startswith("http"):
                    continue
                domain = public_domain_or_blank(url)
                if not domain or domain in seen_domains:
                    continue
                if any(domain == host or domain.endswith("." + host) for host in PLATFORM_HOSTS):
                    continue
                if domain.endswith("invoiceworkshop.com"):
                    continue
                seen_domains.add(domain)
                connection.execute(
                    """INSERT INTO creator_prospects
                         (domain, page_url, name, segment, discovered_at,
                          product_angle, target_url, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(page_url) DO NOTHING""",
                    (domain, url, (result.get("title") or "")[:200], segment, now,
                     config["angle"], config["target"], now))
                found += 1
    connection.commit()
    return {"discovered": found, "segments": chosen, "errors": errors,
            "external_side_effects": "read-only search requests"}


def _parse_date(text: str, html: str = "") -> str | None:
    """The most recent plausible publication date on the page."""
    best = None
    today = datetime.now(timezone.utc).date()
    for pattern in (META_DATE, TIME_ATTR):
        for match in pattern.finditer(html):
            try:
                found = datetime.fromisoformat(match.group(1)).date()
            except ValueError:
                continue
            if found > today:
                continue
            if best is None or found > best:
                best = found
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                if len(match.group(1)) == 4:
                    found = datetime(int(match.group(1)), int(match.group(2)),
                                     int(match.group(3))).date()
                else:
                    found = datetime(int(match.group(3)),
                                     MONTHS[match.group(1)[:3].lower()],
                                     int(match.group(2))).date()
            except (ValueError, KeyError):
                continue
            # A date in the future is a template artefact, not a publication.
            if found > today:
                continue
            if best is None or found > best:
                best = found
    return best.isoformat() if best else None


def _audience(text: str) -> tuple[int | None, str]:
    best, evidence = None, ""
    for match in AUDIENCE.finditer(text):
        try:
            value = int(match.group(1).replace(",", "").split(".")[0])
        except ValueError:
            continue
        # Below a thousand it is noise; above ten million it is a misparse.
        if 1_000 <= value <= 10_000_000 and (best is None or value > best):
            best, evidence = value, match.group(0).strip()
    return best, evidence


def _coverage_kind(text: str) -> str:
    sponsored, affiliate = bool(SPONSORED.search(text)), bool(AFFILIATE.search(text))
    if sponsored and affiliate:
        return "mixed"
    if sponsored:
        return "sponsored"
    if affiliate:
        return "affiliate"
    return "editorial"


def fetch(connection: sqlite3.Connection, limit: int = 25) -> dict:
    """Read each candidate's own page and record what it actually says."""
    from growth_backlink_engine import PageParser, fetch as http_fetch

    now = utc_now()
    rows = connection.execute(
        """SELECT id, page_url FROM creator_prospects
            WHERE status='discovered' ORDER BY id LIMIT ?""", (limit,)).fetchall()
    read, failed = 0, 0
    for row in rows:
        try:
            status, body = http_fetch(row["page_url"])
        except Exception:
            status, body = 0, ""
        if status != 200 or not body:
            failed += 1
            connection.execute(
                """UPDATE creator_prospects
                      SET status='rejected', http_status=?, fetched_at=?,
                          rejection_reason=?, updated_at=?
                    WHERE id=?""",
                (status, now,
                 "page could not be read, so nothing about it could be verified",
                 now, row["id"]))
            continue
        parser = PageParser()
        parser.feed(body)
        text = parser.body_text
        vendor, why = _is_vendor(row["page_url"], parser.title, text)
        if not vendor:
            vendor, why = _is_company(row["page_url"], parser.links)
        if vendor:
            connection.execute(
                """UPDATE creator_prospects
                      SET status='rejected', http_status=?, fetched_at=?,
                          rejection_reason=?, updated_at=?
                    WHERE id=?""",
                (status, now, why, now, row["id"]))
            failed += 1
            continue
        contact_url, contact_kind, recipient = _resolve_contact(row["page_url"], parser)
        form_url, form_checks, form_blockers = None, {}, ""
        if contact_kind != "email" and contact_url:
            verdict = verify_form(contact_url)
            form_checks = verdict["checks"]
            if verdict["usable"]:
                form_url = contact_url
            elif verdict["review"]:
                form_blockers = verdict["review_reason"]
            else:
                form_blockers = "; ".join(verdict["blockers"])[:400]
        audience, evidence = _audience(text)
        connection.execute(
            """UPDATE creator_prospects
                  SET status='fetched', http_status=?, fetched_at=?,
                      last_activity_date=?, audience_estimate=?, audience_evidence=?,
                      recommends_tools=?, coverage_kind=?, contact_url=?,
                      contact_kind=?, recipient=?, contact_verified_at=?,
                      contact_form_url=?, form_verified_at=?, form_checks_json=?,
                      form_blockers=?, updated_at=?
                WHERE id=?""",
            (status, now, _parse_date(text, body), audience, evidence,
             1 if RECOMMENDS.search(text) else 0, _coverage_kind(text),
             contact_url, contact_kind, recipient,
             now if recipient else None,
             form_url, now if form_checks else None,
             json.dumps(form_checks, sort_keys=True), form_blockers,
             now, row["id"]))
        read += 1
    connection.commit()
    return {"read": read, "unreadable": failed,
            "external_side_effects": "read-only GET of each candidate's own page"}


def qualify(connection: sqlite3.Connection) -> dict:
    """Admit or reject on the page's own evidence. Never on how badly we need it."""
    now = utc_now()
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=MAX_ACTIVITY_AGE_DAYS)).isoformat()
    qualified, rejected = 0, []
    for row in connection.execute(
            "SELECT * FROM creator_prospects WHERE status='fetched'").fetchall():
        reasons = []
        if not row["last_activity_date"]:
            reasons.append("no publication date found, so recent activity is unverified")
        elif row["last_activity_date"] < cutoff:
            reasons.append(f"last published {row['last_activity_date']}, over "
                           f"{MAX_ACTIVITY_AGE_DAYS} days ago")
        if not row["recommends_tools"]:
            reasons.append("no evidence they ever recommend a tool; an unpaid suggestion "
                           "would be an interruption rather than something useful")
        if row["coverage_kind"] == "sponsored":
            reasons.append("coverage appears paid-only, so an unpaid editorial suggestion "
                           "is not something they act on")
        if GENERIC_INFLUENCER.search(f"{row['name']} {row['notes']}"):
            reasons.append("reads as a general business-audience account rather than a "
                           "specific audience with a paperwork problem")
        # Two routes, both verified. Qualifying a target neither route can reach
        # would build a backlog the policy can never admit, which is a list that
        # looks like progress and is not.
        route = "email" if (row["contact_kind"] == "email" and row["recipient"]) else (
            "form" if row["form_checks_json"] and row["form_checks_json"] != "{}"
            and not row["form_blockers"] and row["contact_form_url"] else "none")
        if route == "none":
            if row["form_blockers"]:
                reasons.append(f"contact form unusable: {row['form_blockers']}")
            else:
                reasons.append(
                    "no verified contact route: no business email published on their own "
                    "site, and no public editorial or general contact form that could be "
                    "checked")
        if not row["product_angle"] or not row["target_url"]:
            reasons.append("no specific product angle recorded")

        if reasons:
            connection.execute(
                """UPDATE creator_prospects SET status='rejected', rejection_reason=?,
                       updated_at=? WHERE id=?""",
                ("; ".join(reasons), now, row["id"]))
            rejected.append({"domain": row["domain"], "reason": reasons[0]})
            continue
        connection.execute(
            """UPDATE creator_prospects SET status='qualified', fit_score=?,
                   contact_route=?, updated_at=? WHERE id=?""",
            (fit_score(row), route, now, row["id"]))
        qualified += 1
    connection.commit()
    return {"qualified": qualified, "rejected": len(rejected),
            "rejection_sample": rejected[:8]}


def fit_score(row: sqlite3.Row) -> float:
    """Relevance first, reach second, and a reachable contact route above both.

    Reach is deliberately compressed: ten times the audience is not ten times the
    value when the fit is the same, and letting it dominate would rebuild exactly
    the "big following" ranking this module refuses.
    """
    import math
    audience = int(row["audience_estimate"] or 0)
    reach = math.log10(audience) if audience >= 1_000 else 1.0
    recency = 1.0
    if row["last_activity_date"]:
        age = (datetime.now(timezone.utc).date()
               - datetime.fromisoformat(row["last_activity_date"]).date()).days
        recency = 1.0 if age <= 60 else 0.8 if age <= 150 else 0.6
    # An address reaches a person; a form reaches an inbox somebody may triage.
    # Both are real routes, and the difference is smaller than the difference
    # between a good fit and a bad one, so the gap here is deliberately narrow.
    contact = 1.0 if (row["contact_kind"] == "email" and row["recipient"]) else 0.8
    coverage = {"editorial": 1.0, "mixed": 0.8, "affiliate": 0.7,
                "sponsored": 0.3, "unknown": 0.6}[row["coverage_kind"]]
    return round(reach * recency * contact * coverage * (1.2 if row["recommends_tools"] else 0.5), 3)


def backlog(connection: sqlite3.Connection, limit: int = 50) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT id, domain, name, segment, fit_score, audience_estimate,
                  last_activity_date, contact_route, recipient, contact_form_url,
                  coverage_kind, target_url, status
             FROM creator_prospects WHERE status='qualified'
            ORDER BY fit_score DESC, id LIMIT ?""", (limit,))]


def report(connection: sqlite3.Connection) -> dict:
    counts = {row["status"]: row["n"] for row in connection.execute(
        "SELECT status, COUNT(*) n FROM creator_prospects GROUP BY status")}
    by_segment = [dict(row) for row in connection.execute(
        """SELECT segment, COUNT(*) total,
                  SUM(CASE WHEN status='qualified' THEN 1 ELSE 0 END) qualified
             FROM creator_prospects GROUP BY segment ORDER BY segment""")]
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "by_route": {row["contact_route"]: row["n"] for row in connection.execute(
            """SELECT contact_route, COUNT(*) n FROM creator_prospects
                WHERE status='qualified' GROUP BY contact_route""")},
        "by_segment": by_segment,
        "backlog": backlog(connection, 25),
        "top_rejections": [dict(row) for row in connection.execute(
            """SELECT substr(rejection_reason, 1, 90) reason, COUNT(*) n
                 FROM creator_prospects WHERE status='rejected'
                GROUP BY reason ORDER BY n DESC LIMIT 6""")],
        "sending": ("blocked: creator outreach requires its own signed policy, which is "
                    "separate from the resource-page policy and is not active"),
    }


def cycle(connection: sqlite3.Connection, *, queries_per_segment: int = 2,
          fetch_limit: int = 25) -> dict:
    found = discover(connection, queries_per_segment=queries_per_segment)
    read = fetch(connection, limit=fetch_limit)
    judged = qualify(connection)
    return {"discover": found, "fetch": read, "qualify": judged,
            "backlog_size": len(backlog(connection, 500))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("discover", help="Search for candidates")
    find.add_argument("--segments", nargs="*")
    find.add_argument("--queries-per-segment", type=int, default=2)
    read = commands.add_parser("fetch", help="Read each candidate's own page")
    read.add_argument("--limit", type=int, default=25)
    commands.add_parser("qualify", help="Admit or reject on recorded evidence")
    run = commands.add_parser("cycle", help="Discover, fetch and qualify in order")
    run.add_argument("--queries-per-segment", type=int, default=2)
    run.add_argument("--fetch-limit", type=int, default=25)
    show = commands.add_parser("backlog", help="Qualified prospects, best fit first")
    show.add_argument("--limit", type=int, default=50)
    commands.add_parser("report", help="Counts, backlog and why candidates were rejected")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "discover":
        result = discover(connection, args.segments, args.queries_per_segment)
    elif args.command == "fetch":
        result = fetch(connection, args.limit)
    elif args.command == "qualify":
        result = qualify(connection)
    elif args.command == "cycle":
        result = cycle(connection, queries_per_segment=args.queries_per_segment,
                       fetch_limit=args.fetch_limit)
    elif args.command == "backlog":
        result = {"backlog": backlog(connection, args.limit)}
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
