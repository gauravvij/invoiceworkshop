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
  off-topic subject, or a failed second pass.

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

## Known constraint: the search backend

**The free Bing RSS endpoint used for keyword discovery ignores search
operators.** Verified directly on 2026-09-01:

- `site:reddit.com invoice` returned no reddit.com results;
- `site:freelancersunion.org resources` returned Wikipedia and NCERT textbooks;
- a quoted nonsense phrase that should match nothing returned Wikipedia and
  court dockets.

Quoted phrases and `site:` are both discarded, so keyword discovery degrades to
loose matching. The filters behave correctly against this — they reject the
dictionaries, textbooks and competitor pages it returns — but the *ceiling* on
qualified output is set by search quality, not by the pipeline.

The same endpoint backs the existing Level-0 research job, so earlier reported
discovery counts carry the same caveat.

Two mitigations are in place:

1. **Seed-hub crawling**, which needs no search engine. The crawler reads the
   resource sections of membership bodies and trade associations directly, and
   an expansion pass uses discovered resource pages as second-level seeds. This
   produced the majority of real opportunities found so far.
2. **Domain diversity accounting**, so a single cooperative site cannot inflate
   the numbers.

Roughly 40% of association seeds refuse automated access (HTTP 403, or TLS
errors). Their resource pages remain reachable by a person.

Lifting qualified throughput to the 5–15 per cycle target realistically needs a
search API that honours operators — Brave Search, Bing Web Search, Google
Programmable Search or similar. That requires a key and in most cases payment,
so it is an owner decision; nothing was purchased.

## Spam policy

Hard rejects, never score penalties: automated backlink generators, PBNs, link
farms, paid followed links, bulk directory submission, link exchanges,
reciprocal-link demands, mass forum commenting and keyword-rich anchors. If a
candidate exists mainly because a link could be placed there rather than because
InvoiceWorkshop contributes something to the page, it is rejected.
