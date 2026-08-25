# Mission

Design, implement, test and deploy the complete production website for:

**https://invoiceworkshop.com**

This is an SEO-first, free business-document utility. The business model will eventually be display advertising, but the initial launch objective is:

1. Build the best genuinely useful free invoice-generation experience possible.
2. Establish InvoiceWorkshop.com as a topical authority around business-document creation.
3. Rank first for easier supporting transactional queries.
4. Progressively compete for the high-value U.S. query cluster around **invoice generator**.
5. Create repeat/direct usage by making the product behave like persistent software without requiring an account.

Treat **SEO, product quality, speed, crawlability and user retention as equal engineering requirements**.

Do not treat SEO as a later content-marketing task.

---

# Core positioning

Product concept:

> **Free business paperwork tools. No signup. Your business details stay saved in your browser.**

Central differentiator:

> **No signup, but it remembers you.**

A visitor should be able to:

* create a professional document immediately
* save their business details locally
* save clients locally
* save reusable products/services locally
* return later and continue working
* duplicate documents
* convert related business documents
* download professional PDFs
* do all of this without creating an account

Initial document workflow:

**Quotation / Estimate → Work Order → Invoice → Receipt**

And separately:

**Purchase Order**

and:

**Proforma Invoice → Invoice**

All private business/customer/document data should stay on the user's device in V1.

---

# Technology requirements

Use:

* **Astro**
* **TypeScript**
* React only for interactive islands/components where necessary
* Cloudflare **Workers Static Assets**
* GitHub
* Cloudflare Workers Builds / Git integration
* IndexedDB for substantive local data
* localStorage only for lightweight preferences
* client-side PDF generation

Prefer static generation.

Do **not** use SSR unless there is a demonstrated requirement that cannot reasonably be solved statically.

Cloudflare currently supports static Astro sites directly through Workers Static Assets; a purely pre-rendered Astro site does not require the Cloudflare Astro adapter.

Do not use:

* EC2
* VPS
* Kubernetes
* traditional backend server
* WordPress
* Firebase
* Supabase
* D1 initially
* R2 initially
* KV initially
* Durable Objects initially
* external database
* user authentication
* unnecessary APIs

Do not turn this into an infrastructure project.

The initial application should be almost entirely:

**Cloudflare static hosting + browser state.**

---

# Cloudflare deployment

Deploy production through Cloudflare Workers Static Assets.

The repository must include a valid `wrangler.jsonc`.

Use the current compatibility date at implementation time.

The Worker/project name must remain consistent between the Cloudflare project and Wrangler configuration because Cloudflare requires this for repository-connected builds.

Connect the GitHub repository to Cloudflare Workers Builds.

Expected flow:

`feature branch → tests → PR → preview build → main → production`

Cloudflare supports automatic deployments on GitHub pushes and preview versions for non-production branches.

Production custom domain:

**invoiceworkshop.com**

Redirect:

