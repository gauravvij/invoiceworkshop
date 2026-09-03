#!/usr/bin/env python3
"""Search surface expansion, gated on the tool actually being different.

The 90-day target needs hundreds of ranking pages, and the fastest way to fail
at it is to generate hundreds of pages that are the same tool under different
headings. Google calls that scaled content abuse and it is not a slower route to
the target -- it is the end of the domain. So this module treats surface area as
a product question rather than a publishing one.

A FAMILY is a whole dimension of pages: one country, one trade, one document
type, one utility. Families are admitted or refused as a unit, before any page in
them exists, and admission requires a code-level change that makes the tool
behave differently. The gate is mechanical:

  1. demand        -- a real query with real results, recorded as evidence
  2. differentiators -- at least three concrete differences in what the tool
                        produces, listed individually
  3. functional     -- at least two of those must be FUNCTIONAL, meaning they
                        change computation, fields, validation, structure or
                        output. Wording alone can never satisfy this.
  4. product_change -- names the change to the code that delivers them
  5. not duplicate  -- the route is not already served
  6. sourced        -- a country family additionally needs its tax facts recorded
                       against a primary government source, with a recheck date
                       that has not passed. A page that tells someone what their
                       tax authority requires is not editorial content and is not
                       admitted on a differentiator list alone.

A family that cannot state two functional differences is refused and stays
refused, with the reason. That is the whole point of the module: it is much
easier to add the check here than to remove a thousand pages later.
"""

from __future__ import annotations

import argparse
import json
import sqlite3

from growth_common import apply_schema, connect_db, database_path, utc_now

# Differences that change what the tool computes or produces. Anything outside
# this set is presentation, and presentation alone never justifies a page.
FUNCTIONAL_KINDS = frozenset({
    "currency", "tax_computation", "tax_label", "tax_identifier", "required_field",
    "extra_column", "validation", "document_structure", "date_format",
    "line_defaults", "totals_logic", "legal_wording_required", "unit_defaults",
})
PRESENTATIONAL_KINDS = frozenset({"heading", "description", "copy", "example"})

MIN_DIFFERENTIATORS = 3
MIN_FUNCTIONAL = 2

# Build order. Expected growth value is usefulness x realistic traffic upside x
# confidence, divided by effort -- so the crowded receipt SERP still leads,
# because the document kind already exists end to end and the build is small,
# while the weakest field (delivery notes) comes last because it needs a line
# model the rest of the product does not have. A family without a score sorts
# below the ones that have been ranked rather than jumping the queue.
DEFAULT_VALUE = 1.0

# Whether the product change a family depends on already exists.
#
#   content_only -- the capability is shipped, so the page is an entry in
#                   generators.ts and the unattended worker can build it inside
#                   the AUTO envelope.
#   product      -- the capability does not exist yet and lives outside that
#                   envelope (document kinds, totals logic, storage). Admitted,
#                   queued, and deliberately not offered to the worker, which
#                   would only be refused and would waste the run.
BUILD_SCOPES = ("content_only", "product")


class GateRefusal(Exception):
    """The family does not earn its pages. Recorded, not worked around."""


# ---------------------------------------------------------------------------
# The catalogue. Every entry states what the tool would do differently.
# ---------------------------------------------------------------------------

def _d(kind: str, detail: str) -> dict:
    return {"kind": kind, "detail": detail}


