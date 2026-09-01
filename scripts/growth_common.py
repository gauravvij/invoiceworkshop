#!/usr/bin/env python3
"""Shared, standard-library-only helpers for Level-0 growth scripts."""

from __future__ import annotations

import ipaddress
import os
import socket
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "growth.db"
SCHEMA = ROOT / "data" / "growth_schema.sql"
BASE_URL = "https://invoiceworkshop.com"
PRIORITY_PATHS = (
    "/",
    "/proforma-invoice-generator/",
    "/quotation-generator/",
    "/work-order-generator/",
    "/purchase-order-generator/",
    "/estimate-generator/",
    "/construction-invoice-template/",
    "/contractor-invoice-template/",
    "/invoice-template/",
)
PRIORITY_URLS = tuple(BASE_URL + path for path in PRIORITY_PATHS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def database_path(explicit: str | None = None) -> Path:
    return Path(explicit or os.environ.get("GROWTH_DB_PATH") or DEFAULT_DB).expanduser().resolve()


def connect_db(path: str | Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    target = database_path(str(path) if path else None)
    if read_only:
        connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def apply_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    # CREATE TABLE IF NOT EXISTS cannot add columns to an existing local growth
    # store. Keep the small Level-1A migration explicit and idempotent.
    level1a_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(level1a_actions)")
    }
    if level1a_columns and "approved_message_hashes_json" not in level1a_columns:
        connection.execute(
            "ALTER TABLE level1a_actions ADD COLUMN approved_message_hashes_json TEXT NOT NULL DEFAULT '[]'"
        )
    if level1a_columns and "execution_class" not in level1a_columns:
        connection.execute(
            "ALTER TABLE level1a_actions ADD COLUMN execution_class TEXT NOT NULL DEFAULT 'level1a_form'"
        )
        connection.execute(
            "UPDATE level1a_actions SET execution_class='level1a_email' WHERE contact_kind='email'"
        )
    if level1a_columns and "context_value" not in level1a_columns:
        connection.execute(
            "ALTER TABLE level1a_actions ADD COLUMN context_value TEXT NOT NULL DEFAULT ''"
        )
    template_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(level1a_templates)")
    }
    if template_columns and "context_template" not in template_columns:
        connection.execute(
            "ALTER TABLE level1a_templates ADD COLUMN context_template TEXT NOT NULL DEFAULT ''"
        )
    audit_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(level1a_action_audit)")
    }
    if audit_columns and "provider_thread_id" not in audit_columns:
        connection.execute(
            "ALTER TABLE level1a_action_audit ADD COLUMN provider_thread_id TEXT"
        )
    inbound_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(level1a_inbound_audit)")
    }
    if inbound_columns and "authentication_state" not in inbound_columns:
        connection.execute(
            "ALTER TABLE level1a_inbound_audit ADD COLUMN authentication_state TEXT NOT NULL DEFAULT 'unverified'"
        )
    audit_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='level1a_action_audit'"
    ).fetchone()
    audit_sql = audit_sql_row[0] if audit_sql_row else ""
    if audit_sql and "'unknown'" not in audit_sql.split("external_side_effects", 1)[-1]:
        connection.executescript(
            """
            ALTER TABLE level1a_action_audit RENAME TO level1a_action_audit_v5;
            CREATE TABLE level1a_action_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              action_id INTEGER NOT NULL REFERENCES level1a_actions(id),
              message_id TEXT NOT NULL UNIQUE,
              attempt_number INTEGER NOT NULL CHECK (attempt_number BETWEEN 0 AND 2),
              mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'live')),
              started_at TEXT NOT NULL,
              finished_at TEXT NOT NULL,
              subject TEXT NOT NULL,
              body TEXT NOT NULL,
              recipient_or_route TEXT NOT NULL,
              source_page TEXT NOT NULL,
              target_url TEXT NOT NULL,
              message_hash TEXT NOT NULL,
              validation_result TEXT NOT NULL CHECK (validation_result IN ('review_ready', 'passed', 'rejected')),
              rejection_reason TEXT,
              provider_response_id TEXT,
              provider_thread_id TEXT,
              delivery_state TEXT NOT NULL CHECK (delivery_state IN ('none', 'submitted', 'delivered', 'bounced', 'unknown')),
              reply_state TEXT,
              suppression_state TEXT NOT NULL,
              external_side_effects TEXT NOT NULL CHECK (external_side_effects IN ('none', 'email_sent', 'form_submitted', 'unknown'))
            );
            INSERT INTO level1a_action_audit
            SELECT * FROM level1a_action_audit_v5;
            DROP TABLE level1a_action_audit_v5;
            CREATE INDEX IF NOT EXISTS idx_level1a_audit_action
              ON level1a_action_audit(action_id, started_at DESC);
            """
        )
    connection.commit()


def parse_yes_no(value: str) -> int:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no"}:
        raise ValueError("expected yes or no")
    return int(normalized == "yes")


def normalize_public_url(value: str, *, resolve_dns: bool = False) -> str:
    """Validate an external URL and reject local/private-network targets."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must have a public hostname and no embedded credentials")
    if parsed.port and parsed.port not in {80, 443}:
        raise ValueError("non-standard URL ports are not allowed")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("local hostnames are not allowed")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("private or reserved IP addresses are not allowed")

    if resolve_dns:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
        if not addresses:
            raise ValueError("hostname did not resolve")
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("hostname resolves to a private or reserved IP address")

    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))


def canonical_domain(url: str) -> str:
    hostname = urlsplit(normalize_public_url(url)).hostname or ""
    return hostname.removeprefix("www.")


def fetch_public_url(url: str, *, timeout: int = 20, max_redirects: int = 5):
    """GET a public URL with every redirect target validated before access."""
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "InvoiceWorkshop-Level0/1.0 (+https://invoiceworkshop.com/)"
    })
    current = normalize_public_url(url, resolve_dns=True)
    started = time.monotonic()
    for _ in range(max_redirects + 1):
        response = session.get(current, allow_redirects=False, timeout=timeout)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            if not location:
                response.close()
                raise RuntimeError(f"redirect from {current} did not include a Location header")
            current = normalize_public_url(urljoin(current, location), resolve_dns=True)
            response.close()
            continue
        response.elapsed_total_ms = round((time.monotonic() - started) * 1000)
        return response
    raise RuntimeError(f"too many redirects while fetching {url}")
