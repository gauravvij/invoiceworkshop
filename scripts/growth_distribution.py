#!/usr/bin/env python3
"""Distribution state for every shipped product surface.

The system had a blind spot with a shape: it could tell you exactly what had
been built and almost nothing about who had been told. Thirteen product surfaces
were live with effectively zero external audience, and nothing in the growth
database made that visible, because everything it measured -- pages, families,
tests, prospects researched -- goes up when you build and stays flat when nobody
hears about it.

So this is a register, one row per thing a user can open. Each row names the
search cluster it competes in, the resource, creator and directory audiences it
plausibly belongs to, and the angle that makes it worth linking to. Then it
carries the only three numbers that settle the question: referral sessions,
backlinks, organic clicks. A surface with none of them stays marked `debt`, and
it says so on every report until that changes.

Ranking exists so effort concentrates. Promoting thirteen things equally is the
same as promoting none: the top three get the outreach, and the rest wait.
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from growth_common import apply_schema, connect_db, database_path, record_escalation, utc_now

SITE = "https://invoiceworkshop.com"


def _s(route, name, family, cluster, resource, creator, directory, angle, fit):
    return {"route": route, "name": name, "family": family, "search_cluster": cluster,
            "resource_audience": resource, "creator_audience": creator,
            "directory_target": directory, "linkable_angle": angle,
            "distribution_fit": fit}


# Every live surface. `distribution_fit` is a judgement about how easily this
# specific thing can be put in front of someone who is not already searching for
# it -- which is a different question from how much search demand it has, and the
# one this register exists to answer.
SURFACES = [
    _s("/", "Invoice Generator (the workspace)", "core",
       "invoice generator, free invoice maker, invoice online",
       "freelancer and small-business resource pages",
       "small_business_newsletter",
       "AlternativeTo, SaaSHub, Uneed, Product Hunt",
       "a free no-signup document workspace where nothing is uploaded -- the whole "
       "product, which is what a directory or a launch actually lists",
       0.95),
    _s("/receipt-generator/", "Receipt Generator", "doc-receipt",
       "receipt maker, payment receipt template, free receipt generator",
       "freelancer resource pages, bookkeeping client resources",
       "freelancer_newsletter",
       "AlternativeTo (as a receipt maker), Product Hunt gallery",
       "a receipt that records a payment against an invoice, in a market whose first "
       "page is mostly till-receipt replication",
       0.8),
    _s("/progress-draw-schedule/", "Progress Draw Schedule", "asset-progress-draw",
       "retainage calculator, schedule of values, progress draw, AIA G702 G703",
       "construction accounting and trade association resource pages",
       "contractor_creator",
       "none: it is a calculator, not a product listing",
       "sums retainage down the column rather than taking it on the total, and judges "
       "a contractual retainage reduction on the contract rather than line by line -- "
       "the two errors that get a draw returned. Construction-accounting publishers "
       "reference calculators; they do not reference invoice templates",
       0.9),
    _s("/credit-note-generator/", "Credit Note Generator", "doc-credit-note",
       "credit note template, credit memo generator, credit note format",
       "bookkeeping and accounting practice resource pages",
       "bookkeeping_newsletter",
       "AlternativeTo",
       "the document a bookkeeper hands a client who keeps editing the original "
       "invoice instead of crediting it",
       0.7),
    _s("/construction-invoice-template/", "Construction Invoice Template", "vertical",
       "construction invoice template, contractor billing",
       "construction and trade resource pages",
       "contractor_creator", "none",
       "pairs with the draw schedule as a construction billing workflow rather than a "
       "standalone template",
       0.65),
    _s("/timesheet-invoice-generator/", "Timesheet Invoice", "doc-timesheet-invoice",
       "timesheet invoice, hourly invoice template, contractor hours invoice",
       "freelancer and agency resource pages",
       "freelancer_creator", "none",
       "an hours total that reconciles with the money total, which is the defect in "
       "most hourly invoices",
       0.6),
    _s("/contractor-invoice-template/", "Contractor Invoice Template", "vertical",
       "contractor invoice template, independent contractor invoice",
       "freelancer and trade resource pages",
       "contractor_creator", "none",
       "project, jobsite and deposit fields rather than a renamed invoice",
       0.55),
    _s("/delivery-note-template/", "Delivery Note", "doc-delivery-note",
       "delivery note template, packing slip generator",
       "wholesale, fulfilment and small-manufacturer resource pages",
       "small_business_newsletter", "none",
       "carries no prices at all, because it is read in a loading bay -- the thing "
       "every Word template on that SERP gets wrong",
       0.5),
    _s("/quotation-generator/", "Quotation Generator", "core",
       "quotation template, quote generator",
       "small-business resource pages", "small_business_newsletter", "none",
       "converts into an invoice without retyping, which is the workflow rather than "
       "the document",
       0.4),
    _s("/estimate-generator/", "Estimate Generator", "core",
       "estimate template, free estimate generator",
       "trade and service-business resource pages", "contractor_creator", "none",
       "converts to a work order and then an invoice",
       0.4),
    _s("/work-order-generator/", "Work Order Generator", "core",
       "work order template, work order generator",
       "field-service and trade resource pages", "contractor_creator", "none",
       "the authorisation step between an estimate and an invoice",
       0.35),
    _s("/purchase-order-generator/", "Purchase Order Generator", "core",
       "purchase order template, PO generator",
       "procurement and small-business resource pages", "small_business_newsletter", "none",
       "the buyer-side document, which pairs with the delivery note",
       0.35),
    _s("/proforma-invoice-generator/", "Proforma Invoice Generator", "core",
       "proforma invoice, proforma invoice template",
       "import/export and small-business resource pages", "small_business_newsletter", "none",
       "the proforma-versus-commercial-invoice distinction, which is a genuine and "
       "frequently searched confusion",
       0.35),
    _s("/invoice-template/", "Invoice Template", "core",
       "invoice template, free invoice template",
       "general small-business resource pages", "small_business_newsletter", "none",
       "a worked invoice whose arithmetic can be checked against the tool",
       0.3),
    _s("/vat-invoice-template-uk/", "UK VAT Invoice", "locale-gb",
       "vat invoice template uk, vat invoice requirements",
       "UK small-business and bookkeeping resource pages",
       "unresearched: UK bookkeeping and small-business creators", "none",
       "checked against HMRC's own guidance, including the £250 simplified-invoice "
       "threshold and the fact that HMRC does not require the heading",
       0.45),
    _s("/gst-invoice-format-india/", "India GST Invoice", "locale-in",
       "gst invoice format india, gst bill format",
       "Indian small-business and GST practitioner resource pages",
       "unresearched: India GST practitioners", "none",
       "the post-22-September-2025 slab structure, which most published formats still "
       "have wrong",
       0.45),
    _s("/tax-invoice-template-australia/", "Australia Tax Invoice", "locale-au",
       "tax invoice template australia, ato tax invoice",
       "Australian bookkeeping and trade resource pages",
       "unresearched: Australian bookkeeping and trades creators", "none",
       "states what the ATO actually requires rather than the folklore version",
       0.4),
    _s("/gst-hst-invoice-template-canada/", "Canada GST/HST Invoice", "locale-ca",
       "gst hst invoice template canada, cra invoice requirements",
       "Canadian small-business resource pages",
       "unresearched: Canadian small-business creators", "none",
       "the current $100/$500 input-tax-credit thresholds and Nova Scotia at 14%, "
       "both of which most published guidance still has wrong",
       0.4),
]


def register(connection: sqlite3.Connection) -> dict:
    """Write or refresh a row per surface, then measure what each has earned."""
    now = utc_now()
    for surface in SURFACES:
        connection.execute(
            """INSERT INTO product_distribution
                 (route, name, family, search_cluster, resource_audience,
                  creator_audience, directory_target, linkable_angle, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(route) DO UPDATE SET
                 name=excluded.name, family=excluded.family,
                 search_cluster=excluded.search_cluster,
                 resource_audience=excluded.resource_audience,
                 creator_audience=excluded.creator_audience,
                 directory_target=excluded.directory_target,
                 linkable_angle=excluded.linkable_angle,
                 updated_at=excluded.updated_at""",
            (surface["route"], surface["name"], surface["family"],
             surface["search_cluster"], surface["resource_audience"],
             surface["creator_audience"], surface["directory_target"],
             surface["linkable_angle"], now))
    connection.commit()
    return measure(connection)


# One qualified prospect is not a distribution plan. Below this a surface stays
# marked as debt however much research sits behind it, because the point of the
# register is to be uncomfortable about surfaces nobody has been told about.
MIN_TARGETS_FOR_TARGETED = 3


def measure(connection: sqlite3.Connection) -> dict:
    """The three numbers that settle it, per surface, from evidence already held."""
    now = utc_now()
    for surface in SURFACES:
        url = SITE + surface["route"] if surface["route"] != "/" else SITE + "/"
        clicks = connection.execute(
            """SELECT COALESCE(SUM(clicks), 0) FROM gsc_query_facts
                WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM gsc_query_facts)
                  AND page=?""", (url,)).fetchone()[0]
        backlinks = connection.execute(
            "SELECT COUNT(*) FROM placements WHERE status='live' AND link_target=?",
            (url,)).fetchone()[0]
        referrals = connection.execute(
            """SELECT COALESCE(SUM(referral_sessions), 0) FROM breakout_results r
                 JOIN breakout_destinations d ON d.key = r.destination_key
                WHERE d.url = ?""", (url,)).fetchone()[0]
        creator_targets = 0
        segment = surface["creator_audience"]
        if segment and not segment.startswith("unresearched"):
            creator_targets = connection.execute(
                "SELECT COUNT(*) FROM creator_prospects WHERE segment=? AND status='qualified'",
                (segment,)).fetchone()[0]
        # Resource-page outreach is the channel with real inventory, and it
        # targets a specific URL. Counting only creator prospects made every
        # surface look untargeted when several already have somewhere to go.
        resource_targets = connection.execute(
            """SELECT COUNT(DISTINCT a.organization) FROM level1a_actions a
                WHERE a.target_url = ?""", (url,)).fetchone()[0]
        targets = creator_targets + resource_targets
        earning = (clicks or 0) + (backlinks or 0) + (referrals or 0)
        state = ("earning" if earning
                 else "targeted" if targets >= MIN_TARGETS_FOR_TARGETED
                 else "debt")
        connection.execute(
            """UPDATE product_distribution
                  SET organic_clicks=?, backlinks=?, referral_sessions=?,
                      qualified_targets=?,
                      distribution_state=CASE WHEN distribution_state IN ('contacted','placed')
                                              THEN distribution_state ELSE ? END,
                      updated_at=?
                WHERE route=?""",
            (clicks, backlinks, referrals, targets, state, now, surface["route"]))
    connection.commit()

    debt = [dict(row) for row in connection.execute(
        """SELECT route, name FROM product_distribution
            WHERE distribution_state='debt' ORDER BY route""")]
    if debt:
        record_escalation(
            connection, kind="product_distribution_debt", severity="warning",
            subject=f"{len(debt)} of {len(SURFACES)} live product surfaces have no "
                    "external audience at all",
            detail=("No referral session, no backlink and no organic click between them. "
                    "Building more surfaces does not change this number, which is the "
                    "reason the register exists: "
                    + ", ".join(row["name"] for row in debt[:8])),
            fingerprint="product_distribution_debt")
    return {"surfaces": len(SURFACES), "in_debt": len(debt),
            "debt": [row["name"] for row in debt],
            "bar": (f"a surface counts as targeted at {MIN_TARGETS_FOR_TARGETED} qualified "
                    "organizations. One prospect is research, not distribution")}


def rank(connection: sqlite3.Connection, top: int = 3) -> dict:
    """Which surfaces to push now. Effort concentrates or it does nothing.

    Ranked on distribution fit -- how readily somebody who is not already
    searching would put this in front of users -- multiplied by whether an
    audience for it actually exists yet. Search demand is deliberately not in
    this: it is what the other engine optimises, and mixing them would put the
    homepage top of every list forever.
    """
    now = utc_now()
    scored = []
    for surface in SURFACES:
        row = connection.execute(
            "SELECT qualified_targets FROM product_distribution WHERE route=?",
            (surface["route"],)).fetchone()
        targets = int(row["qualified_targets"]) if row else 0
        directory = 0.0 if surface["directory_target"] == "none" else 0.3
        unresearched = surface["creator_audience"].startswith("unresearched")
        audience = 0.0 if unresearched else min(0.4, targets * 0.05)
        scored.append({
            "route": surface["route"], "name": surface["name"],
            "score": round(surface["distribution_fit"] + directory + audience, 3),
            "why": surface["linkable_angle"],
            "qualified_targets": targets,
            "audience_note": ("audience segment not researched yet"
                              if unresearched else f"{targets} qualified targets"),
        })
    scored.sort(key=lambda row: -row["score"])
    for index, row in enumerate(scored, start=1):
        connection.execute(
            """UPDATE product_distribution SET priority_rank=?, priority_reason=?,
                   updated_at=? WHERE route=?""",
            (index, row["why"][:400], now, row["route"]))
    connection.commit()
    return {"push_now": scored[:top], "waiting": [row["name"] for row in scored[top:]],
            "rule": ("promoting everything equally is the same as promoting nothing. "
                     "The top three get the outreach; the rest wait for evidence that "
                     "the channel works at all")}


def report(connection: sqlite3.Connection) -> dict:
    rows = [dict(row) for row in connection.execute(
        """SELECT route, name, distribution_state, priority_rank, qualified_targets,
                  referral_sessions, backlinks, organic_clicks, search_cluster,
                  creator_audience, directory_target
             FROM product_distribution ORDER BY priority_rank, route""")]
    return {
        "surfaces": rows,
        "in_debt": sum(1 for row in rows if row["distribution_state"] == "debt"),
        "external_outcomes": {
            "referral_sessions": sum(row["referral_sessions"] for row in rows),
            "backlinks": sum(row["backlinks"] for row in rows),
            "organic_clicks": sum(row["organic_clicks"] for row in rows),
        },
        "note": ("these three totals are the phase's definition of success. Pages "
                 "built, tests passed and prospects researched are not on this list "
                 "on purpose"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("register", help="Write the register and measure it")
    commands.add_parser("measure", help="Re-read what each surface has earned")
    top = commands.add_parser("rank", help="Which surfaces to push now")
    top.add_argument("--top", type=int, default=3)
    commands.add_parser("report", help="The register, with the external outcomes")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "register":
        result = register(connection)
    elif args.command == "measure":
        result = measure(connection)
    elif args.command == "rank":
        result = rank(connection, args.top)
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
