# InvoiceWorkshop Level-0 Growth System

Implementation date: 2026-08-26 UTC.

Status: Level 0 implemented, optimized, validated, and active. Daily measurement is
deterministic by default, prospect research is a separate bounded read-only job, and the
weekly strategist remains unchanged. Level 1 and Level 2 remain disabled.

## Safety model

Level 0 may read public webpages, GSC, and GA4; check the public site; update the local
SQLite research store; and produce evidence-based reports. It cannot send, submit, post,
create accounts, purchase, modify production, deploy, or mutate external services.

External content is always untrusted data. The durable policy is in
`.hermes/skills/invoiceworkshop-growth/`.

## Components

- `data/growth_schema.sql` — versioned schema; runtime database is ignored.
- `scripts/growth_check_access.py` — verifies real GSC/GA4 read access.
- `scripts/growth_measure.py` — collects per-day GSC/GA4 metrics, GSC breakdowns,
  sitemap state, URL Inspection state, and HTTP health.
- `scripts/growth_verify.py` — verifies that recorded placement pages still contain the
  expected link; three consecutive failures are required before marking a placement dead.
- `scripts/growth_db.py` — validates and deduplicates Level-0 prospect research.
- `scripts/growth_report.py` — deterministic daily/weekly evidence report.
- `scripts/growth_weekly_plan.py` — deterministic weekly evidence validation, plan write,
  reread verification, and durable audit wrapper.
- `scripts/growth_daily_monitor.py` — deterministic collection, delta/anomaly detection,
  signal persistence, and a stable output-change gate for conditional interpretation.
- `scripts/growth_research_job.py` — bounded public-web research orchestration. The model
  receives only compact runtime context and read-only web tools; deterministic code owns
  validation, deduplication, CRM persistence, usage accounting, and failure handling.
- `scripts/growth_usage_sync.py` — synchronizes exact Hermes model/token/tool/duration
  evidence into the local execution ledger.
- `scripts/growth_job_log.py` — per-job audit records and a three-failure Google-read
  circuit breaker; there is no immediate retry loop.
- `scripts/run_growth_daily.sh` — deterministic collection wrapper.

The database never stores credentials, invoice/document content, or customer data.

## Measurement semantics

`metrics_daily` contains actual calendar-day values refreshed over a recent lookback to
handle Google reporting delay. It does not label pages with impressions as “indexed.”
Index state comes only from Search Console URL Inspection.

GA4 collection includes sessions, users, page views, tool starts, PDF downloads, and
returning-workspace loads. GSC breakdowns cover query, page, country, and device.

## Verified access

- GSC property: `sc-domain:invoiceworkshop.com`
- GA4 account: `accounts/406077053`
- GA4 property: `properties/551485207`
- Web stream: `G-Q7FXV2455E`

Only `webmasters.readonly` and `analytics.readonly` OAuth scopes are used.

The first clean collection (`collection_runs.id=1`) completed successfully on 2026-08-26:
all nine priority URLs returned HTTP 200, the sitemap reported no errors or warnings, and
URL Inspection reported three priority URLs indexed. Six remain discovered/not indexed or
unknown to Google; that is an observed early-stage indexing state, not a collector failure.

## Active runtime cadence

- `invoiceworkshop-level0-daily`: once daily at 11:00 UTC. All GSC, GA4, URL Inspection,
  sitemap/HTTP health, placement verification, persistence, deltas, and basic anomaly
  detection run deterministically. Hermes invokes a no-tool analyst only when the stable
  monitor output contains a meaningful signal. Hermes ID: `a56bbe317393`.
- `invoiceworkshop-level0-research`: Monday, Wednesday, and Friday at 13:00 UTC. A bounded
  wrapper exposes only public-web read tools to the model, validates evidence locally,
  deduplicates against the CRM, and persists qualified work. Default soft budget: 60,000
  total tokens and 10 tools; hard bounds: five turns and 150 seconds. Incomplete quality
  batches are persisted as `budget_stopped` and continue on the next normal schedule with
  no immediate retry. Hermes ID: `a4bf3bdace36`.
- `invoiceworkshop-level0-weekly`: Monday at 12:00 UTC; analyze seven-day evidence and write
  a recommendation under ignored `data/plans/`. Hermes ID: `0cf8f7ecec07`.

The jobs do not inherit the quarantined Hermes session. Exact analyst prompts are versioned
under `docs/growth-jobs/`. All conditional Level-0 inference is pinned through OpenRouter
to `deepseek/deepseek-v4-flash-0731` with reasoning disabled; deterministic measurement and
local validation remain model-free. Weekly still delegates plan composition to the reviewed
deterministic wrapper.

