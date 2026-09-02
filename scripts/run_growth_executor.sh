#!/usr/bin/env bash
# Unattended AUTO execution. Runs after the day's deterministic pipeline has
# refreshed the evidence, decides whether any opportunity is worth waking a
# reasoning agent for, and wakes at most one.
#
# Most days this prints NO_ACTION and costs nothing. That is the intended
# result: the system is judged on growth, not on how often it edits the site.
#
# Deliberately NOT inside the shared growth lock. The worker can spend twenty
# minutes in a build and another twenty waiting for CI, and holding the database
# lock for that would starve the discovery jobs behind it. It takes its own
# single-holder lock instead and touches the database only in short bursts.
set -uo pipefail

REPO="/home/azureuser/invoiceworkshop"
PYTHON="/home/azureuser/growth-venv/bin/python"
cd "$REPO"
export PYTHONPATH="$REPO/scripts"
export HOME="/home/azureuser"
# A scheduled job inherits a minimal PATH. Everything the worker shells out to
# has to be on it: claude and node/npm/npx in ~/.local/bin, gh in /usr/local/bin,
# git and flock in /usr/bin.
export PATH="/home/azureuser/.local/bin:/usr/local/bin:/usr/bin:/bin"

# The worker holds its own lock internally; this is belt and braces against two
# schedulers firing the same job.
exec "$PYTHON" scripts/growth_claude_worker.py run "$@"
