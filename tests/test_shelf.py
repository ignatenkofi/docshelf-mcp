"""End-to-end tests for the Shelf facade — using only Markdown sources
(no PDF dependency required)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from docshelf_mcp.core.indexer import IndexHints
from docshelf_mcp.core.shelf import (
    SHELF_MANIFEST_FILENAME,
    SHELF_METADATA_FILENAME,
    Shelf,
)

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


def test_add_document_with_slug_decouples_filename_from_title(tmp_path: Path):
    # #75 acceptance: a latin, date-prefixed slug names the file while a
    # Cyrillic display title lands in INDEX/meta untouched — one call, no
    # .meta.json hand-off.
    shelf = Shelf(tmp_path / "s").init(
        name="S", remote="https://github.com/me/r", default_categories=["sessions"]
    )
    result = shelf.add_document(
        FIXTURE,
        category="sessions",
        slug="2026-07-22-m1-build-sprint",
        title="Сессия: M1 собран за день",
        split=False,
    )

    expected = shelf.root / "docs" / "sessions" / "2026-07-22-m1-build-sprint.md"
    assert result.document_path == expected
    assert expected.is_file()

    # The display title (not the slug) is the INDEX entry text; the slug still
    # appears there as the file's link target, which is expected. Read as UTF-8
    # explicitly — the Cyrillic title would blow up on a cp1252 default (Windows).
    idx = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    assert "Сессия: M1 собран за день" in idx
    assert "docs/sessions/2026-07-22-m1-build-sprint.md" in idx

    # .meta.json keys the slug filename and stores the Cyrillic title verbatim.
    meta = json.loads((shelf.root / "docs" / "sessions" / ".meta.json").read_text(encoding="utf-8"))
    assert meta["2026-07-22-m1-build-sprint.md"]["title"] == "Сессия: M1 собран за день"


def test_add_document_blank_slug_falls_back_to_title(tmp_path: Path):
    # A None/blank slug preserves today's title-derived filename exactly.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["docs"])
    from_none = shelf.add_document(FIXTURE, category="docs", title="Plain Title", split=False)
    assert from_none.document_path.name == "plain-title.md"

    from_blank = shelf.add_document(
        FIXTURE, category="docs", title="Plain Title", slug="   ", split=False
    )
    # Blank slug slugifies to nothing → same title-derived path (in-place update).
    assert from_blank.document_path == from_none.document_path


def test_add_document_with_split(tmp_path: Path):
    # Build a synthetic 'big' MD that crosses the 50 KB threshold.
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500  # ~14 KB per chapter
    text = "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5))
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
    text = "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5))
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
    assert not any("SUBINDEX" in h["relative_path"] for h in shelf.search("Big Document sections"))


# A host's own wording, shaped like memshelf's: its tools are `shelve` and
# `rebuild`, and it has neither add_document nor rebuild_index.
HOST_HINTS = IndexHints(
    empty="_Nothing shelved yet. Use `memshelf shelve` to start._",
    index_footer="Rendered by memshelf; a bot-owned shelf leaves this file to the bot.",
    subindex_footer="rendered by memshelf. See `INDEX.md` at the shelf root.",
)


def test_hints_reach_index_and_subindex_and_doctor_agrees(tmp_path: Path):
    # memshelf renders INDEX.md through Shelf.rebuild_index(), and agents read
    # INDEX.md first: docshelf's lines told them to call add_document and
    # rebuild_index, tools memshelf does not have (memshelf-mcp#197).
    shelf = Shelf(tmp_path / "s", hints=HOST_HINTS).init(name="S")
    index = shelf.root / "INDEX.md"
    assert HOST_HINTS.empty in index.read_text(encoding="utf-8")

    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    big_md.write_text(
        "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5)),
        encoding="utf-8",
    )
    shelf.add_document(big_md, category="big", title="Big Document", split=True)
    shelf.add_document(FIXTURE, category="guides", title="Setup", split=False)

    subindexes = sorted(shelf.root.glob("docs/*/*/SUBINDEX.md"))
    assert len(subindexes) == 1
    for path in [index, *subindexes]:
        text = path.read_text(encoding="utf-8")
        assert "add_document" not in text, path.name
        assert "rebuild_index" not in text, path.name
    rendered = index.read_text(encoding="utf-8")
    sub_text = subindexes[0].read_text(encoding="utf-8")
    # The hint words the line after docshelf's marker, never the marker:
    # shelf-spec tells a docshelf INDEX.md by it (#197 review).
    marker = "*Auto-generated by [docshelf-mcp]"
    assert rendered.splitlines()[-1].startswith(marker)
    assert rendered.endswith(f". {HOST_HINTS.index_footer}*\n")
    assert sub_text.splitlines()[-1].startswith(marker)
    assert sub_text.endswith(f" — {HOST_HINTS.subindex_footer}*\n")

    # doctor's stale-index compares INDEX.md with its own render: rendered
    # without the hints, every host shelf would be "out of date", and
    # doctor(fix=True) would write docshelf's wording back.
    assert "stale-index" not in {f.rule for f in shelf.doctor()}
    shelf.doctor(fix=True)
    assert index.read_text(encoding="utf-8") == rendered

    # Another instance without hints is docshelf's own view of the same shelf.
    assert "stale-index" in {f.rule for f in Shelf(shelf.root).doctor()}


def test_a_subclass_that_skips_super_init_still_renders(tmp_path: Path):
    # hints became an instance attribute set in __init__, so a subclass with
    # its own __init__ that never calls super() broke on rebuild_index with an
    # AttributeError; it worked before the hook (#197 review).
    Shelf(tmp_path / "s").init(name="S")
    expected = (tmp_path / "s" / "INDEX.md").read_text(encoding="utf-8")

    class OwnInit(Shelf):
        def __init__(self, root: Path) -> None:
            self.root = Path(root).resolve()
            self._config = None

    OwnInit(tmp_path / "s").rebuild_index()

    assert (tmp_path / "s" / "INDEX.md").read_text(encoding="utf-8") == expected


def test_add_document_rebuilds_index_exactly_once(tmp_path: Path, monkeypatch):
    shelf = Shelf(tmp_path / "s").init(name="S")
    calls = {"n": 0}
    real = shelf.rebuild_index
    monkeypatch.setattr(
        shelf, "rebuild_index", lambda: (calls.__setitem__("n", calls["n"] + 1), real())[1]
    )

    shelf.add_document(FIXTURE, category="docs", title="One", split=False)
    assert calls["n"] == 1  # not 2 — the tools layer no longer double-rebuilds


def test_add_document_defer_rebuild(tmp_path: Path, monkeypatch):
    shelf = Shelf(tmp_path / "s").init(name="S")
    calls = {"n": 0}
    monkeypatch.setattr(shelf, "rebuild_index", lambda: calls.__setitem__("n", calls["n"] + 1))
    shelf.add_document(FIXTURE, category="docs", title="One", split=False, rebuild_index=False)
    assert calls["n"] == 0


def test_add_directory_ingests_all_and_rebuilds_once(tmp_path: Path, monkeypatch):
    src = tmp_path / "incoming"
    src.mkdir()
    for i in range(3):
        (src / f"doc-{i}.md").write_text(f"# Doc {i}\n\nbody {i}\n", encoding="utf-8")
    (src / "notes.txt").write_text("ignored", encoding="utf-8")  # not matched

    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    calls = {"n": 0}
    real = shelf.rebuild_index
    monkeypatch.setattr(
        shelf, "rebuild_index", lambda: (calls.__setitem__("n", calls["n"] + 1), real())[1]
    )

    results = shelf.add_directory(src, category="docs")
    assert [r["status"] for r in results] == ["ok", "ok", "ok"]
    assert calls["n"] == 1  # single rebuild for the whole batch
    idx = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    assert "Doc 0" in idx and "Doc 1" in idx and "Doc 2" in idx


def test_add_directory_reports_per_file_failure(tmp_path: Path):
    src = tmp_path / "incoming"
    src.mkdir()
    (src / "good.md").write_text("# Good\n\nok\n", encoding="utf-8")
    # A .pdf that isn't a real PDF -> conversion fails for just this file.
    (src / "broken.pdf").write_text("not really a pdf", encoding="utf-8")

    shelf = Shelf(tmp_path / "s").init(name="S")
    results = shelf.add_directory(src, category="docs")
    by_file = {r["file"]: r for r in results}
    assert by_file["good.md"]["status"] == "ok"
    assert by_file["broken.pdf"]["status"] == "error"
    # The good file still landed despite the sibling failure.
    assert (shelf.root / "docs" / "docs" / "good.md").is_file()
    assert "Good" in (shelf.root / "INDEX.md").read_text(encoding="utf-8")


def test_add_directory_missing_dir_raises(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    with pytest.raises(FileNotFoundError):
        shelf.add_directory(tmp_path / "nope", category="docs")


def test_add_directory_default_patterns_cover_all_formats(tmp_path: Path):
    # #52: the default pattern set must cover every format the converter
    # ingests (#16 added DOCX/HTML/EPUB), not just the old ("*.pdf", "*.md") —
    # else a folder of .docx / .epub is silently matched by nothing.
    src = tmp_path / "incoming"
    src.mkdir()
    (src / "note.md").write_text("# Note\n\nbody\n", encoding="utf-8")
    (src / "chapter.markdown").write_text("# Chapter\n\nbody\n", encoding="utf-8")
    # A .docx that isn't a real docx: conversion fails, but the point is that
    # the default patterns *match* it (old defaults would skip it entirely).
    (src / "brief.docx").write_bytes(b"not a real docx")

    shelf = Shelf(tmp_path / "s").init(name="S")
    results = shelf.add_directory(src, category="docs")  # default patterns
    matched = {r["file"] for r in results}
    assert "note.md" in matched
    assert "chapter.markdown" in matched  # missed by the old ("*.pdf", "*.md")
    assert "brief.docx" in matched  # the #52 gap: matched even if it fails to convert


def test_add_document_surfaces_section_warnings(tmp_path: Path):
    # A big doc with one clean chapter and one junk (unit-fragment) heading.
    filler = "Body sentence for padding purposes here. " * 700
    big = tmp_path / "big.md"
    big.write_text(
        "# Manual\n\n"
        "## Overview\n\n" + filler + "\n\n"
        "## 2.5 Gb/s. Full duplex operation is supported.\n\n" + filler + "\n",
        encoding="utf-8",
    )
    shelf = Shelf(tmp_path / "s").init(name="S")
    result = shelf.add_document(big, category="net", title="Manual", split=True)
    assert result.was_split
    rules = {w.rule for w in result.warnings}
    assert "unit-fragment" in rules
    # The clean "Overview" heading is not flagged.
    assert all("Overview" not in w.heading for w in result.warnings)

    # lint_shelf re-derives the same warnings from disk.
    disk = shelf.lint_shelf()
    key = next(iter(disk))
    assert any(w.rule == "unit-fragment" for w in disk[key])


def test_add_document_refuses_slug_collision(tmp_path: Path):
    # Two distinct titles that slugify to the same stem must not clobber each
    # other silently — the second add errors and the first survives intact.
    from docshelf_mcp.core.shelf import DocumentExistsError

    shelf = Shelf(tmp_path / "s").init(name="S")
    a = tmp_path / "a.md"
    a.write_text("# Alpha\n\nUNIQUE_ALPHA_BODY\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# Beta\n\nUNIQUE_BETA_BODY\n", encoding="utf-8")

    shelf.add_document(a, category="c", title="C++ Guide!", split=False)
    with pytest.raises(DocumentExistsError):
        shelf.add_document(b, category="c", title="C++ Guide?", split=False)

    # Exactly one file, still holding the first document's body.
    files = sorted(p.name for p in (shelf.root / "docs" / "c").glob("*.md"))
    assert files == ["c-guide.md"]
    assert "UNIQUE_ALPHA_BODY" in (shelf.root / "docs" / "c" / "c-guide.md").read_text()


def test_add_document_overwrite_flag_replaces_colliding_document(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    a = tmp_path / "a.md"
    a.write_text("# Alpha\n\nUNIQUE_ALPHA_BODY\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# Beta\n\nUNIQUE_BETA_BODY\n", encoding="utf-8")

    shelf.add_document(a, category="c", title="C++ Guide!", split=False)
    result = shelf.add_document(b, category="c", title="C++ Guide?", split=False, overwrite=True)
    assert result.overwritten is True
    body = (shelf.root / "docs" / "c" / "c-guide.md").read_text()
    assert "UNIQUE_BETA_BODY" in body and "UNIQUE_ALPHA_BODY" not in body
    # The meta title reflects the replacement.
    meta = json.loads((shelf.root / "docs" / "c" / ".meta.json").read_text())
    assert meta["c-guide.md"]["title"] == "C++ Guide?"


def test_add_document_same_title_reingest_updates_in_place(tmp_path: Path):
    # Re-adding the SAME title is an in-place update, not a collision — no flag
    # needed, and `overwritten` reports the replacement.
    shelf = Shelf(tmp_path / "s").init(name="S")
    v1 = tmp_path / "v1.md"
    v1.write_text("# Manual\n\nOLD_REVISION\n", encoding="utf-8")
    v2 = tmp_path / "v2.md"
    v2.write_text("# Manual\n\nNEW_REVISION\n", encoding="utf-8")

    first = shelf.add_document(v1, category="c", title="Manual", split=False)
    assert first.overwritten is False
    second = shelf.add_document(v2, category="c", title="Manual", split=False)
    assert second.overwritten is True
    body = (shelf.root / "docs" / "c" / "manual.md").read_text()
    assert "NEW_REVISION" in body and "OLD_REVISION" not in body


def test_add_document_unsluggable_titles_dont_collide_silently(tmp_path: Path):
    # Titles that slugify to nothing both fall back to "document.md"; the second
    # distinct one must not silently overwrite the first.
    from docshelf_mcp.core.shelf import DocumentExistsError

    shelf = Shelf(tmp_path / "s").init(name="S")
    a = tmp_path / "a.md"
    a.write_text("# A\n\nFIRST\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# B\n\nSECOND\n", encoding="utf-8")

    shelf.add_document(a, category="c", title="!!!", split=False)
    # slugify("!!!") is now "", so add_document's `or "document"` guard fires.
    assert (shelf.root / "docs" / "c" / "document.md").is_file()
    with pytest.raises(DocumentExistsError):
        shelf.add_document(b, category="c", title="???", split=False)


def test_rename_to_unsluggable_title_falls_back(tmp_path: Path):
    # Renaming to a title that slugifies to nothing must land on "document.md",
    # not a broken bare ".md" — the rename_document call site guards slugify's
    # now-possible "" the same way add_document does.
    shelf = Shelf(tmp_path / "s").init(name="S")
    src = tmp_path / "a.md"
    src.write_text("# A\n\nbody\n", encoding="utf-8")
    shelf.add_document(src, category="c", title="Real Title", split=False)

    result = shelf.rename_document(category="c", document="Real Title", new_title="!!!")
    assert result.new_path == "docs/c/document.md"
    assert (shelf.root / "docs" / "c" / "document.md").is_file()


def test_add_document_collision_does_not_convert_source(tmp_path: Path, monkeypatch):
    # The guard fires before conversion, so a colliding add never pays the
    # (potentially expensive) conversion cost.
    from docshelf_mcp.core import shelf as shelf_mod
    from docshelf_mcp.core.shelf import DocumentExistsError

    shelf = Shelf(tmp_path / "s").init(name="S")
    a = tmp_path / "a.md"
    a.write_text("# Alpha\n\nbody\n", encoding="utf-8")
    shelf.add_document(a, category="c", title="Same Slug", split=False)

    calls = {"n": 0}
    real = shelf_mod.source_to_markdown
    monkeypatch.setattr(
        shelf_mod,
        "source_to_markdown",
        lambda *args, **kw: (calls.__setitem__("n", calls["n"] + 1), real(*args, **kw))[1],
    )
    b = tmp_path / "b.md"
    b.write_text("# Beta\n\nbody\n", encoding="utf-8")
    with pytest.raises(DocumentExistsError):
        shelf.add_document(b, category="c", title="Same  Slug!", split=False)
    assert calls["n"] == 0  # conversion never ran


def test_add_document_warns_on_empty_conversion(tmp_path: Path):
    # A source that converts to (almost) no text — the scanned/image-only PDF
    # signature — is flagged but still written.
    shelf = Shelf(tmp_path / "s").init(name="S")
    empty = tmp_path / "scan.md"
    empty.write_text("   \n\n\t\n", encoding="utf-8")
    result = shelf.add_document(empty, category="c", title="Scanned PDF", split=False)

    assert any(w.rule == "empty-conversion" for w in result.warnings)
    # The file is still on disk (detection, not rejection).
    assert result.document_path.is_file()


def test_add_document_normal_doc_has_no_empty_warning(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    result = shelf.add_document(FIXTURE, category="c", title="Real Doc", split=False)
    assert not any(w.rule == "empty-conversion" for w in result.warnings)


def test_add_document_title_only_source_is_empty(tmp_path: Path):
    # A source that is just a heading with no body reads as empty.
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "titleonly.md"
    doc.write_text("# Just A Title\n", encoding="utf-8")
    result = shelf.add_document(doc, category="c", title="Just A Title", split=False)
    assert any(w.rule == "empty-conversion" for w in result.warnings)


def test_atomic_write_leaves_previous_file_on_failure(tmp_path: Path, monkeypatch):
    # An interrupted atomic write must not corrupt the existing target, and must
    # leave no stray temp files behind.
    import os as _os

    from docshelf_mcp.core.fsutil import atomic_write_text

    target = tmp_path / "keep.json"
    target.write_text('{"good": true}\n', encoding="utf-8")

    monkeypatch.setattr(
        "docshelf_mcp.core.fsutil.os.replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        atomic_write_text(target, "TORN NEW CONTENT")

    # Old content intact, and no `.keep.json.*.tmp` debris remains.
    assert target.read_text(encoding="utf-8") == '{"good": true}\n'
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "keep.json"]
    assert leftovers == [], f"temp files left behind: {leftovers}"
    assert _os  # keep import used on all platforms


def test_config_and_meta_survive_interrupted_index_write(tmp_path: Path, monkeypatch):
    # Simulate a crash during a rebuild: the pre-existing INDEX.md must remain
    # the last-good version, not an empty/torn file.
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="c", title="One", split=False)
    good_index = (shelf.root / "INDEX.md").read_text(encoding="utf-8")

    monkeypatch.setattr(
        "docshelf_mcp.core.fsutil.os.replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        shelf.rebuild_index()
    assert (shelf.root / "INDEX.md").read_text(encoding="utf-8") == good_index


def test_add_document_unsupported_type(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    bad = tmp_path / "junk.txt"
    bad.write_text("hi")
    with pytest.raises(ValueError):
        shelf.add_document(bad, category="x", title="No")


def test_add_html_document(tmp_path: Path):
    pytest.importorskip("markdownify")
    page = tmp_path / "manual.html"
    page.write_text(
        "<html><body><h1>Router Manual</h1><p>VLAN configuration notes.</p></body></html>",
        encoding="utf-8",
    )
    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    result = shelf.add_document(page, category="net", title="Router Manual", split=False)
    assert result.document_path.is_file()
    assert result.converted_from_pdf is False
    body = result.document_path.read_text(encoding="utf-8")
    assert "VLAN configuration notes" in body
    # Searchable through the normal pipeline.
    assert shelf.search("VLAN")


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


def test_search_boosts_heading_matches(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    body = tmp_path / "body.md"
    body.write_text("# Alpha\n\nvlan appears once in the body text\n", encoding="utf-8")
    head = tmp_path / "head.md"
    head.write_text("# Vlan Guide\n\nunrelated body content\n", encoding="utf-8")
    shelf.add_document(body, category="net", title="Body Only", split=False)
    shelf.add_document(head, category="net", title="Vlan Guide", split=False)

    hits = shelf.search("vlan")
    # The heading match ranks first even though both have one body/heading hit.
    assert hits[0]["relative_path"].endswith("vlan-guide.md")
    assert hits[0]["score"] > hits[1]["score"]


def test_search_prefers_sections_over_split_parent(tmp_path: Path):
    filler = "searchable lorem ipsum dolor sit amet consectetur. " * 700
    big = tmp_path / "big.md"
    big.write_text(
        "# Big\n\n## Alpha\n\n" + filler + "\n\n## Beta\n\n" + filler + "\n",
        encoding="utf-8",
    )
    shelf = Shelf(tmp_path / "s").init(name="S")
    result = shelf.add_document(big, category="docs", title="Big Doc", split=True)
    assert result.was_split

    paths = [h["relative_path"] for h in shelf.search("searchable")]
    assert "docs/docs/big-doc.md" not in paths  # whole-file parent skipped
    assert any("/big-doc/" in p for p in paths)  # sections present


def test_search_snippet_trims_and_collapses(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "d.md"
    doc.write_text(
        "# T\n\nleadingword     NEEDLEZONE     trailingword plus more text after it\n",
        encoding="utf-8",
    )
    shelf.add_document(doc, category="docs", title="D", split=False)
    snip = shelf.search("needlezone")[0]["snippet"]
    assert "  " not in snip  # runs of whitespace collapsed
    assert "NEEDLEZONE" in snip


def test_search_caches_corpus_between_calls(tmp_path: Path, monkeypatch):
    # A repeat search must not re-read unchanged files from disk.
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)

    calls = {"n": 0}
    orig = Path.read_text

    def counting(self, *args, **kwargs):
        if self.suffix == ".md" and "docs" in self.parts:
            calls["n"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)

    shelf.search("BGP")
    first = calls["n"]
    assert first >= 1  # first search reads from disk
    shelf.search("BGP")
    assert calls["n"] == first  # second search is served entirely from cache


def test_search_cache_invalidates_when_file_changes(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "d.md"
    doc.write_text("# D\n\nalpha keyword body\n", encoding="utf-8")
    shelf.add_document(doc, category="c", title="D", split=False)
    assert shelf.search("alpha")

    # Edit the file directly (size changes) — the cache must refresh.
    (shelf.root / "docs" / "c" / "d.md").write_text(
        "# D\n\nbeta replacement content here now\n", encoding="utf-8"
    )
    assert shelf.search("alpha") == []  # stale cached text is not served
    assert shelf.search("beta")  # new content is searchable


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


def test_read_document_returns_content(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)

    res = shelf.read_document("docs/docs/sample.md")
    assert res.relative_path == "docs/docs/sample.md"
    assert "BGP" in res.content
    assert res.size_bytes == len((shelf.root / "docs/docs/sample.md").read_bytes())
    assert res.truncated is False


def test_read_document_truncation_and_offset(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "big.md"
    doc.write_text("# T\n\n" + ("x" * 5000), encoding="utf-8")
    shelf.add_document(doc, category="docs", title="Big One", split=False)
    rel = "docs/docs/big-one.md"

    head = shelf.read_document(rel, max_bytes=100)
    assert len(head.content.encode("utf-8")) == 100
    assert head.truncated is True

    # Paging with an offset reads the tail without truncation.
    total = head.size_bytes
    tail = shelf.read_document(rel, max_bytes=total, offset=total - 10)
    assert tail.truncated is False
    assert len(tail.content) == 10


def test_read_document_truncation_snaps_utf8_boundary(tmp_path: Path):
    # A cut in the middle of a multibyte character must not yield replacement
    # chars: the slice snaps back to a character boundary.
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "u.md"
    doc.write_text("# T\n\n" + "€" * 100, encoding="utf-8")  # € is 3 bytes
    shelf.add_document(doc, category="c", title="Uni", split=False)

    # max_bytes=7 lands mid-'€' (5 header bytes + 2 of a 3-byte char).
    res = shelf.read_document("docs/c/uni.md", max_bytes=7)
    assert "�" not in res.content  # no replacement character
    assert res.truncated is True
    assert res.next_offset <= 7  # trimmed back to the boundary


def test_read_document_paging_with_next_offset_is_lossless(tmp_path: Path):
    # Paging a multibyte file by next_offset reconstructs it exactly, with no
    # dropped/duplicated characters and no replacement chars.
    shelf = Shelf(tmp_path / "s").init(name="S")
    body = "Привет мир — €—中文 " * 40  # mixed 2/3-byte characters
    doc = tmp_path / "cyr.md"
    doc.write_text("# T\n\n" + body, encoding="utf-8")
    shelf.add_document(doc, category="c", title="Cyr", split=False)
    # Ground-truth from the raw on-disk bytes (read_document returns raw bytes;
    # read_text would normalize newlines and mismatch on Windows).
    full = (shelf.root / "docs" / "c" / "cyr.md").read_bytes().decode("utf-8")

    pieces, offset, guard = [], 0, 0
    while True:
        guard += 1
        assert guard < 10_000, "pager made no progress"
        page = shelf.read_document("docs/c/cyr.md", max_bytes=8, offset=offset)
        assert "�" not in page.content
        pieces.append(page.content)
        if not page.truncated:
            break
        assert page.next_offset > offset  # always advances
        offset = page.next_offset
    assert "".join(pieces) == full


def test_read_document_max_bytes_smaller_than_char_still_progresses(tmp_path: Path):
    # max_bytes below one character returns that whole character (over budget)
    # rather than an empty page, so a pager can't stall.
    shelf = Shelf(tmp_path / "s").init(name="S")
    doc = tmp_path / "one.md"
    doc.write_text("€ and more text here", encoding="utf-8")
    shelf.add_document(doc, category="c", title="One", split=False)
    # Offset 0 is a heading ('# One' is prepended); jump to the '€' by its byte
    # offset in the actual on-disk file (newline width is platform-dependent).
    raw = (shelf.root / "docs" / "c" / "one.md").read_bytes()
    euro_byte = raw.index("€".encode())
    page = shelf.read_document("docs/c/one.md", max_bytes=1, offset=euro_byte)
    assert page.content.startswith("€")
    assert page.next_offset == euro_byte + 3  # advanced a full 3-byte char


def test_read_document_rejects_traversal(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    # A secret outside docs/ must be unreadable.
    (shelf.root / "secret.txt").write_text("top secret", encoding="utf-8")

    with pytest.raises(ValueError):
        shelf.read_document("docs/../secret.txt")
    with pytest.raises(ValueError):
        shelf.read_document("../../etc/passwd")
    with pytest.raises(ValueError):
        shelf.read_document("INDEX.md")  # at root, not under docs/


def test_read_document_missing_raises(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    with pytest.raises(FileNotFoundError):
        shelf.read_document("docs/docs/absent.md")


def test_read_document_works_without_remote(tmp_path: Path):
    # The whole point: private/local shelves with no remote still serve content.
    shelf = Shelf(tmp_path / "s").init(name="Local")  # no remote
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    res = shelf.read_document("docs/docs/sample.md")
    assert "BGP" in res.content


def test_remove_split_document_leaves_no_debris(tmp_path: Path):
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    big_md.write_text(
        "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5)),
        encoding="utf-8",
    )
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(big_md, category="big", title="Big Document", split=True)
    shelf.add_document(FIXTURE, category="big", title="Keeper", split=False)

    result = shelf.remove_document(category="big", document="Big Document")
    assert not result.dry_run and result.was_split

    cat_dir = shelf.root / "docs" / "big"
    assert not (cat_dir / "big-document.md").exists()
    assert not (cat_dir / "big-document").exists()  # split dir incl. SUBINDEX
    meta = json.loads((cat_dir / ".meta.json").read_text(encoding="utf-8"))
    assert "big-document.md" not in meta and "keeper.md" in meta
    idx = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    assert "Big Document" not in idx and "Keeper" in idx


def test_remove_document_title_case_prunes_meta(tmp_path: Path):
    # Regression: a title that differs from its slug only by case ("Doomed" ->
    # doomed.md) must resolve to the canonical on-disk path so the .meta.json
    # entry is pruned. On a case-insensitive filesystem (macOS/Windows) the old
    # resolver returned "Doomed.md", which never matched the "doomed.md" key.
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Doomed", split=False)
    meta_path = shelf.root / "docs" / "docs" / ".meta.json"
    assert "doomed.md" in json.loads(meta_path.read_text(encoding="utf-8"))

    result = shelf.remove_document(category="docs", document="Doomed")
    assert result.removed_paths[0].name == "doomed.md"  # canonical, not "Doomed.md"
    # It was the only doc, so the emptied meta file is removed entirely.
    assert not meta_path.exists()


def test_remove_document_dry_run_touches_nothing(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Stay", split=False)

    result = shelf.remove_document(category="docs", document="stay.md", dry_run=True)
    assert result.dry_run
    assert [p.name for p in result.removed_paths] == ["stay.md"]
    assert (shelf.root / "docs" / "docs" / "stay.md").is_file()
    assert "Stay" in (shelf.root / "INDEX.md").read_text(encoding="utf-8")


def test_remove_document_missing_raises(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Present", split=False)

    with pytest.raises(FileNotFoundError):
        shelf.remove_document(category="docs", document="absent")
    with pytest.raises(FileNotFoundError):
        shelf.remove_document(category="nope", document="present")
    # Path traversal in the document name never escapes the category dir.
    with pytest.raises(FileNotFoundError):
        shelf.remove_document(category="docs", document="../../INDEX.md")


def test_rename_document_retitles_and_moves_meta(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    shelf.add_document(FIXTURE, category="docs", title="Old Title", split=False)

    result = shelf.rename_document(category="docs", document="Old Title", new_title="New Title")
    assert result.moved is True
    cat = shelf.root / "docs" / "docs"
    assert not (cat / "old-title.md").exists()
    assert (cat / "new-title.md").is_file()
    meta = json.loads((cat / ".meta.json").read_text())
    assert "old-title.md" not in meta
    assert meta["new-title.md"]["title"] == "New Title"
    idx = (shelf.root / "INDEX.md").read_text()
    assert "New Title" in idx and "**Old Title**" not in idx


def test_rename_document_moves_category_with_split(tmp_path: Path):
    big = tmp_path / "big.md"
    body = "Lorem ipsum dolor sit amet. " * 500
    big.write_text(
        "# T\n\n" + "\n\n".join(f"## S{i}\n\n{body}" for i in range(4)), encoding="utf-8"
    )
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(big, category="misc", title="Manual", split=True)

    result = shelf.rename_document(category="misc", document="Manual", new_category="routers")
    assert result.moved and result.was_split
    old_cat = shelf.root / "docs" / "misc"
    new_cat = shelf.root / "docs" / "routers"
    assert not (old_cat / "manual.md").exists()
    assert not (old_cat / "manual").exists()  # split dir moved too
    assert (new_cat / "manual.md").is_file()
    assert (new_cat / "manual" / "SUBINDEX.md").is_file()  # regenerated
    # The old category's meta no longer references the moved doc (here it was
    # the only entry, so the meta file is removed entirely).
    old_meta = old_cat / ".meta.json"
    assert not old_meta.exists() or "manual.md" not in json.loads(old_meta.read_text())
    assert "manual.md" in json.loads((new_cat / ".meta.json").read_text())


def test_rename_document_description_only_is_in_place(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Doc", description="old", split=False)
    result = shelf.rename_document(
        category="docs", document="Doc", new_description="a much better description"
    )
    assert result.moved is False  # same slug, no file move
    meta = json.loads((shelf.root / "docs" / "docs" / ".meta.json").read_text())
    assert meta["doc.md"]["description"] == "a much better description"
    assert meta["doc.md"]["title"] == "Doc"


def test_rename_document_refuses_target_collision(tmp_path: Path):
    from docshelf_mcp.core.shelf import DocumentExistsError

    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Alpha", split=False)
    shelf.add_document(FIXTURE, category="docs", title="Beta", split=False)
    with pytest.raises(DocumentExistsError):
        shelf.rename_document(category="docs", document="Alpha", new_title="Beta")
    # Both still present.
    assert (shelf.root / "docs" / "docs" / "alpha.md").is_file()
    assert (shelf.root / "docs" / "docs" / "beta.md").is_file()


def test_rename_document_dry_run_touches_nothing(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Stay", split=False)
    result = shelf.rename_document(
        category="docs", document="Stay", new_title="Renamed", dry_run=True
    )
    assert result.dry_run and result.moved
    assert result.new_path == "docs/docs/renamed.md"
    assert (shelf.root / "docs" / "docs" / "stay.md").is_file()
    assert not (shelf.root / "docs" / "docs" / "renamed.md").exists()


def test_rename_document_requires_a_change(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Doc", split=False)
    with pytest.raises(ValueError):
        shelf.rename_document(category="docs", document="Doc")


def test_rename_document_missing_raises(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    with pytest.raises(FileNotFoundError):
        shelf.rename_document(category="docs", document="ghost", new_title="X")


def test_doctor_clean_shelf_has_no_findings(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    assert shelf.doctor() == []


def test_doctor_detects_and_fixes_stale_meta_and_orphan(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Keeper", split=False)
    cat = shelf.root / "docs" / "docs"

    # Inject drift: a stale meta entry + an orphaned split dir.
    meta = json.loads((cat / ".meta.json").read_text())
    meta["ghost.md"] = {"title": "Ghost", "description": ""}
    (cat / ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (cat / "orphan").mkdir()
    (cat / "orphan" / "001-x.md").write_text("## x\n", encoding="utf-8")

    report = shelf.doctor()
    rules = {f.rule for f in report}
    assert "stale-meta-entry" in rules and "orphaned-split-dir" in rules
    assert all(not f.fixed for f in report)  # read-only by default

    fixed = shelf.doctor(fix=True)
    assert any(f.rule == "stale-meta-entry" and f.fixed for f in fixed)
    assert any(f.rule == "orphaned-split-dir" and f.fixed for f in fixed)
    # Debris is gone; a re-run is clean of those two rules.
    assert not (cat / "orphan").exists()
    assert "ghost.md" not in json.loads((cat / ".meta.json").read_text())
    after = {f.rule for f in shelf.doctor()}
    assert "stale-meta-entry" not in after and "orphaned-split-dir" not in after


def test_doctor_detects_stale_index(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="One", split=False)
    # Corrupt INDEX.md so it no longer matches the shelf.
    (shelf.root / "INDEX.md").write_text("# stale\n", encoding="utf-8")

    assert any(f.rule == "stale-index" for f in shelf.doctor())
    shelf.doctor(fix=True)
    assert not any(f.rule == "stale-index" for f in shelf.doctor())


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # Identity via -c so the test never depends on the host's git config and
    # never writes to it.
    return subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=docshelf test",
            "-c",
            "user.email=test@docshelf.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _split_shelf_with_uncommitted_sections(tmp_path: Path) -> tuple[Shelf, Path]:
    """A git shelf whose split directory was never committed, INDEX from the bot.

    This is the shape #97 was filed about: the caller commits the document path
    alone (memshelf's ``shelve`` does exactly that), and ``INDEX.md`` is
    rendered on ``main`` from the *committed* tree — so the file on disk and a
    render of the working tree are two structurally different trees.
    """
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    big_md.write_text(
        "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5)),
        encoding="utf-8",
    )

    shelf = Shelf(tmp_path / "s").init(name="S")
    _git(shelf.root, "init", "-q", "-b", "main")
    _git(shelf.root, "add", "-A")
    _git(shelf.root, "commit", "-qm", "shelf")

    added = shelf.add_document(big_md, category="big", title="Doc", split=True)
    assert added.was_split
    split_dir = added.document_path.parent / added.document_path.stem
    assert split_dir.is_dir()

    # The caller commits the document alone — the sections stay untracked.
    _git(shelf.root, "add", "--", str(added.document_path.relative_to(shelf.root)))
    _git(shelf.root, "commit", "-qm", "doc")

    # INDEX.md as the bot renders it: from a checkout that has no sections.
    clone = tmp_path / "bot"
    subprocess.run(
        ["git", "clone", "-q", str(shelf.root), str(clone)], check=True, capture_output=True
    )
    Shelf(clone).rebuild_index()
    (shelf.root / "INDEX.md").write_text(
        (clone / "INDEX.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return shelf, split_dir


def test_doctor_names_uncommitted_split_dirs_instead_of_prescribing_rebuild(
    tmp_path: Path,
):
    # #97: the two sides of the stale-index comparison are structurally
    # different trees here, so no rebuild can make them equal — and running the
    # prescribed one publishes INDEX links to paths no other checkout has.
    shelf, split_dir = _split_shelf_with_uncommitted_sections(tmp_path)
    rel = split_dir.relative_to(shelf.root).as_posix()

    report = shelf.doctor()
    rules = {f.rule for f in report}
    assert "uncommitted-split-dir" in rules
    assert rel in {f.path for f in report if f.rule == "uncommitted-split-dir"}
    # The permanent warning is gone: this is not a lagging index.
    assert "stale-index" not in rules
    # And nothing in the report sends the reader at rebuild_index.
    assert all("rebuild_index" not in f.suggested_fix for f in report)

    # Even with fix=True the index is left alone — the broken links are exactly
    # what the finding exists to prevent.
    before = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    shelf.doctor(fix=True)
    after = (shelf.root / "INDEX.md").read_text(encoding="utf-8")
    assert after == before
    assert rel not in after


def test_doctor_leaves_committed_split_dirs_alone(tmp_path: Path):
    # A shelf that committed its sections is coherent — every checkout has
    # them — so the finding must not fire, and a genuinely lagging index there
    # is still reported as stale-index with its usual fix.
    shelf, split_dir = _split_shelf_with_uncommitted_sections(tmp_path)
    _git(shelf.root, "add", "-A")
    _git(shelf.root, "commit", "-qm", "sections too")

    rules = {f.rule for f in shelf.doctor()}
    assert "uncommitted-split-dir" not in rules
    assert "stale-index" in rules  # INDEX still carries the bot's render
    assert any(
        f.rule == "stale-index" and f.suggested_fix == "run rebuild_index" for f in shelf.doctor()
    )


def test_doctor_names_uncommitted_sections_next_to_a_stray_file(tmp_path: Path):
    # The index reads the sections of a split holding a figure, so gitstate has
    # to as well (#118 review): otherwise the figure turns the #97 finding back
    # into a stale-index whose fix=True rebuild publishes links to sections no
    # other checkout has.
    shelf, split_dir = _split_shelf_with_uncommitted_sections(tmp_path)
    (split_dir / "figure.png").write_bytes(b"\x89PNG")
    rel = split_dir.relative_to(shelf.root).as_posix()

    rules = {(f.rule, f.path) for f in shelf.doctor()}

    assert ("uncommitted-split-dir", rel) in rules
    assert ("stale-index", "INDEX.md") not in rules


def test_doctor_detects_empty_category_and_duplicate_title(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["hollow"])
    shelf.add_document(FIXTURE, category="docs", title="Dup", split=False)
    # A second document whose title collides after slugify differences —
    # force the same display title via a distinct filename + meta override.
    cat = shelf.root / "docs" / "docs"
    (cat / "dup-two.md").write_text("# Dup\n\nbody\n", encoding="utf-8")
    meta = json.loads((cat / ".meta.json").read_text())
    meta["dup-two.md"] = {"title": "Dup", "description": ""}
    (cat / ".meta.json").write_text(json.dumps(meta), encoding="utf-8")

    rules = {f.rule for f in shelf.doctor()}
    assert "empty-category" in rules  # the pre-created 'hollow' category
    assert "duplicate-title" in rules


def test_shelf_without_remote_still_works(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="Local Shelf")  # no remote
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    text = (shelf.root / "INDEX.md").read_text()
    assert "Sample" in text
    # No raw URL in the entry (because remote is empty).
    assert "raw.githubusercontent.com" not in text


def test_none_provider_offline_shelf_has_relative_links(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="Offline", provider="none")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    text = (shelf.root / "INDEX.md").read_text()
    # A navigable relative link, not a bare label.
    assert "(docs/docs/sample.md)" in text
    assert "raw.githubusercontent.com" not in text


def test_gitlab_provider_enriches_search_and_read(tmp_path: Path):
    from docshelf_mcp import tools as t

    shelf_path = str(tmp_path / "s")
    t.init_shelf(
        t.InitShelfInput(
            shelf_path=shelf_path,
            name="GL",
            github_remote="https://gitlab.com/grp/proj",
            provider="gitlab",
        )
    )
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE),
            category="docs",
            title="Sample",
            split=False,
            shelf_path=shelf_path,
        )
    )
    hit = t.search(t.SearchInput(query="BGP", shelf_path=shelf_path))["hits"][0]
    assert hit["raw_url"] == ("https://gitlab.com/grp/proj/-/raw/main/docs/docs/sample.md")


# -- issue #65: hand-edited .meta.json of any JSON shape must not crash ------


def _write_meta(shelf: Shelf, category: str, payload) -> Path:
    meta = shelf.root / "docs" / category / ".meta.json"
    meta.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return meta


def test_meta_bare_string_entry_scans_as_title_and_doctor_reports(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="guides", title="Foo", split=False)
    _write_meta(shelf, "guides", {"foo.md": "My hand-written title"})
    entries = shelf.scan()  # must not raise (was AttributeError)
    assert [e.title for e in entries] == ["My hand-written title"]
    shelf.rebuild_index()
    shelf.doctor(fix=True)  # doctor must run, not die
    findings = shelf.doctor()
    assert any(f.rule == "meta-shape" and f.severity == "error" for f in findings)


def test_meta_list_top_level_scans_and_doctor_reports(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="guides", title="Foo", split=False)
    _write_meta(shelf, "guides", ["not", "a", "dict"])
    entries = shelf.scan()
    assert entries and entries[0].title  # falls back to filename-derived title
    findings = shelf.doctor()
    assert any(f.rule == "meta-shape" and f.severity == "error" for f in findings)


def test_meta_non_string_title_scans_and_doctor_reports(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="guides", title="Foo", split=False)
    _write_meta(shelf, "guides", {"foo.md": {"title": 5, "description": "ok"}})
    entries = shelf.scan()
    assert entries[0].title  # non-string title dropped, fallback used
    assert entries[0].description == "ok"
    findings = shelf.doctor()
    assert any(f.rule == "meta-shape" for f in findings)


# -- issue #66: rename must not tear the shelf on a split-dir collision ------


def test_rename_refuses_when_split_target_dir_exists(tmp_path: Path):
    from docshelf_mcp.core.shelf import DocumentExistsError

    big = tmp_path / "big.md"
    body = "Lorem ipsum dolor sit amet. " * 500
    big.write_text(
        "# T\n\n" + "\n\n".join(f"## S{i}\n\n{body}" for i in range(4)), encoding="utf-8"
    )
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(big, category="guides", title="Old Title", split=True)
    cat = shelf.root / "docs" / "guides"
    orphan = cat / "new-title"
    orphan.mkdir()
    (orphan / "001-junk.md").write_text("junk\n", encoding="utf-8")

    with pytest.raises(DocumentExistsError):
        shelf.rename_document(category="guides", document="Old Title", new_title="New Title")
    # Disk untouched: parent doc, its sections and meta all still at old slug.
    assert (cat / "old-title.md").is_file()
    assert (cat / "old-title").is_dir()
    assert not (cat / "new-title.md").exists()
    assert "old-title.md" in json.loads((cat / ".meta.json").read_text())


# -- issue #67: provider config that can't render URLs fails fast ------------


def test_init_rejects_unknown_provider(tmp_path: Path):
    with pytest.raises(ValueError, match="giltab"):
        Shelf(tmp_path / "s").init(name="S", provider="giltab")


def test_init_rejects_custom_without_template(tmp_path: Path):
    with pytest.raises(ValueError, match="url_template"):
        Shelf(tmp_path / "s").init(name="S", provider="custom")


def test_init_accepts_custom_with_template(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(
        name="S", provider="custom", url_template="https://cdn.example/{path}"
    )
    assert shelf.config.provider == "custom"


def test_doctor_flags_hand_edited_provider_config(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="S")
    cfg_path = shelf.root / SHELF_METADATA_FILENAME
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    cfg["provider"] = "giltab"  # typo'd by hand
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    findings = Shelf(shelf.root).doctor()
    assert any(f.rule == "unknown-provider" and f.severity == "error" for f in findings)

    cfg["provider"] = "custom"
    cfg["url_template"] = ""
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    findings = Shelf(shelf.root).doctor()
    assert any(f.rule == "custom-without-template" and f.severity == "error" for f in findings)


def test_readd_splittable_content_with_split_false_keeps_split(tmp_path: Path):
    # #47: re-adding still-splittable content with split=False must NOT wipe an
    # existing valid split. The cleanup is gated on the content no longer
    # qualifying, not on the split argument alone.
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    text = "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5))
    big_md.write_text(text, encoding="utf-8")

    shelf = Shelf(tmp_path / "s").init(name="S")
    first = shelf.add_document(big_md, category="big", title="Doc", split=True)
    assert first.was_split
    split_dir = first.document_path.parent / first.document_path.stem
    assert split_dir.is_dir()

    # Re-add identical (still-splittable) content, this time with split=False.
    second = shelf.add_document(big_md, category="big", title="Doc", split=False, overwrite=True)
    assert not second.unsplit  # nothing was destroyed
    assert split_dir.is_dir()  # the valid split survives
    assert list(split_dir.glob("*.md"))


def test_readd_small_content_with_split_false_wipes_stale_split(tmp_path: Path):
    # #47: when the new content genuinely no longer qualifies for splitting, the
    # stale section files are removed and the destruction is surfaced.
    big_md = tmp_path / "big.md"
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    text = "# Title\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5))
    big_md.write_text(text, encoding="utf-8")

    shelf = Shelf(tmp_path / "s").init(name="S")
    first = shelf.add_document(big_md, category="big", title="Doc", split=True)
    split_dir = first.document_path.parent / first.document_path.stem
    assert split_dir.is_dir()

    small = tmp_path / "small.md"
    small.write_text("# Title\n\ntiny body\n", encoding="utf-8")
    second = shelf.add_document(small, category="big", title="Doc", split=False, overwrite=True)
    assert second.unsplit  # the stale split was wiped, and it's signaled
    assert not split_dir.exists()


def test_doctor_flags_colliding_category_dirs(tmp_path: Path):
    # #49: two literal category directories that slugify to the same slug are
    # invisible to the per-category rules but flagged by colliding-category-dirs.
    shelf = Shelf(tmp_path / "s").init(name="S")
    docs = shelf.root / "docs"
    (docs / "Research Papers").mkdir(parents=True)
    (docs / "research-papers").mkdir(parents=True)
    (docs / "Research Papers" / "a.md").write_text("# A\n\nbody\n", encoding="utf-8")
    (docs / "research-papers" / "b.md").write_text("# B\n\nbody\n", encoding="utf-8")

    findings = shelf.doctor()
    colliding = [f for f in findings if f.rule == "colliding-category-dirs"]
    assert len(colliding) == 1
    assert "research-papers" in colliding[0].detail
    # A shelf with distinct slugs raises no such finding.
    shelf2 = Shelf(tmp_path / "s2").init(name="S2")
    shelf2.add_document(FIXTURE, category="papers", title="P", split=False)
    assert not [f for f in shelf2.doctor() if f.rule == "colliding-category-dirs"]


# -- issue #63: recognize shelf.yml as the shelf-spec v0 contract ------------


def test_init_default_writes_no_manifest(tmp_path: Path):
    # Non-breaking: the default init produces exactly today's layout — no
    # shelf.yml unless it is explicitly requested.
    shelf = Shelf(tmp_path / "s").init(name="S")
    assert not (shelf.root / SHELF_MANIFEST_FILENAME).exists()


def test_init_manifest_scaffolds_valid_shelf_yml(tmp_path: Path):
    # Opt-in: a spec-shaped, implicit-category manifest whose name mirrors the
    # config. A unicode name is preserved verbatim (not \uXXXX-escaped) so the
    # memshelf use case reads cleanly.
    shelf = Shelf(tmp_path / "s").init(
        name="Мои документы", default_categories=["alpha"], manifest=True
    )
    manifest_path = shelf.root / SHELF_MANIFEST_FILENAME
    assert manifest_path.is_file()
    raw = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    assert data["spec_version"] == "0.1"  # the two REQUIRED spec fields
    assert data["mode"] == "single"
    assert isinstance(data["spec_version"], str)  # string, not a 0.1 float
    assert data["profile"] == "document"
    assert data["docs_root"] == "docs"
    assert data["index"] == {"path": "INDEX.md", "generated_by": "docshelf-mcp"}
    assert data["name"] == "Мои документы"
    assert "\\u" not in raw  # allow_unicode kept the Cyrillic literal
    # Categories stay implicit so on-the-fly category creation can't rot it.
    assert "categories" not in data


def test_init_manifest_is_idempotent_and_preserves_edits(tmp_path: Path):
    # Re-running init must never clobber a hand-edited manifest.
    path = tmp_path / "s"
    Shelf(path).init(name="S", manifest=True)
    manifest_path = path / SHELF_MANIFEST_FILENAME
    manifest_path.write_text(
        'spec_version: "0.1"\nmode: single\nname: Custom\nprofile: memory\n',
        encoding="utf-8",
    )
    Shelf(path).init(name="S", manifest=True)  # second init, still opt-in
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert data["profile"] == "memory"  # not reset to "document"
    assert data["name"] == "Custom"


def test_scaffolded_manifest_raises_no_config_conflict(tmp_path: Path):
    # A freshly-scaffolded manifest agrees with .docshelf.json by construction,
    # so doctor must not flag docshelf-config-conflict.
    shelf = Shelf(tmp_path / "s").init(name="S", remote="https://github.com/me/r", manifest=True)
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    assert not any(f.rule == "docshelf-config-conflict" for f in shelf.doctor())


def test_doctor_ignores_absent_manifest(tmp_path: Path):
    # The manifest requirement is openshelf's, not docshelf's: a shelf without
    # a shelf.yml is never flagged for the conflict rule.
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)
    assert not any(f.rule == "docshelf-config-conflict" for f in shelf.doctor())


def test_doctor_flags_manifest_name_conflict(tmp_path: Path):
    shelf = Shelf(tmp_path / "s").init(name="Real Name", manifest=True)
    # Drift .docshelf.json's name away from the manifest (the contract).
    cfg_path = shelf.root / SHELF_METADATA_FILENAME
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["name"] = "Renamed By Hand"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    findings = Shelf(shelf.root).doctor()
    conflict = [f for f in findings if f.rule == "docshelf-config-conflict"]
    assert len(conflict) == 1
    assert conflict[0].severity == "warning"
    assert conflict[0].path == SHELF_METADATA_FILENAME
    assert "Real Name" in conflict[0].detail
    assert "Renamed By Hand" in conflict[0].detail


def test_doctor_flags_manifest_category_conflict(tmp_path: Path):
    # .docshelf.json's category_order lists a category the manifest does not
    # declare → the manifest's explicit list is the contract, so it's drift.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["alpha", "beta"])
    (shelf.root / SHELF_MANIFEST_FILENAME).write_text(
        'spec_version: "0.1"\nmode: single\nname: S\ncategories:\n  - alpha\n',
        encoding="utf-8",
    )
    findings = Shelf(shelf.root).doctor()
    conflict = [f for f in findings if f.rule == "docshelf-config-conflict"]
    assert len(conflict) == 1
    assert "category_order lists undeclared categories" in conflict[0].detail
    assert "beta" in conflict[0].detail


def test_doctor_no_conflict_when_manifest_omits_categories(tmp_path: Path):
    # An implicit-category manifest (no `categories`) never conflicts on
    # category_order, however many categories the config carries.
    shelf = Shelf(tmp_path / "s").init(
        name="S", default_categories=["alpha", "beta"], manifest=True
    )
    assert not any(f.rule == "docshelf-config-conflict" for f in shelf.doctor())


def test_doctor_tolerates_malformed_manifest(tmp_path: Path):
    # Schema-validating shelf.yml is openshelf's job; docshelf's doctor must
    # not crash on a non-mapping or unparseable manifest — it just has nothing
    # to reconcile.
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(FIXTURE, category="docs", title="Sample", split=False)

    (shelf.root / SHELF_MANIFEST_FILENAME).write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    assert not any(f.rule == "docshelf-config-conflict" for f in Shelf(shelf.root).doctor())

    (shelf.root / SHELF_MANIFEST_FILENAME).write_text(
        "spec_version: '0.1'\n  mode: [unbalanced\n", encoding="utf-8"
    )
    assert not any(f.rule == "docshelf-config-conflict" for f in Shelf(shelf.root).doctor())


def test_init_shelf_tool_scaffolds_manifest_and_reports_it(tmp_path: Path):
    from docshelf_mcp import tools as t

    shelf_path = str(tmp_path / "s")
    out = t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="Docs", manifest=True))
    assert out["manifest"] is True
    assert (tmp_path / "s" / SHELF_MANIFEST_FILENAME).is_file()

    # Drift the impl config's name, then the doctor tool surfaces the conflict.
    cfg_path = tmp_path / "s" / SHELF_METADATA_FILENAME
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["name"] = "Renamed"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    report = t.doctor(t.DoctorInput(shelf_path=shelf_path))
    assert report["by_rule"].get("docshelf-config-conflict") == 1


def test_init_shelf_tool_default_writes_no_manifest(tmp_path: Path):
    from docshelf_mcp import tools as t

    shelf_path = str(tmp_path / "s")
    out = t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="Docs"))
    assert out["manifest"] is False
    assert not (tmp_path / "s" / SHELF_MANIFEST_FILENAME).exists()


# -- foreign same-stem directories are never deleted as if they were splits --


def _big_markdown(path: Path, title: str = "Title") -> Path:
    chapter_body = "Lorem ipsum dolor sit amet. " * 500
    path.write_text(
        f"# {title}\n\n" + "\n\n".join(f"## Section {i}\n\n{chapter_body}" for i in range(5)),
        encoding="utf-8",
    )
    return path


def _asset_dir(category_dir: Path, name: str = "images") -> Path:
    """A same-stem directory docshelf did not write: a document's image assets."""
    d = category_dir / name
    d.mkdir(parents=True)
    (d / "diagram.png").write_bytes(b"\x89PNG fake")
    return d


def _refusal(call) -> BaseException | None:
    """Run ``call``; return the FileExistsError it raised, or None if it returned.

    Callers assert on the disk *before* the exception: the code before the
    guard returned normally — after deleting the directory — so the survival
    assertion is the one that has to go red there.
    """
    try:
        call()
    except FileExistsError as exc:
        return exc
    return None


@pytest.mark.parametrize("overwrite", [False, True])
def test_add_document_unsplit_refuses_foreign_same_stem_dir(tmp_path: Path, overwrite: bool):
    # A small document titled like an asset directory took the "no longer
    # splittable, wipe the stale split" branch and rmtree'd the user's
    # images/. overwrite=True replaces a document; it never deletes a directory.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    cat = shelf.root / "docs" / "guides"
    images = _asset_dir(cat)
    src = tmp_path / "images-src.md"
    src.write_text("# Images\n\nHow we store images.\n", encoding="utf-8")

    err = _refusal(
        lambda: shelf.add_document(src, category="guides", title="images", overwrite=overwrite)
    )

    assert (images / "diagram.png").is_file()
    assert type(err).__name__ == "SplitDirConflictError"
    assert "docs/guides/images" in str(err)
    # Refused before anything was written: no half-added document.
    assert not (cat / "images.md").exists()
    assert not (cat / ".meta.json").exists()


def test_add_document_split_refuses_foreign_same_stem_dir(tmp_path: Path, monkeypatch):
    # Same trap on the split branch: write_split_files' idempotent rewrite
    # deleted the directory first. The refusal comes before conversion, so the
    # parent .md is not left behind without its sections.
    from docshelf_mcp.core import shelf as shelf_mod

    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    cat = shelf.root / "docs" / "guides"
    images = _asset_dir(cat)
    big = _big_markdown(tmp_path / "big.md", "Images")
    converted: list[Path] = []
    real = shelf_mod.source_to_markdown
    monkeypatch.setattr(
        shelf_mod,
        "source_to_markdown",
        lambda source, **kw: (converted.append(source), real(source, **kw))[1],
    )

    err = _refusal(lambda: shelf.add_document(big, category="guides", title="images"))

    assert sorted(p.name for p in images.iterdir()) == ["diagram.png"]
    assert type(err).__name__ == "SplitDirConflictError"
    assert not (cat / "images.md").exists()
    assert converted == []


def test_add_document_split_refuses_a_regular_file_at_the_split_path(tmp_path: Path):
    # A plain file named like the split directory blocks the split as well.
    # The pre-flight must catch it too (exists, not is_dir): otherwise the
    # refusal only comes from write_split_files, after images.md is written.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    cat = shelf.root / "docs" / "guides"
    (cat / "images").write_text("a file, not a folder\n", encoding="utf-8")
    big = _big_markdown(tmp_path / "big.md", "Images")

    err = _refusal(lambda: shelf.add_document(big, category="guides", title="images"))

    assert (cat / "images").read_text(encoding="utf-8") == "a file, not a folder\n"
    assert type(err).__name__ == "SplitDirConflictError"
    assert not (cat / "images.md").exists()


def test_add_document_resplits_over_its_own_split_dir(tmp_path: Path):
    # The guard must not refuse docshelf's own output: a split carrying its
    # SUBINDEX.md and OS litter is re-split in place, as before.
    shelf = Shelf(tmp_path / "s").init(name="S")
    big = _big_markdown(tmp_path / "big.md")
    first = shelf.add_document(big, category="big", title="Doc")
    split_dir = first.document_path.parent / first.document_path.stem
    (split_dir / "SUBINDEX.md").write_text("# nav\n", encoding="utf-8")
    (split_dir / ".DS_Store").write_bytes(b"\0")

    second = shelf.add_document(big, category="big", title="Doc")
    assert second.was_split and second.overwritten
    assert [p.name for p in second.section_paths] == [p.name for p in first.section_paths]


def test_remove_document_leaves_foreign_same_stem_dir(tmp_path: Path):
    # remove_document took any same-stem directory for the document's
    # sections. An images/ created next to images.md after the add is not the
    # document's: it stays, and neither the removal nor its dry run lists it.
    shelf = Shelf(tmp_path / "s").init(name="S")
    src = tmp_path / "images-src.md"
    src.write_text("# Images\n\nHow we store images.\n", encoding="utf-8")
    shelf.add_document(src, category="guides", title="images")
    cat = shelf.root / "docs" / "guides"
    images = _asset_dir(cat)

    preview = shelf.remove_document(category="guides", document="images", dry_run=True)
    result = shelf.remove_document(category="guides", document="images")

    assert (images / "diagram.png").is_file()
    assert not (cat / "images.md").exists()
    assert result.removed_paths == [cat / "images.md"] and not result.was_split
    assert preview.removed_paths == result.removed_paths and not preview.was_split


def test_doctor_fix_reports_but_keeps_a_foreign_orphan_dir(tmp_path: Path):
    # doctor(fix=True) — "the safe subset" — deleted every directory without a
    # parent document, a document's referenced images/ included. The rule name
    # stays orphaned-split-dir (spec parity); only a split-shaped one is fixed.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    src = tmp_path / "guide-src.md"
    src.write_text("# Setup\n\n![diagram](images/diagram.png)\n\nBody.\n", encoding="utf-8")
    shelf.add_document(src, category="guides", title="setup")
    cat = shelf.root / "docs" / "guides"
    images = _asset_dir(cat)
    orphan = cat / "gone"
    orphan.mkdir()
    (orphan / "001-x.md").write_text("## x\n", encoding="utf-8")

    fixed = shelf.doctor(fix=True)

    assert (images / "diagram.png").is_file()
    assert not orphan.exists()  # a real orphaned split is still cleaned up
    by_path = {f.path: f for f in fixed if f.rule == "orphaned-split-dir"}
    assert by_path["docs/guides/gone"].fixed is True
    assert by_path["docs/guides/images"].fixed is False
    assert "not a docshelf split directory" in by_path["docs/guides/images"].detail
    # Left in place, not forgotten: the next run still names it.
    again = [(f.rule, f.path) for f in shelf.doctor()]
    assert ("orphaned-split-dir", "docs/guides/images") in again


def test_doctor_skips_directories_declared_in_extra_dirs(tmp_path: Path):
    # shelf-spec §2/§9.1: a sidecar declared in shelf.yml `extra_dirs` is
    # exempt from orphaned-split-dir (openshelf's validator skips it). doctor
    # never read the key: it reported the sidecar and fix=True deleted it.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"], manifest=True)
    manifest = shelf.root / SHELF_MANIFEST_FILENAME
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + "extra_dirs:\n  - docs/guides/originals/\n  - docs/attachments\n",
        encoding="utf-8",
    )
    shelf.add_document(FIXTURE, category="guides", title="setup", split=False)
    originals = shelf.root / "docs" / "guides" / "originals"
    originals.mkdir()
    (originals / "setup.pdf").write_bytes(b"%PDF-1.4 original")
    attachments = shelf.root / "docs" / "attachments"
    attachments.mkdir()
    (attachments / "scan.pdf").write_bytes(b"%PDF-1.4 scan")

    findings = shelf.doctor(fix=True)

    assert (originals / "setup.pdf").is_file()
    declared = {"docs/guides/originals", "docs/attachments"}
    assert [f for f in findings if f.path in declared] == []