LOCALES = [
    {
        "key": "locale-gb", "jurisdiction": "gb", "build_scope": "content_only", "name": "UK VAT invoice", "route": "/vat-invoice-template-uk/",
        "demand": "SERP for 'vat invoice template uk' returns UK-specific templates from "
                  "Sage, FreeAgent, GOV.UK guidance and several template libraries",
        "differentiators": [
            _d("tax_label", "Tax is labelled VAT throughout the document and the PDF"),
            _d("tax_computation", "Default rate 20%, with 5% and 0% as standard options"),
            _d("tax_identifier", "VAT registration number field, required for a valid VAT invoice"),
            _d("currency", "GBP default with £ formatting"),
            _d("date_format", "DD/MM/YYYY"),
        ],
        "product_change": "locale preset: tax label, default rate, tax-id field label and "
                          "requirement, currency, date format, document title",
    },
    {
        "key": "locale-in", "jurisdiction": "in", "build_scope": "product", "name": "India GST invoice", "route": "/gst-invoice-format-india/",
        "demand": "SERP for 'gst invoice format india free' returns several dedicated GST "
                  "generators and bill-format downloads; demand is large and specific",
        "differentiators": [
            _d("tax_computation", "GST splits into CGST + SGST for intra-state and IGST for "
                                  "inter-state; the split is computed, not typed"),
            _d("extra_column", "HSN/SAC code column per line, which no other locale needs"),
            _d("tax_identifier", "GSTIN field with 15-character format validation"),
            _d("required_field", "Place of supply, which determines the CGST/SGST vs IGST split"),
            _d("tax_label", "Default rate 18%; slabs are 5% and 18% with a 40% demerit "
                            "rate since 22 September 2025"),
            _d("currency", "INR default with ₹ formatting"),
        ],
        "product_change": "locale preset plus a per-line HSN/SAC column and the "
                          "intra/inter-state GST split in the totals calculation",
    },
    {
        "key": "locale-au", "jurisdiction": "au", "build_scope": "content_only", "name": "Australia tax invoice", "route": "/tax-invoice-template-australia/",
        "demand": "SERP for 'tax invoice template australia' returns ATO guidance and "
                  "Australian-specific generators",
        "differentiators": [
            _d("legal_wording_required", "The document must indicate it is intended to be a "
                                        "tax invoice; the preset titles it Tax Invoice"),
            _d("tax_computation", "GST fixed at 10%"),
            _d("tax_identifier", "ABN field with 11-digit validation"),
            _d("currency", "AUD default"),
            _d("date_format", "DD/MM/YYYY"),
        ],
        "product_change": "locale preset with ABN validation and the required document title",
    },
    {
        "key": "locale-ca", "jurisdiction": "ca", "build_scope": "content_only", "name": "Canada GST/HST invoice", "route": "/gst-hst-invoice-template-canada/",
        "demand": "SERP for 'gst hst invoice template canada' returns CRA guidance and "
                  "province-specific templates",
        "differentiators": [
            _d("tax_computation", "Rate varies by province: 5% GST, 13% HST in Ontario, "
                                  "14% in Nova Scotia since 1 April 2025, 15% in NB/NL/PE, "
                                  "plus QST in Quebec"),
            _d("tax_identifier", "CRA Business Number field"),
            _d("required_field", "Province selector, which sets the applicable rate"),
            _d("currency", "CAD default"),
        ],
        "product_change": "locale preset plus a province table driving the tax rate",
    },
    {
        "key": "locale-ae", "jurisdiction": "ae", "build_scope": "content_only", "name": "UAE VAT invoice", "route": "/vat-invoice-template-uae/",
        "demand": "SERP for 'vat invoice format uae' returns FTA guidance and UAE generators",
        "differentiators": [
            _d("tax_computation", "VAT fixed at 5%"),
            _d("tax_identifier", "TRN field with 15-digit validation"),
            _d("legal_wording_required", "FTA requires 'Tax Invoice' on the document"),
            _d("currency", "AED default"),
        ],
        "product_change": "locale preset with TRN validation",
    },
    {
        "key": "locale-za", "jurisdiction": "za", "build_scope": "content_only", "name": "South Africa VAT invoice", "route": "/vat-invoice-template-south-africa/",
        "demand": "SERP for 'vat invoice template south africa' returns SARS guidance and "
                  "local templates",
        "differentiators": [
            _d("tax_computation", "VAT fixed at 15%"),
            _d("tax_identifier", "SARS VAT number field, 10 digits beginning with 4"),
            _d("legal_wording_required", "SARS requires 'Tax Invoice' for a full tax invoice"),
            _d("currency", "ZAR default"),
        ],
        "product_change": "locale preset with SARS VAT number validation",
    },
    {
        "key": "locale-eu-de", "jurisdiction": "de", "build_scope": "content_only", "name": "Germany VAT (USt) invoice", "route": "/rechnung-vorlage-vat-germany/",
        "demand": "SERP for 'rechnung vorlage kleinunternehmer' shows heavy German demand "
                  "for invoice templates with USt handling",
        "differentiators": [
            _d("tax_computation", "USt default 19% with 7% reduced rate"),
            _d("tax_identifier", "USt-IdNr field"),
            _d("currency", "EUR default"),
            _d("date_format", "DD.MM.YYYY"),
        ],
        "product_change": "locale preset with German tax identifier and date format",
    },
    {
        "key": "locale-ie", "jurisdiction": "ie", "build_scope": "content_only", "name": "Ireland VAT invoice", "route": "/vat-invoice-template-ireland/",
        "demand": "SERP for 'vat invoice template ireland' returns Revenue guidance and "
                  "Irish templates",
        "differentiators": [
            _d("tax_computation", "VAT default 23% with 13.5% and 9% reduced rates"),
            _d("tax_identifier", "Irish VAT number field"),
            _d("currency", "EUR default"),
            _d("date_format", "DD/MM/YYYY"),
        ],
        "product_change": "locale preset with Irish rate table",
    },
    {
        "key": "locale-sg", "jurisdiction": "sg", "build_scope": "content_only", "name": "Singapore GST invoice", "route": "/gst-invoice-template-singapore/",
        "demand": "SERP for 'gst invoice template singapore' returns IRAS guidance and "
                  "Singapore templates",
        "differentiators": [
            _d("tax_computation", "GST fixed at 9%"),
            _d("tax_identifier", "UEN / GST registration number field"),
            _d("legal_wording_required", "IRAS requires 'Tax Invoice' wording"),
            _d("currency", "SGD default"),
        ],
        "product_change": "locale preset with UEN field",
    },
    {
        "key": "locale-nz", "jurisdiction": "nz", "build_scope": "content_only", "name": "New Zealand GST invoice", "route": "/gst-invoice-template-new-zealand/",
        "demand": "SERP for 'gst invoice template nz' returns IRD guidance and NZ templates",
        "differentiators": [
            _d("tax_computation", "GST fixed at 15%"),
            _d("tax_identifier", "IRD number field"),
            _d("currency", "NZD default"),
            _d("date_format", "DD/MM/YYYY"),
        ],
        "product_change": "locale preset with IRD number field",
    },
]

