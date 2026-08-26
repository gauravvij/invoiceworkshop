#!/usr/bin/env python3
"""Verify recorded public placements without obeying or executing page content."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from growth_common import (
    apply_schema,
    connect_db,
    database_path,
    fetch_public_url,
    normalize_public_url,
    utc_now,
)


class AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)


def same_target(candidate: str, target: str) -> bool:
    try:
        left = urlsplit(normalize_public_url(candidate))
        right = urlsplit(normalize_public_url(target))
    except ValueError:
        return False
    left_host = (left.hostname or "").removeprefix("www.")
    right_host = (right.hostname or "").removeprefix("www.")
    left_path = left.path.rstrip("/") or "/"
    right_path = right.path.rstrip("/") or "/"
    return left_host == right_host and left_path == right_path


def page_links_to(html: str, placement_url: str, target: str) -> bool:
    parser = AnchorCollector()
    parser.feed(html)
    return any(same_target(urljoin(placement_url, href), target) for href in parser.hrefs)


def verify_row(row) -> dict:
    placement_url = normalize_public_url(row["placement_url"], resolve_dns=True)
    target = normalize_public_url(row["link_target"])
    response = fetch_public_url(placement_url)
    http_ok = 200 <= response.status_code < 400
    link_present = http_ok and page_links_to(response.text, response.url, target)
    failures = 0 if link_present else row["consecutive_failures"] + 1
    if link_present:
        status = "live"
    elif failures >= 3:
        status = "dead"
    else:
        status = "suspect"
    return {
        "id": row["id"],
        "placement_url": placement_url,
        "status": status,
        "link_present": int(link_present),
        "http_status": response.status_code,
        "consecutive_failures": failures,
        "error": None if http_ok else f"HTTP {response.status_code}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db")
    args = parser.parse_args()
    connection = connect_db(database_path(args.db))
    apply_schema(connection)
    rows = connection.execute(
        """SELECT id, placement_url, link_target, consecutive_failures
             FROM placements ORDER BY id LIMIT 500"""
    ).fetchall()
    results = []
    for row in rows:
        try:
            result = verify_row(row)
        except Exception as error:
            failures = row["consecutive_failures"] + 1
            result = {
                "id": row["id"],
                "placement_url": row["placement_url"],
                "status": "dead" if failures >= 3 else "suspect",
                "link_present": 0,
                "http_status": None,
                "consecutive_failures": failures,
                "error": str(error),
            }
        connection.execute(
            """UPDATE placements
                  SET status=?, link_present=?, last_http_status=?,
                      consecutive_failures=?, verified_at=?
                WHERE id=?""",
            (
                result["status"], result["link_present"], result["http_status"],
                result["consecutive_failures"], utc_now(), result["id"],
            ),
        )
        results.append(result)
    connection.commit()
    print(json.dumps({"checked": len(results), "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
