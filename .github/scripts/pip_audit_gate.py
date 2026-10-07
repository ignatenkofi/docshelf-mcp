"""Gate over a pip-audit JSON report with an accepted-advisories list.

Usage: pip_audit_gate.py REPORT.json IGNORE_FILE [--today YYYY-MM-DD]

Fails (exit 1) when
  * the report audits no package at all — "0 advisories" over nothing is
    not a clean result (#119);
  * the ignore file's `review-by` date has passed — the acceptance expired;
  * pip-audit reports an id the ignore file does not list — a new advisory;
  * the ignore file lists an id pip-audit no longer reports — a stale
    ignore, e.g. after the marker-pdf 2.x port lifted transformers (#112).

The summary line names the number of packages the report audited, counted
from the report itself, so a green run says how much it checked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

REVIEW_BY = re.compile(r"^#\s*review-by:\s*(\d{4}-\d{2}-\d{2})\s*$")


def read_ignore(path: str) -> tuple[dt.date, set[str]]:
    review_by = None
    ids: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = REVIEW_BY.match(line.strip())
            if match:
                review_by = dt.date.fromisoformat(match.group(1))
                continue
            line = line.strip()
            if line and not line.startswith("#"):
                ids.add(line.split()[0])
    if review_by is None:
        sys.exit(f"{path}: no '# review-by: YYYY-MM-DD' line — an acceptance without a date")
    return review_by, ids


def reported(path: str) -> tuple[int, int, dict[str, str]]:
    """(packages audited, packages skipped, advisory id -> "name version")."""
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    audited = skipped = 0
    found: dict[str, str] = {}
    for dep in report["dependencies"]:
        # A dependency pip-audit could not look up carries `skip_reason` and
        # no verdict: it was listed, not audited.
        if "skip_reason" in dep:
            skipped += 1
            continue
        audited += 1
        for vuln in dep.get("vulns", []):
            found[vuln["id"]] = f"{dep['name']} {dep['version']}"
    return audited, skipped, found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("ignore_file")
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = parser.parse_args()

    review_by, accepted = read_ignore(args.ignore_file)
    audited, skipped, found = reported(args.report)
    errors = []
    if audited == 0:
        errors.append(
            f"the report audits 0 packages ({skipped} skipped) — nothing was checked, "
            "so its advisory count means nothing; is the requirements file empty?"
        )
    if args.today > review_by:
        errors.append(
            f"review-by {review_by} has passed: re-decide #112 and move the date "
            f"(or drop the ids) in {args.ignore_file}"
        )
    for vid in sorted(set(found) - accepted):
        errors.append(f"new advisory {vid} ({found[vid]}) — not in {args.ignore_file}")
    # "No longer reported" needs an audit to have run: over an empty report
    # every accepted id would read "remove it", which is the wrong advice.
    if audited:
        for vid in sorted(accepted - set(found)):
            errors.append(f"stale ignore {vid}: pip-audit no longer reports it — remove it")

    print(
        f"pip-audit: {audited} packages audited ({skipped} skipped), "
        f"{len(found)} advisories, {len(accepted)} accepted "
        f"(review-by {review_by}), {len(errors)} problem(s)"
    )
    for err in errors:
        print(f"::error title=pip-audit gate::{err}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