DOCUMENTS = [
    {
        "key": "doc-receipt", "expected_value": 9.0,
        "value_basis": "the kind already exists in the type union, factory, conversions, PDF and storage, so the build is fields and a page rather than a new document model; largest demand of the four", "build_scope": "product", "name": "Receipt generator", "route": "/receipt-generator/",
        "demand": "SERP checked 3 September 2026. 'free receipt maker generator online' "
                  "returns MakeMyReceipt, SimpleReceiptMaker (130+ templates), ReceiptMake, "
                  "ReceiptBaker, ExpensesReceipt, InvoiceSimple, InvoiceFly and CraftMyPDF: "
                  "heavy commercial competition, so real volume. Most of that page is "
                  "till-receipt replication -- register and cashier fields, barcodes, "
                  "'recreate a lost receipt' -- which is a different and worse product. The "
                  "unserved intent is a business confirming a payment against an invoice, "
                  "which the template libraries (Adobe, Docusign, bill.com) answer with a "
                  "static download and the invoicing apps answer behind a login",
        "differentiators": [
            _d("document_structure", "A receipt records payment already taken: no due date, "
                                     "no payment terms, no balance due"),
            _d("required_field", "Amount paid, payment method and date paid replace the "
                                 "amount-due block"),
            _d("totals_logic", "Total paid rather than balance outstanding; a partial "
                               "payment shows the remaining balance explicitly"),
            _d("legal_wording_required", "Titled RECEIPT and marked PAID"),
        ],
        "product_change": "the receipt document kind already exists in the type union and "
                          "has no page; give it payment fields and a paid-status total block",
    },
    {
        "key": "doc-credit-note", "expected_value": 7.0,
        "value_basis": "unambiguous B2B intent, the weakest incumbent tools of the three remaining, and it pairs with the existing invoice through the same conversion mechanism the receipt uses", "build_scope": "product", "name": "Credit note generator", "route": "/credit-note-generator/",
        "demand": "SERP checked 3 September 2026. 'credit note generator template free' "
                  "returns Billdu, PaidNice, InvoiceHome, invoice-generator.com, DepositFix, "
                  "invoicegenerators.ai and Template.net. Several are static downloads rather "
                  "than working generators, and the intent is unambiguous and B2B -- the same "
                  "audience already using the invoice tool",
        "differentiators": [
            _d("document_structure", "References the original invoice it reverses, in full "
                                     "or in part"),
            _d("totals_logic", "Amounts are negative against the original; the running "
                               "credit is tracked against the invoice total"),
            _d("required_field", "Reason for credit, which most tax authorities expect"),
            _d("legal_wording_required", "Titled CREDIT NOTE, never invoice"),
        ],
        "product_change": "new document kind with an original-invoice reference and "
                          "sign-inverted totals",
    },
    {
        "key": "doc-delivery-note", "expected_value": 4.0,
        "value_basis": "weakest field, which is the upside, against the largest build: totals are unit counts rather than money and no existing document behaves that way", "build_scope": "product", "name": "Delivery note / packing slip",
        "route": "/delivery-note-template/",
        "demand": "SERP checked 3 September 2026. 'delivery note template free online "
                  "generator packing slip' returns DeliveryNote.io, FreeDocumentMaker, "
                  "Edit.org, InvoiceProforma, SendInvoice, AIFormatter and Enerpize -- the "
                  "weakest field of the four, several of them thin AI-generated shells. Also "
                  "the largest build: a priceless line model where totals are unit counts "
                  "rather than money, and the audience is fulfilment rather than freelancers",
        "differentiators": [
            _d("document_structure", "No prices at all: quantities shipped against "
                                     "quantities ordered"),
            _d("extra_column", "Quantity ordered, quantity delivered, quantity back-ordered"),
            _d("required_field", "Delivery address distinct from billing address, plus "
                                 "carrier and consignment reference"),
            _d("totals_logic", "Totals are unit counts, not money"),
        ],
        "product_change": "new document kind with a priceless line model, an "
                          "ordered/delivered quantity pair with the back-order shown per "
                          "line, a delivery address separate from the billing address, "
                          "and unit-count totals in place of money totals",
    },
    {
        "key": "doc-timesheet-invoice", "expected_value": 5.0,
        "value_basis": "closest to the existing invoice and cheapest to build, but the head terms are held by QuickBooks and Wave, so the realistic traffic upside is the lowest", "build_scope": "product", "name": "Timesheet invoice",
        "route": "/timesheet-invoice-generator/",
        "demand": "SERP checked 3 September 2026. 'timesheet invoice template contractor "
                  "hours' is held by incumbents -- QuickBooks, Wave, InvoiceSimple, Billdu, "
                  "eForms, MyHours -- with one small dedicated tool (GraphMaker). Strong "
                  "recurring intent among hourly workers, but the head terms are the "
                  "hardest of the four and the audience overlaps our existing users most",
        "differentiators": [
            _d("line_defaults", "Lines are dated work entries: date, hours, rate, description"),
            _d("extra_column", "Date column per line, which the invoice line model has no "
                               "concept of"),
            _d("totals_logic", "Total hours as well as total money, and both must reconcile"),
            _d("unit_defaults", "Hours as the default unit with quarter-hour increments"),
        ],
        "product_change": "new document kind with dated hour lines, hours as the default "
                          "unit, and an hours subtotal summed from the lines at "
                          "quarter-hour precision alongside the money subtotal",
    },
]

