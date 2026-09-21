"""benchmarks/make_chart.py: safe to invoke, deterministic, and a drift guard.

Before it had a CLI the script wrote docs/assets/token-savings.svg on every
invocation — `--help` included — so asking it for help dirtied the working
tree. These tests pin the contract: --help writes nothing, --out writes only
where told, two renders are byte-identical, and --check judges the committed
chart against the numbers in the script.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "benchmarks" / "make_chart.py"
COMMITTED = REPO / "docs" / "assets" / "token-savings.svg"

if not SCRIPT.is_file():
    # benchmarks/ is not part of the sdist; there is nothing to test there.
    pytest.skip("benchmarks/make_chart.py is only in the git checkout", allow_module_level=True)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_help_writes_nothing():
    before = (COMMITTED.stat().st_mtime_ns, COMMITTED.read_bytes())

    result = run("--help")

    assert result.returncode == 0, result.stderr
    assert "--check" in result.stdout and "--out" in result.stdout
    assert (COMMITTED.stat().st_mtime_ns, COMMITTED.read_bytes()) == before, (
        "--help must not touch the committed chart"
    )


def test_out_writes_only_there_and_is_deterministic(tmp_path):
    before = (COMMITTED.stat().st_mtime_ns, COMMITTED.read_bytes())
    first, second = tmp_path / "first.svg", tmp_path / "second.svg"

    assert run("--out", str(first)).returncode == 0
    assert run("--out", str(second)).returncode == 0

    assert first.read_bytes() == second.read_bytes(), "two renders must be byte-identical"
    assert first.read_bytes().startswith(b"<svg ")
    assert (COMMITTED.stat().st_mtime_ns, COMMITTED.read_bytes()) == before


def test_check_passes_on_the_committed_chart():
    # Edit SHELVES without regenerating the SVG and this goes red.
    result = run("--check")

    assert result.returncode == 0, result.stdout + result.stderr


def test_check_fails_on_a_stale_or_missing_chart(tmp_path):
    stale = tmp_path / "stale.svg"
    stale.write_text("<svg/>", encoding="utf-8")

    assert run("--check", "--out", str(stale)).returncode == 1
    assert run("--check", "--out", str(tmp_path / "missing.svg")).returncode == 1

    assert stale.read_text(encoding="utf-8") == "<svg/>", "--check must not write"
    assert not (tmp_path / "missing.svg").exists()
