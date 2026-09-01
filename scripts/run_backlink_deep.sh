#!/usr/bin/env bash
# Two-to-three times weekly: competitor-gap refresh, broken-link discovery and
# a wider channel sweep including the search-independent seed crawl. Read-only.
set -euo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"

"$PYTHON" scripts/growth_backlink_engine.py competitor-gap
"$PYTHON" scripts/growth_backlink_engine.py cycle --mode deep --queries-per-channel 3
"$PYTHON" scripts/growth_backlink_engine.py crawl --mode deep --expand --limit 30
"$PYTHON" scripts/growth_backlink_engine.py qualify