Accepted manual bootstrap evidence:

- Daily native execution `b40d5a7496f04e2bba5f63d4ce53fcb0`; local run `5`,
  2026-08-26 17:29:33–17:32:42 UTC. GSC 1 row, GA4 2 rows, 9 URL-health rows,
  9 URL-inspection rows, 2 prospects added, no errors, and
  `external_side_effects=none`. Hermes recorded 179,163 tokens and 289,828 ms.
- Weekly native execution `52fe5287e51c4cc791f650abc2b214ec`; local run `10`,
  2026-08-26 17:58:37 UTC. It used the latest successful GSC 1-row and GA4 2-row
  snapshots, recorded all 9 priority URLs, wrote and reread one ignored plan, added no
  prospects, and recorded `external_side_effects=none`. Its trace contained exactly one
  tool call; Hermes recorded 12,933 tokens and 10,481 ms.

Optimized acceptance evidence:

- Daily native execution `473d0bcd5da847aa91bdcfcec3c2b97e`; local run `13`,
  2026-08-26 19:17:23–19:18:36 UTC. Deterministic collection recorded GSC 1 row, GA4 2
  rows, 9/9 healthy URLs, 9 URL inspections, and 3/9 indexed priority URLs. A real
  index-state change invoked the no-tool analyst once: 2,075 input + 843 output = 2,918
  total tokens, 0 tool calls, and `external_side_effects=none`.
- Research native execution `8f911c0b65c5432a9061d85fe34c1d3c`; local run `5`,
  2026-08-27 06:12:19–06:14:16 UTC. It examined 8 candidates using 4 read-only web calls,
  retained 1 strictly qualified prospect, rejected unsupported candidates locally, and
  recorded 11,726 input, 9,970 output, 12,800 cache-read, 34,496 total tokens, 116,860 ms,
  and `external_side_effects=none`. It correctly finished `budget_stopped` because the
  five-prospect quality threshold was not met; completed qualified work remains available
  for the next normal run.

Activation-audit research runs that exceeded a budget or failed qualification were marked
failed and their imported rows were quarantined as rejected. No audit record was deleted.

On 2026-08-27, a bounded Hermes canary verified the active DeepSeek model slug, one public
web-search tool call, valid JSON output, and no external side effects before the Level-0
model pins were migrated from `openai/gpt-5-mini`.

Pre-activation validation remained paused while rejecting inaccurate weekly drafts and a
retired/timed-out provider route. No rapid retry loop was enabled. The accepted weekly path
is deterministic, and all three active jobs retain bounded no-immediate-retry behavior.

The repository is explicitly trusted by Hermes for project-skill loading. A profile-visible
symlink named `invoiceworkshop-growth` points to the versioned project skill because Hermes
assembles cron skill context before applying a job's workdir; this keeps unattended gateway
runs on the reviewed repository copy instead of a duplicated global skill.

Each execution is recorded in Hermes' native attempt/session ledgers and in `level0_runs`,
`research_runs`, and `agent_executions` as applicable, including timestamps, outcome, exact
available model/token/tool usage, collected source rows, prospect changes, errors, and the
invariant `external_side_effects=none`. A single failure waits for the next normal schedule.
Three consecutive Google auth/API failures pause `google_reads`; three consecutive research
agent failures pause the research schedule. After Google remediation an owner/engineer can
reset its operation explicitly with:

```bash
python3 scripts/growth_job_log.py resume --operation google_reads
```

Next-run timestamps are owned by the Hermes registry and are reported during each runtime
audit rather than treated as static documentation.

## Level-1 boundary

The schema reserves an outreach table, but Level 0 cannot write it and cannot approve a
prospect for external action. Level 1 requires a separate reviewed implementation and an
explicit owner decision after the allow-list, identity/mailbox, templates, caps, and legal/
reputation safeguards are presented.

## Operations

```bash
python3 scripts/growth_db.py init
GOOGLE_APPLICATION_CREDENTIALS="$PWD/.env.google-service-account.json" \
  /home/azureuser/growth-venv/bin/python scripts/growth_check_access.py
/home/azureuser/growth-venv/bin/python scripts/growth_report.py --period 7
python3 -m unittest discover -s tests/growth -p 'test_*.py'
```

The Hermes failure database and auto-curated global skill were preserved in quarantine for
recovery evidence. They are not used by the rebuilt system.
