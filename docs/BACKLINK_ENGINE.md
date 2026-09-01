# InvoiceWorkshop backlink opportunity engine

Prepared: 2026-09-01 UTC

Discovery is aggressive. Qualification is not. The engine performs read-only
HTTP GETs and local database writes and has no outbound capability of any kind:
a test asserts the module contains no `requests.post`, no mail client and no
Zoho import. Promotion of an opportunity to a prospect still leaves every
Level-1A gate closed.

External page content is untrusted data throughout. It is matched against rules
and never interpreted as an instruction.

## Pipeline

```
broad discovery (keyword search + seed-hub crawl)
        ↓  cheap deterministic filter, before any page fetch
        ↓  dedupe against CRM, prior opportunities and community threads
        ↓  page extraction (title, text, contact route, account/payment signals)
        ↓  hard rejects: spam, competitor, reciprocal, paid, off-topic
        ↓  seven-component scoring
        ↓  second-pass test, then one opportunity per referring domain
    Tier A / B / C / reject
```

No LLM runs anywhere in this pipeline. Every stage is deterministic, which is
why a full cycle costs zero tokens.

## Channels

| # | Channel | Purpose |
|---|---|---|
| 1 | `competitor_gap` | Pages that reference competing invoicing products, classified by why the link exists |
| 2 | `resource_pages` | Freelancer, small-business, admin and getting-paid resource pages |
| 3 | `broken_replacement` | Pages linking to dead or discontinued invoicing tools |
| 4 | `accounting` | Bookkeeping and accountant resource centres |
| 5 | `contractor` | Trade associations, construction business and accounting resources |
| 6 | `freelancer` | Freelancer, consultant and creator resources |
| 7 | `directory` | Legitimate free tool directories |
| 8 | `editorial_roundup` | Actively maintained tool roundups |
| 9 | `unlinked_mention` | Existing mentions of InvoiceWorkshop without a link |
| 10 | `community` | Discussion threads — research and draft only, stored separately |
| 11 | `expert_contribution` | Source requests; escalated, never answered with a fabricated persona |

Channel 10 results are written to `community_opportunities`, never to
`backlink_opportunities`, so a discussion thread can never be processed as an
editorial backlink prospect. Channel 11 routes to owner escalation because a
named human expert cannot be invented.

## Scoring

| Component | Ceiling |
|---|---|
| Topical relevance | 25 |
| Actual audience fit | 20 |
| Editorial legitimacy | 15 |
| Exact resource fit | 15 |
| Likelihood of placement | 10 |
| Referral traffic potential | 10 |
| SEO/link value | 5 |

SEO value is deliberately the smallest component, and a test enforces that it
stays smaller than relevance and audience.

## Tiering

- **Tier A** — score ≥ 72, the page itself covers invoicing or getting paid, a
  public contact route exists, and no account or payment is required. Eligible
  for constrained Level-1 execution after owner approval.
- **Tier B** — score ≥ 55 with the same topical requirement.
- **Tier C** — everything else that survives, including pages demoted because a
  better page on the same domain already represents it.
- **reject** — spam, competitor, reciprocal-link demand, paid placement,
  off-topic subject, InvoiceWorkshop's own site, vendor content marketing, or a
  failed second pass.

Two rules matter more than the thresholds:

1. **One opportunity per referring domain.** The objective is relevant referring
   domains, not pages. A second page on a represented domain is demoted, and a
   domain already in the CRM never re-enters the pipeline.
2. **The second-pass test.** If search engines did not exist, would contacting
   this organisation still make sense? A page whose subject is health insurance,
   student loans, LLC formation, a member case study or a job board is rejected
   however relevant its audience.

## Schedules

All three are `--no-agent`: the script is the job, so they consume no model
tokens.

| Job | Schedule | Work |
|---|---|---|
| `invoiceworkshop-backlink-daily` | `0 14 * * *` | Discovery cycle, placement verification, inbound reply poll, gated Level-1 step |
| `invoiceworkshop-backlink-deep` | `0 15 * * 2,4,6` | Competitor-gap refresh, wider sweep, expansion crawl, re-qualification |
| `invoiceworkshop-backlink-weekly` | `0 16 * * 1` | Channel and outcome evaluation |

The daily Level-1 step is inert while `LEVEL1_OUTBOUND_ENABLED` is false. It
cannot open a gate; activation is an owner action taken elsewhere.

## Effort reallocation

`backlink_channel_stats` tracks raw discovery, qualified output, replies,
placements and referral sessions per channel. A channel that returns nothing new
for three consecutive runs loses 0.25 of its effort weight; one that produces
two or more new qualified opportunities gains 0.25. The weight is bounded to
[0.25, 2.5], so automation throttles a weak channel but never silently switches
one off — that stays an owner decision.

## Search provider