UTILITIES = [
    {
        "key": "util-late-payment", "expected_value": 6.0,
        "value_basis": "a genuine calculator earns links that no template page does, but the jurisdiction rate table is real research", "build_scope": "product", "name": "Late payment interest calculator",
        "route": "/late-payment-interest-calculator/",
        "demand": "Statutory late-payment interest is the most cited freelancer problem in "
                  "the resource pages our own outreach research surfaced",
        "differentiators": [
            _d("tax_computation", "Computes statutory interest and compensation by "
                                  "jurisdiction and days overdue"),
            _d("required_field", "Invoice date, due date, amount and jurisdiction"),
            _d("document_structure", "Produces a demand letter alongside the figure"),
            _d("validation", "Refuses date ranges that are not yet overdue"),
        ],
        "product_change": "a genuine calculator, not a page: jurisdiction rate table plus "
                          "day-count arithmetic",
    },
]

TRADES_PLACEHOLDER = [
    {
        "key": "trade-generic-copy-only", "build_scope": "content_only", "name": "Trade pages, wording only",
        "route": "/plumber-invoice-template/",
        "demand": "'plumber invoice template' has genuine search demand",
        "differentiators": [
            _d("heading", "Says plumber instead of contractor"),
            _d("description", "Mentions plumbing in the meta description"),
            _d("copy", "Examples use plumbing line items"),
        ],
        "product_change": "none: the tool behaves identically",
    },
]

