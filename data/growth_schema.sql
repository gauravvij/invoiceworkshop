-- InvoiceWorkshop Level-0 growth operating store.
-- Local-only: never store credentials, document contents, or customer data here.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES ('schema_version', '5')
ON CONFLICT(key) DO UPDATE SET value = excluded.value;

CREATE TABLE IF NOT EXISTS collection_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL CHECK (status IN ('running', 'ok', 'partial', 'failed')),
  errors_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS level0_runs (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name                 TEXT NOT NULL CHECK (job_name IN ('daily', 'weekly')),
  hermes_job_id            TEXT NOT NULL,
  started_at               TEXT NOT NULL,
  finished_at              TEXT,
  status                   TEXT NOT NULL CHECK (status IN ('running', 'success', 'failure')),
  model_api_usage_json     TEXT NOT NULL DEFAULT '{"availability":"Hermes session metadata"}',
  gsc_rows_collected       INTEGER NOT NULL DEFAULT 0,
  ga4_rows_collected       INTEGER NOT NULL DEFAULT 0,
  prospects_discovered     INTEGER NOT NULL DEFAULT 0,
  prospects_updated        INTEGER NOT NULL DEFAULT 0,
  errors_json              TEXT NOT NULL DEFAULT '[]',
  external_side_effects    TEXT NOT NULL DEFAULT 'none' CHECK (external_side_effects = 'none'),
  collection_run_start_id  INTEGER NOT NULL DEFAULT 0,
  prospect_start_id        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_level0_runs_job_started
  ON level0_runs(job_name, started_at DESC);

CREATE TABLE IF NOT EXISTS measurement_signals (
  id                         INTEGER PRIMARY KEY AUTOINCREMENT,
  collection_run_id          INTEGER NOT NULL UNIQUE REFERENCES collection_runs(id),
  previous_collection_run_id INTEGER,
  created_at                 TEXT NOT NULL,
  meaningful                 INTEGER NOT NULL CHECK (meaningful IN (0, 1)),
  signal_count               INTEGER NOT NULL DEFAULT 0,
  signals_json               TEXT NOT NULL DEFAULT '[]',
  context_json               TEXT NOT NULL DEFAULT '{}',
  external_side_effects      TEXT NOT NULL DEFAULT 'none'
    CHECK (external_side_effects = 'none')
);
CREATE INDEX IF NOT EXISTS idx_measurement_signals_created
  ON measurement_signals(created_at DESC);

CREATE TABLE IF NOT EXISTS research_runs (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  hermes_job_id         TEXT NOT NULL,
  started_at            TEXT NOT NULL,
  finished_at           TEXT,
  status                TEXT NOT NULL CHECK (status IN (
                          'running', 'success', 'failure', 'budget_stopped'
                        )),
  soft_token_budget     INTEGER NOT NULL,
  soft_tool_budget      INTEGER NOT NULL,
  candidates_examined   INTEGER NOT NULL DEFAULT 0,
  prospect_start_id     INTEGER NOT NULL DEFAULT 0,
  prospects_retained    INTEGER NOT NULL DEFAULT 0,
  duplicates_rejected   INTEGER NOT NULL DEFAULT 0,
  tool_calls_reported   INTEGER,
  errors_json           TEXT NOT NULL DEFAULT '[]',
  external_side_effects TEXT NOT NULL DEFAULT 'none'
    CHECK (external_side_effects = 'none')
);
CREATE INDEX IF NOT EXISTS idx_research_runs_started
  ON research_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS agent_executions (
  session_id             TEXT PRIMARY KEY,
  hermes_execution_id    TEXT UNIQUE,
  hermes_job_id          TEXT NOT NULL,
  job_name               TEXT NOT NULL,
  started_at             TEXT NOT NULL,
  finished_at            TEXT,
  status                 TEXT NOT NULL,
  model                  TEXT,
  input_tokens           INTEGER NOT NULL DEFAULT 0,
  output_tokens          INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens      INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens     INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens       INTEGER NOT NULL DEFAULT 0,
  total_tokens           INTEGER NOT NULL DEFAULT 0,
  api_calls              INTEGER NOT NULL DEFAULT 0,
  tool_calls             INTEGER NOT NULL DEFAULT 0,
  execution_duration_ms  INTEGER,
  candidates_examined    INTEGER,
  prospects_retained     INTEGER,
  duplicates_rejected    INTEGER,
  errors_json            TEXT NOT NULL DEFAULT '[]',
  external_side_effects  TEXT NOT NULL DEFAULT 'none'
    CHECK (external_side_effects = 'none'),
  synced_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_executions_job_started
  ON agent_executions(hermes_job_id, started_at DESC);

CREATE TABLE IF NOT EXISTS operation_state (
  operation      TEXT PRIMARY KEY,
  state          TEXT NOT NULL CHECK (state IN ('active', 'paused')),
  failure_streak INTEGER NOT NULL DEFAULT 0,
  last_error     TEXT,
  updated_at     TEXT NOT NULL
);
INSERT INTO operation_state (operation, state, failure_streak, updated_at)
VALUES ('google_reads', 'active', 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(operation) DO NOTHING;

-- Actual per-calendar-day metrics. A collector refreshes recent dates to account
-- for reporting lag; values are not rolling-window totals.
CREATE TABLE IF NOT EXISTS metrics_daily (
  date              TEXT PRIMARY KEY,
  gsc_impressions   INTEGER,
  gsc_clicks        INTEGER,
  gsc_ctr           REAL,
  gsc_avg_position  REAL,
  ga_sessions       INTEGER,
  ga_users          INTEGER,
  ga_pageviews      INTEGER,
  ga_tool_starts    INTEGER,
  ga_pdf_downloads  INTEGER,
  ga_returning      INTEGER,
  collected_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  collected_at TEXT NOT NULL,
  source       TEXT NOT NULL CHECK (source IN ('gsc', 'ga4', 'sitemap', 'inspection', 'health')),
  window_start TEXT,
  window_end   TEXT,
  status       TEXT NOT NULL CHECK (status IN ('ok', 'empty', 'partial', 'failed')),
  row_count    INTEGER NOT NULL DEFAULT 0,
  totals_json  TEXT NOT NULL DEFAULT '{}',
  error        TEXT,
  PRIMARY KEY (collected_at, source)
);

-- Query/page/country/device aggregates for the current lookback window.
CREATE TABLE IF NOT EXISTS gsc_breakdowns (
  snapshot_date TEXT NOT NULL,
  dimension     TEXT NOT NULL CHECK (dimension IN ('query', 'page', 'country', 'device')),
  value         TEXT NOT NULL,
  clicks        INTEGER NOT NULL DEFAULT 0,
  impressions   INTEGER NOT NULL DEFAULT 0,
  ctr           REAL,
  position      REAL,
  window_start  TEXT NOT NULL,
  window_end    TEXT NOT NULL,
  PRIMARY KEY (snapshot_date, dimension, value)
);

-- Combined Search Console facts. Unlike gsc_breakdowns, every row preserves
-- the query/page/country/device/date relationship returned by Google. Older
-- aggregate rows remain untouched and are never backfilled by inference.
CREATE TABLE IF NOT EXISTS gsc_query_facts (
  snapshot_date TEXT NOT NULL,
  date          TEXT NOT NULL,
  query         TEXT NOT NULL,
  page          TEXT NOT NULL,
  country       TEXT NOT NULL,
  device        TEXT NOT NULL,
  clicks        INTEGER NOT NULL DEFAULT 0,
  impressions   INTEGER NOT NULL DEFAULT 0,
  ctr           REAL,
  position      REAL,
  window_start  TEXT NOT NULL,
  window_end    TEXT NOT NULL,
  PRIMARY KEY (snapshot_date, date, query, page, country, device)
);
CREATE INDEX IF NOT EXISTS idx_gsc_query_facts_date
  ON gsc_query_facts(date DESC, impressions DESC);

-- GA4 acquisition facts. traffic_class remains unknown unless an explicit
-- configured rule identifies a row; historical traffic is never relabeled.
CREATE TABLE IF NOT EXISTS ga4_acquisition (
  snapshot_date          TEXT NOT NULL,
  date                   TEXT NOT NULL,
  source                 TEXT NOT NULL,
  medium                 TEXT NOT NULL,
  source_medium          TEXT NOT NULL,
  default_channel_group  TEXT NOT NULL,
  users                  INTEGER NOT NULL DEFAULT 0,
  sessions               INTEGER NOT NULL DEFAULT 0,
  pageviews              INTEGER NOT NULL DEFAULT 0,
  tool_starts            INTEGER NOT NULL DEFAULT 0,
  pdf_downloads          INTEGER NOT NULL DEFAULT 0,
  returning_loads        INTEGER NOT NULL DEFAULT 0,
  traffic_class          TEXT NOT NULL DEFAULT 'unknown'
    CHECK (traffic_class IN ('unknown', 'internal', 'external')),
  classification_reason  TEXT,
  window_start           TEXT NOT NULL,
  window_end             TEXT NOT NULL,
  PRIMARY KEY (
    snapshot_date, date, source, medium, default_channel_group, traffic_class
  )
);
CREATE INDEX IF NOT EXISTS idx_ga4_acquisition_date
  ON ga4_acquisition(date DESC, sessions DESC);

CREATE TABLE IF NOT EXISTS url_health (
  date         TEXT NOT NULL,
  url          TEXT NOT NULL,
  checked_at   TEXT NOT NULL,
  status       INTEGER,
  final_url    TEXT,
  response_ms  INTEGER,
  error        TEXT,
  PRIMARY KEY (date, url)
);

CREATE TABLE IF NOT EXISTS index_state (
  date             TEXT NOT NULL,
  url              TEXT NOT NULL,
  inspected_at     TEXT NOT NULL,
  verdict          TEXT,
  coverage_state   TEXT,
  indexing_state   TEXT,
  robots_state     TEXT,
  fetch_state      TEXT,
  last_crawl_time  TEXT,
  google_canonical TEXT,
  user_canonical   TEXT,
  error            TEXT,
  PRIMARY KEY (date, url)
);

CREATE TABLE IF NOT EXISTS sitemap_state (
  date            TEXT NOT NULL,
  path            TEXT NOT NULL,
  collected_at    TEXT NOT NULL,
  errors          INTEGER,
  warnings        INTEGER,
  last_submitted  TEXT,
  last_downloaded TEXT,
  is_pending      INTEGER,
  error           TEXT,
  PRIMARY KEY (date, path)
);

-- Level-0 research CRM. external_action_approved is deliberately immutable
-- through the Level-0 CLI; a future Level-1 approval workflow must own it.
CREATE TABLE IF NOT EXISTS prospects (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  domain                   TEXT NOT NULL,
  page_url                 TEXT NOT NULL,
  prospect_type            TEXT NOT NULL CHECK (prospect_type IN (
    'resource', 'editorial', 'directory', 'community', 'discovery',
    'broken', 'gap', 'other'
  )),
  opportunity_score        INTEGER NOT NULL CHECK (opportunity_score BETWEEN 0 AND 100),
  risk                     TEXT NOT NULL CHECK (risk IN ('low', 'medium', 'high')),
  why_fit                  TEXT NOT NULL,
  audience                 TEXT NOT NULL,
  contact_method           TEXT NOT NULL,
  requires_account         INTEGER NOT NULL DEFAULT 0 CHECK (requires_account IN (0, 1)),
  requires_payment         INTEGER NOT NULL DEFAULT 0 CHECK (requires_payment IN (0, 1)),
  link_type                TEXT NOT NULL DEFAULT 'unknown',
  source_url               TEXT NOT NULL,
  status                   TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'qualified', 'rejected', 'retired')),
  rejection_reason         TEXT,
  external_action_approved INTEGER NOT NULL DEFAULT 0 CHECK (external_action_approved IN (0, 1)),
  approved_by              TEXT,
  approved_at              TEXT,
  notes                    TEXT NOT NULL DEFAULT '',
  discovered_at            TEXT NOT NULL,
  updated_at               TEXT NOT NULL,
  UNIQUE(domain, page_url)
);
CREATE INDEX IF NOT EXISTS idx_prospects_score ON prospects(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);

-- Evidence and second-pass review fields are separate so the original CRM
-- rows and history remain unchanged while stricter qualifications evolve.
CREATE TABLE IF NOT EXISTS prospect_qualification (
  prospect_id          INTEGER PRIMARY KEY REFERENCES prospects(id),
  channel              TEXT NOT NULL,
  page_evidence        TEXT NOT NULL,
  outbound_resources   TEXT NOT NULL DEFAULT '',
  target_url           TEXT NOT NULL,
  proposed_action      TEXT NOT NULL,
  confidence           TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  second_pass_pass     INTEGER NOT NULL CHECK (second_pass_pass IN (0, 1)),
  review_reason        TEXT NOT NULL,
  reviewed_at          TEXT NOT NULL
);

-- Cheap discovery results enter this queue before any model sees them.
CREATE TABLE IF NOT EXISTS research_candidates (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  domain             TEXT NOT NULL,
  page_url           TEXT NOT NULL,
  channel            TEXT NOT NULL,
  query_theme        TEXT NOT NULL,
  title              TEXT NOT NULL DEFAULT '',
  snippet            TEXT NOT NULL DEFAULT '',
  contact_url        TEXT,
  heuristic_score    INTEGER NOT NULL DEFAULT 0,
  state              TEXT NOT NULL DEFAULT 'queued'
    CHECK (state IN ('queued', 'shortlisted', 'qualified', 'rejected', 'deferred')),
  rejection_reason   TEXT,
  discovered_at      TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE(domain, page_url)
);
CREATE INDEX IF NOT EXISTS idx_research_candidates_state_score
  ON research_candidates(state, heuristic_score DESC, id);

-- Reserved for a separately approved Level-1 implementation. Level 0 never
-- inserts rows here.
CREATE TABLE IF NOT EXISTS outreach (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id INTEGER NOT NULL REFERENCES prospects(id),
  channel     TEXT NOT NULL,
  attempt     INTEGER NOT NULL CHECK (attempt BETWEEN 1 AND 2),
  sent_at     TEXT NOT NULL,
  body_hash   TEXT NOT NULL,
  response    TEXT,
  notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS placements (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id          INTEGER REFERENCES prospects(id),
  placement_url        TEXT NOT NULL,
  link_target          TEXT NOT NULL,
  rel                  TEXT,
  anchor               TEXT,
  status               TEXT NOT NULL DEFAULT 'unverified' CHECK (status IN ('unverified', 'live', 'suspect', 'dead')),
  link_present         INTEGER CHECK (link_present IN (0, 1)),
  last_http_status     INTEGER,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  verified_at          TEXT,
  notes                TEXT NOT NULL DEFAULT '',
  UNIQUE(placement_url, link_target)
);

CREATE TABLE IF NOT EXISTS experiments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  action     TEXT NOT NULL,
  hypothesis TEXT NOT NULL,
  channel    TEXT,
  date       TEXT NOT NULL,
  result     TEXT,
  cost       REAL NOT NULL DEFAULT 0 CHECK (cost >= 0),
  outcome    TEXT,
  repeat     INTEGER CHECK (repeat IN (0, 1))
);
