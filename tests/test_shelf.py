"""End-to-end tests for the Shelf facade — using only Markdown sources
(no PDF dependency required)."""

import json
from pathlib import Path

import pytest

from docshelf_mcp.core.shelf import Shelf

FIXTURE = Path(__file__).parent / "fixtures" / "sample.md"


def test_init_creates_layout(tmp_path: Path):
    shelf = Shelf(tmp_path / "myshelf").init(
        name="Test Shelf",
        remote="https://github.com/me/myrepo",
        default_categories=["alpha", "beta"],
    )
    assert (shelf.root / ".docshelf.json").is_file()
    assert (shelf.root / "INDEX.md").is_file()
    assert (shelf.root / ".gitignore").is_file()
    assert (shelf.root / "docs" / "alpha").is_dir()
    assert (shelf.root / "docs" / "beta").is_dir()

    cfg = json.loads((shelf.root / ".docshelf.json").read_text())
    assert cfg["name"] == "Test Shelf"
    assert cfg["remote"] == "https://github.com/me/myrepo"
    assert "alpha" in cfg["category_order"]


def test_init_is_idempotent(tmp_path: Path):
    Shelf(tmp_path / "s").init(name="V1", default_categories=["a"])
    Shelf(tmp_path / "s").init(name="V1", default_categories=["a", "b"])
    cfg = json.loads((tmp_path / "s" / ".docshelf.json").read_text())
    # Both categories present, no duplicates.
    assert cfg["category_order"].count("a") == 1
    assert "b" in cfg["category_order"]


def test_add_markdown_document(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(
        name="S", remote="https://github.com/me/r", default_categories=["docs"]
    )
    result = shelf.add_document(
        FIXTURE,
        category="docs",
        title="Sample Document",
        description="A test fixture.",
        split=False,
    )

    assert result.document_path.is_file()
    assert not result.was_split
    assert result.converted_from_pdf is False

    # INDEX.md mentions the title and the raw URL.
    idx = (shelf.root / "INDEX.md").read_text()
    assert "Sample Document" in idx
    assert "raw.githubusercontent.com" in idx


def test_add_document_with_split(tmp_path: Path):
    # Build a synthetic 'big' MD that crosses the 50 KB threshold.
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500  # ~14 KB per chapter
    text = "# Title\n\n" + "\n\n".join(
        f"## Section {i}\n\n{chapter_body}" for i in range(5)
    )
    big_md.write_text(text, encoding="utf-8")
    assert len(big_md.read_bytes()) > 50 * 1024  # sanity check on the fixture

    shelf = Shelf(tmp_path / "s").init(name="S")
    result = shelf.add_document(
        big_md,
        category="big",
        title="Big Document",
        split=True,
    )
    assert result.was_split, "expected the splitter to fire"
    assert len(result.section_paths) >= 2
    for p in result.section_paths:
        assert p.exists()
        assert p.name.startswith("0")  # NNN-prefix


def test_add_document_unsupported_type(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    bad = tmp_path / "junk.txt"
    bad.write_text("hi")
    with pytest.raises(ValueError):
        shelf.add_document(bad, category="x", title="No")


def test_search_finds_keyword(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)

    hits = shelf.search("BGP")
    assert len(hits) == 1
    assert hits[0]["score"] >= 1

    # No-match query
    assert shelf.search("xyzzzznevermentioned") == []


def test_search_returns_empty_for_blank_query(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    assert shelf.search("") == []
    assert shelf.search("   ") == []


def test_rebuild_index_reflects_disk(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(
        name="S", remote="https://github.com/me/r", default_categories=["a"]
    )
    shelf.add_document(FIXTURE, category="a", title="One", split=False)
    shelf.add_document(FIXTURE, category="a", title="Two", split=False)

    idx_path = shelf.rebuild_index()
    text = idx_path.read_text()
    assert "One" in text and "Two" in text

    # Delete one file directly, rebuild, confirm it's gone.
    (shelf.root / "docs" / "a" / "one.md").unlink()
    shelf.rebuild_index()
    text = (shelf.root / "INDEX.md").read_text()
    assert "Two" in text
    # The deleted title shouldn't appear in INDEX anymore.
    # ("One" might still appear in passing — but the entry line shouldn't.)
    assert "**One**" not in text


def test_shelf_without_remote_still_works(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="Local Shelf")  # no remote
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    text = (shelf.root / "INDEX.md").read_text()
    assert "Sample" in text
    # No raw URL in the entry (because remote is empty).
    assert "raw.githubusercontent.com" not in text
