-- InvoiceWorkshop Level-0 growth operating store.
-- Local-only: never store credentials, document contents, or customer data here.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT INTO schema_meta (key, value) VALUES ('schema_version', '11')
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