CATALOG = {
    "locale": LOCALES,
    "document": DOCUMENTS,
    "utility": UTILITIES,
    "trade": TRADES_PLACEHOLDER,
}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def fact_index(connection: sqlite3.Connection) -> dict[str, dict]:
    """Per jurisdiction: how many facts are recorded, whether any are overdue,
    and whether every one of them carries a source URL.

    This is the structured source the country gate resolves against. It is read
    from the database rather than from the family definition so that a family
    cannot assert its own compliance.
    """
    today = utc_now()[:10]
    index: dict[str, dict] = {}
    for row in connection.execute(
            """SELECT jurisdiction,
                      COUNT(*) AS facts,
                      SUM(CASE WHEN reverify_by <= ? THEN 1 ELSE 0 END) AS overdue,
                      SUM(CASE WHEN COALESCE(source_url,'') = '' THEN 1 ELSE 0 END) AS unsourced,
                      MIN(reverify_by) AS next_recheck
                 FROM tax_facts GROUP BY jurisdiction""", (today,)):
        index[row["jurisdiction"]] = {
            "facts": row["facts"], "overdue": row["overdue"],
            "unsourced": row["unsourced"], "next_recheck": row["next_recheck"]}
    return index


MIN_FACTS_PER_JURISDICTION = 4


def existing_routes(connection: sqlite3.Connection) -> set[str]:
    from growth_opportunities import CANONICAL
    routes = {url.replace("https://invoiceworkshop.com", "") or "/" for url in CANONICAL}
    routes |= {row["route"] for row in connection.execute(
        "SELECT route FROM page_candidates WHERE status='shipped'")}
    return routes


def check(family: dict, *, taken: set[str], facts: dict[str, dict] | None = None) -> dict:
    """Mechanical admission test. Raises GateRefusal with the reason."""
    differentiators = family.get("differentiators") or []
    functional = [d for d in differentiators if d["kind"] in FUNCTIONAL_KINDS]
    presentational = [d for d in differentiators if d["kind"] in PRESENTATIONAL_KINDS]
    unknown = [d["kind"] for d in differentiators
               if d["kind"] not in FUNCTIONAL_KINDS | PRESENTATIONAL_KINDS]

    if unknown:
        raise GateRefusal(f"unrecognised differentiator kinds: {', '.join(sorted(set(unknown)))}")
    if not family.get("demand"):
        raise GateRefusal("no demand evidence recorded")
    if len(differentiators) < MIN_DIFFERENTIATORS:
        raise GateRefusal(f"{len(differentiators)} differentiators, "
                          f"{MIN_DIFFERENTIATORS} required")
    if len(functional) < MIN_FUNCTIONAL:
        raise GateRefusal(
            f"only {len(functional)} functional difference(s); {MIN_FUNCTIONAL} required. "
            f"Presentational differences ({', '.join(d['kind'] for d in presentational)}) "
            "describe the same tool with different wording, which is scaled content abuse "
            "and would cost the domain more than the pages could earn.")
    change = (family.get("product_change") or "").strip().lower()
    if not change or change.startswith("none"):
        raise GateRefusal("no product change named, so nothing would actually differ")
    if family.get("route") in taken:
        raise GateRefusal(f"route {family['route']} is already served")
    scope = family.get("build_scope")
    if scope not in BUILD_SCOPES:
        raise GateRefusal(f"build scope must be one of {BUILD_SCOPES}, got {scope!r}")
    sourcing = _check_sources(family, facts)
    gate = {
        "build_scope": scope,
        "differentiators": len(differentiators),
        "functional": len(functional),
        "functional_kinds": sorted({d["kind"] for d in functional}),
        "product_change": family["product_change"],
        "expected_value": family.get("expected_value", DEFAULT_VALUE),
        "value_basis": family.get("value_basis", ""),
    }
    gate.update(sourcing)
    return gate


def _check_sources(family: dict, facts: dict[str, dict] | None) -> dict:
    """A country family must be backed by recorded, sourced, unexpired facts.

    Everything a country page asserts about registration numbers, rates and
    required particulars is a claim about law. The differentiator list is written
    here, by us, so it cannot be its own evidence; the evidence is the tax_facts
    record, which carries the government URL and the date the fact was last read
    off it. A family whose facts are missing or overdue is refused until they are
    rechecked, and the refusal names what to do about it.
    """
    jurisdiction = family.get("jurisdiction")
    if not jurisdiction:
        if family["key"].startswith("locale-"):
            raise GateRefusal(
                "country family names no jurisdiction, so its legal claims cannot be "
                "resolved against a recorded source")
        return {"sourced": "not_applicable"}
    recorded = (facts or {}).get(jurisdiction)
    if not recorded or recorded["facts"] < MIN_FACTS_PER_JURISDICTION:
        have = recorded["facts"] if recorded else 0
        raise GateRefusal(
            f"only {have} verified tax fact(s) recorded for '{jurisdiction}'; "
            f"{MIN_FACTS_PER_JURISDICTION} required. Country pages state what a tax "
            "authority requires, so the rates, identifiers and required particulars must "
            "first be read off the primary government source and recorded with "
            "growth_tax_facts.py. Competitor templates are not a source.")
    if recorded["unsourced"]:
        raise GateRefusal(
            f"{recorded['unsourced']} fact(s) for '{jurisdiction}' carry no source URL")
    if recorded["overdue"]:
        raise GateRefusal(
            f"{recorded['overdue']} fact(s) for '{jurisdiction}' are past their recheck "
            f"date; recheck against the primary source before publishing more pages")
    return {"sourced": jurisdiction, "facts": recorded["facts"],
            "facts_recheck_by": recorded["next_recheck"]}


