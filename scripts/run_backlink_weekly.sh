#!/usr/bin/env bash
# Weekly evaluation. Reports links acquired, replies, referrals, search movement
# and which channels earn or lose effort. Reallocation is applied by the engine
# during discovery; this step reports it. Read-only.
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

"$PYTHON" scripts/growth_backlink_engine.py evaluate --period 7
"$PYTHON" scripts/growth_backlink_engine.py report --limit 25
