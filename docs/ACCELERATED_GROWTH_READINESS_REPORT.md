# ACCELERATED GROWTH READINESS REPORT

Prepared: 2026-08-31 UTC

Scope: Level-0 measurement/research correction and a Level-1 pilot design. No
outreach, submission, account creation, public posting, purchase, production
change, or deployment was performed.

## Measurement fixes

- GSC now persists a combined fact at `date + query + page + country + device`.
  The older independent query/page/country/device breakdowns remain intact; no
  historical joins were invented.
- GA4 now persists `source`, `medium`, combined source/medium, and default channel
  group with users, sessions, pageviews, tool starts, PDF downloads, and returning
  workspace loads.
- Internal/QA classification is forward-only. Rows are `unknown` unless explicit
  source/medium patterns are configured with
  `GA4_INTERNAL_SOURCE_MEDIUM_PATTERNS`; old rows are never guessed.
- The live read on 2026-08-31 stored 5 combined GSC facts and 6 GA4 acquisition
  rows. The GA Admin API confirmed account `Invoice Workshop`, property
  `551485207`, stream `G-Q7FXV2455E`, and default URI
  `https://invoiceworkshop.com`.

## Strategist fixes

- “Top prospects” requires both CRM status `qualified` and a passing second-pass
  qualification record.
- The weekly output uses current bounds: three cheap discovery queries, an 8–15
  candidate shortlist, and 5–10 qualified targets.
- It reports `budget_stopped` and failure states, CRM state counts, token/tool
  efficiency, and missing channel coverage.
- Four legacy “qualified” records without the evidence companion were preserved
  and moved to `new`; they are no longer represented as qualified.
- The corrected strategist ran successfully against the current database using
  the latest successful GSC and GA4 snapshots.

## Research architecture

Previous path:

```text
scheduled agent -> broad web search -> repeated exploration -> loose CRM import
```

Corrected path:

```text
cheap fixed-query discovery
  -> deterministic noise/competitor filtering and CRM deduplication
  -> deterministic public page + contact-route fetch
  -> diverse evidence-complete shortlist
  -> no-tool LLM second pass only
  -> strict URL/evidence/payment/fit validation
  -> local CRM
```

The model cannot introduce a URL or route absent from the deterministic shortlist.
Failed model execution returns an unfinished shortlist to the queue. Qualified
records require exact evidence, a frozen target URL, a proposed action, confidence,
and an explicit answer to “would this still help the audience without SEO value?”

## Sprint economics

- Broad deterministic sweep: 18 queries, 170 search results, 48 queued candidates,
  20 duplicates, and 102 deterministic rejects.
- Human-vetted evidence seed: 13 candidates.
- Model batches: 2.
- Candidates examined by the model: 15.
- Strictly qualified: 7.
- Not retained/validation rejected: 8.
- Model: `openai/gpt-5.6-luna` through OpenRouter.
- API calls: 2.
- Model tool calls: 0.
- Input tokens: 6; output tokens: 3,440; cache-write/context tokens: 31,141;
  total recorded tokens: 34,587.
- Tokens per qualified prospect: 4,941.
- Model execution time: 93.352 seconds total.
- External side effects: none.

The 20–30 target was deliberately not forced. Only seven candidates passed the
current evidence standard; lowering the threshold would have reintroduced generic
write-for-us pages, direct competitors, paid/reciprocal directories, or unclear
submission eligibility.

## Channel results

| Channel | Strictly qualified | Result |
| --- | ---: | --- |
| Contractor | 3 | Strongest repeatable channel; three real editorial routes. |
| Freelancer | 1 | Best direct resource-directory match. |
| Small business | 2 | One credible resource route and one lower-confidence editorial route. |
| Accounting | 1 | Genuine resource hub but only a general contact route. |
| Directory | 0 | Free database candidate failed the second pass; paid/reciprocal listings rejected. |
| Community | 0 | Demand evidence exists, but no public posting is justified in Level 0. |
| Competitor gap | 0 | Search exposed content patterns, not a defensible backlink graph. |
| Linkable asset | 0 placements | Research did reveal a contractor-specific asset opportunity. |

