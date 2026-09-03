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

# Statements about what a tax authority requires. These are not editorial copy:
# a reader acts on them, they go stale silently on a political timetable, and
# getting one wrong is a different kind of harm from getting a heading wrong.
# The audit on 2 September 2026 found three of them already published and wrong.
#
# So an unattended run may not write one on its own judgement. It may only
# restate a figure that has already been read off the primary government source
# and recorded in tax_facts; anything else -- a new requirement, a rate nobody
# recorded, a claim with no number in it to check -- is refused here and goes to
# the owner as REVIEW. Ordinary editorial work on the same pages is unaffected,
# because none of these patterns fire on it.
TAX_AUTHORITIES = re.compile(
    r"\b(HMRC|GOV\.UK|ATO|CRA|CBIC|GST Council|IRAS|SARS|FTA|IRD|"
    r"Revenue Commissioners|Finanzamt|Inland Revenue)\b")
TAX_CLAIM_PATTERNS = (
    (TAX_AUTHORITIES, "states what a tax authority requires"),
    (re.compile(r"\b(VAT|GST|HST|QST|USt|sales tax|tax invoice)\b[^.]{0,60}"
                r"\b(must|required|requires|mandatory|threshold|obliged)\b", re.I),
     "states a tax requirement"),
    (re.compile(r"\b(must|required|requires|mandatory|threshold|obliged)\b[^.]{0,60}"
                r"\b(VAT|GST|HST|QST|USt|sales tax|tax invoice)\b", re.I),
     "states a tax requirement"),
    (re.compile(r"\b\d{1,2}(?:\.\d+)?\s?%[^.]{0,40}\b(VAT|GST|HST|QST|USt)\b", re.I),
     "states a tax rate"),
    (re.compile(r"\b(VAT|GST|HST|QST|USt)\b[^.]{0,40}\b\d{1,2}(?:\.\d+)?\s?%", re.I),
     "states a tax rate"),
    (re.compile(r"\b(legally required|required by law|valid tax invoice|statutory)\b", re.I),
     "states a legal requirement"),
)
# Figures inside such a line: percentages and currency amounts. Every one of them
# must match a recorded fact verbatim for the line to pass unattended.
TAX_FIGURE = re.compile(r"(?:[£$€₹]\s?\d[\d,]*(?:\.\d+)?|\b\d{1,3}(?:\.\d+)?\s?%)")

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


def verified_tax_figures(connection) -> frozenset[str]:
    """Figures from tax facts that are recorded, sourced and not yet due a recheck.

    Read from the database, not from the change, so the run cannot vouch for
    itself. Normalised loosely (spaces and thousands separators dropped) because
    the same rate is written "20%" in one place and "20 %" in another.
    """
    today = _today()
    values = set()
    for row in connection.execute(
            """SELECT value FROM tax_facts
                WHERE reverify_by > ? AND COALESCE(source_url,'') <> ''""", (today,)):
        for figure in TAX_FIGURE.findall(row["value"] or ""):
            values.add(_normalise_figure(figure))
    return frozenset(values)


def _normalise_figure(figure: str) -> str:
    return figure.replace(" ", "").replace(",", "").lower()


def _check_tax_claims(added_lines: list[str], verified: frozenset[str]) -> int:
    """Refuse a tax or legal assertion the recorded sources do not already carry."""
    checked = 0
    for line in added_lines:
        text = line[1:]
        why = next((reason for pattern, reason in TAX_CLAIM_PATTERNS if pattern.search(text)),
                   None)
        if why is None:
            continue
        checked += 1
        figures = [_normalise_figure(f) for f in TAX_FIGURE.findall(text)]
        if not figures:
            raise PolicyRefusal(
                f"REVIEW: {why} with nothing in it that can be checked against a recorded "
                f"source, so it cannot be verified unattended: {text.strip()[:120]}")
        unknown = [f for f in figures if f not in verified]
        if unknown:
            raise PolicyRefusal(
                f"REVIEW: {why} using {', '.join(unknown)}, which is not a figure recorded "
                f"in tax_facts against a primary government source. Read it off the "
                f"authority and record it with growth_tax_facts.py first: "
                f"{text.strip()[:120]}")
    return checked


