#!/usr/bin/env python3
"""Emit compact pre-agent context for the scheduled Level-0 research job."""

from __future__ import annotations

import json
from pathlib import Path

from growth_research import start_research

HERMES_JOBS = Path("/home/azureuser/.hermes/cron/jobs.json")
RESEARCH_JOB_NAME = "invoiceworkshop-level0-research"


def resolve_job_id() -> str:
    registry = json.loads(HERMES_JOBS.read_text(encoding="utf-8"))
    matches = [
        str(job["id"])
        for job in registry.get("jobs", [])
        if job.get("name") == RESEARCH_JOB_NAME
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one {RESEARCH_JOB_NAME} job, found {len(matches)}"
        )
    return matches[0]


def main() -> None:
    context = start_research(
        None,
        resolve_job_id(),
        token_budget=40_000,
        tool_budget=10,
    )
    print(json.dumps(context, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
