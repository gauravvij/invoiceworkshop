#!/usr/bin/env bash
# Weekly evaluation and reallocation. Reports links acquired, replies, referrals
# and search movement, then MOVES effort between channels on what they actually
# produced. The new weights feed straight into the opportunity ranking, so a
# channel that repeatedly fails loses ground rather than being described as
# failing in a report. Local writes only: nothing is sent, approved or published.
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

# The decision, not a description of one. `weekly` concludes every experiment
# whose evaluation window has closed, judges the outreach cohort, and then moves
# the channel weights that ranking uses. A channel that keeps failing loses
# ground here; nothing is approved, signed or sent.
"$PYTHON" scripts/growth_allocation.py weekly

# Re-rank immediately under the new weights so Monday's priorities reflect the
# reallocation rather than waiting a day for the next daily run.
"$PYTHON" scripts/growth_opportunities.py refresh
"$PYTHON" scripts/growth_opportunities.py top --limit 10

# The trajectory checkpoint. Measures the week against the plan written at the
# start, and moves intensity: behind target raises the production quota, which
# the executor reads the next time it runs. It never lowers the quality gate --
# being behind is a reason to build more of what helps, never a reason to
# publish something that does not.
"$PYTHON" scripts/growth_trajectory.py checkpoint

# The Monday scoreboard: surface, Google, authority, usage, velocity and the
# distance left to the target, computed from measurements already collected. It
# reads the plan and never rewrites it, so a week that missed stays missed.
"$PYTHON" scripts/growth_scoreboard.py publish
