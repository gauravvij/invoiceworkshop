# Launch Checklist

Status legend: `[x]` verified, `[ ]` incomplete or awaiting production verification.

## Domain and infrastructure

- [x] `https://invoiceworkshop.com/` serves the production build.
- [x] HTTP redirects to HTTPS.
- [x] `www` redirects to the canonical apex.
- [x] Production certificate is valid.
- [x] Worker name and `wrangler.jsonc` name are both `invoiceworkshop`.
- [ ] GitHub deployment is connected and verified.
- [ ] Non-production branch previews are verified.
- [x] Non-canonical Worker hosts receive a noindex response header in Worker code.

## SEO

- [x] Required canonical public pages are statically generated.
- [x] Exactly one H1, unique title, description and self-canonical are covered by automated tests.
- [x] Sitemap and robots files are generated and covered by tests.
- [x] Priority pages have crawlable contextual links.
- [x] Synonym invoice-generator routes redirect to `/`.
- [x] Truthful WebSite, SoftwareApplication and Breadcrumb structured data are present.
- [x] Branded 1200×630 social image and page-level Open Graph/Twitter metadata are present.
- [x] Search Console DNS verification TXT record exists in Cloudflare.
- [ ] Sitemap is submitted in Search Console.
- [ ] Priority URLs are requested for initial indexing.

## Product

- [x] Shared typed model covers invoice, proforma, quotation, estimate, work order, purchase order and receipt.
- [x] Business, customer, dates, currency, items, quantity, price, tax, discount, shipping, adjustment, notes, payment and terms are editable.
- [x] Construction/contractor project, jobsite, deposit and progress/change fields are supported.
- [x] Autosave, visible state, refresh recovery and IndexedDB error handling are implemented.
- [x] Saved customers and reusable catalog items are implemented.
- [x] Duplicate and required conversion paths are implemented.
- [x] PDF and print output are client-side; PDF code is lazy-loaded.
- [x] Local backup export and clear-data controls are implemented.

## Testing and performance

- [x] Type checks and production static build pass.
- [x] Unit tests cover money, rounding, conversions, numbering and serialization.
- [x] Browser flows, SEO and accessibility suites exist.
- [ ] Chromium, Firefox, WebKit and mobile suites pass in CI.
- [x] Lighthouse reports for four key pages meet launch budgets and are saved.
- [ ] Manual PDF/logo/print inspection is complete in current Chrome, Edge, Safari and Firefox.

## Privacy and security

- [x] No document state is sent to application servers or put in URLs.
- [x] GA4 is environment-controlled and event properties are allowlisted.
- [x] Security headers and CSP are configured in `_headers`.
- [x] `.env` and local secrets are excluded from Git.
- [x] Production response headers are verified.
- [x] Dependency audit has no unresolved critical issues (production dependencies: zero known vulnerabilities).

## Post deployment

- [ ] Enable Cloudflare Web Analytics.
- [ ] Verify GA4 page views and privacy-safe product events.
- [x] Record production launch timestamp and commit in `SEARCH_BASELINE.md`.
- [ ] Record initial Search Console measurements when available.
