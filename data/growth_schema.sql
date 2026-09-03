-- InvoiceWorkshop Level-0 growth operating store.
-- Local-only: never store credentials, document contents, or customer data here.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES ('schema_version', '23')
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

-- Level-1A is a separately controlled, disabled-by-default execution layer.
-- Level-0 tools never update these approval or activation records.
CREATE TABLE IF NOT EXISTS level1a_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
INSERT INTO level1a_settings (key, value, updated_at)
VALUES ('outbound_enabled', 'false', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;
INSERT INTO level1a_settings (key, value, updated_at)
VALUES ('daily_new_cap', '3', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;
INSERT INTO level1a_settings (key, value, updated_at)
VALUES ('daily_total_cap', '5', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;
INSERT INTO level1a_settings (key, value, updated_at)
VALUES ('email_outbound_enabled', 'false', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;
INSERT INTO level1a_settings (key, value, updated_at)
VALUES ('form_outbound_enabled', 'false', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
ON CONFLICT(key) DO NOTHING;

CREATE TABLE IF NOT EXISTS level1a_claims (
  claim_key      TEXT NOT NULL,
  version        INTEGER NOT NULL CHECK (version > 0),
  canonical_text TEXT NOT NULL,
  evidence_ref   TEXT NOT NULL,
  active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at     TEXT NOT NULL,
  PRIMARY KEY (claim_key, version)
);

-- Owner-approved wordings for an approved factual claim. Every product assertion
-- in an initial Level-1A message must appear here verbatim, tied to a canonical
-- claim and its evidence, so hand-written copy cannot drift from what is true.
CREATE TABLE IF NOT EXISTS level1a_claim_paraphrases (
  claim_key    TEXT NOT NULL,
  paraphrase   TEXT NOT NULL,
  evidence_ref TEXT NOT NULL,
  active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at   TEXT NOT NULL,
  PRIMARY KEY (claim_key, paraphrase)
);

CREATE TABLE IF NOT EXISTS level1a_templates (
  template_id           TEXT NOT NULL,
  version               INTEGER NOT NULL CHECK (version > 0),
  action_type           TEXT NOT NULL CHECK (action_type IN (
                          'resource_suggestion', 'directory_submission',
                          'broken_resource_replacement', 'roundup_suggestion'
                        )),
  subject_template      TEXT NOT NULL,
  opening_template      TEXT NOT NULL,
  context_template      TEXT NOT NULL DEFAULT '',
  fit_template          TEXT NOT NULL,
  close_template        TEXT NOT NULL,
  max_body_characters   INTEGER NOT NULL CHECK (max_body_characters BETWEEN 200 AND 1500),
  active                INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at            TEXT NOT NULL,
  PRIMARY KEY (template_id, version)
);

CREATE TABLE IF NOT EXISTS level1a_actions (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id               INTEGER NOT NULL REFERENCES prospects(id),
  organization              TEXT NOT NULL,
  external_page_url         TEXT NOT NULL,
  verified_contact_route    TEXT NOT NULL,
  contact_kind              TEXT NOT NULL CHECK (contact_kind IN ('email', 'form')),
  execution_class           TEXT NOT NULL CHECK (execution_class IN (
                              'level1a_email', 'level1a_form'
                            )),
  recipient                 TEXT,
  form_handler              TEXT,
  action_type               TEXT NOT NULL CHECK (action_type IN (
                              'resource_suggestion', 'directory_submission',
                              'broken_resource_replacement', 'roundup_suggestion'
                            )),
  target_url                TEXT NOT NULL,
  allowed_intent            TEXT NOT NULL,
  allowed_claim_keys_json   TEXT NOT NULL,
  forbidden_claims_json     TEXT NOT NULL,
  relevance_terms_json      TEXT NOT NULL,
  template_id               TEXT NOT NULL,
  template_version          INTEGER NOT NULL,
  subject_value             TEXT NOT NULL,
  opening_value             TEXT NOT NULL,
  fit_value                 TEXT NOT NULL,
  context_value             TEXT NOT NULL DEFAULT '',
  close_value               TEXT NOT NULL,
  max_followups             INTEGER NOT NULL DEFAULT 2 CHECK (max_followups BETWEEN 0 AND 2),
  attachments_allowed       INTEGER NOT NULL DEFAULT 0 CHECK (attachments_allowed = 0),
  payment_allowed           INTEGER NOT NULL DEFAULT 0 CHECK (payment_allowed = 0),
  external_action_approved  INTEGER NOT NULL DEFAULT 0 CHECK (external_action_approved IN (0, 1)),
  message_approved          INTEGER NOT NULL DEFAULT 0 CHECK (message_approved IN (0, 1)),
  approved_message_hash     TEXT,
  approved_message_hashes_json TEXT NOT NULL DEFAULT '[]',
  approved_by               TEXT,
  approved_at               TEXT,
  suppression_state         TEXT NOT NULL DEFAULT 'active' CHECK (suppression_state IN (
                              'active', 'declined', 'unsubscribed', 'bounced',
                              'placed', 'suppressed'
                            )),
  last_verified_at          TEXT,
  verification_expires_at   TEXT,
  page_title                TEXT NOT NULL,
  page_excerpt              TEXT NOT NULL,
  created_at                TEXT NOT NULL,
  updated_at                TEXT NOT NULL,
  FOREIGN KEY (template_id, template_version)
    REFERENCES level1a_templates(template_id, version),
  UNIQUE (prospect_id, action_type, verified_contact_route)
);
CREATE INDEX IF NOT EXISTS idx_level1a_actions_org
  ON level1a_actions(organization, suppression_state);

CREATE TABLE IF NOT EXISTS level1a_action_audit (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id             INTEGER NOT NULL REFERENCES level1a_actions(id),
  message_id            TEXT NOT NULL UNIQUE,
  attempt_number        INTEGER NOT NULL CHECK (attempt_number BETWEEN 0 AND 2),
  mode                  TEXT NOT NULL CHECK (mode IN ('dry_run', 'live')),
  started_at            TEXT NOT NULL,
  finished_at           TEXT NOT NULL,
  subject               TEXT NOT NULL,
  body                  TEXT NOT NULL,
  recipient_or_route    TEXT NOT NULL,
  source_page           TEXT NOT NULL,
  target_url            TEXT NOT NULL,
  message_hash          TEXT NOT NULL,
  validation_result     TEXT NOT NULL CHECK (validation_result IN (
                          'review_ready', 'passed', 'rejected'
                        )),
  rejection_reason      TEXT,
  provider_response_id  TEXT,
  provider_thread_id    TEXT,
  delivery_state        TEXT NOT NULL CHECK (delivery_state IN (
                          'none', 'submitted', 'delivered', 'bounced', 'unknown'
                        )),
  reply_state           TEXT,
  suppression_state     TEXT NOT NULL,
  external_side_effects TEXT NOT NULL CHECK (external_side_effects IN (
                          'none', 'email_sent', 'form_submitted', 'unknown'
                        ))
);
CREATE INDEX IF NOT EXISTS idx_level1a_audit_action
  ON level1a_action_audit(action_id, started_at DESC);

CREATE TABLE IF NOT EXISTS level1a_suppressions (
  suppression_key TEXT PRIMARY KEY,
  organization    TEXT NOT NULL,
  recipient       TEXT,
  state           TEXT NOT NULL CHECK (state IN (
                    'declined', 'unsubscribed', 'bounced', 'placed', 'suppressed'
                  )),
  reason          TEXT NOT NULL,
  permanent       INTEGER NOT NULL DEFAULT 1 CHECK (permanent IN (0, 1)),
  created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS level1a_replies (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id               INTEGER NOT NULL REFERENCES level1a_actions(id),
  provider_message_id     TEXT NOT NULL UNIQUE,
  received_at             TEXT NOT NULL,
  classification          TEXT NOT NULL CHECK (classification IN (
                            'positive', 'information_requested', 'decline',
                            'unsubscribe', 'bounce', 'payment_requested',
                            'editorial_author_required', 'partnership',
                            'legal_compliance', 'ambiguous'
                          )),
  requires_escalation     INTEGER NOT NULL CHECK (requires_escalation IN (0, 1)),
  automated_action        TEXT NOT NULL,
  content_hash            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS level1a_mail_poll_state (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS level1a_mail_poll_runs (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at            TEXT NOT NULL,
  finished_at           TEXT NOT NULL,
  status                TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failure')),
  messages_examined     INTEGER NOT NULL DEFAULT 0,
  matched_replies       INTEGER NOT NULL DEFAULT 0,
  bounces_detected      INTEGER NOT NULL DEFAULT 0,
  suppressions_updated  INTEGER NOT NULL DEFAULT 0,
  errors_json           TEXT NOT NULL DEFAULT '[]',
  external_side_effects TEXT NOT NULL DEFAULT 'none' CHECK (external_side_effects='none')
);

CREATE TABLE IF NOT EXISTS level1a_inbound_audit (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_message_id       TEXT NOT NULL UNIQUE,
  provider_thread_id        TEXT,
  received_at               TEXT NOT NULL,
  sender_hash               TEXT NOT NULL,
  subject_hash              TEXT NOT NULL,
  matched_action_id         INTEGER REFERENCES level1a_actions(id),
  match_method              TEXT,
  authentication_state      TEXT NOT NULL CHECK (authentication_state IN (
                              'pass', 'unverified', 'fail'
                            )),
  classification            TEXT,
  requires_escalation       INTEGER CHECK (requires_escalation IN (0, 1)),
  content_hash              TEXT,
  attachment_ignored        INTEGER NOT NULL DEFAULT 0 CHECK (attachment_ignored IN (0, 1)),
  external_content_executed INTEGER NOT NULL DEFAULT 0 CHECK (external_content_executed=0),
  recorded_at               TEXT NOT NULL
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

-- ---------------------------------------------------------------------------
-- Aggressive backlink opportunity engine.
-- Discovery is read-only and deterministic. Nothing here grants outbound
-- capability: execution still runs through the Level-1A action gates.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS backlink_discovery_runs (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at        TEXT NOT NULL,
  finished_at       TEXT,
  mode              TEXT NOT NULL CHECK (mode IN ('daily', 'deep', 'accelerated', 'manual')),
  channels_json     TEXT NOT NULL DEFAULT '[]',
  raw_discovered    INTEGER NOT NULL DEFAULT 0,
  filtered          INTEGER NOT NULL DEFAULT 0,
  duplicates        INTEGER NOT NULL DEFAULT 0,
  extracted         INTEGER NOT NULL DEFAULT 0,
  reviewed          INTEGER NOT NULL DEFAULT 0,
  qualified         INTEGER NOT NULL DEFAULT 0,
  rejected          INTEGER NOT NULL DEFAULT 0,
  llm_reviewed      INTEGER NOT NULL DEFAULT 0,
  tokens_used       INTEGER NOT NULL DEFAULT 0,
  tool_calls        INTEGER NOT NULL DEFAULT 0,
  http_requests     INTEGER NOT NULL DEFAULT 0,
  cost_usd          REAL,
  status            TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'success', 'partial', 'failed')),
  errors_json       TEXT NOT NULL DEFAULT '[]',
  external_side_effects TEXT NOT NULL DEFAULT 'none'
                      CHECK (external_side_effects IN ('none', 'unknown'))
);

-- Part J: which channels earn more effort and which get throttled.
CREATE TABLE IF NOT EXISTS backlink_channel_stats (
  channel            TEXT PRIMARY KEY,
  runs               INTEGER NOT NULL DEFAULT 0,
  raw_discovered     INTEGER NOT NULL DEFAULT 0,
  qualified          INTEGER NOT NULL DEFAULT 0,
  tier_a             INTEGER NOT NULL DEFAULT 0,
  rejected           INTEGER NOT NULL DEFAULT 0,
  contacted          INTEGER NOT NULL DEFAULT 0,
  replies            INTEGER NOT NULL DEFAULT 0,
  placements         INTEGER NOT NULL DEFAULT 0,
  referral_sessions  INTEGER NOT NULL DEFAULT 0,
  barren_streak      INTEGER NOT NULL DEFAULT 0,
  effort_weight      REAL NOT NULL DEFAULT 1.0 CHECK (effort_weight BETWEEN 0.0 AND 3.0),
  last_run_at        TEXT,
  updated_at         TEXT NOT NULL
);

-- Channel 1: reusable competitor-gap dataset so the same domains are not
-- rediscovered every cycle.
CREATE TABLE IF NOT EXISTS competitor_pages (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  competitor     TEXT NOT NULL,
  referring_url  TEXT NOT NULL,
  referring_domain TEXT NOT NULL,
  anchor         TEXT NOT NULL DEFAULT '',
  link_reason    TEXT NOT NULL DEFAULT 'unknown' CHECK (link_reason IN (
                   'resource_recommendation', 'tool_roundup', 'editorial_recommendation',
                   'freelancer_resource', 'small_business_resource', 'contractor_resource',
                   'accounting_resource', 'template_collection', 'educational_resource',
                   'funding_or_news', 'affiliate', 'unrelated_partnership',
                   'login_portal', 'paid_placement', 'spam', 'unknown')),
  actionable     INTEGER NOT NULL DEFAULT 0 CHECK (actionable IN (0, 1)),
  first_seen_at  TEXT NOT NULL,
  last_seen_at   TEXT NOT NULL,
  UNIQUE(competitor, referring_url)
);

-- Scored, tiered opportunities. Editorial/resource work only; community
-- discussion opportunities live in their own table.
CREATE TABLE IF NOT EXISTS backlink_opportunities (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  domain              TEXT NOT NULL,
  page_url            TEXT NOT NULL,
  channel             TEXT NOT NULL,
  discovery_run_id    INTEGER REFERENCES backlink_discovery_runs(id),
  title               TEXT NOT NULL DEFAULT '',
  page_evidence       TEXT NOT NULL DEFAULT '',
  audience            TEXT NOT NULL DEFAULT '',
  contact_route       TEXT,
  contact_kind        TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (contact_kind IN ('email', 'form', 'editorial_guidelines', 'unknown')),
  recipient           TEXT,
  target_url          TEXT NOT NULL,
  opportunity_type    TEXT NOT NULL DEFAULT 'resource' CHECK (opportunity_type IN (
                        'resource', 'roundup', 'directory', 'broken_replacement',
                        'unlinked_mention', 'competitor_gap', 'editorial', 'other')),
  broken_url          TEXT,
  broken_evidence     TEXT,
  score_relevance     INTEGER NOT NULL DEFAULT 0 CHECK (score_relevance BETWEEN 0 AND 25),
  score_audience      INTEGER NOT NULL DEFAULT 0 CHECK (score_audience BETWEEN 0 AND 20),
  score_legitimacy    INTEGER NOT NULL DEFAULT 0 CHECK (score_legitimacy BETWEEN 0 AND 15),
  score_resource_fit  INTEGER NOT NULL DEFAULT 0 CHECK (score_resource_fit BETWEEN 0 AND 15),
  score_likelihood    INTEGER NOT NULL DEFAULT 0 CHECK (score_likelihood BETWEEN 0 AND 10),
  score_referral      INTEGER NOT NULL DEFAULT 0 CHECK (score_referral BETWEEN 0 AND 10),
  score_seo           INTEGER NOT NULL DEFAULT 0 CHECK (score_seo BETWEEN 0 AND 5),
  total_score         INTEGER NOT NULL DEFAULT 0 CHECK (total_score BETWEEN 0 AND 100),
  tier                TEXT NOT NULL DEFAULT 'C' CHECK (tier IN ('A', 'B', 'C', 'reject')),
  second_pass_pass    INTEGER NOT NULL DEFAULT 0 CHECK (second_pass_pass IN (0, 1)),
  second_pass_reason  TEXT NOT NULL DEFAULT '',
  rejection_reason    TEXT,
  requires_account    INTEGER NOT NULL DEFAULT 0 CHECK (requires_account IN (0, 1)),
  requires_payment    INTEGER NOT NULL DEFAULT 0 CHECK (requires_payment IN (0, 1)),
  llm_reviewed        INTEGER NOT NULL DEFAULT 0 CHECK (llm_reviewed IN (0, 1)),
  extracted_at        TEXT,
  fetch_attempts      INTEGER NOT NULL DEFAULT 0,
  vendor_content      INTEGER NOT NULL DEFAULT 0 CHECK (vendor_content IN (0, 1)),
  -- Outbound linking behaviour. A page that already sends readers to third-party
  -- tools is far likelier to add another than one that links nowhere.
  external_link_count INTEGER NOT NULL DEFAULT -1,
  tool_link_count     INTEGER NOT NULL DEFAULT -1,
  promoted_prospect_id INTEGER REFERENCES prospects(id),
  discovered_at       TEXT NOT NULL,
  updated_at          TEXT NOT NULL,
  UNIQUE(domain, page_url)
);
CREATE INDEX IF NOT EXISTS idx_backlink_opportunities_tier
  ON backlink_opportunities(tier, total_score DESC);

-- Channel 10. Deliberately separate from editorial backlink prospects:
-- research and draft only, never autonomous posting.
CREATE TABLE IF NOT EXISTS community_opportunities (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  platform           TEXT NOT NULL,
  thread_url         TEXT NOT NULL UNIQUE,
  title              TEXT NOT NULL DEFAULT '',
  question_summary   TEXT NOT NULL DEFAULT '',
  relevance_evidence TEXT NOT NULL DEFAULT '',
  helpful_without_link INTEGER NOT NULL DEFAULT 0 CHECK (helpful_without_link IN (0, 1)),
  links_permitted    TEXT NOT NULL DEFAULT 'unknown'
                       CHECK (links_permitted IN ('yes', 'no', 'unknown')),
  thread_recent      INTEGER NOT NULL DEFAULT 0 CHECK (thread_recent IN (0, 1)),
  requires_identity  INTEGER NOT NULL DEFAULT 0 CHECK (requires_identity IN (0, 1)),
  suggested_target   TEXT NOT NULL DEFAULT '',
  draft_response     TEXT NOT NULL DEFAULT '',
  state              TEXT NOT NULL DEFAULT 'draft_only'
                       CHECK (state IN ('draft_only', 'owner_review', 'rejected')),
  rejection_reason   TEXT,
  discovered_at      TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);

-- Part F: placement observations over time, joined to product outcomes.
CREATE TABLE IF NOT EXISTS placement_observations (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  placement_id      INTEGER NOT NULL REFERENCES placements(id),
  observed_at       TEXT NOT NULL,
  http_status       INTEGER,
  indexable         INTEGER CHECK (indexable IN (0, 1)),
  link_present      INTEGER CHECK (link_present IN (0, 1)),
  rel               TEXT,
  anchor            TEXT,
  surrounding_text  TEXT NOT NULL DEFAULT '',
  referral_sessions INTEGER,
  notes             TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_placement_observations_placement
  ON placement_observations(placement_id, observed_at DESC);

-- Every owner-approval verification attempt, successful or not. The server
-- holds only a public verification key, so a row here records that a signature
-- made off-server was checked, never that this machine could have produced one.
CREATE TABLE IF NOT EXISTS level1a_approval_audit (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  scope           TEXT NOT NULL CHECK (scope IN ('action', 'manifest')),
  action_id       INTEGER,
  target_hash     TEXT NOT NULL,
  payload_sha256  TEXT NOT NULL,
  method          TEXT NOT NULL CHECK (method IN ('ed25519_sshsig', 'hmac_legacy')),
  signer_identity TEXT,
  key_fingerprint TEXT,
  verified        INTEGER NOT NULL CHECK (verified IN (0, 1)),
  detail          TEXT NOT NULL DEFAULT '',
  recorded_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_level1a_approval_audit_action
  ON level1a_approval_audit(action_id, recorded_at DESC);

-- ---------------------------------------------------------------------------
-- Unified growth-opportunity model.
--
-- The point is to let different KINDS of growth action compete on one scale, so
-- "improve a page that is gaining impressions" can outrank "email another
-- mediocre resource page" when it deserves to. Scores are estimates, not
-- precision: they exist to order work, not to look scientific.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS growth_opportunities (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_key     TEXT NOT NULL UNIQUE,   -- stable identity for re-scoring
  opportunity_type    TEXT NOT NULL CHECK (opportunity_type IN (
                        'SEO_PAGE_IMPROVEMENT', 'PRODUCT_UTILITY', 'NEW_SEARCH_LANDING_ASSET',
                        'LINKABLE_ASSET', 'RESOURCE_OUTREACH', 'DIRECTORY_DISTRIBUTION',
                        'INTERNAL_LINKING', 'CTR_IMPROVEMENT', 'TECHNICAL_SEO',
                        'CONTENT_REFRESH', 'SERP_GAP', 'BACKLINK_GAP',
                        'COMMUNITY_OPPORTUNITY', 'AI_SEARCH_VISIBILITY_OPPORTUNITY')),
  title               TEXT NOT NULL,
  target_url          TEXT,
  target_query        TEXT,
  evidence            TEXT NOT NULL DEFAULT '',
  evidence_strength   TEXT NOT NULL DEFAULT 'weak'
                        CHECK (evidence_strength IN ('none', 'weak', 'moderate', 'strong')),
  -- Inputs to the estimate. NULL means unknown, which is scored conservatively
  -- rather than optimistically.
  current_impressions INTEGER,
  current_clicks      INTEGER,
  current_position    REAL,
  demand_estimate     INTEGER,               -- rough monthly searches, if known
  feasibility         REAL CHECK (feasibility BETWEEN 0 AND 1),
  intent_quality      REAL CHECK (intent_quality BETWEEN 0 AND 1),
  expected_upside     INTEGER,               -- rough monthly qualified sessions
  authority_benefit   REAL CHECK (authority_benefit BETWEEN 0 AND 1),
  effort_days         REAL,
  confidence          REAL CHECK (confidence BETWEEN 0 AND 1),
  time_to_impact_days INTEGER,
  reversible          INTEGER NOT NULL DEFAULT 1 CHECK (reversible IN (0, 1)),
  risk                TEXT NOT NULL DEFAULT 'low' CHECK (risk IN ('low', 'medium', 'high')),
  expected_growth_value REAL NOT NULL DEFAULT 0,
  execution_tier      TEXT NOT NULL DEFAULT 'REVIEW'
                        CHECK (execution_tier IN ('AUTO', 'REVIEW', 'BLOCKED')),
  state               TEXT NOT NULL DEFAULT 'open'
                        CHECK (state IN ('open', 'in_progress', 'done', 'dismissed', 'escalated')),
  dismissed_reason    TEXT,
  experiment_id       INTEGER,
  first_seen_at       TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_growth_opportunities_rank
  ON growth_opportunities(state, expected_growth_value DESC);

-- Every meaningful growth action, so effects can be attributed over time rather
-- than assumed from coincidence.
CREATE TABLE IF NOT EXISTS growth_experiments (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_key    TEXT,
  hypothesis         TEXT NOT NULL,
  action             TEXT NOT NULL,
  action_type        TEXT NOT NULL,
  target_url         TEXT,
  target_query       TEXT,
  started_at         TEXT NOT NULL,
  evaluate_after     TEXT NOT NULL,          -- no conclusions before this date
  baseline_json      TEXT NOT NULL DEFAULT '{}',
  expected_outcome   TEXT NOT NULL DEFAULT '',
  observed_json      TEXT NOT NULL DEFAULT '{}',
  conclusion         TEXT,
  outcome            TEXT CHECK (outcome IN ('positive', 'negative', 'neutral', 'inconclusive')),
  attribution_note   TEXT NOT NULL DEFAULT '',
  concluded_at       TEXT,
  updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_growth_experiments_open
  ON growth_experiments(outcome, evaluate_after);

-- Owner-signed outreach policy. The owner signs the policy once; the executor
-- then checks each candidate action against it deterministically.
CREATE TABLE IF NOT EXISTS outreach_policy (
  version            INTEGER PRIMARY KEY,
  policy_json        TEXT NOT NULL,
  policy_hash        TEXT NOT NULL,
  signed             INTEGER NOT NULL DEFAULT 0 CHECK (signed IN (0, 1)),
  signer_fingerprint TEXT,
  signed_at          TEXT,
  active             INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  created_at         TEXT NOT NULL
);

-- Actions admitted under a signed policy rather than an individual signature.
CREATE TABLE IF NOT EXISTS policy_admissions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id       INTEGER NOT NULL REFERENCES level1a_actions(id),
  policy_version  INTEGER NOT NULL,
  policy_hash     TEXT NOT NULL,
  admitted        INTEGER NOT NULL CHECK (admitted IN (0, 1)),
  checks_json     TEXT NOT NULL DEFAULT '{}',
  refusal_reason  TEXT,
  recorded_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_admissions_action
  ON policy_admissions(action_id, recorded_at DESC);

-- Measured structure per canonical page, taken from the built output rather than
-- estimated. `words` is DIAGNOSTIC ONLY: Google states no preferred length, and
-- a page is never improved here because it is short. What the model acts on is
-- the feature set -- whether the page carries a worked example, a comparison of
-- the documents users confuse it with, and whether it answers the queries it
-- already surfaces for.
CREATE TABLE IF NOT EXISTS page_content_stats (
  url          TEXT NOT NULL,
  measured_at  TEXT NOT NULL,
  words        INTEGER NOT NULL,
  headings     INTEGER NOT NULL DEFAULT 0,
  bytes        INTEGER NOT NULL DEFAULT 0,
  internal_out INTEGER NOT NULL DEFAULT 0,
  internal_in  INTEGER NOT NULL DEFAULT 0,
  features_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (url, measured_at)
);
CREATE INDEX IF NOT EXISTS idx_page_content_stats_url ON page_content_stats(url, measured_at DESC);



-- Diagnosis of why a canonical URL is not earning traffic. The four index states
-- have genuinely different causes and only one of them implicates content:
--
--   indexed               nothing to do here
--   discovered_not_crawled  Google knows the URL and has never fetched it, so
--                         the page content cannot be the reason. Rewriting it
--                         is churn. The constraint is crawl scheduling.
--   crawled_not_indexed   Google read it and declined to index. This is the one
--                         state where differentiation is genuinely implicated.
--   unknown               Google has no record of the URL at all: a discovery
--                         problem (sitemap, internal links, external signals).
--
-- `blocking_checks` lists readiness checks that actually failed. When it is
-- empty the correct action is to wait, and that is recorded rather than turned
-- into another rewrite.
CREATE TABLE IF NOT EXISTS index_diagnosis (
  url              TEXT NOT NULL,
  diagnosed_at     TEXT NOT NULL,
  index_state      TEXT NOT NULL CHECK (index_state IN (
                     'indexed', 'discovered_not_crawled', 'crawled_not_indexed', 'unknown')),
  coverage_state   TEXT NOT NULL DEFAULT '',
  last_crawl_time  TEXT,
  constraint_kind  TEXT NOT NULL CHECK (constraint_kind IN (
                     'none', 'crawl_scheduling', 'discovery_signals', 'content_quality')),
  ready_json       TEXT NOT NULL DEFAULT '{}',
  blocking_checks  TEXT NOT NULL DEFAULT '',
  recommended      TEXT NOT NULL DEFAULT '',
  first_seen_state TEXT,
  days_in_state    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (url, diagnosed_at)
);
CREATE INDEX IF NOT EXISTS idx_index_diagnosis_url ON index_diagnosis(url, diagnosed_at DESC);

-- Effort allocation across growth channels. The weekly job moves these weights
-- on observed outcomes and the weights feed straight back into ranking, so a
-- channel that repeatedly fails genuinely loses ground instead of being
-- described as failing in a report nobody acts on.
CREATE TABLE IF NOT EXISTS channel_allocation (
  -- Not an allowlist. The channel portfolio is a growth decision and lives in
  -- growth_allocation.py; pinning it here only meant adding a channel needed a
  -- schema migration, which is how the portfolio stayed frozen.
  channel        TEXT PRIMARY KEY,
  weight         REAL NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0.2 AND 1.6),
  attempts       INTEGER NOT NULL DEFAULT 0,
  wins           INTEGER NOT NULL DEFAULT 0,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  min_sample     INTEGER NOT NULL DEFAULT 3,
  last_reason    TEXT NOT NULL DEFAULT 'initial prior; no outcomes observed yet',
  updated_at     TEXT NOT NULL
);

-- Every reallocation decision, including the decisions NOT to move a weight.
-- "Insufficient evidence" is a result worth keeping: it is what stops a single
-- impression from being read as a trend.
CREATE TABLE IF NOT EXISTS allocation_decisions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  decided_at     TEXT NOT NULL,
  channel        TEXT NOT NULL,
  previous_weight REAL NOT NULL,
  new_weight     REAL NOT NULL,
  attempts       INTEGER NOT NULL DEFAULT 0,
  wins           INTEGER NOT NULL DEFAULT 0,
  evidence       TEXT NOT NULL DEFAULT '',
  decision       TEXT NOT NULL CHECK (decision IN ('increase', 'reduce', 'hold', 'insufficient_evidence')),
  rationale      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_allocation_decisions ON allocation_decisions(decided_at DESC);

-- Outcome of the fixed-size outreach calibration cohort. Written once the
-- approved prospects have completed their initial and follow-up cycle, so the
-- decision to widen, narrow or stop the email channel rests on delivery, reply
-- and placement rates rather than on how many messages were sent.
CREATE TABLE IF NOT EXISTS outreach_calibration (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  evaluated_at        TEXT NOT NULL,
  cohort_size         INTEGER NOT NULL,
  completed           INTEGER NOT NULL,
  sent                INTEGER NOT NULL,
  delivered           INTEGER NOT NULL,
  bounced             INTEGER NOT NULL,
  replies             INTEGER NOT NULL,
  positive_replies    INTEGER NOT NULL,
  placements          INTEGER NOT NULL,
  by_class_json       TEXT NOT NULL DEFAULT '{}',
  recommendation      TEXT NOT NULL CHECK (recommendation IN (
                        'SIGN_POLICY_AND_AUTONOMIZE', 'MODIFY_POLICY_TEMPLATES',
                        'REDUCE_EMAIL_ALLOCATION', 'STOP_CHANNEL', 'CONTINUE_CALIBRATION')),
  rationale           TEXT NOT NULL DEFAULT ''
);


-- Every unattended Claude Code invocation, successful or not. This is the
-- ledger the weekly review uses to answer "is waking the reasoning agent
-- producing enough growth value to justify what it costs?", so a run that
-- decided to do nothing is as important to record as one that shipped.
CREATE TABLE IF NOT EXISTS claude_runs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  run_type       TEXT NOT NULL CHECK (run_type IN (
                   'auto_opportunity', 'weekly_strategist', 'fixture')),
  opportunity_key TEXT,
  opportunity_id INTEGER,
  target_url     TEXT,
  model          TEXT NOT NULL DEFAULT '',
  session_id     TEXT,
  outcome        TEXT NOT NULL CHECK (outcome IN (
                   'changed', 'no_action', 'refused', 'validation_failed',
                   'deploy_failed', 'verify_failed', 'rolled_back', 'timeout',
                   'blocked_auth', 'error')),
  num_turns      INTEGER,
  cost_usd       REAL,
  duration_ms    INTEGER,
  files_changed  TEXT NOT NULL DEFAULT '',
  commit_sha     TEXT,
  ci_run_id      TEXT,
  deployed       INTEGER NOT NULL DEFAULT 0 CHECK (deployed IN (0, 1)),
  summary        TEXT NOT NULL DEFAULT '',
  error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_claude_runs_started ON claude_runs(started_at DESC);

-- One row per unattended orchestrator run. Written whether or not anything
-- happened, so a silent week is distinguishable from a scheduler that stopped.
CREATE TABLE IF NOT EXISTS autonomous_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  trigger       TEXT NOT NULL DEFAULT 'scheduler',
  decision      TEXT NOT NULL CHECK (decision IN (
                  'no_action', 'claude_invoked', 'deterministic_only',
                  'budget_exhausted', 'locked', 'blocked', 'error')),
  reason        TEXT NOT NULL DEFAULT '',
  claude_run_id INTEGER REFERENCES claude_runs(id),
  steps_json    TEXT NOT NULL DEFAULT '{}'
);

-- Things a person actually needs to see. Routine successful runs never land
-- here; the point of the table is that its being empty is meaningful.
CREATE TABLE IF NOT EXISTS escalations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  raised_at    TEXT NOT NULL,
  kind         TEXT NOT NULL,
  severity     TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  subject      TEXT NOT NULL,
  detail       TEXT NOT NULL DEFAULT '',
  fingerprint  TEXT NOT NULL UNIQUE,
  occurrences  INTEGER NOT NULL DEFAULT 1,
  last_seen_at TEXT NOT NULL,
  acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1)),
  resolved_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_escalations_open
  ON escalations(resolved_at, severity, last_seen_at DESC);


-- The 90-day aggressive growth experiment.
--
-- One row per metric per week, written once when the experiment starts, so the
-- targets cannot drift to meet whatever happened. Sessions are the destination;
-- the leading indicators are what can actually be steered in the first weeks,
-- when sessions are still rounding to zero.
CREATE TABLE IF NOT EXISTS growth_targets (
  experiment    TEXT NOT NULL,
  week          INTEGER NOT NULL CHECK (week BETWEEN 0 AND 13),
  week_ending   TEXT NOT NULL,
  -- Deliberately not an allowlist. The metric set is the objective, it lives
  -- in growth_trajectory.py, and duplicating it here only meant the objective
  -- could not change without a schema migration.
  metric        TEXT NOT NULL,
  target        REAL NOT NULL,
  rationale     TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (experiment, week, metric)
);

-- What actually happened, measured, against what was planned. Written weekly and
-- never edited: the record of a missed week is the point of the record.
CREATE TABLE IF NOT EXISTS trajectory_checkpoints (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment     TEXT NOT NULL,
  week           INTEGER NOT NULL,
  checked_at     TEXT NOT NULL,
  metrics_json   TEXT NOT NULL DEFAULT '{}',
  attainment     REAL NOT NULL DEFAULT 0,
  intensity_before INTEGER NOT NULL,
  intensity_after  INTEGER NOT NULL,
  verdict        TEXT NOT NULL DEFAULT '',
  UNIQUE (experiment, week)
);

-- Current intensity, and why. Raising this raises production quotas; it never
-- lowers the quality bar, because the way to be below target is to build more
-- of what genuinely helps, not more of what does not.
CREATE TABLE IF NOT EXISTS intensity_state (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  level         INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
  since         TEXT NOT NULL,
  reason        TEXT NOT NULL DEFAULT '',
  updated_at    TEXT NOT NULL
);

-- A family is a whole dimension of pages -- one country, one trade, one document
-- type -- and is admitted or refused as a unit. Admitting a family is the only
-- decision that can create pages, so the quality test lives here rather than on
-- the individual page, where it would be too late and too easy to wave through.
CREATE TABLE IF NOT EXISTS page_families (
  family_key      TEXT PRIMARY KEY,
  dimension       TEXT NOT NULL CHECK (dimension IN ('locale', 'trade', 'document', 'utility')),
  name            TEXT NOT NULL,
  demand_evidence TEXT NOT NULL DEFAULT '',
  differentiation TEXT NOT NULL DEFAULT '',
  product_change  TEXT NOT NULL DEFAULT '',
  gate_json       TEXT NOT NULL DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
                    'proposed', 'admitted', 'refused', 'built')),
  refusal_reason  TEXT,
  page_count      INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

-- Individual pages inside an admitted family, with the evidence that each one
-- is a different tool rather than the same tool under a different heading.
CREATE TABLE IF NOT EXISTS page_candidates (
  slug             TEXT PRIMARY KEY,
  family_key       TEXT NOT NULL REFERENCES page_families(family_key),
  title            TEXT NOT NULL,
  route            TEXT NOT NULL,
  demand_score     REAL NOT NULL DEFAULT 0,
  differentiators  TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                     'queued', 'building', 'shipped', 'rejected')),
  rejection_reason TEXT,
  shipped_at       TEXT,
  commit_sha       TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_page_candidates_family
  ON page_candidates(family_key, status);


-- Tax and invoicing facts asserted on a country page, each tied to the primary
-- government source it came from and the date it was checked.
--
-- Pages that state what a tax authority requires are a different risk class from
-- ordinary marketing copy: they go stale silently, and a reader acts on them. So
-- every such fact is recorded with its source and a reverification date, and a
-- fact past that date is a REVIEW item rather than something the unattended
-- worker may quietly restate.
--
-- The four pages shipped before this table existed carried three errors that
-- only a primary source would catch: India's 12% and 28% slabs were abolished in
-- September 2025, Canada's input-tax-credit thresholds moved from $30/$150 to
-- $100/$500 in April 2021, and HMRC does not in fact require the words "VAT
-- invoice" as a document title.
CREATE TABLE IF NOT EXISTS tax_facts (
  jurisdiction   TEXT NOT NULL,
  fact_key       TEXT NOT NULL,
  value          TEXT NOT NULL,
  source_name    TEXT NOT NULL,
  source_url     TEXT NOT NULL,
  verified_on    TEXT NOT NULL,
  reverify_by    TEXT NOT NULL,
  confidence     TEXT NOT NULL DEFAULT 'primary_source' CHECK (confidence IN (
                   'primary_source', 'primary_source_indirect', 'unverified')),
  caveat         TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (jurisdiction, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_tax_facts_reverify ON tax_facts(reverify_by);

-- Non-search distribution. One row per destination we have actually looked at,
-- carrying what was verified about it and on what date, because a directory's
-- terms and its account requirements change and a stale note is what leads to
-- submitting somewhere that has quietly become a link farm.
CREATE TABLE IF NOT EXISTS breakout_destinations (
  key                        TEXT PRIMARY KEY,
  channel                    TEXT NOT NULL,
  name                       TEXT NOT NULL,
  url                        TEXT NOT NULL,
  submit_url                 TEXT,
  audience_fit               TEXT NOT NULL,
  evidence                   TEXT NOT NULL DEFAULT '',
  verified_on                TEXT NOT NULL,
  source_url                 TEXT NOT NULL DEFAULT '',
  -- What the destination demands of us. Each of these can force REVIEW on its
  -- own; none of them may be worked around.
  requires_account           INTEGER NOT NULL DEFAULT 1 CHECK (requires_account IN (0,1)),
  requires_payment           INTEGER NOT NULL DEFAULT 0 CHECK (requires_payment IN (0,1)),
  requires_personal_identity INTEGER NOT NULL DEFAULT 0 CHECK (requires_personal_identity IN (0,1)),
  requires_community_posting INTEGER NOT NULL DEFAULT 0 CHECK (requires_community_posting IN (0,1)),
  -- Scoring inputs, each recorded rather than inferred.
  reach                      INTEGER NOT NULL DEFAULT 0,
  intent                     REAL NOT NULL DEFAULT 0,
  speed_days                 INTEGER NOT NULL DEFAULT 90,
  confidence                 REAL NOT NULL DEFAULT 0,
  effort                     REAL NOT NULL DEFAULT 1,
  score                      REAL NOT NULL DEFAULT 0,
  gate_status                TEXT NOT NULL DEFAULT 'admitted'
                               CHECK (gate_status IN ('admitted', 'refused')),
  refusal_reason             TEXT,
  execution_class            TEXT NOT NULL DEFAULT 'REVIEW'
                               CHECK (execution_class IN ('AUTO', 'REVIEW', 'BLOCKED')),
  execution_reason           TEXT NOT NULL DEFAULT '',
  status                     TEXT NOT NULL DEFAULT 'identified'
                               CHECK (status IN ('identified', 'prepared', 'submitted',
                                                 'live', 'declined', 'failed')),
  bundle_json                TEXT NOT NULL DEFAULT '{}',
  notes                      TEXT NOT NULL DEFAULT '',
  created_at                 TEXT NOT NULL,
  updated_at                 TEXT NOT NULL
);

-- What a destination actually produced. Submission count is not an outcome, so
-- it is not stored here; sessions, tool starts and downloads are.
CREATE TABLE IF NOT EXISTS breakout_results (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  destination_key   TEXT NOT NULL REFERENCES breakout_destinations(key),
  observed_on       TEXT NOT NULL,
  referral_sessions INTEGER NOT NULL DEFAULT 0,
  tool_starts       INTEGER NOT NULL DEFAULT 0,
  pdf_downloads     INTEGER NOT NULL DEFAULT 0,
  backlinks         INTEGER NOT NULL DEFAULT 0,
  cost_usd          REAL NOT NULL DEFAULT 0,
  owner_minutes     INTEGER NOT NULL DEFAULT 0,
  note              TEXT NOT NULL DEFAULT '',
  UNIQUE(destination_key, observed_on)
);

CREATE INDEX IF NOT EXISTS idx_breakout_rank
  ON breakout_destinations(gate_status, execution_class, score DESC);

-- Creator and newsletter distribution prospects. Deliberately a separate table
-- from `prospects`: the resource-page cohort is a calibration experiment with
-- its own volume limit and its own reporting, and merging the two would let one
-- borrow the other's evidence.
CREATE TABLE IF NOT EXISTS creator_prospects (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  domain              TEXT NOT NULL,
  page_url            TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL DEFAULT '',
  segment             TEXT NOT NULL,
  discovered_at       TEXT NOT NULL,
  fetched_at          TEXT,
  http_status         INTEGER,
  -- Verified signals. Each is a fact read off the page, not an inference.
  last_activity_date  TEXT,
  audience_estimate   INTEGER,
  audience_evidence   TEXT NOT NULL DEFAULT '',
  recommends_tools    INTEGER NOT NULL DEFAULT 0 CHECK (recommends_tools IN (0,1)),
  -- Whether their coverage reads editorial, sponsored or affiliate. Sponsored
  -- and affiliate are not disqualifying in themselves, but an unpaid editorial
  -- suggestion to a site that only runs paid placements wastes both sides' time.
  coverage_kind       TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (coverage_kind IN ('editorial', 'sponsored', 'affiliate',
                                                 'mixed', 'unknown')),
  contact_url         TEXT,
  contact_kind        TEXT NOT NULL DEFAULT 'unknown',
  recipient           TEXT,
  contact_verified_at TEXT,
  -- Which live capability their audience would actually care about.
  product_angle       TEXT NOT NULL DEFAULT '',
  target_url          TEXT NOT NULL DEFAULT '',
  fit_score           REAL NOT NULL DEFAULT 0,
  status              TEXT NOT NULL DEFAULT 'discovered'
                        CHECK (status IN ('discovered', 'fetched', 'qualified',
                                          'rejected', 'staged', 'contacted',
                                          'replied', 'placed', 'suppressed')),
  rejection_reason    TEXT,
  notes               TEXT NOT NULL DEFAULT '',
  updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creator_status ON creator_prospects(status, fit_score DESC);
CREATE INDEX IF NOT EXISTS idx_creator_domain ON creator_prospects(domain);

-- The sign-once authorization for unpaid creator/newsletter suggestions. Kept
-- apart from `outreach_policy` so that signing one never widens the other.
CREATE TABLE IF NOT EXISTS creator_policy (
  version            INTEGER PRIMARY KEY,
  policy_json        TEXT NOT NULL,
  policy_hash        TEXT NOT NULL,
  signed             INTEGER NOT NULL DEFAULT 0 CHECK (signed IN (0, 1)),
  signer_fingerprint TEXT,
  signed_at          TEXT,
  active             INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
  created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS creator_admissions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  prospect_id    INTEGER NOT NULL REFERENCES creator_prospects(id),
  policy_version INTEGER NOT NULL,
  policy_hash    TEXT NOT NULL,
  admitted       INTEGER NOT NULL CHECK (admitted IN (0, 1)),
  checks_json    TEXT NOT NULL DEFAULT '{}',
  refusal_reason TEXT,
  recorded_at    TEXT NOT NULL
);

-- Launch instrumentation. One row per tracked distribution event, so a launch
-- is measured on what it sent rather than on how it felt.
CREATE TABLE IF NOT EXISTS launch_events (
  key            TEXT PRIMARY KEY,
  destination    TEXT NOT NULL,
  utm_source     TEXT NOT NULL,
  planned_for    TEXT,
  launched_at    TEXT,
  status         TEXT NOT NULL DEFAULT 'planned'
                   CHECK (status IN ('planned', 'blocked', 'live', 'complete', 'cancelled')),
  eligibility    TEXT NOT NULL DEFAULT '',
  blocking_note  TEXT NOT NULL DEFAULT '',
  metrics_json   TEXT NOT NULL DEFAULT '{}',
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

-- Distribution state per shipped product surface. One row per thing a user can
-- actually open, so a product with no external audience is visible as debt
-- rather than being invisible because nobody asked.
CREATE TABLE IF NOT EXISTS product_distribution (
  route                TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,
  family               TEXT NOT NULL DEFAULT '',
  search_cluster       TEXT NOT NULL DEFAULT '',
  resource_audience    TEXT NOT NULL DEFAULT '',
  creator_audience     TEXT NOT NULL DEFAULT '',
  directory_target     TEXT NOT NULL DEFAULT '',
  linkable_angle       TEXT NOT NULL DEFAULT '',
  distribution_state   TEXT NOT NULL DEFAULT 'debt'
                         CHECK (distribution_state IN ('debt', 'targeted', 'contacted',
                                                       'placed', 'earning')),
  referral_sessions    INTEGER NOT NULL DEFAULT 0,
  backlinks            INTEGER NOT NULL DEFAULT 0,
  organic_clicks       INTEGER NOT NULL DEFAULT 0,
  qualified_targets    INTEGER NOT NULL DEFAULT 0,
  priority_rank        INTEGER,
  priority_reason      TEXT NOT NULL DEFAULT '',
  updated_at           TEXT NOT NULL
);
