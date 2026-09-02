#!/usr/bin/env bash
# Health watchdog. Silent when healthy: the scheduler delivers stdout, so no
# output means nothing needs a person. Any output at all is something that does.
set -uo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"
export HOME="/home/azureuser"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

exec "$PYTHON" scripts/growth_health.py
