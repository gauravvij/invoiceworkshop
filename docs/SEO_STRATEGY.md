# SEO Strategy

## Search intent and canonical URL map

| Priority | Canonical page | Primary intent |
|---|---|---|
| Economic target | `/` | invoice generator |
| Major wedge | `/proforma-invoice-generator/` | proforma invoice generator |
| Early authority wedge | `/quotation-generator/` | quotation generator |
| High commercial value | `/work-order-generator/` | work order generator |
| Supporting | `/purchase-order-generator/` | purchase order generator |
| Supporting | `/estimate-generator/` | estimate generator |
| Vertical | `/construction-invoice-template/` | construction invoice template |
| Vertical | `/contractor-invoice-template/` | contractor invoice template |
| Template | `/invoice-template/` | invoice template |

The homepage owns the complete `invoice generator` cluster, including natural variants such as free invoice generator, invoice maker, invoice builder, invoice creator, online invoice tool and invoice generator with logo. These variants must not receive separate pages.

## Pages that must not be created

Do not add `/invoice-generator/`, `/invoice-maker/`, `/invoice-builder/`, `/free-invoice-generator/`, `/online-invoice-generator/` or other synonym pages. Historical or accidental variants redirect permanently to `/`. Do not create trade, city or keyword doorway pages without validated demand and a genuinely different product experience.

## Canonical rules

- Canonical origin: `https://invoiceworkshop.com`.
- The apex HTTPS hostname is the only canonical host.
- `www` redirects to the apex and preserves path/query.
- Public routes consistently use trailing slashes, except `/404.html`, `/robots.txt` and `/sitemap.xml`.
- Every indexable page has one self-referencing canonical.
- Document state never appears in paths or query strings.
- Preview and `workers.dev` hosts return `X-Robots-Tag: noindex, nofollow, noarchive`.
- Only canonical indexable URLs appear in `/sitemap.xml`.

## Internal linking

The homepage links to all generator wedges and gives the strongest contextual authority to proforma, quotation, estimate, work order and purchase order. Supporting tools link back to the invoice generator at the point where the workflow naturally converts into billing. Each page also links to two or three closely related document types with meaningful anchor text.

Navigation uses ordinary `<a href>` elements. Important links and explanations are statically rendered and do not depend on React or client JavaScript.

## On-page and content rules

- The functioning editor appears immediately after a concise H1 and value proposition.
- Exactly one H1 appears per page.
- Each title and description is unique, concise and written for a human.
- Supporting copy answers document-specific questions below the tool.
- Never claim universal legal/tax compliance or invent statistics, reviews or usage numbers.
- Update factual claims only from authoritative sources and cite when useful.

## Structured data

All pages include truthful `WebSite` data. Generator pages add `SoftwareApplication` with a zero-price offer and actual browser-based features. Non-home generator pages add `BreadcrumbList`. Do not add reviews, aggregate ratings, user counts, organization facts or FAQ schema without truthful visible source content and eligibility review.

## Search Console measurement

Use the Domain property for `invoiceworkshop.com`. Keep the DNS verification record in place and submit `https://invoiceworkshop.com/sitemap.xml` once after launch. Request initial indexing for the homepage and the five priority supporting generators, then rely on crawlable linking and the sitemap rather than repeated manual submissions.

Track by page/query group:

- impressions, clicks, CTR and average position;
- indexed vs. excluded canonical URLs;
- branded vs. non-branded queries;
- mobile and desktop trends;
- movement from supporting wedges toward the homepage economic target.

Record launch baselines in `docs/SEARCH_BASELINE.md`. Do not create new URLs merely because Search Console exposes close keyword variants; consolidate variants by intent first.
