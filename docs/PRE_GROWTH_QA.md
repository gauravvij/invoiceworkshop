# Pre-Growth QA Record

Verification date: 2026-08-25 UTC

Production hardening source commit: `42698fc`

Production deployment: 2026-08-25 19:57:24 UTC; Cloudflare Worker version `9d8b6428-ddff-4e17-8d24-cf88766fb8f5` at 100%.

## Build and automated coverage

- `npm test`: 15 unit tests passed.
- `npm run build`: Astro type check and production build passed with 14 static pages and no errors, warnings or hints.
- Playwright: 57 tests passed with 11 intentional environment skips across Chromium, Firefox, WebKit and mobile Chromium.
- GitHub Actions quality run: unit/build, browser tests, Lighthouse and Cloudflare deployment passed.
- Production dependencies: `npm audit --omit=dev` reported zero known vulnerabilities and no critical production issue remains.

## PDF and print inspection

A realistic invoice was generated in Chromium as a two-page Letter PDF. It contained a logo, long business and customer identities, complete addresses and contact fields, 14 line items, a long description, quantities, rates, discount, tax, shipping, adjustment, notes, payment instructions and terms.

The rendered pages were inspected visually. Logo aspect ratio and clarity, fonts, currency formatting, calculations, table alignment, repeated table header, row page breaks, notes, footer page numbers, margins, filename and page count passed. No content was clipped, no blank page was created and no InvoiceWorkshop promotional branding appeared in the PDF or print output. Extracted PDF text was also checked for the removed promotional phrases.

The same functional suite passed current Chromium, Firefox and WebKit engines. Branded Microsoft Edge and Apple Safari are not installed in the Linux QA environment; a final hands-on vendor-browser check remains an explicitly external manual check, not a known defect.

## Mobile and local persistence

The phone-sized Chromium flow passed: business and customer entry, multiple items, preview, PDF download, refresh persistence, saved-customer reuse and duplication. The fixed mobile Download PDF bar remained visible.

IndexedDB schema v1-to-v2 migration, refresh recovery and malformed-record recovery passed. The database has an explicit version, preserves valid records during upgrade, aborts failed upgrades safely, closes on version change and filters or normalizes malformed stored entries.

## Privacy and analytics

A production browser-network canary used unique business, customer, email, address, tax ID, line-item, bank and note values. None appeared in any request URL, query string or body. The only observed third-party services were Google Analytics 4 and Cloudflare Web Analytics. Product analytics contained only allowlisted event names and abstract document/conversion types.

GA4 property `551485207` is configured from a deployment environment variable, disables Google signals in the page configuration and delays the analytics library until interaction or an eight-second fallback. Event names and event properties are allowlisted in code. Its 2026-08-25 report contained:

| Event | Event count | Users |
|---|---:|---:|
| `page_view` | 108 | 93 |
| `tool_started` | 9 | 9 |
| `returning_workspace_loaded` | 6 | 1 |
| `document_converted` | 5 | 3 |
| `document_saved` | 4 | 4 |
| `pdf_downloaded` | 2 | 2 |
| `document_duplicated` | 1 | 1 |

These same-day counts include QA traffic and are validation evidence, not an acquisition benchmark. Cloudflare Web Analytics uses automatic beacon injection; its script returned 200 and its RUM request was observed without document content.

## Preview and production SEO

PR preview `https://pr-1-invoiceworkshop.gaurav-vij137.workers.dev/` returned HTTP 200 with an effective `X-Robots-Tag: noindex`. Its canonical and Open Graph URL pointed to `https://invoiceworkshop.com/`. The preview hostname was absent from the production sitemap. Production returned HTTP 200 without a noindex header.

The production crawl covered all 13 canonical public pages. Each returned 200 with one H1, a unique title and useful description, self-canonical, matching Open Graph URL, valid JSON-LD, sitemap inclusion and a crawlable internal link. No broken internal link, image, localhost/staging reference, query-state canonical or malformed schema was found. Synonym invoice URLs redirect directly to `/`.

## Production Lighthouse baseline

Single-run Lighthouse measurements from 2026-08-25 UTC:

| Page | Performance | Accessibility | Best practices | SEO | LCP | CLS | TBT |
|---|---:|---:|---:|---:|---:|---:|---:|
| `/` | 98 | 100 | 100 | 100 | 1,788 ms | 0 | 70 ms |
| `/proforma-invoice-generator/` | 98 | 100 | 100 | 100 | 1,873 ms | 0 | 41 ms |
| `/quotation-generator/` | 98 | 100 | 100 | 100 | 1,844 ms | 0 | 87 ms |
| `/work-order-generator/` | 98 | 100 | 100 | 100 | 1,824 ms | 0 | 82 ms |

CI also retained its three-run local Lighthouse artifacts and passed the configured performance, accessibility, best-practices, SEO, LCP, CLS and TBT budgets.

## External manual follow-ups

- In Search Console URL Inspection, request indexing once for the six remaining non-indexed priority URLs listed in `SEARCH_BASELINE.md`, then record the actual time. The service-account API is read-only for ordinary-page indexing and Google's Indexing API was intentionally not used.
- Perform the final hands-on smoke check in branded Microsoft Edge and Apple Safari when those vendor browsers/devices are available. Chromium, Firefox and WebKit engine automation is green and no browser-engine defect is known.
- In Cloudflare, open Workers & Pages > `invoiceworkshop` > Settings > Builds and disconnect the native repository build. GitHub Actions is the verified deployment source of truth; the native integration is redundant and currently posts an immediate failed check without affecting the successful production deployment. The present account-owned API token works for Workers deployment but Cloudflare's Builds API rejects it as an invalid user-scoped token, so this dashboard-only cleanup was not performed programmatically.
