# Search Launch Baseline

Launch timestamp: 2026-08-25 13:15 UTC

Initial launch commit: `7a43a58`

First automated `main` deployment: 2026-08-25 13:29 UTC

Cloudflare Worker version: `6a708e04-22f0-495d-a06f-845e048f8b5c`

Pre-growth hardening deployment: 2026-08-25 19:57:24 UTC

Pre-growth hardening source commit: `42698fc`

Pre-growth Cloudflare Worker version: `9d8b6428-ddff-4e17-8d24-cf88766fb8f5`

Sitemap submitted: 2026-08-25 14:42:48 UTC; processed with zero errors and zero warnings.

Indexing-request timestamp: not available. Search Console does not expose ordinary-page indexing requests through the service-account API, and the prohibited Indexing API was not used.

| Page | Primary query | Launch impressions | Launch clicks | Average position | Notes |
|---|---|---:|---:|---:|---|
| `/` | invoice generator | Pending | Pending | Pending | Economic target |
| `/proforma-invoice-generator/` | proforma invoice generator | Pending | Pending | Pending | Major wedge |
| `/quotation-generator/` | quotation generator | Pending | Pending | Pending | Early authority wedge |
| `/work-order-generator/` | work order generator | Pending | Pending | Pending | High commercial value |
| `/purchase-order-generator/` | purchase order generator | Pending | Pending | Pending | Supporting |
| `/estimate-generator/` | estimate generator | Pending | Pending | Pending | Supporting |

The Search Analytics API returned no rows for 2026-08-25, so initial impressions, clicks, queries, countries and devices remain unavailable rather than being inferred as zero. Populate them after normal reporting delay; do not interpret same-day absence as failure.

## Initial Search Console inspection

Recorded again 2026-08-25 after the pre-growth deployment:

- `/`: submitted and indexed; last crawled 15:27:37 UTC; Google-selected canonical matches the production canonical.
- `/proforma-invoice-generator/`: submitted and indexed; last crawled 19:02:51 UTC; Google-selected canonical matches the production canonical.
- `/quotation-generator/`, `/work-order-generator/`, `/purchase-order-generator/`, `/estimate-generator/` and `/contractor-invoice-template/`: discovered, currently not indexed and not yet crawled.
- `/construction-invoice-template/`: not yet known to Google.
- Indexing is allowed on both crawled pages and each fetch succeeded.
- Sitemap processing is complete with zero warnings and zero errors.

Request indexing once in Search Console URL Inspection for the six remaining non-indexed priority URLs after this deployment. Do not use the Indexing API or repeat requests. Record the actual manual request time here when complete.
