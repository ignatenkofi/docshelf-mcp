"""Tests for clean_markdown / split_by_h2 / write_split_files."""

from pathlib import Path

from docshelf_mcp.core.splitter import (
    clean_markdown,
    should_split,
    split_by_h2,
    write_split_files,
)

SAMPLE = """# Title

Some preamble.

## Intro

Hello world.

## Chapter Two

Body of chapter two.

## Chapter Three

End.
"""


def test_split_returns_three_sections():
    sections = split_by_h2(SAMPLE)
    assert len(sections) == 4  # preamble + 3 H2
    titles = [s[0] for s in sections]
    assert titles == ["preamble", "Intro", "Chapter Two", "Chapter Three"]


def test_split_section_body_starts_with_heading():
    sections = split_by_h2(SAMPLE)
    # Non-preamble sections should start with their `## ` line.
    for _title, body in sections[1:]:
        first_line = body.splitlines()[0]
        assert first_line.startswith("## ")


def test_clean_markdown_collapses_blank_runs():
    noisy = "Para 1\n\n\n\n\nPara 2\n"
    cleaned = clean_markdown(noisy)
    # Should have at most one blank line between paragraphs.
    assert "\n\n\n" not in cleaned


def test_clean_markdown_demotes_fake_h1():
    text = "# 0 X chain=forward action=accept\n# Real Heading\n"
    cleaned = clean_markdown(text)
    # "# 0 X" should be demoted (no longer starts with "# ")
    lines = cleaned.splitlines()
    assert any("0 X chain=forward" in ln and not ln.startswith("# ") for ln in lines)
    # "# Real Heading" survives untouched.
    assert "# Real Heading" in lines


def test_should_split_threshold():
    # Small text — never split.
    assert should_split("## a\n## b\n", threshold_bytes=100) is False
    # Big text with H2s — split.
    big = "## a\n" + ("body\n" * 1000) + "## b\nmore\n"
    assert should_split(big, threshold_bytes=50) is True
    # Big text with too few H2s — don't split.
    big_no_h2 = ("body\n" * 5000)
    assert should_split(big_no_h2, threshold_bytes=50) is False


def test_write_split_files_creates_numbered_files(tmp_path: Path):
    sections = split_by_h2(SAMPLE)
    out = tmp_path / "out"
    paths = write_split_files(sections, out)

    assert out.is_dir()
    assert len(paths) == len(sections)
    # Files are numbered NNN-...
    names = sorted(p.name for p in out.iterdir())
    assert names[0].startswith("001-")
    assert all(p.suffix == ".md" for p in paths)


def test_write_split_files_idempotent(tmp_path: Path):
    sections = split_by_h2(SAMPLE)
    out = tmp_path / "out"
    write_split_files(sections, out)
    paths_first = sorted(p.name for p in out.iterdir())

    # Re-run with fewer sections — directory should be wiped, not appended to.
    write_split_files(sections[:2], out)
    paths_second = sorted(p.name for p in out.iterdir())

    assert paths_second != paths_first
    assert len(paths_second) == 2
