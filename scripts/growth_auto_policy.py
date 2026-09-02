#!/usr/bin/env python3
"""What an unattended reasoning agent is allowed to change, and when it is worth
waking one at all.

Two separate questions live here, and both are deterministic:

1. **Is there an opportunity worth an unattended Claude run today?** The default
   answer is no. Waking the agent because a score wobbled, because fifty more
   weak backlink prospects appeared, or because a page is short is churn, and
   churn on a seven-day-old domain costs more than it earns.
2. **If a run happens, what may its diff touch?** The agent gets no shell and no
   deployment credentials; this module is what decides whether the change it
   produced is inside the envelope before anything is committed.

Neither question is answered by the model. A policy the agent could talk its way
past would not be a policy.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Diff envelope
# --------------------------------------------------------------------------

# Files an AUTO change may touch. Everything else is REVIEW by definition: this
# is an allowlist, so a path nobody thought about is refused rather than
# permitted.
ALLOWED_PATHS = (
    "src/content/generators.ts",      # page copy, worked examples, comparisons
    "src/components/GeneratorPage.astro",
    "src/layouts/BaseLayout.astro",
    "src/styles/global.css",
    "src/components/workspace/workspace-a11y.css",
    "tests/e2e/",                     # a guard test for the change just made
)

# Named explicitly as well as excluded by the allowlist, because these are the
# paths where a mistake is expensive rather than merely wrong, and a reader of
# this file should be able to see the list without deriving it.
BLOCKED_PATHS = (
    "package.json", "package-lock.json", "astro.config.ts", "tsconfig.json",
    "wrangler.toml", "wrangler.jsonc", "vitest.config.ts", "playwright.config.ts",
    "lighthouserc.json", ".github/", ".env", "public/robots.txt",
    "src/pages/",                     # routes and canonical architecture
    "src/lib/",                       # money, PDF, storage, numbering, analytics
    "src/components/workspace/DocumentWorkspace.tsx",
    "scripts/", "data/", "requirements-growth.txt", "docs/",
)

# Structural facts about the site that an AUTO change may never alter. Each is
# checked against the diff text itself, so a change that edits a canonical path
# is refused even though it lives in an allowed file.
FROZEN_PATTERNS = (
    (re.compile(r"^[+-].*\bpath:\s*'"), "changes a page route"),
    (re.compile(r"^[+-].*rel=[\"']canonical"), "changes canonical markup"),
    (re.compile(r"^[+-].*\bimport\s+.*from\s+['\"][^./]"), "adds a package import"),
    (re.compile(r"^[+-].*\b(process\.env|import\.meta\.env)\b"), "reads configuration or secrets"),
    (re.compile(r"^[+-].*\b(fetch|XMLHttpRequest|WebSocket)\s*\("), "adds a network call"),
    (re.compile(r"^[+-].*\b(localStorage|indexedDB|IDBDatabase)\b"), "touches persistence"),
    (re.compile(r"^[+-].*<script"), "adds script markup"),
    (re.compile(r"^[+-].*\b(api[_-]?key|secret|token|password|credential)\s*[:=]", re.I),
     "looks like a credential"),
)

# Any absolute URL the change introduces must be one of these. An outbound link
# to somewhere new is an editorial decision, not a growth automation.
ALLOWED_URL_HOSTS = ("invoiceworkshop.com", "fonts.googleapis.com", "fonts.gstatic.com")
URL_PATTERN = re.compile(r"https?://([A-Za-z0-9.-]+)")

# Claims about the product that the site may make. New wording that asserts
# something outside this set is a claim nobody reviewed.
CLAIM_RED_FLAGS = (
    re.compile(r"\b(guarantee|guaranteed|certified|compliant with|legally)\b", re.I),
    re.compile(r"\b(bank[- ]level|military[- ]grade|100% (secure|accurate))\b", re.I),
    re.compile(r"\b(gdpr|hipaa|soc ?2|pci)\b", re.I),
    re.compile(r"(\bnumber one\b|#1\b|\bbest[- ]in[- ]class\b|\baward[- ]winning\b)", re.I),
)

MAX_CHANGED_FILES = 3
MAX_DIFF_LINES = 400


class PolicyRefusal(Exception):
    """The change is outside the AUTO envelope. Never caught and downgraded."""


def _is_allowed(path: str) -> bool:
    if any(path == blocked or path.startswith(blocked) for blocked in BLOCKED_PATHS):
        return False
    return any(path == allowed or path.startswith(allowed) for allowed in ALLOWED_PATHS)


def changed_files(cwd: Path | None = None) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=cwd or ROOT,
        check=True, capture_output=True, text=True,
    )
    files = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip().split(" -> ")[-1])
    return sorted(files)


def working_diff(paths: list[str], cwd: Path | None = None) -> str:
    """The diff for exactly these paths.

    Scoped deliberately. An earlier version diffed the whole working tree, so
    unrelated untracked files in the checkout counted toward the change budget
    and a small edit was refused for being two thousand lines long. The set of
    files being judged and the set being measured have to be the same set.
    """
    root = cwd or ROOT
    if not paths:
        return ""
    tracked, untracked = [], ""
    for path in paths:
        known = subprocess.run(["git", "ls-files", "--error-unmatch", "--", path], cwd=root,
                               check=False, capture_output=True, text=True)
        if known.returncode == 0:
            tracked.append(path)
            continue
        full = root / path
        if full.is_file():
            body = full.read_text(encoding="utf-8", errors="ignore")
            untracked += f"\n+++ b/{path}\n" + "".join(
                f"+{line}\n" for line in body.splitlines()
            )
    diff = ""
    if tracked:
        diff = subprocess.run(["git", "diff", "--", *tracked], cwd=root, check=True,
                              capture_output=True, text=True).stdout
    return diff + untracked


def validate_change(files: list[str], diff: str) -> dict:
    """Refuse anything outside the envelope. Returns the checks that passed."""
    if not files:
        raise PolicyRefusal("no files changed")
    if len(files) > MAX_CHANGED_FILES:
        raise PolicyRefusal(
            f"{len(files)} files changed, limit is {MAX_CHANGED_FILES}: {', '.join(files)}"
        )
    for path in files:
        if not _is_allowed(path):
            raise PolicyRefusal(f"{path} is outside the AUTO file allowlist")

    body = [line for line in diff.splitlines() if line[:1] in "+-"
            and not line.startswith(("+++", "---"))]
    if len(body) > MAX_DIFF_LINES:
        raise PolicyRefusal(f"{len(body)} changed lines, limit is {MAX_DIFF_LINES}")

    for line in body:
        for pattern, why in FROZEN_PATTERNS:
            if pattern.search(line):
                raise PolicyRefusal(f"{why}: {line.strip()[:120]}")

    added = "\n".join(line for line in body if line.startswith("+"))
    for host in URL_PATTERN.findall(added):
        if not any(host == allowed or host.endswith("." + allowed)
                   for allowed in ALLOWED_URL_HOSTS):
            raise PolicyRefusal(f"introduces an external URL host: {host}")
    for pattern in CLAIM_RED_FLAGS:
        found = pattern.search(added)
        if found:
            raise PolicyRefusal(f"introduces an unreviewed product claim: {found.group(0)}")

    return {
        "files": files, "changed_lines": len(body),
        "within_file_allowlist": True, "no_frozen_pattern": True,
        "no_new_external_url": True, "no_unreviewed_claim": True,
    }


# --------------------------------------------------------------------------
# Eligibility: is it worth waking the agent at all?
# --------------------------------------------------------------------------

# Opportunity types where semantic reasoning or a source edit is what is
# actually missing. Outreach is never here: that system has its own approval
# gate and no reasoning agent may touch it.
CLAUDE_ELIGIBLE_TYPES = (
    "SEO_PAGE_IMPROVEMENT", "CTR_IMPROVEMENT", "CONTENT_REFRESH",
    "INTERNAL_LINKING", "TECHNICAL_SEO",
)

MAX_RUNS_PER_DAY = 1
MAX_ATTEMPTS_PER_OPPORTUNITY = 2
# A page that was just changed needs time to be recrawled before it is worth
# touching again, and the experiment measuring the last change is still open.
REATTEMPT_COOLDOWN_DAYS = 45
# Below this the opportunity is not worth a deploy, whatever its band.
MIN_EXPECTED_VALUE = 3.0


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def runs_today(connection: sqlite3.Connection) -> int:
    return int(connection.execute(
        "SELECT COUNT(*) FROM claude_runs WHERE substr(started_at,1,10)=? "
        "AND run_type<>'fixture'", (_today(),)
    ).fetchone()[0])


def _blocking_experiment(connection: sqlite3.Connection, url: str | None) -> str | None:
    if not url:
        return None
    row = connection.execute(
        """SELECT id, evaluate_after FROM growth_experiments
            WHERE target_url=? AND outcome IS NULL AND evaluate_after > ?
            ORDER BY evaluate_after DESC LIMIT 1""",
        (url, _today()),
    ).fetchone()
    return f"experiment {row['id']} runs until {row['evaluate_after']}" if row else None


def disqualify(connection: sqlite3.Connection, row: dict) -> str | None:
    """Why this opportunity must not wake Claude, or None if it may."""
    if row.get("state") != "open":
        return f"state is {row.get('state')}"
    if row.get("execution_tier") != "AUTO":
        return f"tier is {row.get('execution_tier')}"
    if row.get("opportunity_type") not in CLAUDE_ELIGIBLE_TYPES:
        return f"{row.get('opportunity_type')} is handled deterministically or is REVIEW"
    if int(row.get("priority_band") or 3) != 1:
        return f"priority band {row.get('priority_band')}, only band 1 justifies a run"
    if float(row.get("expected_growth_value") or 0) < MIN_EXPECTED_VALUE:
        return (f"expected value {row.get('expected_growth_value')} below the "
                f"{MIN_EXPECTED_VALUE} floor for a production change")
    if int(row.get("attempt_count") or 0) >= MAX_ATTEMPTS_PER_OPPORTUNITY:
        return f"already attempted {row.get('attempt_count')} times"
    last = row.get("last_attempted_at")
    if last:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
        if age < timedelta(days=REATTEMPT_COOLDOWN_DAYS):
            return (f"attempted {age.days} days ago; the cooldown is "
                    f"{REATTEMPT_COOLDOWN_DAYS} days so the last change can be measured")
    blocking = _blocking_experiment(connection, row.get("target_url"))
    if blocking:
        return f"blocked by an open experiment on the same page: {blocking}"
    return None


def select_candidate(connection: sqlite3.Connection) -> dict:
    """The one opportunity worth an unattended run today, or a reason there is none."""
    if runs_today(connection) >= MAX_RUNS_PER_DAY:
        return {"eligible": False, "reason": "daily Claude run budget already used",
                "code": "budget_exhausted"}
    rows = [dict(row) for row in connection.execute(
        """SELECT * FROM growth_opportunities WHERE state='open'
            ORDER BY priority_band ASC, expected_growth_value DESC LIMIT 40"""
    )]
    considered = []
    for row in rows:
        reason = disqualify(connection, row)
        if reason is None:
            return {
                "eligible": True, "opportunity": row,
                "considered": considered[:8],
                "reason": (f"band {row['priority_band']} {row['opportunity_type']} "
                           f"needing a source change: {row['title']}"),
            }
        considered.append({"opportunity_key": row["opportunity_key"], "skipped": reason})
    return {"eligible": False, "reason": "no opportunity clears the threshold today",
            "code": "no_action", "considered": considered[:8]}


def policy_document() -> str:
    """The envelope, written for the agent that has to work inside it."""
    return json.dumps({
        "allowed_files": list(ALLOWED_PATHS),
        "blocked_files": list(BLOCKED_PATHS),
        "max_changed_files": MAX_CHANGED_FILES,
        "max_changed_lines": MAX_DIFF_LINES,
        "never_change": [why for _, why in FROZEN_PATTERNS],
        "allowed_url_hosts": list(ALLOWED_URL_HOSTS),
        "allowed_change_categories": [
            "factual explanatory copy a reader can act on",
            "a worked example with arithmetic that can be checked",
            "a comparison or reference section between documents users confuse",
            "internal links to existing canonical pages",
            "title or meta description backed by query evidence",
            "small accessibility fixes",
            "small layout or UX fixes",
            "factual refresh of existing content",
        ],
        "blocked_change_categories": [
            "new pages, routes, canonicals, sitemap or robots architecture",
            "dependencies, build configuration, secrets, credentials",
            "persistence, PDF or money calculations, analytics configuration",
            "payment, ads, authentication, external integrations",
            "outbound email or any outreach behaviour",
            "arbitrary application logic",
            "legal or compliance claims",
            "padding written to make a page longer",
        ],
    }, indent=2, sort_keys=True)


if __name__ == "__main__":
    print(policy_document())
