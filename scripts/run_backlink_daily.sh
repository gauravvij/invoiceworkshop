#!/usr/bin/env bash
# Daily Level-0 growth operations. Every step is a read-only GET plus local
# writes to data/growth.db.
#
# Order matters and is deliberate:
#
#   1. poll inbound replies and bounces   -> reply/suppression state
#   2. verify recorded placements         -> placement state
#   3. execute eligible approved outbound -> follow-ups see 1 and 2
#   4. discovery cycle                    -> slow, and nothing depends on it
#
# A reply or bounce that arrived before this run is therefore always processed
# before the same run decides whether to send a follow-up. Discovery runs last
# precisely because it is the long step; putting it first would delay reply
# processing and, under `set -e`, a discovery failure would skip it entirely.
set -euo pipefail

# Growth jobs share one SQLite file and discovery holds a long write
# transaction, so two of them running at once can fail on a lock rather than
# simply waiting. Serialise them: a later job queues behind an earlier one
# instead of crashing. -E 0 means a wait timeout exits cleanly, not as a failure.
LOCKFILE="/home/azureuser/.config/invoiceworkshop/growth.lock"
if [[ -z "${GROWTH_LOCK_HELD:-}" ]]; then
  export GROWTH_LOCK_HELD=1
  exec flock -w 2400 -E 0 "$LOCKFILE" "$0" "$@"
fi

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"

# The AnySearch key lives in .env (gitignored). Load only that one variable:
# sourcing the whole file would pull Cloudflare and S3 credentials into a
# read-only discovery job that has no use for them.
if [[ -r "$REPO/.env" ]]; then
  ANYSEARCH_API_KEY="$(sed -n 's/^[[:space:]]*ANYSEARCH_API_KEY[[:space:]]*=[[:space:]]*//p' "$REPO/.env" | tail -n1 | tr -d '"'"'"'\r')"
  export ANYSEARCH_API_KEY
fi

# --- 1. inbound state -------------------------------------------------------
# A failed poll means we cannot know whether a prospect replied or bounced, so
# it must block outbound rather than be shrugged off.
inbound_ok=1
"$PYTHON" scripts/growth_level1a_mailbox.py poll || inbound_ok=0

# --- 2. placement state -----------------------------------------------------
"$PYTHON" scripts/growth_backlink_engine.py verify-placements --limit 40 || true

# --- 3. approved outbound ---------------------------------------------------
# The environment kill switch lives in an owner-controlled file outside the
# repository, so outbound can be stopped without a commit or a database change.
# An absent file means disabled.
LEVEL1_ENV_FILE="/home/azureuser/.config/invoiceworkshop/level1.env"
if [[ -r "$LEVEL1_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$LEVEL1_ENV_FILE"; set +a
fi

if [[ "$inbound_ok" -ne 1 ]]; then
  echo '{"level1_execution":"skipped: inbound poll failed, reply state is unknown"}'
elif [[ "${LEVEL1_OUTBOUND_ENABLED:-false}" == "true" ]]; then
  # Sends only the next eligible attempt for actions the owner already approved.
  # Accepts no recipient, subject or body and cannot reach an unapproved action.
  "$PYTHON" scripts/growth_level1a.py run-approved
  # Reports whether a signed outreach policy is active. Until one is signed this
  # only ever prints state; it cannot admit anything on its own.
  "$PYTHON" scripts/growth_outreach_policy.py status
else
  echo '{"level1_execution":"skipped: LEVEL1_OUTBOUND_ENABLED is false"}'
fi

# --- 4. discovery -----------------------------------------------------------
"$PYTHON" scripts/growth_backlink_engine.py cycle --mode daily --queries-per-channel 2

# --- 5. growth intelligence -------------------------------------------------
# Re-measure page structure, classify why each URL is or is not indexed, and
# rebuild the opportunity ranking from current evidence, so tomorrow's
# priorities follow the data rather than yesterday's assumptions.
# Deterministic: no model is invoked to restate unchanged metrics.
#
# `diagnose` is what stops indexing churn. A URL that is correctly published and
# simply has not been crawled yet is recorded as waiting, not rewritten.
"$PYTHON" scripts/growth_opportunities.py diagnose
"$PYTHON" scripts/growth_opportunities.py refresh
"$PYTHON" scripts/growth_opportunities.py top --limit 8

# Where the outreach calibration cohort has got to. Recommends; approves
# nothing. Only the owner's signature can widen the channel.
"$PYTHON" scripts/growth_allocation.py outreach-calibration

# --- 6. the 90-day experiment ----------------------------------------------
# Re-run the admission gate so any new family evidence is judged, then report
# where the trajectory stands. Both are deterministic and cost nothing; the
# gate refuses families rather than admitting them, so running it often is safe.
"$PYTHON" scripts/growth_surface.py evaluate
"$PYTHON" scripts/growth_trajectory.py status

# Facts on the country pages that have gone past their recheck date. A page that
# tells someone what HMRC or the ATO requires goes stale silently on a political
# timetable, so it is checked on a clock rather than when someone notices.
# Reports and escalates; it cannot edit a page.
"$PYTHON" scripts/growth_tax_facts.py check

# --- 7. non-search distribution --------------------------------------------
# Re-run the destination gate and write the submission bundles. Both are local:
# the gate refuses rather than submits, and preparation writes copy into the
# database. Nothing is sent, no account is created and no form is posted --
# every destination that needs one of those is REVIEW by construction.
"$PYTHON" scripts/growth_breakout.py evaluate
"$PYTHON" scripts/growth_breakout.py prepare
