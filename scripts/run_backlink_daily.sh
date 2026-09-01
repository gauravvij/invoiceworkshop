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

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"

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
else
  echo '{"level1_execution":"skipped: LEVEL1_OUTBOUND_ENABLED is false"}'
fi

# --- 4. discovery -----------------------------------------------------------
"$PYTHON" scripts/growth_backlink_engine.py cycle --mode daily --queries-per-channel 2