def test_doctor_does_not_call_a_foreign_same_stem_dir_out_of_sync(tmp_path: Path):
    # split-out-of-sync compared any same-stem directory with a fresh split
    # and prescribed "re-add the document", which now (rightly) refuses.
    shelf = Shelf(tmp_path / "s").init(name="S")
    src = tmp_path / "images-src.md"
    src.write_text("# Images\n\nHow we store images.\n", encoding="utf-8")
    shelf.add_document(src, category="guides", title="images")
    _asset_dir(shelf.root / "docs" / "guides")

    rules = {(f.rule, f.path) for f in shelf.doctor()}
    assert ("split-out-of-sync", "docs/guides/images.md") not in rules


@pytest.mark.parametrize("stray", [None, "figure.png"])
def test_doctor_still_flags_a_real_split_out_of_sync(tmp_path: Path, stray: str | None):
    # A figure next to the sections leaves them the ones the index lists, so
    # they are still compared with a fresh split of the parent (#118 review).
    shelf = Shelf(tmp_path / "s").init(name="S")
    first = shelf.add_document(_big_markdown(tmp_path / "big.md"), category="big", title="Doc")
    first.section_paths[-1].unlink()
    if stray:
        (first.section_paths[0].parent / stray).write_bytes(b"\x89PNG")

    rules = {(f.rule, f.path) for f in shelf.doctor()}
    assert ("split-out-of-sync", "docs/big/doc.md") in rules