def validate_change(files: list[str], diff: str,
                    verified_tax: frozenset[str] = frozenset()) -> dict:
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

    tax_claims = _check_tax_claims([line for line in body if line.startswith("+")],
                                   verified_tax)

    return {
        "files": files, "changed_lines": len(body),
        "within_file_allowlist": True, "no_frozen_pattern": True,
        "no_new_external_url": True, "no_unreviewed_claim": True,
        "tax_claims_checked": tax_claims, "tax_claims_source_backed": True,
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

# Baseline only. The live figure comes from the experiment's intensity, so
# falling behind the trajectory actually buys more production rather than
# producing a note about needing more production.
MAX_RUNS_PER_DAY = 1
MAX_ATTEMPTS_PER_OPPORTUNITY = 2
# A page that was just changed needs time to be recrawled before it is worth
# touching again, and the experiment measuring the last change is still open.
REATTEMPT_COOLDOWN_DAYS = 45
# Below this the opportunity is not worth a deploy, whatever its band.
MIN_EXPECTED_VALUE = 3.0


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def daily_run_budget(connection: sqlite3.Connection) -> int:
    """Reasoning runs allowed today, set by the experiment's current intensity."""
    try:
        import growth_trajectory
        return int(growth_trajectory.intensity(connection)["claude_runs_per_day"])
    except Exception:
        return MAX_RUNS_PER_DAY


def pages_this_week(connection: sqlite3.Connection) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        return int(connection.execute(
            "SELECT COUNT(*) FROM page_candidates WHERE status='shipped' AND shipped_at >= ?",
            (since,)).fetchone()[0])
    except sqlite3.Error:
        return 0


def weekly_page_quota(connection: sqlite3.Connection) -> int:
    try:
        import growth_trajectory
        return int(growth_trajectory.intensity(connection)["pages_per_week"])
    except Exception:
        return 2


def next_surface_page(connection: sqlite3.Connection) -> dict | None:
    """A queued page from an admitted family, if this week's quota allows one.

    New surface area outranks improving an existing page while the experiment is
    behind: nine pages cannot reach the target however good they are.
    """
    if pages_this_week(connection) >= weekly_page_quota(connection):
        return None
    try:
        # Only families whose product capability already exists. A family that
        # needs a new document kind is real work, but it lives outside the AUTO
        # envelope, so offering it here would spend a run on a certain refusal.
        row = connection.execute(
            """SELECT c.slug, c.title, c.route, c.differentiators, f.dimension,
                      f.product_change, f.demand_evidence
                 FROM page_candidates c JOIN page_families f ON f.family_key=c.family_key
                WHERE c.status='queued' AND f.status IN ('admitted','built')
                  AND json_extract(f.gate_json, '$.build_scope') = 'content_only'
                ORDER BY c.demand_score DESC, c.slug LIMIT 1""").fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


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
    budget = daily_run_budget(connection)
    used = runs_today(connection)
    if used >= budget:
        return {"eligible": False,
                "reason": f"today's run budget is used ({used}/{budget} at the current intensity)",
                "code": "budget_exhausted"}

    # Surface area first while the experiment is behind: improving one of nine
    # pages cannot reach a target that needs hundreds of them.
    page = next_surface_page(connection)
    if page:
        return {
            "eligible": True, "surface_page": page,
            "opportunity": {
                "opportunity_key": f"surface:{page['slug']}",
                "opportunity_type": "NEW_SEARCH_LANDING_ASSET",
                "title": f"Build {page['route']} ({page['title']})",
                "target_url": "https://invoiceworkshop.com" + page["route"],
                "evidence": page["demand_evidence"],
                "priority_band": 1, "expected_growth_value": 50.0,
                "attempt_count": 0, "state": "open", "execution_tier": "AUTO",
            },
            "reason": (f"surface expansion: {page['route']} from an admitted family "
                       f"({pages_this_week(connection)}/{weekly_page_quota(connection)} "
                       "pages shipped this week)"),
        }
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
            "any new statement about what a tax authority requires, or any tax rate "
            "or threshold figure not already recorded in tax_facts against a primary "
            "government source",
        ],
        "tax_and_legal_rule": (
            "Country pages state what HMRC, the ATO, the CRA and the GST Council "
            "require. You may reword such a sentence, but you may not change what it "
            "asserts and you may not introduce a rate, threshold or requirement of "
            "your own. Every figure in a sentence like that is checked verbatim "
            "against the recorded facts, and a sentence that asserts a requirement "
            "with no figure in it cannot be checked at all, so it is refused and sent "
            "to the owner for review. If a page looks factually wrong, say so in the "
            "summary and take NO_ACTION rather than correcting it from memory."
        ),
    }, indent=2, sort_keys=True)


if __name__ == "__main__":
    print(policy_document())