**[www.invoiceworkshop.com](http://www.invoiceworkshop.com) → https://invoiceworkshop.com/**

Only one hostname should be canonical.

---

# URL strategy — CRITICAL

Do not invent SEO pages.

Do not generate hundreds of programmatic URLs.

Do not create separate pages merely for close keyword variants.

Initial indexable architecture:

### Homepage

`/`

This IS the primary Invoice Generator.

There must NOT also be a duplicate `/invoice-generator/`.

The homepage targets the entire core intent cluster:

* invoice generator
* free invoice generator
* invoice maker
* invoice builder
* invoice creator
* online invoice tool
* invoice generator with logo

These belong on ONE canonical page.

---

### Supporting pages

`/proforma-invoice-generator/`

`/quotation-generator/`

`/work-order-generator/`

`/purchase-order-generator/`

`/estimate-generator/`

`/construction-invoice-template/`

`/contractor-invoice-template/`

`/invoice-template/`

Also create essential trust/system pages:

`/about/`

`/privacy/`

`/terms/`

`/contact/`

`/404.html`

Do not create:

`/invoice-maker/`

`/invoice-builder/`

`/free-invoice-generator/`

`/online-invoice-generator/`

or similar synonym pages.

All of those intents consolidate into `/`.

Google explicitly recommends canonical consolidation for duplicate/similar URLs and warns against unnecessary URL duplication.

---

# Keyword priority

SEO effort should follow this order.

## Economic target

### Homepage `/`

Primary:

**invoice generator**

Secondary/natural variants:

* free invoice generator
* invoice maker
* invoice builder
* invoice creator
* online invoice tool
* invoice generator with logo

This page receives the strongest internal authority.

---

## Major wedge

### `/proforma-invoice-generator/`

Target:

* proforma invoice
* pro forma invoice
* proforma invoice generator
* proforma invoice template

This is one of the most strategically important supporting pages.

---

## Early authority wedge

### `/quotation-generator/`

Target:

* quotation generator
* quotation maker
* business quotation generator
* business quote generator

Do not over-optimize ambiguous inspirational “quote generator” intent.

---

## High-commercial-value supporting page

### `/work-order-generator/`

Target:

* work order generator
* free work order generator
* work order maker

---

## Supporting procurement page

### `/purchase-order-generator/`

Target:

* purchase order generator
* PO generator
* purchase order maker

---

## Supporting page

### `/estimate-generator/`

Target:

* estimate generator
* estimate maker
* free estimate
* estimate template where contextually appropriate

---

## Vertical opportunities

### `/construction-invoice-template/`

Must be a genuine construction-specific generator/template, not the generic invoice page with the word “construction” substituted.

Support fields/features relevant to construction such as:

* jobsite
* labor
* materials
* deposits
* progress billing if practical
* change-order references
* notes
* payment terms

### `/contractor-invoice-template/`

Likewise, make this genuinely contractor-specific.

Do not generate dozens of trade-specific pages without evidence of demand.

---

# Product architecture

Create a shared typed document model rather than separate incompatible tools.

Conceptually:

```text
BusinessProfile
Client
CatalogItem
DocumentBase
LineItem
Money
Tax
Discount
PaymentTerms
DocumentMetadata
```

Then document types:

```text
Invoice
ProformaInvoice
Quotation
Estimate
WorkOrder
PurchaseOrder
Receipt
```

Build conversion functions cleanly:

```text
quotation → invoice
estimate → workOrder
estimate → invoice
workOrder → invoice
proforma → invoice
invoice → receipt
```

Conversions should preserve relevant fields so the user does not retype data.

---

# Local persistence

Use IndexedDB.

Persist locally:

* business profile
* logo where practical
* address
* tax/business identifier
* payment instructions
* default currency
* default tax settings
* default terms
* customers
* common products/services
* draft documents
* completed documents
* document numbering preferences

Use localStorage only for small preferences such as:

* theme
* selected template
* UI state

Provide:

**Clear local data**

functionality.

Explain clearly that data is saved in the browser/device.

No customer-specific data should be transmitted to our servers in V1.

---

# Privacy requirement — NON-NEGOTIABLE

Never send document data to:

* Google Analytics
* Cloudflare analytics
* ad systems
* URLs
* query parameters
* logs
* metadata
* external APIs

Never expose fields such as:

* customer name
* customer email
* address
* tax IDs
* invoice values
* bank details
* document contents

through analytics events.

Analytics can contain only abstract event information such as:

```text
tool = invoice
event = pdf_download
```

Never:

```text
client_name = ...
invoice_total = ...
```

---

# Invoice generator UX

The homepage must immediately behave like a working product.

Above the fold, the visitor should see:

1. Brand/header
2. Clear H1
3. Short value proposition
4. Actual invoice editor
5. Live document preview

Do NOT place a 1,500-word SEO article before the tool.

Suggested page H1:

# Free Invoice Generator

Suggested supporting text:

> Create professional invoices online for free. No signup required. Add your logo, items, taxes and payment details, then download a PDF instantly.

Include visible reassurance:

> Your business and customer data stays in your browser.

---

# Invoice capabilities

V1 invoice tool should support at minimum:

* sender/business details
* logo
* customer details
* invoice number
* issue date
* due date
* currency
* line items
* description
* quantity
* unit price
* tax
* discount
* optional shipping/adjustment
* subtotal
* total
* notes
* payment instructions
* terms
* customizable labels where reasonable
* PDF download
* print
* duplicate invoice
* locally saved drafts
* saved customers
* saved products/services

Calculations must use proper decimal/money handling.

Do not rely on floating-point arithmetic naïvely.

---

# PDF generation

PDF generation happens client-side.

Requirements:

* crisp vector/text output where possible
* multi-page handling
* long line-item tables
* clean page breaks
* repeat relevant table headers if feasible
* professional typography
* printable A4 and/or Letter layouts
* preserve selected currency formatting
* downloadable filename such as:
  `invoice-INV-104.pdf`

PDF code should be lazy-loaded when practical so it does not degrade initial Core Web Vitals.

Choose the most reliable client-side PDF approach after evaluating bundle size, browser support and layout fidelity.

Document the choice.

---

# Design principles

Visual style:

* clean
* professional
* trustworthy
* lightweight
* modern
* business-oriented
* not “AI startup”
* not flashy
* not template-marketplace clutter

Prioritize usability over visual novelty.

Desktop experience is especially important for this market, but mobile must work fully.

The editor/preview can use a responsive split layout:

Desktop:

```text
Editor | Live invoice preview
```

Mobile:

```text
Editor
Preview toggle
```

Use semantic HTML wherever possible.

---

# Performance requirements

This is an SEO product.

Performance regressions are release blockers.

Target Google “good” Core Web Vitals:

* **LCP ≤ 2.5s**
* **INP < 200ms**
* **CLS < 0.1**

Google currently recommends these thresholds.

Additional goals:

* minimal JavaScript on initial page
* lazy-load PDF engine
* lazy-load secondary functionality where appropriate
* no enormous UI framework
* optimized SVG/icons
* responsive images
* reserve image/ad layout dimensions to prevent CLS
* avoid external fonts unless they clearly justify their performance cost
* prefer system/local-safe font stacks if visually acceptable

Run Lighthouse on mobile and desktop.

Aim for 95+ in:

* Performance
* Accessibility
* Best Practices
* SEO

Do not game Lighthouse scores at the expense of product quality.

Google emphasizes overall page experience rather than a single score.

---

# Static SEO requirements

Every indexable page must be rendered as crawlable HTML at build time.

Do NOT require JavaScript for Google to discover:

* H1
* core descriptive content
* navigation
* internal links
* related tools
* metadata

All important internal links must be ordinary crawlable:

```html
<a href="...">
```

not JS-only navigation.

Google specifically recommends crawlable anchor elements with `href` and contextual internal linking.

---

# Titles

Each page gets one concise descriptive `<title>`.

Examples:

Homepage:

**Free Invoice Generator & Invoice Maker | Invoice Workshop**

Proforma:

**Free Proforma Invoice Generator | Invoice Workshop**

Quotation:

**Free Quotation Generator | Invoice Workshop**

Work order:

**Free Work Order Generator | Invoice Workshop**

Purchase order:

**Free Purchase Order Generator | Invoice Workshop**

Estimate:

**Free Estimate Generator | Invoice Workshop**

Do not keyword-stuff titles.

Google recommends concise, descriptive unique titles with a clear prominent main heading.

---

# Meta descriptions

Write unique human-focused descriptions for every page.

Do not mechanically concatenate keywords.

Meta descriptions should explain:

* what the tool does
* free/no-signup benefit
* useful distinguishing feature

Never claim:

* “best”
* “#1”
* guaranteed legal compliance
* guaranteed tax compliance

unless objectively substantiated.

---

# H1/H2 architecture

Exactly one clear primary H1 per page.

Example homepage:

`H1: Free Invoice Generator`

Useful sections beneath might include:

* Create an invoice online
* How the invoice generator works
* What should an invoice include?
* Save your business details without an account
* Invoice generator vs invoice template
* Related business documents

Do not construct headings merely to repeat exact keywords.

---

# On-page content

Every tool page should contain useful content BELOW/AROUND the functioning tool.

Content must help users genuinely understand the document.

Do not produce generic AI SEO filler.

Each page should explain questions relevant specifically to that document.

For example:

### Work Order page

Explain:

* what a work order is
* what information belongs on it
* difference between estimate/work order/invoice
* when to convert a work order into an invoice

### Proforma page

Explain:

* what a proforma invoice is
* how it differs from a final invoice
* typical fields
* conversion into a final invoice

Avoid jurisdiction-specific legal/tax guarantees.

Google explicitly recommends people-first content designed for the intended audience rather than content produced primarily to manipulate rankings.

---

# Internal linking strategy

This is extremely important.

Homepage should link contextually to:

* Proforma Invoice Generator
* Quotation Generator
* Estimate Generator
* Work Order Generator
* Purchase Order Generator
* Construction Invoice
* Contractor Invoice

Supporting pages should link back toward the invoice generator where workflow-relevant.

Examples:

Quotation page:

> Once a quotation is approved, convert it into an **invoice**.

Work order:

> When the work is completed, create an **invoice** from the work order.

Proforma:

> Convert the proforma into a **final invoice**.

Use meaningful anchors, not repeated spam anchors.

Every page we care about must have at least one crawlable internal link from another relevant page. Google explicitly recommends this.

---

# Canonicals

Every indexable page gets a self-referencing canonical.

Example homepage:

```html
<link rel="canonical" href="https://invoiceworkshop.com/" />
```

Canonical hostname:

**https://invoiceworkshop.com**

Normalize:

* HTTP → HTTPS
* www → non-www
* duplicate trailing-slash variants consistently

Use Cloudflare Workers Static Assets `_redirects` where appropriate. Cloudflare supports `_redirects` directly for static assets.

Avoid allowing query parameters representing document state to become indexable duplicate URLs.

---

# Sitemap

Generate:

`/sitemap-index.xml` or `/sitemap.xml`

containing ONLY canonical indexable URLs.

Do not include:

* preview URLs
* document state
* query variations
* drafts
* duplicate URLs
* internal application state

Google recommends putting preferred canonical URLs into the sitemap.

---

# Robots

Create:

`/robots.txt`

Allow normal crawling.

Reference the sitemap.

Do not accidentally block:

* JS/CSS required for rendering
* indexable pages

Cloudflare preview/Workers development URLs must NOT become indexed.

Use an `X-Robots-Tag: noindex` or appropriate configuration for non-production preview domains if needed.

---

# Structured data

Implement only truthful structured data.

Potentially appropriate:

* `WebSite`
* `SoftwareApplication` / appropriate software-tool structured data on generator pages
* `BreadcrumbList` on non-home pages

Do not fabricate:

* reviews
* stars
* ratings
* number of users
* pricing claims
* company attributes

Validate structured data before launch.

Google supports `SoftwareApplication` structured data but requires adherence to its structured-data guidelines.

Do not add schema merely because an SEO checklist says so.

---

# Social metadata

Every public page:

* Open Graph title
* description
* canonical URL
* suitable OG image
* Twitter/X metadata

Generate a consistent branded OG graphic.

Do not load huge images on the actual page just for social previews.

---

# Security headers

Use Cloudflare Workers Static Assets `_headers`.

Cloudflare supports custom headers directly for static assets.

Configure sensible production security headers including where compatible:

* `X-Content-Type-Options: nosniff`
* `Referrer-Policy`
* `Permissions-Policy`
* anti-framing protection
* reasonable Content Security Policy

Do not create an over-restrictive CSP that breaks analytics, future AdSense or application functionality.

Keep third-party origins minimal.

Use HTTPS exclusively.

---

# Analytics readiness

Prepare integrations for:

### Google Search Console

Mandatory after deployment.

Generate verification readiness.

Create sitemap ready for submission.

---

### GA4

Support configuration via environment/public config.

Events:

* `tool_started`
* `document_saved`
* `document_duplicated`
* `pdf_downloaded`
* `document_converted`
* `returning_workspace_loaded`

Properties may include:

```text
document_type
conversion_from
conversion_to
```

Never customer/document content.

---

### Cloudflare Web Analytics

Enable if possible.

Use as independent first-party traffic/performance visibility.

---

# Advertising

Do NOT optimize the initial site around aggressive ads.

Initial priorities:

1. user experience
2. SEO
3. retention
4. ranking
5. monetization

Create ad-slot components/layout placeholders so monetization can be introduced later without redesigning the site.

But:

* do not insert ads that resemble buttons
* do not place ads immediately adjacent to Download PDF
* do not create deceptive CTA/ad layouts
* reserve dimensions to avoid CLS

Main content and advertisements must remain clearly distinguishable.

Google's current page-experience guidance explicitly warns against excessive/distracting ads and designs where users cannot clearly distinguish primary content.

---

# Legal/safety scope

Do NOT implement standalone tools for:

* fake receipts
* recreated branded receipts
* fake bank statements
* pay stubs
* tax documents
* identity documents
* government documents
* medical documents
* official certificates

Receipt functionality may exist as:

**Invoice → mark paid → generate receipt**

for legitimate business use.

Do not create functionality intended to imitate documents issued by third parties.

---

# Accessibility

Meet WCAG-minded baseline quality.

At minimum:

* keyboard-operable forms
* real labels
* focus states
* sufficient contrast
* semantic controls
* form validation that does not depend only on color
* accessible live regions where appropriate
* usable zoom
* appropriate input modes on mobile

Accessibility regressions are release blockers.

---

# Automated tests

Implement serious tests.

## Unit

Test:

* invoice calculations
* discounts
* taxes
* subtotals
* totals
* rounding
* currencies
* document conversions
* document numbering
* storage serialization/deserialization

---

## Browser/E2E

Use Playwright.

Critical flows:

1. first-time visitor opens homepage
2. creates invoice
3. adds several items
4. applies tax
5. PDF downloads correctly
6. refresh page
7. business profile persists
8. customer persists
9. saved product persists
10. duplicate invoice works
11. convert estimate → invoice
12. convert work order → invoice
13. clear local data works
14. mobile workflow works

---

## SEO tests

Automate checks for every public URL:

* HTTP 200
* exactly one H1
* non-empty title
* non-empty description
* self canonical
* indexable
* canonical appears in sitemap
* no duplicate titles
* no duplicate canonicals
* crawlable navigation
* valid structured data where present
* no accidental staging domain references
* no `localhost`
* no `noindex` on production
* sitemap valid
* robots valid

Make SEO regression tests part of CI.

A change that breaks these should fail the build.

---

# Performance CI

Run Lighthouse or equivalent automated audit on core pages.

At minimum test:

* `/`
* `/proforma-invoice-generator/`
* `/quotation-generator/`
* `/work-order-generator/`

Set reasonable performance budgets.

Fail CI on major regressions.

---

# Browser matrix

Verify current versions of:

* Chrome
* Edge
* Safari
* Firefox

Test:

* desktop
* mobile viewport
* IndexedDB persistence
* PDF generation/download
* logo handling
* print output

---

# Error handling

The application must never silently lose documents.

Implement:

* autosave status
* graceful IndexedDB error handling
* clear storage-error messages
* fallback export where practical
* recovery after accidental refresh
* safe migrations when the local schema changes

Version the local database schema.

Future releases must not destroy existing user data.

---

# Content quality

Do not invent factual statistics.

Do not invent tax/legal rules.

Do not say a document is “legally compliant everywhere.”

If explanatory content requires factual claims beyond basic document functionality, research authoritative sources and cite/link them where useful.

Keep content concise and useful.

No AI-sounding SEO filler.

---

# Do NOT do any of the following

* no keyword stuffing
* no invisible SEO text
* no programmatic doorway pages
* no thousands of city/profession pages
* no copied competitor copy
* no copied competitor design
* no backlink automation
* no fake testimonials
* no fake review schema
* no mass-generated blog
* no fake “updated today” dates
* no fake usage counters
* no deceptive download buttons
* no account requirement
* no private customer data on servers
* no unnecessary backend
* no premature AI functionality
* no chat widget
* no unnecessary npm dependency bloat
* no SSR unless justified
* no separate `/invoice-generator/` duplicate of `/`

---

# Launch checklist

Before production launch, verify manually and automatically:

### Domain/infrastructure

* `https://invoiceworkshop.com/` works
* HTTP redirects to HTTPS
* www redirects correctly
* certificate valid
* production Worker connected
* GitHub deployment works
* preview deploys work
* preview domains are protected from indexing

### SEO

* canonical homepage correct
* canonical supporting pages correct
* sitemap accessible
* robots accessible
* all priority pages linked
* no duplicate invoice-generator URL
* titles/descriptions finalized
* structured data valid
* OG tags correct
* 404 genuinely returns 404 behavior
* no broken links

### Product

* full invoice workflow works
* local persistence works
* document conversions work
* PDF works
* refresh recovery works
* privacy behavior verified

### Performance

* Lighthouse reports saved
* CWV targets respected
* bundles inspected
* PDF library lazy-loaded
* no unexpected third-party requests

### Security

* headers checked
* no exposed secrets
* CSP/security configuration tested
* dependency audit clean of critical issues

---

# Post-deployment setup

After deployment:

1. Add/verify InvoiceWorkshop.com in Google Search Console.
2. Submit sitemap.
3. Request indexing for:

   * `/`
   * `/proforma-invoice-generator/`
   * `/quotation-generator/`
   * `/work-order-generator/`
   * `/purchase-order-generator/`
   * `/estimate-generator/`
4. Enable analytics.
5. Record launch timestamp.
6. Establish baseline Lighthouse reports.
7. Create a file documenting target queries and launch positions/impressions.

Do not repeatedly submit URLs for indexing.

---

# Repository documentation

Produce:

`README.md`

with:

* architecture
* local development
* testing
* deployment
* Cloudflare setup
* analytics setup
* privacy model

Create:

`docs/SEO_STRATEGY.md`

This file is mandatory.

Document:

* target queries
* one-page-per-intent mapping
* canonical rules
* internal linking strategy
* pages we explicitly must NOT create
* current ranking priority
* schema strategy
* Search Console measurement strategy

This document exists specifically so future coding agents do not accidentally destroy the SEO architecture.

Create:

`docs/PRODUCT_PRINCIPLES.md`

including:

* no signup
* local first
* no customer data transmitted
* conversion workflow
* simplicity
* performance
* no deceptive advertising

Create:

`docs/LAUNCH_CHECKLIST.md`

and mark every launch requirement complete or incomplete.

---

# Final deliverable

Do not stop after generating code.

Complete the entire pipeline that available credentials permit:

1. research any implementation details needed
2. create repository/project
3. implement product
4. implement all launch pages
5. implement SEO
6. implement persistence
7. implement PDF exports
8. write tests
9. execute tests
10. execute Lighthouse/performance checks
11. fix failures
12. configure Cloudflare deployment
13. connect Git-based deployment where credentials permit
14. deploy to production where credentials permit
15. verify production URLs
16. provide final deployment/report

If some account-level action cannot be completed because authentication/permission is unavailable, do **everything else**, and provide the exact minimal manual action required.

Do not replace implementation with instructions to the user.

---

# Final report format

At completion return:

## Production

* live URL
* deployment status
* Git commit
* Cloudflare Worker/project

## Implemented pages

table of all URLs

## Product

list of implemented functionality

## SEO

* titles
* primary query mapping
* sitemap
* canonicals
* structured data
* internal linking
* crawl/index status

## Performance

Lighthouse results by key page

## Tests

* unit
* E2E
* SEO
* accessibility

## Privacy/security

summary

## Cloudflare

configuration summary

## Outstanding manual steps

Only things genuinely impossible without account access.

## Known risks

No hidden TODOs.

---

# Decision principle

When faced with a tradeoff, optimize in this order:

1. genuine user usefulness
2. crawlability/indexability
3. search-intent alignment
4. reliability/data safety
5. speed/Core Web Vitals
6. repeat usage
7. maintainability
8. visual polish
9. monetization

Never sacrifice the first six to improve the last three.

The site should be something a user would choose to use and bookmark **even if Google did not exist**.