def _deny_listing(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Make ``directory`` unlistable, as chmod 000 does for an ordinary user.

    chmod proves nothing as root or on Windows, so the OS refusal is simulated
    at ``Path.iterdir`` — the call is_split_dir lists through.
    """
    real_iterdir = Path.iterdir

    def iterdir(self: Path):
        if self == directory:
            raise PermissionError(13, "Permission denied", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)


@pytest.mark.parametrize("fix", [False, True])
def test_doctor_reports_an_unreadable_dir_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fix: bool
):
    # Telling a split from someone else's directory means listing it. One the
    # process may not read (another user's folder, chmod 000) made the
    # read-only doctor() raise PermissionError — and memshelf's push gate calls
    # it directly — where it used to be reported. Unreadable proves nothing is
    # docshelf's: reported as orphaned-split-dir and left in place.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    shelf.add_document(FIXTURE, category="guides", title="setup", split=False)
    private = shelf.root / "docs" / "guides" / "private"
    private.mkdir()
    (private / "note.txt").write_text("mine\n", encoding="utf-8")
    _deny_listing(monkeypatch, private)

    findings = shelf.doctor(fix=fix)

    hits = [(f.rule, f.fixed) for f in findings if f.path == "docs/guides/private"]
    assert hits == [("orphaned-split-dir", False)]
    assert (private / "note.txt").is_file()


def test_add_document_refuses_an_unreadable_same_stem_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # The same unreadable directory under a document's stem: the clear refusal,
    # not a raw PermissionError, and nothing written.
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    cat = shelf.root / "docs" / "guides"
    private = cat / "private"
    private.mkdir()
    _deny_listing(monkeypatch, private)

    err = _refusal(
        lambda: shelf.add_document(FIXTURE, category="guides", title="private", split=False)
    )

    assert type(err).__name__ == "SplitDirConflictError"
    assert not (cat / "private.md").exists()


# -- #118: a foreign same-stem directory is not read as a split --------------


def _doc_with_foreign_stem_dir(tmp_path: Path, *, git: bool = False) -> tuple[Shelf, Path]:
    """``images.md``, a single-file document, and the user's own ``images/notes.md``.

    #118's reproduction: the directory was never docshelf's, it only shares
    the document's stem. With ``git``, everything but that directory is
    committed — it is untracked, as a folder dropped next to a document is.
    """
    shelf = Shelf(tmp_path / "s").init(name="S", remote="o/r")
    src = tmp_path / "images-src.md"
    src.write_text("# Images\n\nHow we store zebrafinch images.\n", encoding="utf-8")
    shelf.add_document(src, category="guides", title="images", split=False)
    if git:
        _git(shelf.root, "init", "-q", "-b", "main")
        _git(shelf.root, "add", "-A")
        _git(shelf.root, "commit", "-qm", "shelf")
    foreign = shelf.root / "docs" / "guides" / "images"
    foreign.mkdir()
    (foreign / "notes.md").write_text("my own notes\n", encoding="utf-8")
    return shelf, foreign


def test_scan_and_rebuild_ignore_a_foreign_same_stem_dir(tmp_path: Path):
    # The indexer took any same-stem directory for the document's sections:
    # the user's notes.md went into INDEX.md as a section of images.md, and
    # rebuild_index wrote a SUBINDEX.md into their directory.
    shelf, foreign = _doc_with_foreign_stem_dir(tmp_path)

    entry = next(e for e in shelf.scan() if e.relative_path == "docs/guides/images.md")
    shelf.rebuild_index()

    assert entry.section_paths == []
    assert sorted(p.name for p in foreign.iterdir()) == ["notes.md"]
    assert "notes.md" not in (shelf.root / "INDEX.md").read_text(encoding="utf-8")


def test_search_keeps_a_document_next_to_a_foreign_same_stem_dir(tmp_path: Path):
    # search skips a split parent in favour of its sections, and any same-stem
    # directory holding a .md passed for a split: the document's own text
    # dropped out of every search.
    shelf, _ = _doc_with_foreign_stem_dir(tmp_path)

    paths = [h["relative_path"] for h in shelf.search("zebrafinch")]

    assert paths == ["docs/guides/images.md"]


def test_doctor_does_not_take_a_foreign_dir_for_uncommitted_sections(tmp_path: Path):
    # gitstate read the untracked foreign directory as uncommitted sections.
    # Its advice — delete the directory and re-add with split=False — is wrong
    # for someone else's files, and the finding suppressed stale-index and the
    # fix=True rebuild of a genuinely stale INDEX.md.
    shelf, foreign = _doc_with_foreign_stem_dir(tmp_path, git=True)
    index = shelf.root / "INDEX.md"
    index.write_text("# stale\n", encoding="utf-8")

    rules = {(f.rule, f.path) for f in shelf.doctor()}
    shelf.doctor(fix=True)

    assert ("uncommitted-split-dir", "docs/guides/images") not in rules
    assert ("stale-index", "INDEX.md") in rules
    assert index.read_text(encoding="utf-8") != "# stale\n"
    assert sorted(p.name for p in foreign.iterdir()) == ["notes.md"]


_CONFLICT_CAUSE = {
    "foreign-dir": "holds diagram.png, which docshelf did not write",
    "split-with-a-stray-file": "holds notes.md, which docshelf did not write",
    "plain-file": "is not a directory",
}


@pytest.mark.parametrize("shape", sorted(_CONFLICT_CAUSE))
def test_doctor_announces_the_split_dir_conflict_a_re_add_refuses_on(tmp_path: Path, shape: str):
    # Every state add_document's pre-flight refuses on is reported first. A
    # split with one stray file was the silent case: it stopped being
    # split-shaped, split-out-of-sync skipped it, and the user learned of the
    # conflict only from the SplitDirConflictError.
    shelf = Shelf(tmp_path / "s").init(name="S")
    big = _big_markdown(tmp_path / "big.md", "Doc")
    cat = shelf.root / "docs" / "big"
    written: list[str] = []
    if shape == "split-with-a-stray-file":
        added = shelf.add_document(big, category="big", title="Doc")
        written = [p.relative_to(shelf.root).as_posix() for p in added.section_paths]
        assert len(written) == 6  # preamble + five H2 sections
        stray = cat / "doc" / "notes.md"
        stray.write_text("mine\n", encoding="utf-8")
    else:
        shelf.add_document(FIXTURE, category="big", title="Doc", split=False)
        if shape == "foreign-dir":
            stray = _asset_dir(cat, "doc") / "diagram.png"
        else:
            stray = cat / "doc"
            stray.write_text("a file, not a folder\n", encoding="utf-8")

    found = [f for f in shelf.doctor(fix=True) if f.rule == "split-dir-conflict"]

    assert [(f.path, f.severity, f.fixed) for f in found] == [("docs/big/doc", "warning", False)]
    assert stray.is_file()  # fix=True left it alone
    assert _CONFLICT_CAUSE[shape] in found[0].detail
    # The advice is to move it aside, never to delete someone's files — nor
    # to declare it: extra_dirs does not lift the refusal (#118 review).
    assert "move it aside" in found[0].suggested_fix
    assert "extra_dirs" not in found[0].suggested_fix
    assert not re.search(r"\b(delete|remove|rm)\b", found[0].suggested_fix)
    # Only NNN-*.md files are read as sections: the stray notes.md never, and
    # a split's own sections still — a stray file hides none of them.
    assert [e.section_paths for e in shelf.scan()] == [written]
    # And the refusal the finding announces is real, naming the same cause.
    err = _refusal(lambda: shelf.add_document(big, category="big", title="Doc", overwrite=True))
    assert type(err).__name__ == "SplitDirConflictError"
    assert _CONFLICT_CAUSE[shape] in str(err)


def test_doctor_does_not_flag_a_split_docshelf_wrote(tmp_path: Path):
    # The rule must not fire on docshelf's own output: sections, SUBINDEX.md
    # and OS litter are a split, not a conflict.
    shelf = Shelf(tmp_path / "s").init(name="S")
    first = shelf.add_document(_big_markdown(tmp_path / "big.md"), category="big", title="Doc")
    split_dir = first.document_path.parent / first.document_path.stem
    assert (split_dir / "SUBINDEX.md").is_file()
    (split_dir / ".DS_Store").write_bytes(b"\0")

    assert not [f for f in shelf.doctor() if f.rule == "split-dir-conflict"]


def _declare_extra_dirs(shelf: Shelf, *dirs: str) -> None:
    manifest = shelf.root / SHELF_MANIFEST_FILENAME
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + "extra_dirs:\n"
        + "".join(f'  - "{d}"\n' for d in dirs),
        encoding="utf-8",
    )


def test_doctor_still_reports_a_declared_dir_at_a_split_path(tmp_path: Path):
    # extra_dirs exempts a sidecar from the category and orphan rules, but the
    # re-add pre-flight never read it: a declared folder at a document's split
    # path still makes the re-add refuse. doctor skipped it, so declaring it
    # silenced the finding and kept the refusal (#118 review).
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"], manifest=True)
    _declare_extra_dirs(shelf, "docs/guides/images/")
    shelf.add_document(FIXTURE, category="guides", title="images", split=False)
    _asset_dir(shelf.root / "docs" / "guides")

    found = [(f.rule, f.path) for f in shelf.doctor() if f.path == "docs/guides/images"]
    err = _refusal(
        lambda: shelf.add_document(
            FIXTURE, category="guides", title="images", split=False, overwrite=True
        )
    )

    assert found == [("split-dir-conflict", "docs/guides/images")]
    assert type(err).__name__ == "SplitDirConflictError"


def test_a_figure_dropped_into_a_split_hides_none_of_its_sections(tmp_path: Path):
    # Reading a split only when it held nothing else dropped every section of
    # one someone put figure.png into: INDEX.md lost the links at the next,
    # unrelated add. Only NNN-*.md files are sections, whatever else is there;
    # the folder is still not docshelf's to rewrite, which doctor names.
    shelf = Shelf(tmp_path / "s").init(name="S")
    added = shelf.add_document(_big_markdown(tmp_path / "big.md"), category="big", title="Doc")
    split_dir = added.document_path.parent / added.document_path.stem
    links = [p.relative_to(shelf.root).as_posix() for p in added.section_paths]
    index = shelf.root / "INDEX.md"
    before = index.read_text(encoding="utf-8")
    (split_dir / "figure.png").write_bytes(b"\x89PNG")

    shelf.add_document(FIXTURE, category="notes", title="Other", split=False)
    after = index.read_text(encoding="utf-8")
    findings = {(f.rule, f.path) for f in shelf.doctor()}

    assert len(links) == 6  # preamble + five H2 sections
    assert [link for link in links if link in before] == links
    assert [link for link in links if link in after] == links
    assert ("split-dir-conflict", "docs/big/doc") in findings
    assert ("stale-index", "INDEX.md") not in findings
    assert (split_dir / "figure.png").is_file()


def test_a_split_reached_through_a_symlink_is_not_read(tmp_path: Path):
    # A split moved elsewhere and linked back was read through the link. A
    # symlinked split is not a split: no sections, nothing written through it,
    # the parent searchable again, and the finding says "symlink".
    shelf = Shelf(tmp_path / "s").init(name="S")
    added = shelf.add_document(_big_markdown(tmp_path / "big.md"), category="big", title="Doc")
    split_dir = added.document_path.parent / added.document_path.stem
    moved = tmp_path / "elsewhere"
    shutil.move(str(split_dir), str(moved))
    try:
        split_dir.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available on this filesystem/account")
    (moved / "SUBINDEX.md").unlink()

    entry = next(e for e in shelf.scan() if e.relative_path == "docs/big/doc.md")
    found = [f for f in shelf.doctor() if f.rule == "split-dir-conflict"]
    shelf.rebuild_index()
    hits = [h["relative_path"] for h in shelf.search("lorem")]

    assert entry.section_paths == []
    assert [f.path for f in found] == ["docs/big/doc"]
    assert "is a symlink" in found[0].detail
    assert not (moved / "SUBINDEX.md").exists()
    assert hits == ["docs/big/doc.md"]


def test_a_symlink_inside_a_split_makes_it_someone_elses(tmp_path: Path):
    # docshelf never writes a symlink: a split holding one is not docshelf's
    # to rewrite or read, and the re-add refuses with the cause named.
    shelf = Shelf(tmp_path / "s").init(name="S")
    big = _big_markdown(tmp_path / "big.md")
    added = shelf.add_document(big, category="big", title="Doc")
    split_dir = added.document_path.parent / added.document_path.stem
    outside = tmp_path / "outside.md"
    outside.write_text("## Mine\n", encoding="utf-8")
    try:
        (split_dir / "999-mine.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available on this filesystem/account")

    found = [f for f in shelf.doctor(fix=True) if f.rule == "split-dir-conflict"]
    err = _refusal(lambda: shelf.add_document(big, category="big", title="Doc", overwrite=True))

    assert [e.section_paths for e in shelf.scan()] == [[]]
    assert [f.path for f in found] == ["docs/big/doc"]
    assert "holds a symlink (999-mine.md)" in found[0].detail
    assert type(err).__name__ == "SplitDirConflictError"
    assert "symlink" in str(err)
    assert (split_dir / "999-mine.md").is_symlink() and outside.is_file()


def test_a_dangling_symlink_at_the_split_path_is_refused_up_front(tmp_path: Path):
    # exists() follows the link and found nothing there: the pre-flight let the
    # add through, the document was written, and only the split then failed on
    # the link. lstat sees the link, so nothing is written.
    shelf = Shelf(tmp_path / "s").init(name="S")
    cat = shelf.root / "docs" / "big"
    cat.mkdir(parents=True, exist_ok=True)
    try:
        (cat / "doc").symlink_to(tmp_path / "gone", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available on this filesystem/account")

    err = _refusal(
        lambda: shelf.add_document(_big_markdown(tmp_path / "big.md"), category="big", title="Doc")
    )

    assert type(err).__name__ == "SplitDirConflictError"
    assert "is a symlink" in str(err)
    assert not (cat / "doc.md").exists()


def _case_insensitive(directory: Path) -> bool:
    probe = directory / "CaseProbe"
    probe.mkdir()
    try:
        return (directory / "caseprobe").exists()
    finally:
        probe.rmdir()


def test_doctor_names_a_split_path_spelt_differently_on_disk_once(tmp_path: Path):
    # On a case-insensitive filesystem (APFS, NTFS by default) Images/ is
    # images.md's split path, and the re-add refuses on it. doctor reported it
    # twice — an orphan by its own name, a conflict by the document's — and no
    # extra_dirs entry cleared both (#118 review).
    if not _case_insensitive(tmp_path):
        pytest.skip("case-sensitive filesystem: Images/ is not images.md's split path")
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    shelf.add_document(FIXTURE, category="guides", title="images", split=False)
    _asset_dir(shelf.root / "docs" / "guides", "Images")

    found = [(f.rule, f.path) for f in shelf.doctor() if "images" in f.path.lower()]
    err = _refusal(
        lambda: shelf.add_document(
            FIXTURE, category="guides", title="images", split=False, overwrite=True
        )
    )

    assert found == [("split-dir-conflict", "docs/guides/Images")]
    assert type(err).__name__ == "SplitDirConflictError"


def test_doctor_calls_a_case_variant_an_orphan_where_case_matters(tmp_path: Path):
    # The counterpart: where the filesystem tells Images/ from images/, the
    # folder is nobody's split path — an orphan, and the re-add goes through.
    if _case_insensitive(tmp_path):
        pytest.skip("case-insensitive filesystem: Images/ is images.md's split path")
    shelf = Shelf(tmp_path / "s").init(name="S", default_categories=["guides"])
    shelf.add_document(FIXTURE, category="guides", title="images", split=False)
    _asset_dir(shelf.root / "docs" / "guides", "Images")

    found = [(f.rule, f.path) for f in shelf.doctor() if "images" in f.path.lower()]

    readd = shelf.add_document(
        FIXTURE, category="guides", title="images", split=False, overwrite=True
    )

    assert found == [("orphaned-split-dir", "docs/guides/Images")]
    assert readd.overwritten


def test_colliding_category_dirs_skips_a_declared_sidecar(tmp_path: Path):
    # USAGE promises a declared sidecar sits next to the documents "without a
    # finding", yet colliding-category-dirs walked every directory in docs/
    # unfiltered: a sidecar "docs/Research Papers" next to the category
    # docs/research-papers was reported as a duplicate category.
    shelf = Shelf(tmp_path / "s").init(name="S", manifest=True)
    _declare_extra_dirs(shelf, "docs/Research Papers")
    shelf.add_document(FIXTURE, category="research-papers", title="P", split=False)
    sidecar = shelf.root / "docs" / "Research Papers"
    sidecar.mkdir()
    (sidecar / "paper.pdf").write_bytes(b"%PDF-1.4 original")

    assert [f for f in shelf.doctor() if f.rule == "colliding-category-dirs"] == []
