#!/usr/bin/env python3
"""Narrow read-only Google API client used by Level-0 collectors."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from growth_common import ROOT

READ_ONLY_SCOPES = (
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
)


# Sitemap submission is the one write this system does against Google, and it is
# kept in its own client with its own scope so the read path stays read-only by
# construction rather than by convention. Submitting an already-submitted sitemap
# is idempotent: it asks Google to re-fetch, nothing more.
SITEMAP_WRITE_SCOPES = ("https://www.googleapis.com/auth/webmasters",)


class GoogleReadError(RuntimeError):
    pass


class GoogleReadClient:
    def __init__(self, credential_path: str | None = None, timeout: int = 30):
        self.credential_path = Path(
            credential_path
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or ROOT / ".env.google-service-account.json"
        ).expanduser().resolve()
        if not self.credential_path.is_file():
            raise GoogleReadError(f"service-account credential not found: {self.credential_path}")
        credentials = service_account.Credentials.from_service_account_file(
            self.credential_path, scopes=READ_ONLY_SCOPES
        )
        credentials.refresh(Request())
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {credentials.token}"})
        self.timeout = timeout

    def _json(self, method: str, url: str, **kwargs):
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if not response.ok:
            detail = response.text.replace("\n", " ")[:500]
            raise GoogleReadError(f"{method} {url} -> HTTP {response.status_code}: {detail}")
        return response.json()

    def list_gsc_sites(self):
        return self._json("GET", "https://www.googleapis.com/webmasters/v3/sites")

    def query_gsc(self, site: str, body: dict):
        encoded = quote(site, safe="")
        return self._json(
            "POST",
            f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query",
            json=body,
        )

    def list_sitemaps(self, site: str):
        encoded = quote(site, safe="")
        return self._json("GET", f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/sitemaps")

    def inspect_url(self, site: str, url: str):
        return self._json(
            "POST",
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
            json={"inspectionUrl": url, "siteUrl": site, "languageCode": "en-US"},
        )

    def account_summaries(self):
        return self._json("GET", "https://analyticsadmin.googleapis.com/v1beta/accountSummaries")

    def list_data_streams(self, property_id: str):
        return self._json(
            "GET", f"https://analyticsadmin.googleapis.com/v1beta/properties/{property_id}/dataStreams"
        )

    def run_ga_report(self, property_id: str, body: dict):
        return self._json(
            "POST",
            f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
            json=body,
        )


class GoogleSitemapClient(GoogleReadClient):
    """Resubmits the sitemap. Deliberately the only writing this does.

    Google had downloaded the sitemap on 1 September and recorded 13 URLs when
    the live file listed 22: nine pages shipped after its last fetch were absent
    from Google's view of the site, and it re-fetches on its own schedule. A
    submission asks for that fetch instead of waiting for it.
    """

    def __init__(self, credential_path: str | None = None, timeout: int = 30):
        super().__init__(credential_path, timeout)
        credentials = service_account.Credentials.from_service_account_file(
            str(self.credential_path), scopes=SITEMAP_WRITE_SCOPES
        )
        credentials.refresh(Request())
        self.session.headers.update({"Authorization": f"Bearer {credentials.token}"})

    def _sitemap_url(self, site: str, sitemap: str) -> str:
        return (f"https://www.googleapis.com/webmasters/v3/sites/{quote(site, safe='')}"
                f"/sitemaps/{quote(sitemap, safe='')}")

    def submit_sitemap(self, site: str, sitemap: str) -> dict:
        response = self.session.put(self._sitemap_url(site, sitemap), timeout=self.timeout)
        if not response.ok:
            raise GoogleReadError(f"sitemap submit returned {response.status_code}: {response.text[:200]}")
        return self.sitemap_state(site, sitemap)

    def sitemap_state(self, site: str, sitemap: str) -> dict:
        response = self.session.get(self._sitemap_url(site, sitemap), timeout=self.timeout)
        if not response.ok:
            raise GoogleReadError(f"sitemap read returned {response.status_code}")
        body = response.json()
        contents = (body.get("contents") or [{}])[0]
        return {
            "path": body.get("path"),
            "last_submitted": body.get("lastSubmitted"),
            "last_downloaded": body.get("lastDownloaded"),
            "pending": body.get("isPending"),
            "urls_google_has": int(contents.get("submitted", 0) or 0),
            "urls_google_indexed": int(contents.get("indexed", 0) or 0),
            "errors": int(body.get("errors", 0) or 0),
            "warnings": int(body.get("warnings", 0) or 0),
        }
