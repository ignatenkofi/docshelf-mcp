""".github/scripts/pip_audit_gate.py: "0 advisories" must not pass over nothing.

The gate printed only an advisory count, and an empty report failed it only
by accident — as 23 "stale ignore" errors, while the accepted list from #112
is non-empty. Once that list empties, an audit that checked nothing would
read "0 advisories" and pass (#119). These tests run the script the way the
dependency-audit job does.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".github" / "scripts" / "pip_audit_gate.py"
IGNORE = REPO / ".github" / "pip-audit-ignore.txt"

if not SCRIPT.is_file():
    # .github/ is not part of the sdist; there is nothing to test there.
    pytest.skip("pip_audit_gate.py is only in the git checkout", allow_module_level=True)


def gate(report: dict, ignore: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "pip-audit.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), str(ignore), "--today", "2026-10-07"],
        capture_output=True,
        text=True,
        check=False,
    )


def accepted_ids() -> list[str]:
    ids = []
    for line in IGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line.split()[0])
    return ids


def empty_ignore(tmp_path: Path) -> Path:
    path = tmp_path / "ignore.txt"
    path.write_text("# review-by: 2026-12-31\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("accepted", ["the real list", "an empty list"])
def test_an_empty_report_fails_and_says_nothing_was_audited(tmp_path: Path, accepted: str):
    ignore = IGNORE if accepted == "the real list" else empty_ignore(tmp_path)

    result = gate({"dependencies": [], "fixes": []}, ignore, tmp_path)

    assert result.returncode == 1, result.stdout
    assert "0 packages audited" in result.stdout
    # Not 23 "remove it" errors: over an empty report the accepted ids are
    # not stale, and the advice would empty the list.
    assert "stale ignore" not in result.stdout


def test_skipped_packages_are_not_counted_as_audited(tmp_path: Path):
    report = {
        "dependencies": [{"name": "nowhere", "skip_reason": "Dependency not found on PyPI"}],
        "fixes": [],
    }

    result = gate(report, empty_ignore(tmp_path), tmp_path)

    assert result.returncode == 1, result.stdout
    assert "0 packages audited (1 skipped)" in result.stdout


@pytest.mark.parametrize(
    "entry",
    [{}, {"name": "x"}, {"name": "x", "version": "1.0"}, {"name": "x", "vulns": []}],
    ids=["empty", "name-only", "no-vulns", "no-version"],
)
def test_an_entry_without_a_verdict_is_not_counted_as_audited(tmp_path: Path, entry: dict):
    # Anything without a skip_reason counted as audited: {"dependencies": [{}]}
    # passed as "1 packages audited" (#119 review). A verdict is a version and
    # a vulns list; an entry with neither that nor a skip_reason fails the gate.
    result = gate({"dependencies": [entry], "fixes": []}, empty_ignore(tmp_path), tmp_path)

    assert result.returncode == 1, result.stdout
    assert "0 packages audited (0 skipped, 1 unreadable)" in result.stdout
    assert "is this pip-audit's JSON?" in result.stdout


def test_a_real_audit_passes_and_names_the_package_count(tmp_path: Path):
    # Positive control: every accepted id reported, nothing else — the CI
    # shape of a clean run. The summary says how much was checked.
    report = {
        "dependencies": [
            {"name": "pillow", "version": "10.4.0", "vulns": [{"id": i} for i in accepted_ids()]},
            {"name": "mcp", "version": "2.1.1", "vulns": []},
        ],
        "fixes": [],
    }

    result = gate(report, IGNORE, tmp_path)

    assert result.returncode == 0, result.stdout
    assert "2 packages audited (0 skipped)" in result.stdout
    assert "0 problem(s)" in result.stdout
