#!/usr/bin/env bash
# Daily Level-0 backlink operations. Every step is a read-only GET plus local
# writes to data/growth.db. Level-1 execution is attempted only when the owner
# has opened both the environment and database gates; while they are closed the
# execution step is a documented no-op.
set -euo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"

"$PYTHON" scripts/growth_backlink_engine.py cycle --mode daily --queries-per-channel 2
"$PYTHON" scripts/growth_backlink_engine.py verify-placements --limit 40

# Inbound reply processing is read-only and matches only previously sent actions.
"$PYTHON" scripts/growth_level1a_mailbox.py poll || true

# Level-1 execution. The environment kill switch lives in an owner-controlled
# file outside the repository, so outbound can be stopped without a commit or a
# database change. Absent file means disabled.
LEVEL1_ENV_FILE="/home/azureuser/.config/invoiceworkshop/level1.env"
if [[ -r "$LEVEL1_ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$LEVEL1_ENV_FILE"; set +a
fi

if [[ "${LEVEL1_OUTBOUND_ENABLED:-false}" == "true" ]]; then
  # Sends only the next eligible attempt for actions the owner already approved.
  # Accepts no recipient, subject or body and cannot reach an unapproved action.
  "$PYTHON" scripts/growth_level1a.py run-approved
else
  echo '{"level1_execution":"skipped: LEVEL1_OUTBOUND_ENABLED is false"}'
fi