Future scheduled research should prioritize contractor editorial/resource pages,
freelancer resource curators, accounting/client-resource hubs, and targeted small-
business education sites. It should deprioritize direct invoicing competitors,
generic guest-post pages, SEO-first directories, paid listings, reciprocal-link
requirements, and pages repeatedly blocked before evidence can be verified.

## Tier A

These five pass the “useful without SEO” review and are suitable for a small pilot
after identity/mailbox setup and owner approval.

| Prospect | Evidence and route | Proposed target |
| --- | --- | --- |
| Freelance Things | [Curated freelancer tools and on-page resource submission](https://www.freelancethings.co/official-information) | `https://invoiceworkshop.com/invoice-template/` |
| Construction Executive | [Non-branded contractor editorial guidelines](https://constructionexec.com/editorial-guidelines/) | `https://invoiceworkshop.com/construction-invoice-template/` |
| Modern Contractor Solutions | [Educational contractor editorial route](https://mcsmag.com/editorial/) | `https://invoiceworkshop.com/contractor-invoice-template/` |
| Contractor Magazine | [Contributor guidelines for labor/cost-saving contractor content](https://www.contractormag.com/contributors-guidelines) | `https://invoiceworkshop.com/contractor-invoice-template/` |
| LedgerCo | [Small-business accounting resource hub](https://ledgerco.ca/resources/) and [contact route](https://ledgerco.ca/contact/) | `https://invoiceworkshop.com/invoice-template/` |

## Tier B

- [USASBE resource submission](https://www.usasbe.org/submit-a-resource): strong
  education fit, but the page frames sharing as a member activity and its external
  Google Form currently requires sign-in. Confirm non-member eligibility and any
  membership/payment condition before considering it. No account or payment may be
  created without approval.
- [Entrepreneur Resources submission](https://www.entrepreneur-resources.net/submit-an-article):
  relevant small-business categories and a direct route, but lower editorial quality
  and an article requirement make this a reserve action.

## Level-1 pilot

This is a design only. Initial cap: three new contacts per day and five total messages
per day including follow-ups. Use one route per organization. Send at most one follow-up
after seven business days; a second follow-up is allowed by policy but is not recommended
for this first pilot. Stop immediately on rejection, unsubscribe, complaint, unclear
eligibility, payment, reciprocal-link request, or a request for misleading promotion.

### 1. Freelance Things resource suggestion

- Route: the form on `https://www.freelancethings.co/official-information`.
- Account/mailbox: no account; a working domain mailbox is required.
- Identity: `InvoiceWorkshop Team`.
- Exact draft:

> InvoiceWorkshop is a free, no-account browser workspace for creating invoices,
> estimates, quotations, purchase orders and work orders. Document data stays in the
> user's browser, and the invoice template can be used and exported as PDF without a
> signup: https://invoiceworkshop.com/invoice-template/ . It may be useful for
> freelancers who want a straightforward invoicing tool without moving client details
> into another hosted account.

- Success: accepted directory/newsletter inclusion or a substantive editor reply.
- Abort: sponsorship/payment request, reciprocal link, or a request to overstate privacy
  or capabilities.

### 2. Construction Executive pitch

- Route: `editor@constructionexec.com`, published on the editorial-guidelines page.
- Account/mailbox: domain mailbox required; no account.
- Identity: a real owner-approved named author with role, location, bio, contact detail,
  and headshot. Never use a fabricated persona.
- Subject: `Pitch: A field checklist for cleaner construction invoices`
- Exact draft:

> Hello Construction Executive editorial team,
>
> I would like to propose a non-branded 900–1,200 word article for nonresidential
> contractors: “A field checklist for construction invoices that are easier to approve.”
> It would cover project and contract references, labor/material separation, change-order
> traceability, payment terms, retainage handling, and a pre-send review workflow. The
> article would be educational, written in third person, and exclusive. Where useful, it
> could reference a free worked construction-invoice example at
> https://invoiceworkshop.com/construction-invoice-template/; external links would remain
> entirely at the editor's discretion.
>
> Author: [approved real name, title, location and brief relevant credentials]. Writing
> samples: [owner-supplied links]. Thank you for considering the idea.

- Success: pitch acceptance or request for an outline/manuscript.
- Abort: no approved human byline/credentials, exclusivity conflict, or sponsored/paid
  placement requirement.

### 3. Modern Contractor Solutions pitch

- Route: `matt@mcsmag.com`, published on the editorial page.
- Account/mailbox: domain mailbox required; no account.
- Identity: a real owner-approved author; provide title, company, phone, bio, and available
  images as the publication requests.
- Subject: `Article proposal: Reducing invoice-preparation friction for contractors`
- Exact draft:

> Hello Matt,
>
> Proposed title: “A repeatable invoice workflow for busy contracting teams.” The article
> would give commercial and concrete contractors a concise process for gathering job
> references, separating labor and materials, documenting approved changes, checking
> payment terms and producing a client-ready invoice. It would be educational and focused
> on day-to-day operational efficiency, not a product promotion. A free contractor invoice
> example at https://invoiceworkshop.com/contractor-invoice-template/ could be included
> only if editorially useful.
>
> Author: [approved real name, title, company and contact]. Bio: [approved 2–3 sentences].
> Company: InvoiceWorkshop provides local-first browser tools for common business
> documents. Images: [state only what actually exists].

- Success: editorial interest, requested outline, or accepted contribution.
- Abort: missing approved author details, requirement for undisclosed promotion, or paid
  placement.

### 4. Contractor Magazine pitch

- Route: `sspaulding@endeavorb2b.com`, the Editor-in-Chief address published on
  `https://www.contractormag.com/contributors-guidelines`.
- Account/mailbox: domain mailbox required; no account; a contributor agreement may be
  required after acceptance.
- Identity: real named author, 50–75 word bio, headshot, and demonstrable relevant
  experience. The final article must comply with the publication's stated AI-content rule.
- Subject: `Best-practices pitch: Cutting invoice admin time without losing job detail`
- Exact draft:

> Hello Steve,
>
> I would like to propose an 800–1,100 word best-practices article for plumbing and
> mechanical contracting businesses: “Cutting invoice administration time without losing
> job detail.” It would explain a repeatable intake and review process for technician work
> notes, labor/material breakdowns, customer and job references, payment terms and final
> approval. The focus would stay on the contractor's workflow and cost-saving practices,
> with no commercial claims. If useful to readers, a free worked template at
> https://invoiceworkshop.com/contractor-invoice-template/ can illustrate the checklist.
>
> Author: [approved real name and credentials]. Samples: [owner-supplied links].

- Success: acceptance, request for more detail, or signed contributor step.
- Abort: no qualifying human author, inability to comply with the contributor agreement
  or AI limit, or a paid/sponsored-only route.

### 5. LedgerCo resource suggestion

- Route: `https://ledgerco.ca/contact/` / the public `info@ledgerco.ca` address.
- Account/mailbox: domain mailbox required; no account.
- Identity: `InvoiceWorkshop Team`.
- Subject: `Possible companion resource for your invoice-template library`
- Exact draft:

> Hello LedgerCo team,
>
> Your resource library already helps business owners with invoice templates, bookkeeping
> checklists and receivables tracking. InvoiceWorkshop may be a useful optional companion:
> it is a free, no-account browser workspace that lets a business prepare an invoice and
> export a PDF while keeping the entered document data in the browser. The relevant page
> is https://invoiceworkshop.com/invoice-template/ . If it does not meet your resource
> standards, no response or inclusion is expected.
>
> InvoiceWorkshop Team
> hello@invoiceworkshop.com

- Success: editorial evaluation, inclusion, or useful feedback.
- Abort: sales/demo routing only, payment/reciprocal-link request, or no indication that
  the resource team accepts external suggestions.

## Mailbox and identity requirement

Use `hello@invoiceworkshop.com`; do not create a second team mailbox for this small pilot.

- Resource submissions: From name `InvoiceWorkshop Team`; reply-to
  `hello@invoiceworkshop.com`.
- Editorial pitches: From name `[approved real person] — InvoiceWorkshop`; the same mailbox
  may be used, but the signature and byline must name the real person.
- Minimal team signature: `InvoiceWorkshop Team | https://invoiceworkshop.com/ | Free,
  local-first business document tools`.
- Minimal author signature: real name, actual role, InvoiceWorkshop, domain, and one real
  contact method. Do not invent credentials, location, history, clients, or expertise.

Current DNS has no published MX, SPF, or DMARC record. Before activation the owner must:

1. Choose a real mail provider and create `hello@invoiceworkshop.com` as a send-and-receive
   mailbox (not only a forwarding alias).
2. Publish that provider's exact MX, SPF, and DKIM records.
3. Publish DMARC initially in monitoring mode (`p=none`) with an owner-controlled aggregate
   report destination, then verify alignment.
4. Send and receive test messages to an external mailbox and verify SPF, DKIM and DMARC pass.
5. Supply the real author name, role, short bio, relevant credentials/writing samples and
   headshot for any editorial action; alternatively approve only the two team-identity
   resource actions.

## Linkable asset

### BUILD NOW

Concept: a “Construction Invoice Approval Checklist” with a filled, fictional example
covering contract/job references, labor and materials, approved change orders, payment
terms, retainage, tax review, and a final pre-send checklist.

- Audience: commercial contractors, specialty trades, administrators, and small
  contracting firms.
- Plausible citers: Construction Executive, Modern Contractor Solutions, Contractor
  Magazine, accounting firms serving trades, and contractor resource hubs.
- Evidence: three independent contractor publications explicitly accept practical,
  educational business/productivity material; current GSC facts also contain the exact
  “construction invoice generator” query mapped to the construction template page.
- Location: enrich the existing
  `https://invoiceworkshop.com/construction-invoice-template/`; do not create a new indexed
  URL in this task.
- Distribution value: it gives editors and resource curators a genuinely useful reference,
  rather than asking them to cite a generic product homepage.

No asset or production page was changed in this task.

## Current search state

- Priority URL Inspection: 4 of 9 pass (`/`, `/construction-invoice-template/`,
  `/proforma-invoice-generator/`, `/work-order-generator/`). Four are discovered but not
  indexed; `/contractor-invoice-template/` is currently unknown to Google.
- Latest combined GSC facts: 5 fact rows totaling 6 impressions and 0 clicks. Query/page mappings are:
  “online work order generator” → `/work-order-generator/` (4 impressions across
  2026-08-27 through 2026-08-29); “construction invoice generator” →
  `/construction-invoice-template/` (1); and “proforma invoice generator” →
  `/proforma-invoice-generator/` (1).
- Latest GA4 acquisition persistence contains six dated rows, all `(direct) / (none)` and
  default channel `Direct`. They remain `unknown` for internal/external classification
  because no explicit QA pattern is configured. The large 2026-08-25 row must not be
  retroactively labeled as owner traffic.

These small search volumes are directional only. They support contractor/work-order and
proforma distribution priorities but do not justify new keyword pages or ranking claims.

## Safety and readiness

- External actions: zero.
- Emails/forms/submissions/posts/accounts/purchases: zero.
- Production files/deployments: zero.
- External content was treated only as untrusted evidence.
- Level 1 remains disabled; no Level-1 schedule exists.
- Level-0 scheduled cadence remains daily measurement, Monday/Wednesday/Friday research,
  and weekly strategy. No additional schedule was added.

Answers:

1. Level 1 is not yet activatable. The five-action design is ready for review, but the
   mailbox/authentication and real editorial identity prerequisites are not complete, and
   the execution guardrails have not been implemented or activation-tested.
2. The owner must complete the five mailbox/identity steps above and approve the fixed
   allowlist, exact drafts, daily caps, and the existing-URL asset plan.
3. After those steps and a separately reviewed Level-1 implementation/activation test,
   routine operation can proceed without per-message approval only inside the approved
   allowlist, identity, templates, caps and stop conditions. New channels, payment,
   reciprocal terms, public accounts/posts, legal complaints, or reputation risk must
   escalate.

### LEVEL 1 NOT READY
