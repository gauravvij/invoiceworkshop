#!/usr/bin/env bash
# Weekly evaluation. Reports links acquired, replies, referrals, search movement
# and which channels earn or lose effort. Reallocation is applied by the engine
# during discovery; this step reports it. Read-only.
set -euo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"

"$PYTHON" scripts/growth_backlink_engine.py evaluate --period 7
"$PYTHON" scripts/growth_backlink_engine.py report --limit 25
