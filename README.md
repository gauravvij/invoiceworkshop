# Invoice Workshop

Production source for [InvoiceWorkshop.com](https://invoiceworkshop.com): free business-document tools that require no signup and store substantive workspace data in the user's browser.

## Architecture

- Astro static generation for crawlable HTML, metadata, navigation and content.
- One React client island powers the interactive document workspace.
- Shared TypeScript models and conversions support invoice, proforma invoice, quotation, estimate, work order, purchase order and receipt records.
- IndexedDB stores business profiles, contacts, catalog items, numbering settings and documents. `localStorage` is reserved for small interface preferences.
- Money is stored as integer minor units. Quantities are parsed at six-decimal precision and calculations use `BigInt` intermediates with explicit rounding.
- jsPDF and jsPDF-AutoTable are lazy-loaded only when a PDF is requested. This provides vector text, reliable line-item tables, repeating headers and multi-page output without transmitting document contents.
- Cloudflare Workers Static Assets serves `dist/`. A minimal Worker adds canonical `www` redirects and `X-Robots-Tag: noindex` on preview/Workers hostnames.

No account, backend database, customer API or server-side document processing exists in V1.

## Local development

Requirements: Node.js 22.12 or newer and npm 11 or newer.

```bash
npm install
cp .env.example .env
npm run dev
```

`GA4_MEASUREMENT_ID` is optional and is a public measurement identifier, not a secret. Never add customer or document data to analytics events.

## Build and test

```bash
npm run check
npm test
npm run build
npx playwright install chromium firefox webkit
npm run test:e2e
npm run lighthouse
```

The browser tests serve the built static assets, so run `npm run build` before invoking Playwright directly. CI runs unit tests, a production build, Chromium/Firefox/WebKit and mobile browser flows, SEO regression tests, accessibility checks and Lighthouse budgets. Use `npm run deploy:preview` or `wrangler dev` separately when validating Worker-specific routing and headers.

## Deployment

The repository uses Cloudflare Workers Static Assets. `wrangler.jsonc` is the source of truth and its `name` must stay `invoiceworkshop`, matching the Cloudflare Worker.

Preferred flow:

1. Connect `gauravvij/invoiceworkshop` in Cloudflare Workers Builds.
2. Production branch: `main`.
3. Build command: `npm run build`.
4. Production deploy command: `npx wrangler deploy`.
5. Preview deploy command: `npx wrangler versions upload`.
6. Enable non-production branch builds for preview versions.

Manual authenticated deployment:

```bash
CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_API_TOKEN=... npm run deploy
```

The configured custom domains are `invoiceworkshop.com` and `www.invoiceworkshop.com`; the Worker redirects `www` permanently to the canonical apex. Non-production hosts receive `X-Robots-Tag: noindex, nofollow, noarchive`.

## Analytics

GA4 is included only when `GA4_MEASUREMENT_ID` exists at build time. Allowed custom events are:

- `tool_started`
- `document_saved`
- `document_duplicated`
- `pdf_downloaded`
- `document_converted`
- `returning_workspace_loaded`

Allowed properties are `document_type`, `conversion_from` and `conversion_to`. Never add names, emails, addresses, tax IDs, document numbers, money values, bank details, line items, notes or document contents.

Cloudflare Web Analytics can be enabled from the Cloudflare dashboard for independent aggregate traffic and performance visibility.

## Privacy and recovery

All substantive document state remains on the device. The product provides explicit local backup export and permanent local-data clearing. IndexedDB schema changes must be additive and migration-safe; never delete or replace an object store without a tested migration and recovery path.

See [SEO strategy](docs/SEO_STRATEGY.md), [product principles](docs/PRODUCT_PRINCIPLES.md) and [launch checklist](docs/LAUNCH_CHECKLIST.md) before changing architecture or public URLs.
