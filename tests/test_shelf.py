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


def test_split_document_gets_subindex(tmp_path: Path):
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    text = "# Title\n\n" + "\n\n".join(
        f"## Section {i}\n\n{chapter_body}" for i in range(5)
    )
    big_md.write_text(text, encoding="utf-8")

    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    result = shelf.add_document(big_md, category="big", title="Big Document", split=True)
    assert result.was_split

    subindex = result.document_path.parent / result.document_path.stem / "SUBINDEX.md"
    assert subindex.is_file()
    sub_text = subindex.read_text(encoding="utf-8")
    assert "# Big Document — sections" in sub_text
    assert "raw.githubusercontent.com" in sub_text

    # SUBINDEX is navigation: not a section in INDEX counts, not a search hit.
    idx = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    assert "sections: 5" in idx or "sections: 6" in idx  # preamble may add one
    assert shelf.search("Lorem")  # body text is findable...
    assert not any(
        "SUBINDEX" in h["relative_path"] for h in shelf.search("Big Document sections")
    )


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


def test_search_requires_all_tokens(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "bridge-only.md"
    doc.write_text("# Net\n\nbridge configuration here\n", encoding="utf-8")
    shelf.add_document(doc, category="net", title="Bridge Only", split=False)

    # Default mode="all": a doc containing only one of two tokens is no hit.
    assert shelf.search("vlan bridge") == []
    # Explicit mode="any" relaxes to at-least-one token.
    any_hits = shelf.search("vlan bridge", mode="any")
    assert len(any_hits) == 1

    # A doc with both tokens matches in the default mode.
    both = tmp_path / "both.md"
    both.write_text("# Net\n\nvlan over bridge\n", encoding="utf-8")
    shelf.add_document(both, category="net", title="Both", split=False)
    all_hits = shelf.search("vlan bridge")
    assert [h["relative_path"] for h in all_hits] == ["docs/net/both.md"]


def test_search_ranks_by_total_occurrences(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    one = tmp_path / "one.md"
    one.write_text("# A\n\nvlan bridge\n", encoding="utf-8")
    many = tmp_path / "many.md"
    many.write_text("# B\n\nvlan bridge vlan bridge vlan\n", encoding="utf-8")
    shelf.add_document(one, category="net", title="One Mention", split=False)
    shelf.add_document(many, category="net", title="Many Mentions", split=False)

    hits = shelf.search("vlan bridge")
    assert hits[0]["relative_path"] == "docs/net/many-mentions.md"
    assert hits[0]["score"] > hits[1]["score"]


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
