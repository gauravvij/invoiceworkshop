#!/usr/bin/env python3
"""Non-search distribution: the second growth engine.

The scoreboard established a fact the search engine cannot argue with: from a
zero organic baseline, 300,000-700,000 monthly pageviews in ninety days needs
110% weekly compounding, which search does not deliver on that timetable. This
module exists to find traffic that does not wait for rankings to mature.

It is not a link-building machine. Three rules do most of the work:

  1. A destination is admitted on evidence about the destination, recorded with
     the date it was checked and the page it was checked on. Directory farms,
     pay-for-followed-link schemes and abandoned sites are refused by the gate,
     not by judgement at submission time.

  2. Execution class is derived from what the destination DEMANDS, never from
     how much we want the link. An account, a payment, a personal maker
     identity or community participation each force REVIEW on its own. There is
     no path from "the target is behind" to an AUTO submission, and no path at
     all to inventing a founder persona: that is BLOCKED, permanently, and the
     refusal is part of the record rather than a policy note somewhere else.

  3. Outcomes are sessions, tool starts and downloads. A submission count is not
     an outcome. A channel that sends a thousand people who leave immediately
     scores below one that sends a hundred who make a document.

What this module can do unattended is prepare. For every owner-required
destination it assembles the complete submission -- copy, positioning, asset
list, tracked URL, the exact fields the form asks for -- so the owner action is
minutes of review rather than an evening of writing.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date

from growth_common import apply_schema, connect_db, database_path, record_escalation, utc_now

SITE = "https://invoiceworkshop.com"
VERIFIED_ON = "2026-09-03"

# The channels this engine feeds, matching the weekly allocator's portfolio.
CHANNELS = ("launch_platforms", "directories", "creator_newsletter",
            "social_community", "product_loops", "linkable_assets")

# Reasons a destination is refused outright. Each is a property of the
# destination, checkable before anything is sent.
FARM_SIGNALS = ("pay_for_followed_link", "no_editorial_review", "abandoned",
                "spun_network", "link_exchange_required", "audience_is_submitters")


class DestinationRefusal(Exception):
    """The destination does not earn a submission. Recorded, not worked around."""


# ---------------------------------------------------------------------------
# The catalogue. Everything here was checked on VERIFIED_ON at `source_url`.
# Anything that could not be checked says so rather than being asserted.
# ---------------------------------------------------------------------------

def _d(**kwargs) -> dict:
    base = {
        "submit_url": "", "evidence": "", "source_url": "", "farm_signals": [],
        "requires_account": True, "requires_payment": False,
        "requires_personal_identity": False, "requires_community_posting": False,
        "reach": 0, "intent": 0.5, "speed_days": 30, "confidence": 0.5, "effort": 1.0,
        "verified_on": VERIFIED_ON,
    }
    base.update(kwargs)
    return base


DESTINATIONS = [
    # ---- launch platforms -------------------------------------------------
    _d(key="ph-launch", channel="launch_platforms", name="Product Hunt",
       url="https://www.producthunt.com/",
       submit_url="https://www.producthunt.com/posts/new",
       audience_fit="Makers, indie founders and small-business operators looking for "
                    "free tools. InvoiceWorkshop is a free, no-signup, browser-only "
                    "document workspace, which is the shape of product this audience "
                    "shares. Fit is real but not perfect: the audience skews technical "
                    "rather than to the tradespeople the construction pages serve.",
       evidence="Checked 3 September 2026. Submission is free and featuring is free. "
                "ELIGIBILITY: the personal account must be at least ONE WEEK old, and "
                "joining earlier is recommended. An earlier version of this record said "
                "30 days; that figure came from a third-party launch guide rather than "
                "from Product Hunt, and it was wrong. A personal account is required to "
                "post, and a hunter is explicitly unnecessary -- posting yourself gives "
                "full control. Product Hunt removes products whose makers spam their "
                "audience or pay for upvotes, and paying anyone to hunt or send traffic "
                "can get an account permanently banned. Assets: 240x240 thumbnail, "
                "tagline, description (260 characters), topics, pricing tag, and "
                "optional gallery images or video. Posts go live at 12:01am PST.",
       source_url="https://help.producthunt.com/en/articles/479557-how-to-post-a-product",
       requires_account=True, requires_personal_identity=True,
       reach=2000, intent=0.55, speed_days=1, confidence=0.55, effort=3.0),

    _d(key="uneed", channel="launch_platforms", name="Uneed",
       url="https://www.uneed.best/", submit_url="https://www.uneed.best/submit-a-tool",
       audience_fit="Tool-discovery audience with a newsletter. Smaller than Product "
                    "Hunt and less technical, which suits a business utility.",
       evidence="Checked 3 September 2026 on the submit page: submission starts without "
                "an account -- it scrapes the page from the product name and URL -- but "
                "sign-up is required to save the listing. Free, with paid fast-track and "
                "queue-skip options we are not using.",
       source_url="https://www.uneed.best/submit-a-tool",
       requires_account=True, reach=300, intent=0.6, speed_days=14,
       confidence=0.45, effort=1.0),

    _d(key="betalist", channel="launch_platforms", name="BetaList",
       url="https://betalist.com/",
       audience_fit="Early-adopter audience for pre-launch and newly launched startups. "
                    "InvoiceWorkshop has been live for some time, so the fit is weaker "
                    "than for a genuine pre-launch product.",
       evidence="Not independently verified on 3 September 2026: the platform is widely "
                "cited as pre-launch-oriented, and its current submission terms were not "
                "read directly. Recorded as unverified rather than asserted.",
       source_url="", requires_account=True, reach=150, intent=0.35,
       speed_days=21, confidence=0.2, effort=1.0),

    # ---- directories ------------------------------------------------------
    _d(key="alternativeto", channel="directories", name="AlternativeTo",
       url="https://alternativeto.net/",
       audience_fit="People searching for an alternative to a paid invoicing product. "
                    "That is the highest-intent non-search surface available to us: the "
                    "visitor is already looking for exactly what this is.",
       evidence="Checked 3 September 2026. Free submission; a profile with description "
                "and screenshots is required, and the new-app URL 404s without a signed-in "
                "session, so an account is needed.",
       source_url="https://alternativeto.net/",
       requires_account=True, reach=400, intent=0.85, speed_days=21,
       confidence=0.6, effort=1.0),

    _d(key="saashub", channel="directories", name="SaaSHub",
       url="https://www.saashub.com/",
       submit_url="https://www.saashub.com/services/submit",
       audience_fit="Comparison-shopping audience, same intent shape as AlternativeTo.",
       evidence="Checked 3 September 2026 on the submit page: free, but the product must "
                "be verified from a domain email address for the submission to be "
                "prioritised, and all submissions go through approval. Requires the URL, "
                "categories and a competitor list.",
       source_url="https://www.saashub.com/services/submit",
       requires_account=True, reach=250, intent=0.8, speed_days=30,
       confidence=0.5, effort=1.0),

    _d(key="launching-next", channel="directories", name="Launching Next",
       url="https://www.launchingnext.com/",
       audience_fit="Permanent directory listing for new products.",
       evidence="Could not be verified on 3 September 2026: the submit page returned "
                "HTTP 403 to an automated fetch. Terms and account requirements unknown, "
                "so it is not admitted until a human or a later fetch confirms them.",
       source_url="https://www.launchingnext.com/submit/",
       requires_account=True, reach=80, intent=0.3, speed_days=30,
       confidence=0.15, effort=0.5),

    _d(key="generic-saas-listicle-farm", channel="directories",
       name="\"260+ SaaS directories\" submission lists",
       url="https://example-directory-farm.invalid/",
       audience_fit="None. The audience of these sites is other people submitting to "
                    "directories, not anyone who needs an invoice.",
       evidence="Checked 3 September 2026. The bulk submission lists that dominate this "
                "SERP are themselves lead magnets for paid submission services. Listed "
                "here so the refusal is recorded rather than left implicit.",
       source_url="https://www.position.digital/blog/saas-directories/",
       farm_signals=["audience_is_submitters", "pay_for_followed_link"],
       reach=0, intent=0.0, speed_days=1, confidence=0.9, effort=0.5),

    # ---- creator / newsletter --------------------------------------------
    _d(key="bookkeeping-creators", channel="creator_newsletter",
       name="Bookkeeping and small-business finance creators",
       url="https://invoiceworkshop.com/",
       audience_fit="Creators teaching bookkeeping to freelancers and trades have "
                    "exactly the audience that needs a free invoice, receipt and credit "
                    "note workspace, and a free no-signup tool is something they can "
                    "recommend without a conflict.",
       evidence="Pipeline, not a single destination: candidates are researched and "
                "scored by the existing prospect engine. The pitch is a demonstration of "
                "a specific workflow -- invoice to receipt to credit note, or a "
                "construction progress bill -- not a request for a mention.",
       source_url="", requires_account=False, requires_personal_identity=False,
       reach=1500, intent=0.75, speed_days=21, confidence=0.35, effort=2.0),

    _d(key="freelancer-newsletters", channel="creator_newsletter",
       name="Freelancer and solo-business newsletters",
       url="https://invoiceworkshop.com/",
       audience_fit="A newsletter feature puts a free tool in front of a whole list at "
                    "once, which is one of the few genuinely non-linear surfaces "
                    "available without payment.",
       evidence="Pipeline. Sponsorship is explicitly out of scope: an unpaid editorial "
                "mention is Level-1A outreach and follows the existing approval gate; "
                "anything paid is REVIEW and no money is spent unattended.",
       source_url="", requires_account=False,
       reach=2000, intent=0.7, speed_days=21, confidence=0.3, effort=2.0),

    # ---- social / community ----------------------------------------------
    _d(key="reddit-smallbusiness", channel="social_community",
       name="r/smallbusiness and adjacent subreddits",
       url="https://www.reddit.com/r/smallbusiness/",
       audience_fit="The audience is right and the questions asked there are literally "
                    "the ones the tool answers.",
       evidence="Checked 3 September 2026. r/smallbusiness removes product mentions from "
                "posts and comments where they read as promotional, direct or indirect, "
                "and confines promotion to a weekly thread. Across surveyed founder "
                "subreddits a majority ban self-promotion outright. Posting here needs a "
                "real person with real standing in the community, which is not something "
                "an unattended system can or should manufacture.",
       source_url="https://www.reddit.com/r/smallbusiness/about/rules/",
       requires_account=True, requires_personal_identity=True,
       requires_community_posting=True,
       reach=800, intent=0.7, speed_days=3, confidence=0.25, effort=2.0),

    _d(key="youtube-invoice-howto", channel="social_community",
       name="YouTube how-to search surface",
       url="https://www.youtube.com/",
       audience_fit="'How to make an invoice' style queries have durable video demand "
                    "and the tool demonstrates well on screen.",
       evidence="Requires a channel, a real presenter and sustained publishing. Recorded "
                "so it is not repeatedly rediscovered, but it is an owner decision about "
                "how they want to spend their own time, not a system action.",
       source_url="", requires_account=True, requires_personal_identity=True,
       reach=1000, intent=0.6, speed_days=60, confidence=0.2, effort=4.0),

    # ---- linkable assets (built here, not submitted anywhere) -------------
    _d(key="asset-progress-draw", channel="linkable_assets",
       name="Construction progress-draw and retainage schedule",
       url=f"{SITE}/progress-draw-schedule/",
       audience_fit="Contractors billing in draws against a schedule of values, with "
                    "retainage withheld per draw. The arithmetic is genuinely painful, "
                    "genuinely searched, and genuinely got wrong.",
       evidence="Ties directly to the construction and contractor page cluster that "
                "already exists, so it is a product extension rather than a widget built "
                "to attract links. Construction-accounting and trade sites reference "
                "calculators of this kind because their readers ask for them.",
       source_url="", requires_account=False,
       reach=600, intent=0.8, speed_days=45, confidence=0.45, effort=3.0),

    _d(key="asset-payment-terms", channel="linkable_assets",
       name="Payment terms and due-date calculator",
       url=f"{SITE}/payment-terms-calculator/",
       audience_fit="Net 30, net 45, EOM, 2/10 net 30 -- the terms are a small set and "
                    "the due dates are consistently miscalculated.",
       evidence="Small build on arithmetic the invoice tool already does. Lower ceiling "
                "than the draw schedule because the answer is easy enough to reason out.",
       source_url="", requires_account=False,
       reach=200, intent=0.6, speed_days=45, confidence=0.4, effort=1.0),

    # ---- product loops ----------------------------------------------------
    _d(key="loop-share-tool", channel="product_loops",
       name="Share-this-tool link after a download",
       url=SITE,
       audience_fit="Someone who has just produced a document they needed is the one "
                    "moment they might pass the tool on. Nothing is attached to the "
                    "document itself.",
       evidence="No watermark, no backend, no document data leaves the browser: a plain "
                "tracked link to the tool page, offered after a successful download. "
                "Anything involving shared or stored documents is a backend and is "
                "REVIEW.",
       source_url="", requires_account=False,
       reach=100, intent=0.5, speed_days=30, confidence=0.3, effort=1.0),
]


# ---------------------------------------------------------------------------
# The gate and the execution class
# ---------------------------------------------------------------------------

def check(destination: dict) -> dict:
    """Admit or refuse, on properties of the destination alone."""
    signals = [s for s in destination.get("farm_signals", []) if s in FARM_SIGNALS]
    unknown = [s for s in destination.get("farm_signals", []) if s not in FARM_SIGNALS]
    if unknown:
        raise DestinationRefusal(f"unrecognised farm signal(s): {', '.join(unknown)}")
    if signals:
        raise DestinationRefusal(
            "refused on destination quality: " + ", ".join(signals) + ". A link from a "
            "site whose audience is other submitters is worth less than nothing, and "
            "paying for a followed link is outside what this system will do at any "
            "distance from the target.")
    if not destination.get("audience_fit"):
        raise DestinationRefusal("no audience fit recorded")
    if not destination.get("evidence"):
        raise DestinationRefusal("nothing recorded about what was actually checked")
    if destination.get("channel") not in CHANNELS:
        raise DestinationRefusal(f"unknown channel {destination.get('channel')!r}")
    if float(destination.get("confidence", 0)) < 0.2:
        raise DestinationRefusal(
            "the destination's own terms could not be verified, so a submission would be "
            "made blind. Verify the current terms first.")
    return {"admitted": True}


def execution_class(destination: dict) -> tuple[str, str]:
    """What the destination demands decides this, never how badly we want it.

    Returned as (class, reason). The reason is shown to the owner, so it says
    which requirement forced the classification rather than just naming it.
    """
    if destination.get("requires_payment"):
        return "REVIEW", ("costs money, and this system does not spend money "
                          "unattended under any circumstances")
    if destination.get("requires_personal_identity"):
        return "REVIEW", ("needs a real person -- a maker profile, a presenter, a "
                          "community identity. Creating one would be inventing a founder, "
                          "which is never done. Everything except the human part is "
                          "prepared here")
    if destination.get("requires_community_posting"):
        return "REVIEW", ("needs standing in a community, which is earned by a person "
                          "over time and cannot be manufactured")
    if destination.get("requires_account"):
        return "REVIEW", ("needs an external account, which is outside the unattended "
                          "permission set. The submission itself is written and ready")
    if destination.get("channel") == "creator_newsletter":
        return "AUTO", ("research and staging run unattended; every message still passes "
                        "the existing Level-1A approval gate, which this engine does not "
                        "touch and cannot widen")
    return "AUTO", "no account, no payment, no identity and no posting required"


def score(destination: dict) -> float:
    """Reach x intent x confidence x speed, over effort.

    Speed is in the numerator deliberately: the question this engine exists to
    answer is which channel can move in days, and a destination that pays out in
    ninety days is worth less than one that pays out in one, at equal size.
    """
    speed = 1.0 / max(1, int(destination.get("speed_days", 90))) ** 0.5
    return round(
        int(destination.get("reach", 0))
        * float(destination.get("intent", 0))
        * float(destination.get("confidence", 0))
        * speed
        / max(0.25, float(destination.get("effort", 1))),
        2)


def evaluate(connection: sqlite3.Connection) -> dict:
    now = utc_now()
    admitted, refused = [], []
    for destination in DESTINATIONS:
        try:
            check(destination)
            gate_status, reason = "admitted", None
            klass, why = execution_class(destination)
            value = score(destination)
            admitted.append({"key": destination["key"], "class": klass, "score": value})
        except DestinationRefusal as refusal:
            gate_status, reason = "refused", str(refusal)
            klass, why, value = "BLOCKED", str(refusal), 0.0
            refused.append({"key": destination["key"], "reason": reason})
        connection.execute(
            """INSERT INTO breakout_destinations
                 (key, channel, name, url, submit_url, audience_fit, evidence,
                  verified_on, source_url, requires_account, requires_payment,
                  requires_personal_identity, requires_community_posting, reach, intent,
                  speed_days, confidence, effort, score, gate_status, refusal_reason,
                  execution_class, execution_reason, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 audience_fit=excluded.audience_fit, evidence=excluded.evidence,
                 verified_on=excluded.verified_on, source_url=excluded.source_url,
                 requires_account=excluded.requires_account,
                 requires_payment=excluded.requires_payment,
                 requires_personal_identity=excluded.requires_personal_identity,
                 requires_community_posting=excluded.requires_community_posting,
                 reach=excluded.reach, intent=excluded.intent,
                 speed_days=excluded.speed_days, confidence=excluded.confidence,
                 effort=excluded.effort, score=excluded.score,
                 gate_status=excluded.gate_status, refusal_reason=excluded.refusal_reason,
                 execution_class=excluded.execution_class,
                 execution_reason=excluded.execution_reason,
                 updated_at=excluded.updated_at""",
            (destination["key"], destination["channel"], destination["name"],
             destination["url"], destination["submit_url"], destination["audience_fit"],
             destination["evidence"], destination["verified_on"], destination["source_url"],
             int(destination["requires_account"]), int(destination["requires_payment"]),
             int(destination["requires_personal_identity"]),
             int(destination["requires_community_posting"]),
             destination["reach"], destination["intent"], destination["speed_days"],
             destination["confidence"], destination["effort"], value,
             gate_status, reason, klass, why, now, now))
    connection.commit()
    return {
        "admitted": sorted(admitted, key=lambda row: -row["score"]),
        "refused": refused,
        "auto_executable": [row["key"] for row in admitted if row["class"] == "AUTO"],
        "note": ("Execution class comes from what the destination demands. Being behind "
                 "target cannot move a destination from REVIEW to AUTO, and no persona "
                 "is ever created to satisfy an identity requirement."),
    }


# ---------------------------------------------------------------------------
# Preparation: everything a human would otherwise have to write
# ---------------------------------------------------------------------------

TAGLINE = "The free no-signup paperwork workspace for a small business."

# What the site actually offers, read from the live routes rather than written
# out here. A launch that describes the product as it was three families ago is
# worse than no launch, and this is the part that goes stale first.
TOOL_NAMES = {
    "/": "invoices",
    "/quotation-generator/": "quotations",
    "/estimate-generator/": "estimates",
    "/work-order-generator/": "work orders",
    "/purchase-order-generator/": "purchase orders",
    "/proforma-invoice-generator/": "proforma invoices",
    "/receipt-generator/": "receipts",
    "/credit-note-generator/": "credit notes",
    "/timesheet-invoice-generator/": "timesheet invoices",
    "/delivery-note-template/": "delivery notes",
    "/progress-draw-schedule/": "construction progress draws with retainage",
}


def live_tools() -> list[str]:
    """The document types currently shipped, in the order they are listed."""
    from growth_opportunities import CANONICAL
    routes = {url.replace("https://invoiceworkshop.com", "") or "/" for url in CANONICAL}
    return [name for path, name in TOOL_NAMES.items() if path in routes]


def _tool_sentence() -> str:
    tools = live_tools()
    if not tools:
        return "business documents"
    return ", ".join(tools[:-1]) + f" and {tools[-1]}" if len(tools) > 1 else tools[0]


def positioning() -> str:
    return (
        "InvoiceWorkshop is a free business-paperwork workspace that runs entirely in "
        f"the browser: {_tool_sentence()}. Saved customers and line items, live totals, "
        "per-line tax, conversion between documents, and instant PDF download. No "
        "account, no upload, no watermark -- the documents never leave the device they "
        "are made on."
    )


def description() -> str:
    return (
        "Most free invoice tools want an email address before they will show you a "
        "document, watermark the PDF, or keep your customer list on someone else's "
        "server. InvoiceWorkshop does none of those. Open it, fill it in, download the "
        "PDF.\n\n"
        "It stopped being an invoice generator some time ago. It now covers the "
        f"paperwork a small business actually cycles through -- {_tool_sentence()} -- "
        "and moves between them: quote a job, turn the quotation into an invoice, "
        "receipt the payment when it lands, credit it if something comes back. Your "
        "business details, customers and common items are remembered on the device, so "
        "the second document takes seconds.\n\n"
        "The details are the point. Tax is computed per line and rounded there, the way "
        "an accountant checks it. A delivery note carries no prices, because it is read "
        "by whoever signs for the goods. A timesheet totals the hours as well as the "
        "money, and the two reconcile. The construction draw schedule sums retainage "
        "from the column rather than taking it on the total. There are country presets "
        "for UK VAT, India GST, Australian tax invoices and Canadian GST/HST, each "
        "checked against the tax authority's own guidance rather than a competitor's "
        "blog -- which turned up three things we had wrong.\n\n"
        "Free, no signup, no upload, no watermark."
    )

ASSET_LIST = (
    "240x240 icon (site mark on the brand ground)",
    "Gallery 1: the invoice editor with a filled document and live preview",
    "Gallery 2: the finished PDF beside the editor",
    "Gallery 3: invoice converting to a receipt, showing the PAID mark",
    "Gallery 4: the UK VAT preset, showing the VAT number field and rate options",
    "Gallery 5: mobile width, editor and preview toggle",
    "Optional 45-second screen recording: quote -> invoice -> receipt, no narration",
)

def maker_comment() -> str:
    return (
        "I built this because every free invoice generator I tried wanted an email "
        "address before it would show me a document, and half of them watermarked the "
        "PDF. This one runs entirely in your browser -- your business details, "
        "customers and documents are saved on your device and never uploaded, which is "
        "also why there is no account.\n\n"
        f"It has grown well past invoices: {_tool_sentence()}, with conversion between "
        "them so you are not retyping. The parts I am most pleased with are the "
        "unglamorous ones -- the delivery note has no prices on it because it gets read "
        "in a loading bay, the timesheet's hours total reconciles with its money total, "
        "and the construction draw schedule sums retainage down the column instead of "
        "taking it off the total, which is the difference a reviewer actually finds.\n\n"
        "The country presets were checked against the tax authorities' own guidance "
        "rather than secondary sources. That turned up three things I had wrong, which "
        "is its own argument for reading the primary source.\n\n"
        "Happy to answer anything about how the local-only storage works."
    )


# The one launch with a date. Recorded here rather than left in a plan, so the
# eligibility rule and the target date are checkable and the bundle can refuse
# to say "ready" before the account is old enough.
PRODUCT_HUNT_LAUNCH = {
    "key": "ph-2026-09-15",
    "destination": "Product Hunt",
    "utm_source": "producthunt",
    "planned_for": "2026-09-15",       # a Tuesday
    "alternatives": ["2026-09-16", "2026-09-17"],
    "account_min_age_days": 7,
    "go_live": "12:01am PST",
}

# What the launch is judged on. Upvotes are deliberately absent: they are the
# thing a launch optimises for when nobody is measuring whether anyone stayed.
LAUNCH_METRICS = (
    "landing_sessions", "tool_starts", "pdf_downloads", "pageviews_per_session",
    "returning_or_direct_after_launch", "referring_domains_gained",
    "branded_search_impressions",
)


def launch_plan(connection: sqlite3.Connection, *, account_created_on: str | None = None) -> dict:
    """Record the launch, and say plainly whether the date is actually reachable.

    `account_created_on` is the only input the system cannot observe: the owner
    holds the Product Hunt account. Without it the launch is recorded as blocked
    on an unverified eligibility date rather than assumed ready.
    """
    from datetime import date, timedelta
    now = utc_now()
    plan = dict(PRODUCT_HUNT_LAUNCH)
    target = date.fromisoformat(plan["planned_for"])
    if account_created_on:
        eligible_on = (date.fromisoformat(account_created_on)
                       + timedelta(days=plan["account_min_age_days"]))
        ready = eligible_on <= target
        eligibility = (f"account created {account_created_on}, eligible from "
                       f"{eligible_on.isoformat()}: "
                       + ("clear for the target date" if ready else
                          f"NOT eligible on {plan['planned_for']}; earliest is "
                          f"{eligible_on.isoformat()}"))
        status, blocking = ("planned", "") if ready else (
            "blocked", f"account is not one week old until {eligible_on.isoformat()}")
    else:
        eligibility = ("account creation date not recorded, so eligibility cannot be "
                       "verified. Product Hunt requires the personal account to be at "
                       "least one week old.")
        status, blocking = "blocked", "owner has not recorded the account creation date"
    connection.execute(
        """INSERT INTO launch_events
             (key, destination, utm_source, planned_for, status, eligibility,
              blocking_note, metrics_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             planned_for=excluded.planned_for, status=excluded.status,
             eligibility=excluded.eligibility, blocking_note=excluded.blocking_note,
             updated_at=excluded.updated_at""",
        (plan["key"], plan["destination"], plan["utm_source"], plan["planned_for"],
         status, eligibility, blocking, json.dumps({"tracked": list(LAUNCH_METRICS)}),
         now, now))
    connection.commit()
    return {**plan, "status": status, "eligibility": eligibility,
            "blocking_note": blocking,
            "tracked_urls": {
                "home": tracked_url("/", plan["utm_source"]),
                "receipt": tracked_url("/receipt-generator/", plan["utm_source"]),
                "credit_note": tracked_url("/credit-note-generator/", plan["utm_source"]),
                "progress_draw": tracked_url("/progress-draw-schedule/", plan["utm_source"]),
            },
            "judged_on": list(LAUNCH_METRICS),
            "not_judged_on": "upvotes, which measure a morning rather than a product"}


def launch_results(connection: sqlite3.Connection, key: str = PRODUCT_HUNT_LAUNCH["key"]) -> dict:
    """What the launch actually sent, from analytics rather than from the platform.

    Attribution is by utm_source on our own domain: the sessions are ours to
    measure, and a platform's own dashboard measures its page, not our product.
    """
    row = connection.execute("SELECT * FROM launch_events WHERE key=?", (key,)).fetchone()
    if row is None:
        return {"error": f"no launch event {key!r}"}
    since = row["launched_at"] or row["planned_for"] or "1970-01-01"
    totals = connection.execute(
        """SELECT COALESCE(SUM(sessions), 0) sessions,
                  COALESCE(SUM(pageviews), 0) pageviews,
                  COALESCE(SUM(tool_starts), 0) tool_starts,
                  COALESCE(SUM(pdf_downloads), 0) pdf_downloads
             FROM ga4_acquisition
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ga4_acquisition)
              AND date >= ?
              AND (lower(source) LIKE ? OR lower(source_medium) LIKE ?)""",
        (since[:10], f"%{row['utm_source']}%", f"%{row['utm_source']}%")).fetchone()
    sessions = int(totals["sessions"] or 0)
    return {
        "launch": key, "status": row["status"], "utm_source": row["utm_source"],
        "landing_sessions": sessions,
        "pageviews": int(totals["pageviews"] or 0),
        "tool_starts": int(totals["tool_starts"] or 0),
        "pdf_downloads": int(totals["pdf_downloads"] or 0),
        "pageviews_per_session": round(int(totals["pageviews"] or 0) / sessions, 2) if sessions else 0,
        "completion_rate": round(int(totals["pdf_downloads"] or 0) / sessions, 3) if sessions else 0,
        "note": ("judged on useful users and downstream distribution, not on upvotes. "
                 "A launch that sends a thousand people who never make a document has "
                 "produced a good morning and nothing else."),
    }


def tracked_url(path: str, destination_key: str) -> str:
    """One tracked URL per destination, so a referral can be attributed.

    Plain UTM parameters on our own domain: nothing is set on the visitor and
    nothing is shared with the destination beyond the click itself.
    """
    source = destination_key.replace("_", "-")
    return (f"{SITE}{path}?utm_source={source}&utm_medium=referral"
            f"&utm_campaign=breakout-2026q4")


def bundle_for(destination: dict) -> dict:
    """The complete submission, written so the owner reviews rather than writes."""
    key = destination["key"]
    common = {
        "destination": destination["name"],
        "submit_url": destination["submit_url"] or destination["url"],
        "tracked_url": tracked_url("/", key),
        "tagline": TAGLINE,
        "positioning": positioning(),
        "description": description(),
        "live_tools": live_tools(),
        "assets_needed": list(ASSET_LIST),
        "requirements_verified_on": destination["verified_on"],
        "what_the_owner_must_do": destination.get("owner_action", ""),
        "what_is_already_done": "copy, positioning, tagline, description, asset list, "
                                "tracked URL and category choices",
    }
    if key == "ph-launch":
        common.update({
            "maker_comment": maker_comment(),
            "topics": ["Productivity", "SaaS", "Finance", "Small Business"],
            "positioning_note":
                "Presented as a paperwork workspace, not as another invoice generator. "
                "The tool list is read from the live routes when the bundle is written, "
                "so it does not go stale between now and launch day; re-run `prepare` "
                "before launching and re-read this.",
            "launch_day_advice": "Tuesday to Thursday, live at 12:01am PST",
            "what_the_owner_must_do":
                "Sign in to a Product Hunt account that is at least 30 days old and has "
                "genuine activity, create the post, paste this copy, upload the gallery "
                "images and post the maker comment. The maker identity has to be a real "
                "person and it is not ours to create.",
        })
    elif key in ("alternativeto", "saashub"):
        common.update({
            "categories": ["Invoicing", "Accounting", "Small business", "Document tools"],
            "alternative_to": ["Invoice Simple", "Zoho Invoice", "Wave", "FreshBooks",
                               "invoice-generator.com", "Billdu"],
            "differentiator_line": "Free with no account and no upload; documents stay in "
                                   "the browser. Covers receipts and credit notes, not "
                                   "invoices alone.",
            "what_the_owner_must_do":
                ("Create or sign in to an account and paste this listing. SaaSHub also "
                 "wants the product verified from a domain email address."
                 if key == "saashub" else
                 "Create or sign in to an account and paste this listing."),
        })
    elif key == "uneed":
        common["what_the_owner_must_do"] = (
            "Start the submission with the product name and URL -- no account is needed "
            "for that step -- then sign up to save it. Do not pay for fast-track.")
    setup = OWNER_SETUP.get(key)
    if setup:
        common["one_time_setup"] = setup["steps"]
        common["minutes"] = setup["minutes"]
        common["after_setup"] = setup["after_setup"]
    return common


# The smallest one-time procedure for each destination that needs an account,
# and what stops needing the owner once it exists. The point of recording the
# second half is that routine updates must not come back to them.
OWNER_SETUP = {
    "ph-launch": {
        "minutes": 20,
        "steps": [
            "Create or sign in to a personal Product Hunt account. It must be at "
            "least ONE WEEK old on launch day -- create it today and 15 September is "
            "comfortably clear.",
            "Complete the onboarding prompts; a zero-activity account is weaker.",
            "On launch day: Submit -> New Product, paste the prepared tagline, "
            "description, topics and thumbnail, then post the maker comment.",
            "Post yourself. A hunter is unnecessary, and paying one is against the "
            "guidelines and can get the product removed.",
        ],
        "after_setup": ("nothing recurring. The launch is a one-off event; results are "
                        "read from our own analytics by utm_source, not from the "
                        "platform, so no further access is needed"),
    },
    "alternativeto": {
        "minutes": 5,
        "steps": [
            "Create an account and add the app.",
            "Paste the prepared description, categories and alternative-to list.",
            "Upload two screenshots (the editor, and a finished PDF).",
        ],
        "after_setup": ("listing edits and new-tool entries can be prepared here and "
                        "pasted; no repeated owner research is needed"),
    },
    "saashub": {
        "minutes": 8,
        "steps": [
            "Create an account and submit the product URL.",
            "Choose the prepared categories and paste the competitor list -- SaaSHub "
            "prioritises submissions that name competitors.",
            "Verify the product from an @invoiceworkshop.com address when prompted; "
            "unverified submissions sit lower in the approval queue.",
        ],
        "after_setup": ("once verified, profile updates are a paste. The approval queue "
                        "is theirs, not ours, so nothing here is worth chasing"),
    },
    "uneed": {
        "minutes": 5,
        "steps": [
            "Open the submit page and enter the product name and URL. No account is "
            "needed for this step; it scrapes the page.",
            "Sign up when prompted to save the listing.",
            "Decline the paid fast-track and queue-skip options.",
        ],
        "after_setup": "none; a listing is a one-time submission",
    },
}


def prepare(connection: sqlite3.Connection, *, limit: int = 10) -> dict:
    """Write the submission bundle for every admitted destination worth one.

    Purely local: it writes to the growth database and sends nothing. The point
    is that a REVIEW destination arrives at the owner finished.
    """
    now = utc_now()
    catalogue = {d["key"]: d for d in DESTINATIONS}
    prepared = []
    for row in connection.execute(
            """SELECT key FROM breakout_destinations
                WHERE gate_status='admitted' AND status='identified'
                  AND execution_class IN ('AUTO','REVIEW')
                ORDER BY score DESC LIMIT ?""", (limit,)):
        destination = catalogue.get(row["key"])
        if destination is None or destination["channel"] in ("linkable_assets", "product_loops"):
            continue
        bundle = bundle_for(destination)
        connection.execute(
            """UPDATE breakout_destinations
                  SET bundle_json=?, status='prepared', updated_at=?
                WHERE key=?""",
            (json.dumps(bundle, sort_keys=True), now, row["key"]))
        prepared.append(row["key"])
    connection.commit()
    if prepared:
        owner_required = [dict(r) for r in connection.execute(
            """SELECT key, name, score FROM breakout_destinations
                WHERE status='prepared' AND execution_class='REVIEW'
                ORDER BY score DESC""")]
        if owner_required:
            record_escalation(
                connection, kind="breakout_owner_launch", severity="info",
                subject=f"{len(owner_required)} distribution launch(es) prepared and "
                        "waiting on an owner account or identity",
                detail=("Copy, positioning, assets list and tracked URLs are written and "
                        "stored against each destination. What remains needs a real "
                        "account or a real person, which is not created here: "
                        + ", ".join(f"{r['name']} (score {r['score']:.0f})"
                                    for r in owner_required)),
                fingerprint="breakout_owner_launch")
    return {"prepared": prepared, "external_side_effects": "none"}


def bundle(connection: sqlite3.Connection, key: str) -> dict:
    row = connection.execute(
        "SELECT name, execution_class, execution_reason, bundle_json "
        "FROM breakout_destinations WHERE key=?", (key,)).fetchone()
    if row is None:
        return {"error": f"no destination {key!r}"}
    return {"name": row["name"], "execution_class": row["execution_class"],
            "execution_reason": row["execution_reason"],
            "bundle": json.loads(row["bundle_json"] or "{}")}


# Which creator segment each shipped product family should be put in front of,
# and the page a message about it would point at. A family with no entry here
# has shipped without anyone deciding who it is for, which is the condition
# `distribution_debt` exists to surface.
FAMILY_AUDIENCE = {
    "doc-receipt": ("freelancer_newsletter", "https://invoiceworkshop.com/receipt-generator/"),
    "doc-credit-note": ("bookkeeping_newsletter", "https://invoiceworkshop.com/credit-note-generator/"),
    "doc-timesheet-invoice": ("freelancer_creator", "https://invoiceworkshop.com/timesheet-invoice-generator/"),
    "doc-delivery-note": ("small_business_newsletter", "https://invoiceworkshop.com/delivery-note-template/"),
    "asset-progress-draw": ("contractor_creator", "https://invoiceworkshop.com/progress-draw-schedule/"),
}

# Families whose audience exists but has not been researched yet, with the
# reason. Distinguished from a family nobody has thought about at all: the debt
# is the same but what would clear it is different, and a message that says
# "no audience segment chosen" for a UK VAT page is not actually true.
PENDING_SEGMENT = {
    "locale-gb": "UK bookkeeping and small-business creators. The researched segments "
                 "are US-centric, and recommending a UK VAT page to a US newsletter "
                 "would be a worse use of the contact than not sending it",
    "locale-in": "India GST practitioners and small-business creators",
    "locale-au": "Australian bookkeeping and trades creators",
    "locale-ca": "Canadian small-business and bookkeeping creators",
}

# How much distribution a shipped family owes before it counts as launched.
MIN_TARGETS_PER_FAMILY = 20
MIN_LAUNCH_SURFACES = 3


def distribution_debt(connection: sqlite3.Connection) -> dict:
    """Product families that shipped and were never put in front of anyone.

    Building a generator and publishing it is half the work; the other half is
    that somebody who needs it finds out. This makes the second half checkable
    rather than aspirational, so a family cannot quietly count as launched
    because its page went live.
    """
    surfaces = int(connection.execute(
        """SELECT COUNT(*) FROM breakout_destinations
            WHERE gate_status='admitted' AND channel IN ('launch_platforms', 'directories')"""
    ).fetchone()[0])
    debts = []
    for row in connection.execute(
            "SELECT family_key, name FROM page_families WHERE status='built'"):
        audience = FAMILY_AUDIENCE.get(row["family_key"])
        if audience is None:
            pending = PENDING_SEGMENT.get(row["family_key"])
            debts.append({
                "family": row["family_key"], "name": row["name"],
                "owes": (f"needs a segment that has not been researched: {pending}"
                         if pending else "no audience segment chosen for it at all")})
            continue
        segment, target = audience
        available = int(connection.execute(
            """SELECT COUNT(*) FROM creator_prospects
                WHERE segment=? AND status='qualified'""", (segment,)).fetchone()[0])
        missing = []
        if available < MIN_TARGETS_PER_FAMILY:
            missing.append(f"{available} qualified {segment} targets, "
                           f"{MIN_TARGETS_PER_FAMILY} wanted")
        if surfaces < MIN_LAUNCH_SURFACES:
            missing.append(f"{surfaces} admitted launch or directory surfaces, "
                           f"{MIN_LAUNCH_SURFACES} wanted")
        if missing:
            debts.append({"family": row["family_key"], "name": row["name"],
                          "segment": segment, "target_url": target,
                          "owes": "; ".join(missing)})
    if debts:
        record_escalation(
            connection, kind="distribution_debt", severity="info",
            subject=f"{len(debts)} shipped product famil(ies) have no distribution behind them",
            detail=("A generator that nobody is told about is half-finished. Each of these "
                    "shipped and is live, and the audience research or launch surface that "
                    "would put it in front of someone does not exist yet: "
                    + "; ".join(f"{d['name']} ({d['owes']})" for d in debts[:6])),
            fingerprint="distribution_debt")
    else:
        from growth_common import resolve_escalation
        resolve_escalation(connection, "distribution_debt")
    return {"families_with_debt": debts, "launch_surfaces_admitted": surfaces,
            "rule": (f"a shipped family owes {MIN_TARGETS_PER_FAMILY} qualified audience "
                     f"targets and {MIN_LAUNCH_SURFACES} launch surfaces before it counts "
                     "as launched rather than merely published")}


# Where to look for a submission that has not gone public yet. A directory
# usually gives no receipt beyond "in the queue", so the only honest way to know
# it landed is to keep looking at the page it would appear on.
WATCH_PAGES = {
    "alternativeto": "https://alternativeto.net/software/invoice-workshop/about/",
    "startupproject": "https://startupproject.org/?s=invoiceworkshop",
    "launchpedia": "https://launchpedia.co/?s=invoice+workshop",
}

# Matching the brand name in the page text does not work on a search page: the
# site echoes the query back, so "invoice workshop" is present on a page that
# found nothing. Only a link counts, and only the domain identifies us.
HREF_TO_SITE = re.compile(r'href="[^"]*invoiceworkshop\.com[^"]*"', re.I)


def pending_listings(connection: sqlite3.Connection) -> dict:
    """Whether anything submitted has become public, and whether it links to us.

    A listing that is live but carries no link to the site is worth knowing about
    separately from one that is still in a queue: the first is a placement that
    failed, the second has not happened yet.
    """
    import urllib.error
    import urllib.request

    now = utc_now()
    results = []
    for row in connection.execute(
        "SELECT key, name, status FROM breakout_destinations WHERE status IN ('submitted','live')"
    ):
        watch = WATCH_PAGES.get(row["key"])
        if not watch:
            results.append({"destination": row["name"], "state": "no watch page recorded"})
            continue
        request = urllib.request.Request(
            watch, headers={"User-Agent": "Mozilla/5.0 (compatible; InvoiceWorkshop/1.0)"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status, body = response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            status, body = error.code, ""
        except Exception as error:  # a network failure is not evidence of anything
            results.append({"destination": row["name"], "state": f"unreachable: {error}"})
            continue

        # Anonymous fetch: a submission still in review is invisible to it, which
        # is exactly the distinction being drawn.
        links_out = bool(HREF_TO_SITE.search(body))
        mentioned = "invoiceworkshop.com" in body.lower()
        state = ("live and linking" if links_out
                 else "mentions the domain but does not link to it" if mentioned
                 else "not public yet")
        if state == "live and linking":
            connection.execute(
                """UPDATE breakout_destinations SET status='live', notes=?, updated_at=?
                   WHERE key=?""",
                (f"public and linking as of {now[:10]} ({watch})", now, row["key"]))
            connection.execute(
                """INSERT INTO placements (prospect_id, placement_url, link_target, rel, anchor,
                                           status, link_present, last_http_status, verified_at, notes)
                   SELECT NULL, ?, ?, '', '', 'live', 1, ?, ?, ?
                   WHERE NOT EXISTS (SELECT 1 FROM placements WHERE placement_url=?)""",
                (watch, SITE, status, now, f"first seen by pending_listings on {now[:10]}", watch))
        results.append({"destination": row["name"], "watch_page": watch,
                        "http_status": status, "state": state})
    connection.commit()
    return {"checked_on": now[:10], "listings": results,
            "live": sum(1 for r in results if r.get("state") == "live and linking")}


def ranked(connection: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [dict(row) for row in connection.execute(
        """SELECT key, channel, name, execution_class, status, score, reach, intent,
                  speed_days, confidence, effort, substr(audience_fit, 1, 160) fit
             FROM breakout_destinations
            WHERE gate_status='admitted'
            ORDER BY score DESC, key LIMIT ?""", (limit,))]


# ---------------------------------------------------------------------------
# Traffic mix
# ---------------------------------------------------------------------------

# GA4's channel groups, mapped to the buckets the owner asked to see separately.
# Anything unrecognised lands in "other" rather than being folded into a bucket
# it might not belong to.
CHANNEL_BUCKETS = {
    "Organic Search": "organic_search",
    "Direct": "direct",
    "Referral": "referral",
    "Organic Social": "social",
    "Paid Social": "social",
    "Social": "social",
    "Email": "creator_newsletter",
    "Organic Video": "social",
    "Unassigned": "unassigned",
}


def traffic_mix(connection: sqlite3.Connection) -> dict:
    """Sessions, pageviews and completions split by where the visitor came from.

    Kept separate on purpose. Folding direct traffic into the organic number is
    how a search strategy gets credit for traffic search did not send, and every
    figure in the trajectory depends on that separation holding.
    """
    rows = connection.execute(
        """SELECT default_channel_group AS grp,
                  SUM(sessions) sessions, SUM(pageviews) pageviews,
                  SUM(tool_starts) tool_starts, SUM(pdf_downloads) pdf_downloads
             FROM ga4_acquisition
            WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ga4_acquisition)
            GROUP BY default_channel_group""").fetchall()
    mix: dict[str, dict] = {}
    for row in rows:
        bucket = CHANNEL_BUCKETS.get(row["grp"], "other")
        entry = mix.setdefault(bucket, {"sessions": 0, "pageviews": 0,
                                        "tool_starts": 0, "pdf_downloads": 0,
                                        "ga4_groups": []})
        entry["sessions"] += int(row["sessions"] or 0)
        entry["pageviews"] += int(row["pageviews"] or 0)
        entry["tool_starts"] += int(row["tool_starts"] or 0)
        entry["pdf_downloads"] += int(row["pdf_downloads"] or 0)
        if row["grp"] not in entry["ga4_groups"]:
            entry["ga4_groups"].append(row["grp"])
    total = sum(entry["sessions"] for entry in mix.values()) or 1
    for entry in mix.values():
        entry["share"] = round(entry["sessions"] / total, 3)
        # The metric that decides whether a channel was worth anything. A
        # thousand visitors who never start a document beat nobody, but not by
        # much, and this is where that shows up.
        entry["completion_rate"] = (round(entry["pdf_downloads"] / entry["sessions"], 3)
                                    if entry["sessions"] else 0.0)
    return {"mix": mix, "total_sessions": total,
            "launch_platform_note": ("launch and directory referrals arrive as Referral "
                                     "with a utm_source, which the tracked URLs set")}


def report(connection: sqlite3.Connection) -> dict:
    return {
        "ranked": ranked(connection, 30),
        "refused": [dict(row) for row in connection.execute(
            """SELECT key, name, refusal_reason FROM breakout_destinations
                WHERE gate_status='refused'""")],
        "by_class": {row["execution_class"]: row["n"] for row in connection.execute(
            """SELECT execution_class, COUNT(*) n FROM breakout_destinations
                WHERE gate_status='admitted' GROUP BY execution_class""")},
        "prepared": [dict(row) for row in connection.execute(
            """SELECT key, name, status FROM breakout_destinations
                WHERE status<>'identified' ORDER BY score DESC""")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("evaluate", help="Run the catalogue through the gate")
    top = commands.add_parser("ranked", help="Destinations by expected value")
    top.add_argument("--limit", type=int, default=20)
    commands.add_parser("report", help="Everything, including what was refused")
    commands.add_parser("traffic-mix", help="Sessions split by where they came from")
    launch = commands.add_parser("launch-plan", help="Record and check the Product Hunt launch")
    launch.add_argument("--account-created-on",
                        help="ISO date the owner's Product Hunt account was created")
    commands.add_parser("launch-results", help="What the launch actually sent")
    commands.add_parser("pending-listings",
                        help="Whether anything submitted has gone public and links to us")
    commands.add_parser("distribution-debt",
                        help="Shipped families nobody has been told about")
    prep = commands.add_parser("prepare", help="Write the submission bundles")
    prep.add_argument("--limit", type=int, default=10)
    show = commands.add_parser("bundle", help="Print one prepared submission")
    show.add_argument("key")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "evaluate":
        result = evaluate(connection)
    elif args.command == "ranked":
        result = {"ranked": ranked(connection, args.limit)}
    elif args.command == "prepare":
        result = prepare(connection, limit=args.limit)
    elif args.command == "bundle":
        result = bundle(connection, args.key)
    elif args.command == "traffic-mix":
        result = traffic_mix(connection)
    elif args.command == "launch-plan":
        result = launch_plan(connection, account_created_on=args.account_created_on)
    elif args.command == "launch-results":
        result = launch_results(connection)
    elif args.command == "pending-listings":
        result = pending_listings(connection)
    elif args.command == "distribution-debt":
        result = distribution_debt(connection)
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
