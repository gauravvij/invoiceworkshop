# InvoiceWorkshop Level-0 Growth System

Implementation date: 2026-08-26 UTC.

Status: Level 0 implemented, validated, and active. The daily and weekly recurring jobs
were enabled on 2026-08-26 after clean manual bootstrap runs. Level 1 and Level 2 remain
disabled.

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

- `invoiceworkshop-level0-daily`: once daily at 11:00 UTC; measure, verify, inspect at most
  three unique public pages, add at most two qualified prospects, update CRM, and report
  anomalies. Hermes ID:
  `a56bbe317393`.
- `invoiceworkshop-level0-weekly`: Monday at 12:00 UTC; analyze seven-day evidence and write
  a recommendation under ignored `data/plans/`. Hermes ID: `0cf8f7ecec07`.

Both jobs start fresh and load the project skill. Neither inherits the quarantined Hermes
session. Their exact prompts are versioned under `docs/growth-jobs/`. The daily job is
pinned to `z-ai/glm-5.3-flash` through OpenRouter. The weekly job is pinned to
`openai/gpt-5-mini` with low reasoning and delegates plan composition to the reviewed
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

Pre-activation validation remained paused while rejecting inaccurate weekly drafts and a
retired/timed-out provider route. No rapid retry loop was enabled. The accepted weekly path
is deterministic, and both active jobs retain bounded no-immediate-retry behavior.

The repository is explicitly trusted by Hermes for project-skill loading. A profile-visible
symlink named `invoiceworkshop-growth` points to the versioned project skill because Hermes
assembles cron skill context before applying a job's workdir; this keeps unattended gateway
runs on the reviewed repository copy instead of a duplicated global skill.

Each execution is recorded in Hermes' native attempt/session ledgers and in `level0_runs`,
including timestamps, outcome, available usage provenance, collected source rows, prospect
changes, errors, and the invariant `external_side_effects=none`. A single failure waits for
the next normal schedule. Three consecutive Google auth/API failures pause `google_reads`;
after remediation an owner/engineer can reset it explicitly with:

```bash
python3 scripts/growth_job_log.py resume --operation google_reads
```

Current next runs: daily at `2026-08-27T11:00:00+00:00`; weekly at
`2026-08-31T12:00:00+00:00`.

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
