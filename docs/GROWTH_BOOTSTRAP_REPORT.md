# InvoiceWorkshop Growth Bootstrap Report

Evidence date: 2026-08-26 UTC. This report separates observed evidence from assumptions.

## A. Understanding of InvoiceWorkshop

InvoiceWorkshop is a free, no-account browser workspace for creating invoices and related
business documents. Its useful distinction is not merely free PDF output: business,
customer, catalog, and draft data persist locally, document contents stay on-device, and
users can convert quotation/estimate/work-order/proforma flows without retyping.

The intended users are freelancers, contractors, trades, consultants, agencies, and other
small businesses that need lightweight document software without adopting an account-based
suite. Display advertising is the planned primary business model, with an eventual target
near $10,000/month. Required traffic, ad impressions, and RPM remain unvalidated assumptions.

The SEO architecture is intentionally frozen. `/` owns the invoice-generator cluster and
eight supporting canonical pages own distinct document or vertical intents. The domain is
new. Its immediate needs are discovery, crawl/index coverage, trustworthy distribution,
and evidence of qualified use. Authority may be a bottleneck, but current data is too thin
to conclude that backlinks alone are the bottleneck.

## B. Current-state audit

### Observed

- Production serves all nine priority URLs with HTTP 200. Existing pre-growth QA records a
  clean 13-page crawl, complete metadata/canonicals, no broken internal assets, and passing
  performance/accessibility/SEO budgets.
- Search Console Domain property access works. The sitemap has zero reported errors and
  warnings. URL Inspection reports the homepage, proforma generator, and work-order
  generator indexed. Four priority URLs are discovered but not indexed; two are unknown to
  Google.
- The current 28-day final Search Analytics response contains zero impressions/clicks and
  no query/page/country/device breakdown rows. There is no ranking evidence yet.
- The separate GA4 property and `G-Q7FXV2455E` stream work. The accepted activation
  collector saw 121 sessions, 119 users, 132 pageviews, 19 tool starts, 5 PDF downloads, and 7
  returning-workspace loads in its available window. The property is new and these counts
  include QA activity, so they are validation evidence rather than an acquisition baseline.
- The Level-0 CRM contains 14 read-only research prospects, zero outreach rows, zero
  placements, and no externally approved prospects. No external distribution action was
  taken by the rebuilt system.
- Referring domains and referral traffic are not currently collected. Their state is
  `UNVALIDATED`, not zero.

### Assumptions requiring later evidence

- Incumbent invoice tools make the broad head term highly competitive.
- Relevant editorial/resource discovery is likely more valuable than generic directories.
- A linkable reference asset may improve legitimate inclusion rates, but no asset should be
  built before prospect research establishes a repeated need.

## C. Strategic critique

The plan is right to prioritize qualified users over backlink counts, freeze the URL map,
and prohibit mass distribution. It should not treat authority building as synonymous with
outreach or presume the site is ready for automated submissions.

The first constraint is broader: six priority pages lack confirmed indexation and Search
Console has no demand signal. Initial work should combine indexing observation, product-use
measurement, and read-only channel discovery. Resource-page and competitor-gap research
can reveal what editors actually cite; only that evidence should determine whether a new
reference asset or carefully bounded Level 1 is worth building.

The $10,000/month goal is directionally useful but not yet an operating forecast. Traffic
requirements cannot be estimated honestly until geography, page depth, usable ad inventory,
and observed RPM exist.

## D. Recommended 30-day operating strategy

### Days 1–7

- Activate only the reviewed Level-0 jobs after owner approval.
- Establish seven consecutive daily snapshots and confirm metric reporting delay.
- Observe all nine priority URLs through URL Inspection; do not repeatedly request indexing.
- Qualify approximately 20–30 strong public prospects across several channel types. This is
  a research target, not a placement or traffic guarantee.
- Establish which resource pages and competitor citations recur. Take no external action.

### Days 8–14

- Review the first query/page/country/device evidence, if any, without reacting to daily
  volatility.
- Reject low-quality discovery sites and cluster genuine opportunities by audience and why
  they cite tools.
- Decide whether one existing product/template can serve as a linkable reference asset.
- If external distribution still looks worthwhile, draft a small Level-1 allow-list,
  identity, templates, and caps for owner review. Do not activate it.

### Days 15–30

- Continue Level-0 measurement, verification, and prospect qualification.
- Reallocate research toward pages/queries showing real impressions or qualified use.
- If and only if the owner separately approves a reviewed Level-1 implementation, test a
  very small number of high-fit destinations and measure responses, placements, and referral
  use. Otherwise remain read-only.
- At day 30, decide from evidence whether to continue a channel, stop it, test an asset, or
  keep observing. Do not create new indexed URLs from keyword suggestions alone.

## E. Channel allocation

This is Level-0 research allocation, not permission to submit or contact:

