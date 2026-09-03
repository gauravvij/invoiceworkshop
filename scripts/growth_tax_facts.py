#!/usr/bin/env python3
"""Tax and invoicing facts stated on country pages, with their sources.

A page that tells someone what their tax authority requires is a different
category of content from a page that describes a product. It goes stale without
any signal, and a reader acts on it. So every such fact is recorded here with
the primary government source it came from, the date it was checked and the date
it needs checking again.

Verified 2026-09-02 against primary sources. Three of the facts already
published were wrong, and none of them could have been caught without going to
the source:

  * India removed the 12% and 28% slabs on 22 September 2025. The page offered
    them as options.
  * Canada replaced the $30 and $150 input-tax-credit thresholds with $100 and
    $500 on 20 April 2021. The page stated the old ones.
  * HMRC does not require the words "VAT invoice" as a document title. The page
    said it did.

`confidence` distinguishes a fact read directly off the authority's own page
from one carried by its press service where the underlying page would not
render. Nothing here is marked verified that was taken from a competitor blog.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone

from growth_common import apply_schema, connect_db, database_path, record_escalation

VERIFIED_ON = "2026-09-02"
# Tax rules change on political timetables, not ours. Two months is short enough
# that a budget change is caught before a reader acts on a stale figure.
REVERIFY_AFTER_DAYS = 60


def _r() -> str:
    return (date.fromisoformat(VERIFIED_ON) + timedelta(days=REVERIFY_AFTER_DAYS)).isoformat()


FACTS = [
    # ---- United Kingdom ---------------------------------------------------
    ("gb", "standard_rate", "20%", "GOV.UK — VAT rates",
     "https://www.gov.uk/vat-record-keeping/vat-invoices", "primary_source", ""),
    ("gb", "reduced_rate", "5%", "GOV.UK — VAT rates",
     "https://www.gov.uk/vat-record-keeping/vat-invoices", "primary_source", ""),
    ("gb", "zero_rate", "0%", "GOV.UK — VAT rates",
     "https://www.gov.uk/vat-record-keeping/vat-invoices", "primary_source", ""),
    ("gb", "document_title_required", "No",
     "HMRC VAT Notice 700, section 16",
     "https://www.gov.uk/guidance/vat-guide-notice-700", "primary_source",
     "The guidance does not mandate the heading 'VAT invoice'. What matters is that "
     "the required particulars are present. The page previously claimed HMRC requires "
     "the title."),
    ("gb", "simplified_invoice_threshold", "£250",
     "HMRC VAT Notice 700, section 16",
     "https://www.gov.uk/guidance/vat-guide-notice-700", "primary_source",
     "A simplified invoice with fewer particulars is available where the consideration "
     "does not exceed £250."),
    ("gb", "who_must_issue", "VAT-registered businesses, charging VAT on taxable supplies",
     "GOV.UK — VAT invoices",
     "https://www.gov.uk/vat-record-keeping/vat-invoices", "primary_source",
     "Not every seller issues a VAT invoice; it follows from being registered."),

    # ---- India ------------------------------------------------------------
    ("in", "rate_slabs", "0%, 5%, 18%, and 40% on demerit goods",
     "PIB — Recommendations of the 56th GST Council meeting",
     "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2163555", "primary_source_indirect",
     "The 12% and 28% slabs were removed and a 40% demerit rate introduced, effective "
     "22 September 2025. CBIC's own rate pages redirect to taxinformation.cbic.gov.in "
     "and did not render, so this is taken from the Government of India press release "
     "rather than the rate schedule itself. Treat the slab list as directional and "
     "recheck before relying on it."),
    ("in", "rate_change_effective", "22 September 2025",
     "PIB — 56th GST Council",
     "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2163555", "primary_source_indirect", ""),
    ("in", "place_of_supply_condition",
     "Required for inter-State supplies; the split between CGST/SGST and IGST follows it",
     "CGST Rules, Rule 46", "https://cbic-gst.gov.in/", "unverified",
     "The CGST Rules PDF did not render. The page now states the conditionality rather "
     "than presenting place of supply as an unconditional field."),

    # ---- Australia --------------------------------------------------------
    ("au", "gst_rate", "10%", "ATO — Tax invoices",
     "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices",
     "primary_source_indirect",
     "ato.gov.au returns 403 to automated fetches; taken from the ATO's own indexed "
     "guidance summary."),
    ("au", "document_indication",
     "The document must indicate it is intended to be a tax invoice",
     "ATO — Tax invoices / GSTR 2013/1",
     "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices",
     "primary_source_indirect",
     "The requirement is that the document indicates it is intended to be a tax "
     "invoice. Showing the words 'Tax invoice' satisfies that, but the wording itself "
     "is not what the law asks for."),
    ("au", "buyer_identity_threshold", "A$1,000",
     "ATO — Tax invoices",
     "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices",
     "primary_source_indirect",
     "Sales of A$1,000 or more must also show the buyer's identity or ABN."),

    # ---- Canada -----------------------------------------------------------
    ("ca", "itc_thresholds", "$100 and $500",
     "CRA — Excise and GST/HST News No. 118",
     "https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/news118/news118-excise-gst-hst-news-no-118.html",
     "primary_source",
     "\"the thresholds of $30 and $150 have been replaced by $100 and $500, effective "
     "April 20, 2021\". GST/HST Memorandum 8.4 still shows the old figures and is dated "
     "2012; the News item supersedes it. The page previously stated $30 and $150."),
    ("ca", "gst_rate", "5%",
     "CRA — Charge and collect the GST/HST",
     "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-receipts-invoices.html",
     "primary_source", ""),
    ("ca", "hst_rates", "13% Ontario; 14% Nova Scotia; 15% New Brunswick, Newfoundland and Labrador, Prince Edward Island",
     "CRA — GST/HST rates",
     "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate.html",
     "primary_source",
     "Nova Scotia decreased its provincial portion to 9%, making HST 14% from 1 April "
     "2025. The page previously implied only 13% and 15% existed."),
    ("ca", "hst_display_rule",
     "Show the total HST rate; do not show the federal and provincial parts separately",
     "CRA — Charge and collect the GST/HST",
     "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-receipts-invoices.html",
     "primary_source", ""),
]


def load(connection) -> dict:
    for jurisdiction, key, value, name, url, confidence, caveat in FACTS:
        connection.execute(
            """INSERT INTO tax_facts
                 (jurisdiction, fact_key, value, source_name, source_url,
                  verified_on, reverify_by, confidence, caveat)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(jurisdiction, fact_key) DO UPDATE SET
                 value=excluded.value, source_name=excluded.source_name,
                 source_url=excluded.source_url, verified_on=excluded.verified_on,
                 reverify_by=excluded.reverify_by, confidence=excluded.confidence,
                 caveat=excluded.caveat""",
            (jurisdiction, key, value, name, url, VERIFIED_ON, _r(), confidence, caveat))
    connection.commit()
    return {"loaded": len(FACTS), "verified_on": VERIFIED_ON, "reverify_by": _r()}


def stale(connection) -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    return [dict(row) for row in connection.execute(
        """SELECT jurisdiction, fact_key, value, source_url, verified_on, reverify_by,
                  confidence
             FROM tax_facts WHERE reverify_by <= ? ORDER BY reverify_by, jurisdiction""",
        (today,))]


def check(connection) -> dict:
    """Facts due for rechecking, and facts never confirmed at the source."""
    overdue = stale(connection)
    weak = [dict(row) for row in connection.execute(
        "SELECT jurisdiction, fact_key, caveat FROM tax_facts WHERE confidence='unverified'")]
    if overdue:
        record_escalation(
            connection, kind="tax_facts_stale", severity="warning",
            subject=f"{len(overdue)} published tax fact(s) are past their recheck date",
            detail=("Country pages state what a tax authority requires. Those statements "
                    "go stale silently and a reader acts on them, so they are rechecked "
                    "against the primary source rather than left to age: "
                    + ", ".join(f"{row['jurisdiction']}/{row['fact_key']}" for row in overdue[:8])),
            fingerprint="tax_facts_stale")
    return {"overdue": overdue, "unverified": weak,
            "total": connection.execute("SELECT COUNT(*) FROM tax_facts").fetchone()[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("load", help="Record the verified facts and their sources")
    commands.add_parser("check", help="Facts past their recheck date, or never confirmed")
    commands.add_parser("list", help="Every recorded fact with its source")
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "load":
        result = load(connection)
    elif args.command == "check":
        result = check(connection)
    else:
        result = {"facts": [dict(row) for row in connection.execute(
            "SELECT * FROM tax_facts ORDER BY jurisdiction, fact_key")]}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
