#!/usr/bin/env python3
"""Telling crawlers about our URLs directly, rather than waiting to be found.

Every page on the site is currently `discovered_not_crawled`: Google holds the
URL and has never fetched it. Rewriting a page Google has not read cannot help,
which leaves two levers -- authority, and telling a crawler directly.

IndexNow is the second one. It is an open protocol Bing, Yandex, Seznam and
Naver all consume from a single POST, it needs no account and no verification
beyond a key file served from the site itself, and Bing acts on it in hours
rather than the weeks Google is taking. Bing traffic is real traffic, and a page
indexed anywhere is a page that can be linked from anywhere.

The protocol asks that a URL is submitted when its content changed, not on a
schedule. So this fetches each URL, hashes what is actually live, and submits
only the ones whose hash differs from what was last sent. A run where nothing
changed sends nothing and says so -- that is the correct outcome, not a failure.

Google is the other half. It does not take IndexNow, but it does re-fetch a
sitemap on request, and on 4 September it was working from a copy downloaded on
1 September listing 13 URLs when the live file listed 22 -- nine pages it simply
did not know about. `sitemap` compares Google's count against the live one and
resubmits when they disagree, which is a request to re-fetch and nothing more.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import urllib.error
import urllib.request

from growth_common import apply_schema, connect_db, database_path, utc_now

SITE = "https://invoiceworkshop.com"
SITEMAP = f"{SITE}/sitemap.xml"

# The key is public by design: IndexNow authenticates by requiring the same
# value to be served from the host being submitted, which is what proves control
# of the domain. There is nothing secret to leak here.
KEY = "46cc4cdaa10ab90aec425bc943e6b305"
KEY_LOCATION = f"{SITE}/{KEY}.txt"

# One endpoint is enough. api.indexnow.org shares a submission with every
# participating engine, so posting to each engine separately would be the same
# URLs four times over.
ENDPOINT = "https://api.indexnow.org/indexnow"

USER_AGENT = "InvoiceWorkshop-IndexNow/1.0 (+https://invoiceworkshop.com/)"
TIMEOUT = 30

# IndexNow accepts up to 10,000 URLs per request. The site is nowhere near that,
# but batching keeps a future large sitemap from silently failing.
BATCH = 500


def _get(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def sitemap_urls() -> list[str]:
    status, body = _get(SITEMAP)
    if status != 200:
        raise SystemExit(f"sitemap returned {status}, so there is no URL list to submit")
    return re.findall(r"<loc>([^<]+)</loc>", body.decode("utf-8", "replace"))


def _live_hash(url: str) -> str | None:
    """The hash of what a crawler would actually be sent.

    A URL that is not returning 200 is not submitted at all: asking an engine to
    index a page that is erroring is how a host loses IndexNow access.
    """
    status, body = _get(url)
    if status != 200:
        return None
    return hashlib.sha256(body).hexdigest()


def changed(connection: sqlite3.Connection, *, force: bool = False) -> list[dict]:
    """URLs whose live content differs from what was last submitted."""
    known = {
        row["url"]: row["content_hash"]
        for row in connection.execute("SELECT url, content_hash FROM indexnow_submissions")
    }
    pending = []
    for url in sitemap_urls():
        digest = _live_hash(url)
        if digest is None:
            continue
        if force or known.get(url) != digest:
            pending.append({"url": url, "content_hash": digest})
    return pending


def submit(connection: sqlite3.Connection, *, force: bool = False, dry_run: bool = False) -> dict:
    pending = changed(connection, force=force)
    if not pending:
        return {"submitted": 0, "outcome": "nothing changed since the last submission"}
    if dry_run:
        return {"submitted": 0, "would_submit": [entry["url"] for entry in pending],
                "outcome": "dry run"}

    now = utc_now()
    results = []
    for start in range(0, len(pending), BATCH):
        batch = pending[start:start + BATCH]
        payload = json.dumps({
            "host": SITE.split("//", 1)[1],
            "key": KEY,
            "keyLocation": KEY_LOCATION,
            "urlList": [entry["url"] for entry in batch],
        }).encode("utf-8")
        request = urllib.request.Request(
            ENDPOINT, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8",
                     "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                status = response.status
                response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            error.read()
        except urllib.error.URLError as error:
            status = 0
            results.append({"count": len(batch), "status": 0, "error": str(error.reason)})

        # 200 accepted, 202 accepted but the key is still being validated. Both
        # mean the URLs are in; anything else means they are not, and recording
        # the hash anyway would suppress the retry.
        accepted = status in (200, 202)
        outcome = "accepted" if accepted else f"rejected ({status})"
        results.append({"count": len(batch), "status": status, "outcome": outcome})
        if accepted:
            connection.executemany(
                """INSERT INTO indexnow_submissions
                     (url, content_hash, last_submitted_at, http_status, outcome)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                     content_hash=excluded.content_hash,
                     last_submitted_at=excluded.last_submitted_at,
                     http_status=excluded.http_status,
                     outcome=excluded.outcome""",
                [(entry["url"], entry["content_hash"], now, status, outcome) for entry in batch],
            )
            connection.commit()

    submitted = sum(r["count"] for r in results if r.get("outcome") == "accepted")
    return {"submitted": submitted, "batches": results,
            "urls": [entry["url"] for entry in pending][:50]}


# The site: operator on a plain search page. It is a coarse instrument -- engines
# sample it and it is not an index count -- but the distinction that matters here
# is zero versus not zero, and it needs no account to read.
COVERAGE = {
    "bing": "https://www.bing.com/search?q=site%3Ainvoiceworkshop.com&count=30",
    "duckduckgo": "https://html.duckduckgo.com/html/?q=site%3Ainvoiceworkshop.com",
}


def coverage(connection: sqlite3.Connection, *, record: bool = True) -> dict:
    """How many of our own URLs an engine will admit to holding."""
    today = utc_now()[:10]
    results = {}
    for engine, query in COVERAGE.items():
        status_code, body = _get(query)
        if status_code != 200:
            results[engine] = {"error": f"query returned {status_code}"}
            continue
        seen = sorted(set(re.findall(
            r"https://invoiceworkshop\.com/[a-z0-9\-/]*", body.decode("utf-8", "replace"))))
        results[engine] = {"urls_seen": len(seen), "sample": seen[:10]}
        if record:
            connection.execute(
                """INSERT INTO search_coverage (observed_on, engine, urls_seen, sample_json, note)
                   VALUES (?, ?, ?, ?, '')
                   ON CONFLICT(observed_on, engine) DO UPDATE SET
                     urls_seen=excluded.urls_seen, sample_json=excluded.sample_json""",
                (today, engine, len(seen), json.dumps(seen[:20])),
            )
    if record:
        connection.commit()
    return {"observed_on": today, "engines": results}


GSC_SITE = "sc-domain:invoiceworkshop.com"


def sitemap(connection: sqlite3.Connection, *, force: bool = False) -> dict:
    """Resubmit the sitemap when Google is working from a stale copy of it."""
    from growth_google import GoogleSitemapClient

    live = len(sitemap_urls())
    client = GoogleSitemapClient()
    before = client.sitemap_state(GSC_SITE, SITEMAP)
    stale = before["urls_google_has"] != live
    if not (stale or force):
        return {"live_urls": live, "google_has": before["urls_google_has"],
                "action": "none: Google's copy matches the live sitemap", "state": before}
    after = client.submit_sitemap(GSC_SITE, SITEMAP)
    return {"live_urls": live, "google_had": before["urls_google_has"],
            "google_has": after["urls_google_has"],
            "action": "resubmitted", "state": after}


def status(connection: sqlite3.Connection) -> dict:
    rows = [dict(row) for row in connection.execute(
        "SELECT url, last_submitted_at, http_status, outcome FROM indexnow_submissions"
        " ORDER BY last_submitted_at DESC")]
    key_status, key_body = _get(KEY_LOCATION)
    return {
        "key_file": KEY_LOCATION,
        "key_file_serving": key_status == 200 and key_body.decode("utf-8", "replace").strip() == KEY,
        "submitted_urls": len(rows),
        "sitemap_urls": len(sitemap_urls()),
        "recent": rows[:10],
        "coverage": [dict(row) for row in connection.execute(
            "SELECT observed_on, engine, urls_seen FROM search_coverage"
            " ORDER BY observed_on DESC, engine LIMIT 6")],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["submit", "status", "changed", "coverage", "sitemap"])
    parser.add_argument("--force", action="store_true",
                        help="resubmit every live URL, not only the changed ones")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    connection = connect_db(args.db or database_path())
    apply_schema(connection)

    if args.command == "submit":
        result = submit(connection, force=args.force, dry_run=args.dry_run)
    elif args.command == "sitemap":
        result = sitemap(connection, force=args.force)
    elif args.command == "coverage":
        result = coverage(connection)
    elif args.command == "changed":
        result = {"changed": [entry["url"] for entry in changed(connection, force=args.force)]}
    else:
        result = status(connection)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