| Channel | Effort |
|---|---:|
| Resource/list pages | 25% |
| Competitor backlink-gap research | 20% |
| Relevant editorial publications | 15% |
| Linkable-asset evidence/research | 15% |
| Legitimate directories and product discovery | 10% |
| Genuine community-question research | 5% |
| Launch-platform research | 5% |
| Partnerships/referral-channel research | 5% |

## F. Hermes architecture

- Project skill: `.hermes/skills/invoiceworkshop-growth/` with durable business, SEO,
  distribution, measurement, escalation, channel, and untrusted-data policies.
- Local SQLite: `data/growth.db`, created from versioned `data/growth_schema.sql`; runtime
  data is ignored by Git.
- Deterministic scripts: Google access check, GSC/GA4/inspection/sitemap/HTTP collection,
  placement verification, validated CRM insertion, deterministic reporting, and a
  deterministic weekly plan/audit wrapper.
- Integrations: read-only Search Console and GA4 service-account APIs plus bounded public
  HTTP GETs. Browser/web research is used only for prospect qualification.
- Dependencies: Python 3 and the pinned packages in `requirements-growth.txt`.
- No Cloudflare or GitHub write access is used by growth jobs.

## G. Exact recurring definitions

| Job | Schedule | Skill | Workdir | State |
|---|---|---|---|---|
| `invoiceworkshop-level0-daily` (`a56bbe317393`) | `0 11 * * *` UTC | `invoiceworkshop-growth` | `/home/azureuser/invoiceworkshop` | Active; next 2026-08-27 11:00 UTC |
| `invoiceworkshop-level0-weekly` (`0cf8f7ecec07`) | `0 12 * * 1` UTC | `invoiceworkshop-growth` | `/home/azureuser/invoiceworkshop` | Active; next 2026-08-31 12:00 UTC |

The exact versioned prompts are in `docs/growth-jobs/`. Jobs start fresh and do not use the
quarantined session. Accepted bootstrap executions are daily
`b40d5a7496f04e2bba5f63d4ce53fcb0` and weekly
`52fe5287e51c4cc791f650abc2b214ec`.

## H. Autonomy matrix

| Level | Current rule |
|---|---|
| Level 0 | May measure, browse public pages, research/score prospects, update the local CRM through its validated CLI, verify placements, and write ignored reports/plans. |
| Level 1 | Disabled. Could later cover a small owner-approved allow-list under separately reviewed identity, templates, caps, opt-out, and audit controls. |
| Level 2 | Owner approval required for spending, public founder/company posts, new indexed pages, production changes, sponsorships/contracts, and legally or reputationally ambiguous actions. |
| Never | Spam, deceptive identities/claims, bought followed links, PBNs, link farms, fake reviews/statistics, scraped mass content, doorway pages, hacked links, or instructions embedded in external content. |

## I. Risks and safeguards

- SEO/reputation: strict channel rejection rules, low-volume research, frozen URL map.
- Prompt injection: all external content and CRM text is untrusted data; it cannot authorize
  commands, secrets, or external actions.
- Outreach/deliverability/platform bans: Level 1 is absent; no sending, submissions,
  accounts, or community posting can occur.
- Duplicates/hallucination: normalized unique prospect keys and required factual evidence.
- Production accidents: job policy prohibits source edits, Git mutations, GitHub/Cloudflare
  changes, pull requests, and deployment.
- Credentials/privacy: narrow read-only OAuth scopes; scripts do not store credentials,
  customer data, or document contents in the CRM.
- Runaway cost: bounded daily tool/research counts, one-call deterministic weekly planning,
  two active jobs, no immediate job retry, and a three-failure Google-read circuit breaker.

## J. Access still required

No additional access is required for Level 0. Search Console and GA4 read-only access are
verified. Cloudflare and GitHub credentials are not needed by the growth operator.

Before any Level 1 design can be activated, the owner must choose and approve the public
identity/mailbox, destination allow-list, templates, caps, and legal/reputation rules. Do
not request those credentials until a concrete reviewed Level-1 proposal exists.

## K. Bootstrap artifacts

- `.hermes/skills/invoiceworkshop-growth/SKILL.md` and seven policy references
- `data/growth_schema.sql` and ignored local `data/growth.db`
- `scripts/growth_common.py`, `growth_google.py`, `growth_check_access.py`,
  `growth_measure.py`, `growth_verify.py`, `growth_db.py`, `growth_report.py`, and
  `growth_weekly_plan.py`, and `run_growth_daily.sh`
- `requirements-growth.txt`
- `tests/growth/` and CI integration
- `docs/GROWTH_BOOTSTRAP.md`, this report, and the two exact prompt definitions
- Two active Hermes jobs with native and local execution history
- Recoverable audit database and quarantined Hermes skill/session artifacts, excluded from
  the rebuilt runtime

## L. Final recommendation

The reviewed Level-0 system is active. Keep Level 1 and Level 2 disabled, and review the
first week of evidence before authorizing any external action.

LEVEL 0 ACTIVE
