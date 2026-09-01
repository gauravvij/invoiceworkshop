#!/usr/bin/env bash
# Two-to-three times weekly: competitor-gap refresh, broken-link discovery and
# a wider channel sweep including the search-independent seed crawl. Read-only.
set -euo pipefail

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

"$PYTHON" scripts/growth_backlink_engine.py competitor-gap
"$PYTHON" scripts/growth_backlink_engine.py cycle --mode deep --queries-per-channel 3
"$PYTHON" scripts/growth_backlink_engine.py crawl --mode deep --expand --limit 30
"$PYTHON" scripts/growth_backlink_engine.py qualify
