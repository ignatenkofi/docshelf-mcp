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


# --------------------------------------------------------------- fence-awareness


def _titles(text):
    return [t for t, _ in split_by_h2(text)]


def test_hash_lines_inside_backtick_fence_are_not_headings():
    md = "```bash\n# install deps\n## reconfigure the daemon\nfoo --init\n```\n"
    # Zero H2s -> not enough to split even when big.
    assert should_split("body\n" * 5000 + md, threshold_bytes=50) is False
    assert _titles(md) == ["preamble"]


def test_hash_lines_inside_tilde_fence_are_not_headings():
    md = "~~~\n## [global]\nkey = value\n~~~\n"
    assert _titles(md) == ["preamble"]


def test_info_string_opener_and_bare_closer():
    md = "```ini\n## section markers start with double-hash\nport = 8080\n```\n"
    assert _titles(md) == ["preamble"]


def test_real_h2_before_and_after_fence_still_split():
    md = (
        "## Configuration\n\nEdit the file:\n\n"
        "```bash\nvim /etc/foo.conf\n```\n\n"
        "## Verification\n\nRun the check.\n"
    )
    # Doc starts with an H2, so there is no preamble section.
    titles = _titles(md)
    assert titles == ["Configuration", "Verification"]
    # Each section body keeps balanced fences.
    for _title, body in split_by_h2(md):
        assert body.count("```") % 2 == 0


def test_unterminated_fence_runs_to_eof():
    md = (
        "## Router Config\n\n```rsc\n/ip firewall filter\n"
        "## the export dump runs to end of file\nadd chain=input\n"
    )
    # Only the real H2 before the fence counts; the interior one is code.
    # Doc starts with the H2, so no preamble section.
    assert _titles(md) == ["Router Config"]


def test_fake_h1_inside_fence_is_not_demoted():
    md = "```text\n# 12 ADC chain=input action=accept\n# 0 X ether1 mtu=1500\n```\n"
    cleaned = clean_markdown(md)
    # Verbatim: no 4-space indent added, no leading "# " stripped.
    assert "# 12 ADC chain=input action=accept" in cleaned
    assert "# 0 X ether1 mtu=1500" in cleaned
    assert "    12 ADC" not in cleaned


def test_cross_char_fence_markers_do_not_close():
    md = (
        "~~~\nfirst tilde block\n```\n## backtick line does not close tilde\n~~~\n\n"
        "## Real Heading\n\n"
        "```\nsecond block\n~~~\n## tilde line does not close backtick\n```\n"
    )
    assert _titles(md) == ["preamble", "Real Heading"]


def test_indented_fence_is_recognized():
    md = "1. Edit:\n\n   ```ini\n## not a heading\n   port = 22\n   ```\n"
    assert _titles(md) == ["preamble"]


def test_closing_fence_with_trailing_whitespace():
    md = "```bash\necho hi\n```   \n## Real Heading After Fence\n"
    assert _titles(md) == ["preamble", "Real Heading After Fence"]


def test_consecutive_fences_with_hash_between():
    md = "```bash\necho one\n```\n## Real Heading Between Fences\n```bash\necho two\n```\n"
    assert _titles(md) == ["preamble", "Real Heading Between Fences"]


def test_longer_outer_fence_not_closed_by_shorter_interior():
    md = (
        "````markdown\n```bash\n## example code inside outer fence\n```\n"
        "## still inside the 4-backtick fence\n````\n"
    )
    assert _titles(md) == ["preamble"]


def test_two_backticks_are_not_a_fence():
    md = "``inline snippet not a fence``\n\n## Real Heading\n"
    assert _titles(md) == ["preamble", "Real Heading"]


def test_fake_h1_outside_fence_still_demoted():
    # Regression guard: the fix must not disable demotion for real stray H1s.
    cleaned = clean_markdown("# 0 X chain=forward action=accept\n# Real Heading\n")
    assert "    0 X chain=forward" in cleaned
    assert "# Real Heading" in cleaned
