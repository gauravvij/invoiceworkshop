# Metrics (operating)

## Hierarchy (priority order)
1. Qualified users (tool starts, PDF downloads, returning-workspace loads)
2. Real editorial/relevant mentions
3. Relevant referring domains
4. Search Console impressions (US first)
5. Ranking movement
6. Repeat/direct usage
7. Raw backlink count (intentionally LAST — do not optimise for it)

## Measurement sources
- **GSC Search Analytics API** (read-only): impressions, clicks, CTR, position across
  query/page/country/device/date.
- **GA4 Data API** (read-only): sessions, users, pageviews, `tool_started`,
  `pdf_downloaded`, and `returning_workspace_loaded`.
- **Search Console URL Inspection API** (read-only): the index state of each canonical
  priority URL. Search Analytics impressions are not an indexation count.
- Public HTTP GETs and the Search Console Sitemaps API: URL and sitemap health.
- Placement state from the local CRM and `growth_verify.py`. Referring-domain and referral
  traffic collection is not implemented; never infer either from placements.

Ranking buckets:
- >50 monitor · 21–50 improving → possible · 11–20 high-priority · 4–10 very-high
  (understand why not Top 3) · 1–3 protect/expand only on evidence.

## Proposed cadence (jobs remain paused until owner activation)
- Daily: deterministic measure, snapshot, placement verification, and bounded prospect
  discovery.
- Weekly: review seven-day evidence and write a recommendation only.

## Snapshot semantics
`metrics_daily` stores actual per-calendar-day GSC and GA4 values. The collector refreshes
recent days to absorb reporting delay. Query/page/country/device aggregates are stored
separately, as are URL Inspection, sitemap, and HTTP-health results.

## Honesty rule
- Never infer an absent measurement. Mark it `UNVALIDATED`. Do not claim gains without a
  snapshot diff. RPM/ad-heavy maths (e.g. $10K/mo requires ~0.5M–1M+ ad impressions at
  ~$10–25 RPM) is ASSUMED until observed.
