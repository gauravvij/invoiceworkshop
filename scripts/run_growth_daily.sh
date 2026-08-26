#!/usr/bin/env bash
# Deterministic Level-0 collection. External operations are read-only GETs or
# read-report POSTs to Google APIs; local state is limited to data/growth.db.
set -euo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"

cd "$REPO"
export GOOGLE_APPLICATION_CREDENTIALS="$REPO/.env.google-service-account.json"
export GA4_PROPERTY_ID="551485207"
export GSC_SITE="sc-domain:invoiceworkshop.com"

"$PYTHON" scripts/growth_db.py init

measure_status=0
if "$PYTHON" scripts/growth_job_log.py guard --operation google_reads; then
  "$PYTHON" scripts/growth_measure.py || measure_status=$?
else
  guard_status=$?
  if [[ "$guard_status" -ne 75 ]]; then
    exit "$guard_status"
  fi
  "$PYTHON" scripts/growth_measure.py --public-only || measure_status=$?
fi
"$PYTHON" scripts/growth_verify.py
"$PYTHON" scripts/growth_report.py --period 14

exit "$measure_status"