def evaluate(connection: sqlite3.Connection) -> dict:
    """Run every catalogued family through the gate and record the verdicts."""
    now = utc_now()
    taken = existing_routes(connection)
    facts = fact_index(connection)
    built = {row["family_key"] for row in connection.execute(
        "SELECT family_key FROM page_families WHERE status='built'")}
    admitted, refused, already = [], [], []
    for dimension, families in CATALOG.items():
        for family in families:
            # A family that already shipped is not a candidate; re-testing it
            # would report its own route as a duplicate of itself.
            if family["key"] in built:
                already.append(family["key"])
                continue
            try:
                gate = check(family, taken=taken, facts=facts)
                status, reason = "admitted", None
                admitted.append({"family": family["key"], "route": family["route"],
                                 "functional": gate["functional"]})
            except GateRefusal as refusal:
                gate, status, reason = {}, "refused", str(refusal)
                refused.append({"family": family["key"], "reason": reason})
            connection.execute(
                """INSERT INTO page_families
                     (family_key, dimension, name, demand_evidence, differentiation,
                      product_change, gate_json, status, refusal_reason, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(family_key) DO UPDATE SET
                     gate_json=excluded.gate_json,
                     status=CASE WHEN page_families.status='built' THEN 'built'
                                 ELSE excluded.status END,
                     refusal_reason=excluded.refusal_reason,
                     updated_at=excluded.updated_at""",
                (family["key"], dimension, family["name"], family["demand"],
                 json.dumps(family["differentiators"], sort_keys=True),
                 family["product_change"], json.dumps(gate, sort_keys=True),
                 status, reason, now, now),
            )
            if status == "admitted":
                connection.execute(
                    """INSERT INTO page_candidates
                         (slug, family_key, title, route, demand_score, differentiators,
                          status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                       ON CONFLICT(slug) DO UPDATE SET
                         differentiators=excluded.differentiators,
                         demand_score=excluded.demand_score,
                         updated_at=excluded.updated_at""",
                    (family["key"], family["key"], family["name"], family["route"],
                     float(family.get("expected_value", DEFAULT_VALUE)),
                     json.dumps(family["differentiators"], sort_keys=True), now, now),
                )
    connection.commit()
    return {
        "admitted": admitted, "refused": refused, "already_built": already,
        "admitted_count": len(admitted), "refused_count": len(refused),
        "note": ("Refusals are permanent for as long as the family cannot state two "
                 "functional differences. A page family that only changes wording is "
                 "not a slower path to the traffic target; it is the end of it."),
        "external_side_effects": "none",
    }


def queue(connection: sqlite3.Connection, limit: int = 20) -> list[dict]:
    """Admitted, unbuilt pages, most differentiated first."""
    return [dict(row) for row in connection.execute(
        """SELECT c.slug, c.title, c.route, c.demand_score, f.dimension, f.product_change
             FROM page_candidates c JOIN page_families f ON f.family_key=c.family_key
            WHERE c.status='queued' AND f.status IN ('admitted','built')
            ORDER BY c.demand_score DESC, c.slug LIMIT ?""", (limit,))]


def report(connection: sqlite3.Connection) -> dict:
    return {
        "families": [dict(row) for row in connection.execute(
            """SELECT dimension, family_key, name, status, substr(refusal_reason,1,140) reason
                 FROM page_families ORDER BY status, dimension, family_key""")],
        "queued_pages": queue(connection, 50),
        "shipped": connection.execute(
            "SELECT COUNT(*) FROM page_candidates WHERE status='shipped'").fetchone()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("evaluate", help="Run the catalogue through the admission gate")
    commands.add_parser("report", help="Families, verdicts and the build queue")
    show = commands.add_parser("queue", help="Next pages to build")
    show.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    if args.command == "evaluate":
        result = evaluate(connection)
    elif args.command == "queue":
        result = {"queue": queue(connection, args.limit)}
    else:
        result = report(connection)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
