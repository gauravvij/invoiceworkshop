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
                "The maker account should be 30+ days old with genuine activity; new "
                "zero-activity accounts are down-weighted. Assets required: 240x240 "
                "icon, 3-5 gallery images or a 30-90s demo video, tagline under 60 "
                "characters, 2-3 paragraph description, and a maker comment. Posts go "
                "live at 12:01am PST; Tuesday to Thursday is the usual advice.",
       source_url="https://www.producthunt.com/launch",
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

TAGLINE = "Free invoices, receipts and credit notes. No signup, nothing uploaded."

POSITIONING = (
    "InvoiceWorkshop is a free business-document workspace that runs entirely in the "
    "browser. Invoices, quotations, estimates, work orders, purchase orders, receipts "
    "and credit notes, with saved customers and line items, live totals, per-line tax "
    "and instant PDF download. No account, no upload, no watermark: the documents never "
    "leave the device they are made on."
)

DESCRIPTION = (
    "Most free invoice tools ask for an email before showing you anything, put a "
    "watermark on the PDF, or store your customer list on someone else's server. "
    "InvoiceWorkshop does none of those. Open it, fill it in, download the PDF.\n\n"
    "It covers the documents a small business actually cycles through rather than "
    "invoices alone: quote a job, convert the quotation into an invoice, receipt the "
    "payment when it lands, and issue a credit note if something comes back. Business "
    "details, customers and common line items are remembered on the device, so the "
    "second document takes seconds. There are country presets for UK VAT, India GST, "
    "Australian tax invoices and Canadian GST/HST, each checked against the tax "
    "authority's own guidance rather than a competitor's blog.\n\n"
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

MAKER_COMMENT = (
    "I built this because every free invoice generator I tried wanted an email address "
    "before it would show me a document, and half of them watermarked the PDF. This one "
    "runs entirely in your browser -- your business details, customers and documents are "
    "saved on your device and never uploaded, which is also why there is no account.\n\n"
    "It has grown past invoices: quotations, estimates, work orders, purchase orders, "
    "receipts and credit notes, with conversion between them so you are not retyping. "
    "The country presets (UK VAT, India GST, Australia, Canada) were checked against the "
    "tax authorities' own guidance -- I found three things I had got wrong from secondary "
    "sources, which is its own argument for reading the primary one.\n\n"
    "Happy to answer anything about how the local-only storage works."
)


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
        "positioning": POSITIONING,
        "description": DESCRIPTION,
        "assets_needed": list(ASSET_LIST),
        "requirements_verified_on": destination["verified_on"],
        "what_the_owner_must_do": destination.get("owner_action", ""),
        "what_is_already_done": "copy, positioning, tagline, description, asset list, "
                                "tracked URL and category choices",
    }
    if key == "ph-launch":
        common.update({
            "maker_comment": MAKER_COMMENT,
            "topics": ["Productivity", "SaaS", "Design Tools", "Finance"],
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
    return common


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
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
