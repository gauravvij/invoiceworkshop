#!/usr/bin/env python3
"""The free invoice generator audit: how the sample was drawn and what was measured.

The published corpus on "best free invoice generator" is almost entirely written
by invoice generator vendors ranking themselves first. Nothing in it is
reproducible and none of it is checked. This module builds a sample nobody
chose by hand, hands it to a browser that records what each tool actually does
with the data typed into it, and keeps the evidence.

Commands:
  sample    draw the sampling frame from live search results
  dataset   turn the measurements into the published CSV and the headline counts
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from growth_common import public_domain_or_blank, utc_now  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "audit"
FRAME = DATA / "frame.json"
MEASUREMENTS = DATA / "measurements"

# Our own tool. It is measured on exactly the same terms as everything else and
# appears in the published table, but it is excluded from every headline figure.
# A study whose author is inside its own percentage is an advertisement.
OWN_DOMAIN = "invoiceworkshop.com"

# What people actually type. Fixed here so the frame can be redrawn and compared
# rather than argued about, and deliberately not seeded with any tool's name.
QUERIES = (
    "free invoice generator",
    "free invoice generator no signup",
    "create invoice online free pdf",
    "invoice maker free download pdf",
    "free invoice template generator online",
    "invoice generator no watermark free",
    "online invoice generator for freelancers",
    "free invoice generator small business",
    "free invoice generator uk vat",
    "free gst invoice generator india",
    "free invoice generator australia",
    "invoice generator free no sign up no email",
    "simple invoice generator online",
    "free receipt and invoice generator",
    "contractor invoice generator free",
    "hourly invoice generator free online",
    "free invoice builder pdf download",
    "make an invoice free online tool",
)

# Places a tool cannot be. Excluded before ranking so the frame is not padded
# with things that were never in scope.
NOT_A_TOOL_HOST = (
    "reddit.com", "youtube.com", "wikipedia.org", "play.google.com",
    "apps.apple.com", "microsoft.com", "facebook.com", "linkedin.com",
    "medium.com", "quora.com", "producthunt.com", "github.com",
    "trustpilot.com", "capterra.com", "g2.com", "alternativeto.net",
    "x.com", "twitter.com", "pinterest.com", "amazon.com",
)

# A path that announces itself as an article about tools rather than a tool.
NOT_A_TOOL_PATH = ("/blog/", "/blog", "/articles/", "/news/", "/guide/",
                   "/learn/", "/academy/", "/resources/", "/comparison")


def _is_candidate(url: str) -> tuple[bool, str]:
    domain = public_domain_or_blank(url)
    if not domain:
        return False, "no public hostname"
    if any(domain == host or domain.endswith("." + host) for host in NOT_A_TOOL_HOST):
        return False, f"not a tool host ({domain})"
    lowered = url.lower()
    if any(part in lowered for part in NOT_A_TOOL_PATH):
        return False, "article path, not a tool"
    # A search engine's own redirect wrapper is not a page anyone can visit
    # twice. One of these was drawn into the first frame and measured as a tool.
    if any(part in lowered for part in ("/goto?", "/url?", "/aclk?", "/redirect?")):
        return False, "search-engine redirect, not a tool page"
    return True, ""


def sample(limit: int = 50) -> dict:
    """Whatever currently ranks for what people type, deduplicated by domain.

    Drawing the sample from live results rather than a hand-written list is the
    point: it removes the one place where the author of a comparison normally
    puts a thumb on the scale, which is deciding who is in it.
    """
    from growth_search_providers import get_provider

    provider = get_provider()
    drawn: dict[str, dict] = {}
    log: list[dict] = []
    for query in QUERIES:
        try:
            results = provider.search(query, limit=20)
        except Exception as error:  # a provider failure is recorded, not hidden
            log.append({"query": query, "error": str(error)})
            continue
        for rank, row in enumerate(results, start=1):
            url = (row.get("page_url") or "").strip()
            if not url:
                continue
            ok, why = _is_candidate(url)
            domain = public_domain_or_blank(url)
            if not ok:
                log.append({"query": query, "rank": rank, "url": url, "excluded": why})
                continue
            if domain in drawn:
                drawn[domain]["also_ranked_for"].append(query)
                continue
            drawn[domain] = {
                "domain": domain,
                "url": url,
                "title": row.get("title", ""),
                "found_by_query": query,
                "found_at_rank": rank,
                "also_ranked_for": [],
                "is_publisher_own_tool": domain == OWN_DOMAIN,
            }
    frame = {
        "drawn_on": utc_now(),
        "provider": type(provider).__name__,
        "queries": list(QUERIES),
        "results_per_query": 20,
        "candidates": list(drawn.values())[:limit],
        "excluded": log,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    FRAME.write_text(json.dumps(frame, indent=2) + "\n")
    return {"drawn": len(frame["candidates"]), "excluded": len(log), "file": str(FRAME)}


# A string no tool could contain by accident, typed into every field so that
# "did anything I typed leave the page" has a yes/no answer instead of a guess.
CANARY = "AUDITCANARY7Q3X"

HARNESS = ROOT / "scripts" / "audit_measure.cjs"


def measure(only: str | None = None, redo: bool = False) -> dict:
    """Run every tool in the frame through the browser harness, one at a time.

    Serial on purpose. Two headless Chromiums competing for the same machine
    change the timings the measurement depends on, and a study that cannot be
    reproduced on a laptop is not worth publishing.
    """
    import subprocess

    frame = json.loads(FRAME.read_text())
    MEASUREMENTS.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    for candidate in frame["candidates"]:
        domain = candidate["domain"]
        if only and only != domain:
            continue
        out = MEASUREMENTS / domain
        if (out / "evidence.json").exists() and not redo:
            done.append({"domain": domain, "state": "already measured"})
            continue
        out.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["xvfb-run", "-a", "node", str(HARNESS), candidate["url"], str(out), CANARY],
                cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            line = (result.stdout or "").strip().splitlines()
            done.append({"domain": domain, "state": "measured",
                         "summary": line[-1][:300] if line else ""})
        except subprocess.TimeoutExpired:
            # Recorded as unmeasured. A tool that did not finish is not a tool
            # that passed, and it is not a tool that failed either.
            (out / "evidence.json").write_text(json.dumps({
                "url": candidate["url"], "measured_at": utc_now(), "reachable": None,
                "canary_left_the_browser": None,
                "notes": ["harness timed out after 300s"]}, indent=2) + "\n")
            failed.append({"domain": domain, "state": "timeout"})
        print(json.dumps(done[-1] if done else failed[-1]), flush=True)
    return {"measured": len(done), "failed": len(failed)}


# The claim a tool makes about where your data goes is usually not on the tool
# page -- it is in the privacy policy. Looking only at the page the editor is on
# reported "no claim" for tools that make the claim loudly one click away.
CLAIM_PATTERNS = (
    r"(never|does not|doesn'?t|will not|won'?t|no data (is|are)?)\s+(ever\s+)?"
    r"(leave|leaves|leaving|sent|send|sends|uploaded|upload|transmit|transmitted|stored?)"
    r"[^.]{0,90}(browser|device|computer|server|our servers)",
    r"stays?\s+(in|on)\s+your\s+(browser|device|computer)",
    r"processed?\s+(entirely\s+)?(locally|client[- ]side|in\s+your\s+browser|on your device)",
    r"client[- ]side\s+(only|processing|generation)",
    r"100%\s+(local|in[- ]browser|client[- ]side)",
    r"(all|everything)\s+(happens|runs|stays)\s+(locally|in your browser|on your device)",
)

CLAIM_PAGES = ("", "/privacy", "/privacy-policy", "/privacy/", "/legal/privacy")


def claims(only: str | None = None) -> dict:
    """What each tool says about where your data goes, and where it says it.

    Kept separate from the browser run on purpose: this is reading, not
    measuring, and the two should not be able to contaminate each other.
    """
    import re
    import urllib.error
    import urllib.request
    from urllib.parse import urljoin

    patterns = [re.compile(p, re.I) for p in CLAIM_PATTERNS]
    tag = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
    frame = json.loads(FRAME.read_text())
    found = 0
    for candidate in frame["candidates"]:
        domain = candidate["domain"]
        if only and only != domain:
            continue
        out = MEASUREMENTS / domain
        out.mkdir(parents=True, exist_ok=True)
        record = {"checked_at": utc_now(), "claim": None, "quote": "", "source_url": "",
                  "pages_read": []}
        for suffix in CLAIM_PAGES:
            url = urljoin(candidate["url"], suffix) if suffix else candidate["url"]
            try:
                request = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; InvoiceWorkshopResearch/1.0; "
                                  "+https://invoiceworkshop.com/research/)"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    body = response.read(3_000_000).decode("utf-8", "replace")
            except Exception:
                continue
            record["pages_read"].append(url)
            text = re.sub(r"\s+", " ", tag.sub(" ", body))
            for pattern in patterns:
                match = pattern.search(text)
                if not match:
                    continue
                start = max(0, match.start() - 100)
                record.update({
                    "claim": True,
                    "quote": text[start:match.end() + 100].strip()[:300],
                    "source_url": url,
                })
                break
            if record["claim"]:
                break
        if record["claim"] is None and record["pages_read"]:
            record["claim"] = False
        (out / "claim.json").write_text(json.dumps(record, indent=2) + "\n")
        if record["claim"]:
            found += 1
        print(json.dumps({"domain": domain, "claim": record["claim"],
                          "source": record["source_url"]}), flush=True)
    return {"tools_claiming_local_processing": found}


def _pdf_branding(folder: Path, domain: str) -> tuple[str, str]:
    """Whether the downloaded PDF carries the tool's own name in its text.

    Reported as branding, not as a watermark. A name in a footer and a diagonal
    stamp across the page are different things, and this can only tell them
    apart by reading the words, so it says only what it can see.
    """
    import subprocess

    pdfs = sorted(folder.glob("download-*.pdf")) + sorted(folder.glob("download-*.PDF"))
    if not pdfs:
        return "", "no pdf captured"
    try:
        text = subprocess.run(["pdftotext", str(pdfs[0]), "-"],
                              capture_output=True, text=True, timeout=60).stdout
    except Exception as error:
        return "", f"pdftotext failed: {error}"
    stem = domain.split(".")[0].lower()
    lowered = text.lower()
    if stem and stem in lowered:
        line = next((l.strip() for l in text.splitlines() if stem in l.lower()), "")
        return "yes", line[:120]
    return "no", ""


def _brand(domain: str) -> str:
    """The name part of a domain: 'invoicesimple' out of 'www.invoicesimple.com'."""
    parts = [p for p in domain.split(".") if p not in ("www", "app", "portal", "tools", "create")]
    return parts[0] if parts else domain


def same_operator(tool_domain: str, destination: str) -> bool:
    """Whether a destination is plainly the same company under another domain.

    `invoicesimple.com` posts the invoice to `data.getinvoicesimple.com`. Those
    are different registered domains, and calling that "sent to a third party"
    would be a false accusation about a company's own backend. The rule is
    mechanical and stated on the page: the names contain each other. It is not
    a claim about who owns what, only about what the names say.
    """
    a, b = _brand(tool_domain), _brand(destination)
    return bool(a and b and (a in b or b in a))


def _row(candidate: dict, evidence: dict, folder: Path) -> dict:
    egress = evidence.get("canary_left_the_browser")
    branding, branding_note = _pdf_branding(folder, candidate["domain"])
    claim_path = folder / "claim.json"
    claim = json.loads(claim_path.read_text()) if claim_path.exists() else {}
    claim_state = {True: "yes", False: "no", None: "unmeasured"}[claim.get("claim")]
    claim_quote = claim.get("quote") or ""
    claim_source = claim.get("source_url") or ""
    destinations = evidence.get("canary_destinations") or []
    unrelated = sorted({d["domain"] for d in destinations
                        if not d.get("first_party")
                        and not same_operator(candidate["domain"], d["domain"])})
    unrelated_state = "unmeasured" if egress is None else ("yes" if unrelated else "no")
    return {
        "domain": candidate["domain"],
        "measured_url": evidence.get("final_url") or candidate["url"],
        "measured_at": (evidence.get("measured_at") or "")[:19],
        "publisher_own_tool": "yes" if candidate.get("is_publisher_own_tool") else "no",
        "reachable": {True: "yes", False: "no", None: "unknown"}.get(evidence.get("reachable"), "unknown"),
        "http_status": evidence.get("http_status") or "",
        "editable_fields_found": evidence.get("fillable_fields") or 0,
        "fields_filled": evidence.get("fields_filled") or 0,
        "action_clicked": evidence.get("action_clicked") or "",
        "pdf_downloaded_without_account": "yes" if evidence.get("pdf_downloaded") else "no",
        "typed_data_left_the_browser": {True: "yes", False: "no", None: "unmeasured"}[egress],
        "sent_to_an_unrelated_domain": unrelated_state,
        "received_by": "; ".join(sorted({d["domain"] for d in destinations})),
        "unrelated_recipients": "; ".join(unrelated),
        "fields_that_left": "; ".join(
            sorted({(f.get("name") or f.get("placeholder") or f.get("label") or f.get("type") or "")
                    for f in (evidence.get("leaked_fields") or [])} - {""})),
        "sign_in_form_on_page": {True: "yes", False: "no", None: "unmeasured"}.get(
            evidence.get("login_form_present"), "unmeasured"),
        "claims_local_processing": claim_state,
        "claim_quote": claim_quote[:300],
        "claim_source_url": claim_source,
        "signup_wording_on_page": evidence.get("signup_wall_text") or "",
        "third_party_domains_contacted": len(evidence.get("third_party_domains") or []),
        "known_ad_tracker_domains": len(evidence.get("ad_tracker_domains") or []),
        "own_name_in_pdf_text": branding,
        "notes": "; ".join(evidence.get("notes") or []) or branding_note,
    }


COLUMNS = ("domain", "measured_url", "measured_at", "publisher_own_tool", "reachable",
           "http_status", "editable_fields_found", "fields_filled", "action_clicked",
           "pdf_downloaded_without_account", "typed_data_left_the_browser",
           "sent_to_an_unrelated_domain", "received_by", "unrelated_recipients",
           "fields_that_left", "sign_in_form_on_page",
           "claims_local_processing", "claim_quote", "claim_source_url",
           "signup_wording_on_page",
           "third_party_domains_contacted", "known_ad_tracker_domains",
           "own_name_in_pdf_text", "notes")


def dataset() -> dict:
    """The published CSV and the numbers the write-up is allowed to state.

    Every headline is computed over third-party tools only and over the ones
    that could actually be measured. A denominator that quietly includes tools
    the harness never reached would flatter whichever answer we wanted.
    """
    frame = json.loads(FRAME.read_text())
    rows = []
    for candidate in frame["candidates"]:
        folder = MEASUREMENTS / candidate["domain"]
        path = folder / "evidence.json"
        if not path.exists():
            continue
        rows.append(_row(candidate, json.loads(path.read_text()), folder))
    rows.sort(key=lambda r: r["domain"])

    out = ROOT / "public" / "research"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "free-invoice-generator-audit-2026.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    others = [r for r in rows if r["publisher_own_tool"] == "no"]
    measured = [r for r in others if r["typed_data_left_the_browser"] in ("yes", "no")]
    left = [r for r in measured if r["typed_data_left_the_browser"] == "yes"]
    to_third = [r for r in measured if r["sent_to_an_unrelated_domain"] == "yes"]
    behind_account = [r for r in others
                      if r["typed_data_left_the_browser"] == "unmeasured"
                      and r["sign_in_form_on_page"] == "yes"]
    claimers = [r for r in measured if r["claims_local_processing"] == "yes"]
    broke_claim = [r for r in claimers if r["typed_data_left_the_browser"] == "yes"]
    third = sorted(r["third_party_domains_contacted"] for r in others)
    summary = {
        "drawn_on": frame["drawn_on"][:10],
        "queries": len(frame["queries"]),
        "tools_in_frame": len(rows),
        "third_party_tools": len(others),
        "measurable": len(measured),
        "not_measurable": len(others) - len(measured),
        "typed_data_left_the_browser": len(left),
        "sent_to_an_unrelated_company": len(to_third),
        "sent_only_to_the_tools_own_service": len(left) - len(to_third),
        "unrelated_recipients": sorted({d for r in to_third
                                        for d in r["unrelated_recipients"].split("; ") if d}),
        "kept_in_the_browser": len(measured) - len(left),
        "editor_behind_an_account": len(behind_account),
        "claimed_local_processing": len(claimers),
        "claimed_local_but_sent_it_anyway": len(broke_claim),
        "pdf_without_an_account": sum(1 for r in others if r["pdf_downloaded_without_account"] == "yes"),
        "third_party_domains_median": third[len(third) // 2] if third else 0,
        "third_party_domains_max": max(third) if third else 0,
        "third_party_domains_max_domain": max(
            others, key=lambda r: r["third_party_domains_contacted"])["domain"] if others else "",
        "csv": str(csv_path.relative_to(ROOT)),
    }
    (DATA / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    # The page renders from this file, so the prose and the table cannot drift
    # apart from the CSV people download. There is no second copy of a number.
    site_data = ROOT / "src" / "data"
    site_data.mkdir(parents=True, exist_ok=True)
    (site_data / "invoice-generator-audit-2026.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n")
    return summary


def _measurements() -> list[dict]:
    if not MEASUREMENTS.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(MEASUREMENTS.glob("*/evidence.json"))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    draw = sub.add_parser("sample")
    draw.add_argument("--limit", type=int, default=50)
    sub.add_parser("frame")
    sub.add_parser("dataset")
    claim = sub.add_parser("claims")
    claim.add_argument("--only")
    run = sub.add_parser("measure")
    run.add_argument("--only")
    run.add_argument("--redo", action="store_true")
    args = parser.parse_args()

    if args.command == "sample":
        print(json.dumps(sample(args.limit), indent=2))
    elif args.command == "claims":
        print(json.dumps(claims(args.only), indent=2))
    elif args.command == "dataset":
        print(json.dumps(dataset(), indent=2))
    elif args.command == "measure":
        print(json.dumps(measure(args.only, args.redo), indent=2))
    elif args.command == "frame":
        print(json.dumps(json.loads(FRAME.read_text())["candidates"], indent=2))


if __name__ == "__main__":
    main()
