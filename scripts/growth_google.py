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