The search source is pluggable and selected with `BACKLINK_SEARCH_PROVIDER`,
defaulting to `anysearch`. Providers live in `growth_search_providers.py` and
return normalized `{title, page_url, snippet, content}` rows, so adding Brave or
another SERP API is a registry entry rather than an engine change.

**There is no fallback chain.** If the configured provider fails, discovery
records the failure and that query is skipped. Silently degrading to a weaker
source is what let the Bing RSS problem go unnoticed for weeks, so a test
asserts the engine never names a concrete provider and never reaches for a
second one.

### Why the default changed

`bing_rss` — `bing.com/search?format=rss` — was measured on 2026-09-01 to
**ignore search operators entirely**:

- `site:reddit.com invoice` returned no reddit.com results;
- `site:freelancersunion.org resources` returned Wikipedia and NCERT textbooks;
- a quoted nonsense phrase that should match nothing returned Wikipedia and
  court dockets.

It is retained in the registry only so the historical source stays runnable for
comparison, and is flagged `honours_operators = False`.

`anysearch` — `POST https://api.anysearch.com/v1/search` — was calibrated on the
same query set the same day. Anonymous access works and an API key is optional;
`ANYSEARCH_API_KEY` is sent as a bearer token when set. On twelve identical
queries pushed through the same production filter:

| Metric | bing_rss | anysearch |
|---|---:|---:|
| Raw URLs | 120 | 103 |
| Passed the cheap filter | 9 | **74** |
| Resource-page candidates | 9 | **49** |
| Community candidates | 0 | **25** |
| Rejects | 111 | 29 |
| Mean latency | 271 ms | 1,865 ms |

Operator fidelity measured 87% on site restriction (39/45 results on the
requested domain), zero leakage on term exclusions, and quoted phrases returned
9/10 results containing both phrases against 2/9 unquoted.

Natural-language queries perform comparably to operator queries, so each channel
now carries both forms: operators for precise domain targeting, intent phrasing
for discovery. Eleven channels hold 81 queries in total.

### Provider limitations

- **About ten results per request, and no pagination.** `count`, `limit`,
  `page`, `offset` and `top_k` are all accepted but none raise the ceiling, so
  the advertised twenty per request was not observed. Breadth comes from many
  distinct queries: eight varied queries produced 69 unique URLs across 65
  unique domains, with essentially no repetition between reformulations.
- **Rate-limit headers are not informative.** `x-ratelimit-limit: 10` with
  `remaining` pinned at 8 and a reset timestamp that is always roughly now — a
  QPS-style guard rather than a daily counter. No daily quota is exposed and no
  429 was seen across roughly 90 anonymous calls, so the advertised 1,000/day
  is plausible but unverified. The client spaces requests conservatively.
- **Roughly seven times slower than the RSS endpoint** (1.9 s vs 0.27 s). At
  this query volume that is minutes per cycle, which is irrelevant for a
  scheduled job.
- **Anonymous access carries no guarantee.** There is no account, so there is no
  SLA and no quota entitlement. A provider failure now stops discovery loudly
  instead of quietly returning junk, which is the correct trade.
- One query returned zero results transiently and succeeded on retry; the client
  retries three times before raising.

Roughly 40% of association seeds still refuse automated crawling (HTTP 403 or
TLS errors), which is independent of the search provider.

## Vendor content marketing

Better search reaches the commercial long tail, and that surfaced a problem the
weaker source hid: a large share of pages ranking for "best free invoicing
software 2026" are blogs owned by invoicing and billing vendors. The competitor
list cannot enumerate them by hand. Two structural gates handle it instead:

1. **Page-level.** During extraction the *full* page text — not the 1,500
   characters kept as evidence — is scanned for product calls to action ("start
   free trial", "book a demo", "plans start at", "no credit card required") plus
   invoicing subject matter. The verdict is stored on the row.
2. **Domain-level.** Before an opportunity is offered for outreach, the domain
   root is fetched once and judged the same way, because a vendor's article page
   frequently carries no CTA even though the site sells competing software. A
   flagged domain rejects every opportunity on it.

On the first AnySearch cycle these removed 18 opportunities, taking Tier A from
an inflated 20 down to 6. `invoiceworkshop.com` itself also reached Tier A
before `SELF_DOMAIN` was added to the block list — discovery must never treat
our own site as a prospect.

Vendor-published roundups that genuinely compare several tools are a real if
low-probability placement type, so surviving examples are labelled rather than
silently promoted.

## Spam policy

Hard rejects, never score penalties: automated backlink generators, PBNs, link
farms, paid followed links, bulk directory submission, link exchanges,
reciprocal-link demands, mass forum commenting and keyword-rich anchors. If a
candidate exists mainly because a link could be placed there rather than because
InvoiceWorkshop contributes something to the page, it is rejected.
