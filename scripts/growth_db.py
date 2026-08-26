#!/usr/bin/env python3
"""Deterministic CLI for InvoiceWorkshop's local Level-0 research store."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from growth_common import (
    apply_schema,
    canonical_domain,
    connect_db,
    database_path,
    normalize_public_url,
    parse_yes_no,
    utc_now,
)

PROSPECT_TYPES = ("resource", "editorial", "directory", "community", "discovery", "broken", "gap", "other")


def initialize(path: Path) -> sqlite3.Connection:
    connection = connect_db(path)
    apply_schema(connection)
    return connection


def cmd_init(args: argparse.Namespace) -> None:
    connection = initialize(database_path(args.db))
    version = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    print(json.dumps({"database": str(database_path(args.db)), "schema_version": int(version), "status": "ready"}))


def cmd_add_prospect(args: argparse.Namespace) -> None:
    page_url = normalize_public_url(args.page_url)
    source_url = normalize_public_url(args.source_url)
    domain = canonical_domain(page_url)
    now = utc_now()
    connection = initialize(database_path(args.db))
    values = {
        "domain": domain,
        "page_url": page_url,
        "prospect_type": args.type,
        "opportunity_score": args.score,
        "risk": args.risk,
        "why_fit": args.why_fit.strip(),
        "audience": args.audience.strip(),
        "contact_method": args.contact_method.strip(),
        "requires_account": parse_yes_no(args.requires_account),
        "requires_payment": parse_yes_no(args.requires_payment),
        "link_type": args.link_type.strip() or "unknown",
        "source_url": source_url,
        "status": args.status,
        "rejection_reason": args.rejection_reason.strip() or None,
        "notes": args.notes.strip(),
        "discovered_at": now,
        "updated_at": now,
    }
    if not values["why_fit"] or not values["audience"] or not values["contact_method"]:
        raise SystemExit("why-fit, audience, and contact-method must contain verified facts")
    if args.status == "rejected" and not values["rejection_reason"]:
        raise SystemExit("rejected prospects require --rejection-reason")
    try:
        cursor = connection.execute(
            """INSERT INTO prospects (
                   domain, page_url, prospect_type, opportunity_score, risk,
                   why_fit, audience, contact_method, requires_account,
                   requires_payment, link_type, source_url, status,
                   rejection_reason, notes, discovered_at, updated_at
               ) VALUES (
                   :domain, :page_url, :prospect_type, :opportunity_score, :risk,
                   :why_fit, :audience, :contact_method, :requires_account,
                   :requires_payment, :link_type, :source_url, :status,
                   :rejection_reason, :notes, :discovered_at, :updated_at
               )""",
            values,
        )
        connection.commit()
        print(json.dumps({"id": cursor.lastrowid, "status": "added", "domain": domain, "page_url": page_url}))
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed" not in str(error):
            raise
        existing = connection.execute(
            "SELECT id FROM prospects WHERE domain=? AND page_url=?", (domain, page_url)
        ).fetchone()
        print(json.dumps({"id": existing["id"], "status": "duplicate", "domain": domain, "page_url": page_url}))


def cmd_list(args: argparse.Namespace) -> None:
    connection = initialize(database_path(args.db))
    rows = connection.execute(
        """SELECT id, domain, page_url, prospect_type, opportunity_score, risk,
                  why_fit, audience, contact_method, requires_account,
                  requires_payment, link_type, source_url, status,
                  external_action_approved, notes, discovered_at
             FROM prospects
            WHERE (? IS NULL OR status = ?)
            ORDER BY opportunity_score DESC, id ASC
            LIMIT ?""",
        (args.status, args.status, args.limit),
    ).fetchall()
    print(json.dumps([dict(row) for row in rows], indent=2, sort_keys=True))


def cmd_status(args: argparse.Namespace) -> None:
    connection = initialize(database_path(args.db))
    tables = ("collection_runs", "level0_runs", "metrics_daily", "gsc_breakdowns", "url_health", "index_state", "prospects", "outreach", "placements", "experiments")
    counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
    version = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    print(json.dumps({"database": str(database_path(args.db)), "schema_version": int(version), "counts": counts}, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db", help="Override the database path (or use GROWTH_DB_PATH)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init").set_defaults(handler=cmd_init)

    add = commands.add_parser("add-prospect", help="Insert one externally read-only research finding")
    add.add_argument("--page-url", required=True)
    add.add_argument("--source-url", required=True, help="Public page that supports the finding")
    add.add_argument("--type", required=True, choices=PROSPECT_TYPES)
    add.add_argument("--score", required=True, type=int, choices=range(0, 101), metavar="0..100")
    add.add_argument("--risk", required=True, choices=("low", "medium", "high"))
    add.add_argument("--why-fit", required=True)
    add.add_argument("--audience", required=True)
    add.add_argument("--contact-method", required=True)
    add.add_argument("--requires-account", required=True, choices=("yes", "no"))
    add.add_argument("--requires-payment", required=True, choices=("yes", "no"))
    add.add_argument("--link-type", default="unknown")
    add.add_argument("--status", default="new", choices=("new", "qualified", "rejected"))
    add.add_argument("--rejection-reason", default="")
    add.add_argument("--notes", default="")
    add.set_defaults(handler=cmd_add_prospect)

    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=50, choices=range(1, 501), metavar="1..500")
    listing.add_argument("--status", choices=("new", "qualified", "rejected", "retired"))
    listing.set_defaults(handler=cmd_list)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    return root


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
