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


def test_add_document_rebuilds_index_exactly_once(tmp_path: Path, monkeypatch):
    shelf = Shelf(tmp_path / "s").init(name="S")
    calls = {"n": 0}
    real = shelf.rebuild_index
    monkeypatch.setattr(shelf, "rebuild_index", lambda: (calls.__setitem__("n", calls["n"] + 1), real())[1])

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
    monkeypatch.setattr(shelf, "rebuild_index", lambda: (calls.__setitem__("n", calls["n"] + 1), real())[1])

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
    result = shelf.add_document(
        b, category="c", title="C++ Guide?", split=False, overwrite=True
    )
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
    # An unsluggable title falls back to slugify's own "section" stem.
    assert (shelf.root / "docs" / "c" / "section.md").is_file()
    with pytest.raises(DocumentExistsError):
        shelf.add_document(b, category="c", title="???", split=False)


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
        "<html><body><h1>Router Manual</h1><p>VLAN configuration notes.</p>"
        "</body></html>",
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

    result = shelf.rename_document(
        category="docs", document="Old Title", new_title="New Title"
    )
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
    big.write_text("# T\n\n" + "\n\n".join(f"## S{i}\n\n{body}" for i in range(4)),
                   encoding="utf-8")
    shelf = Shelf(tmp_path / "s").init(name="S")
    shelf.add_document(big, category="misc", title="Manual", split=True)

    result = shelf.rename_document(
        category="misc", document="Manual", new_category="routers"
    )
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
    shelf.add_document(FIXTURE, category="docs", title="Doc", description="old",
                       split=False)
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
            source_path=str(FIXTURE), category="docs", title="Sample",
            split=False, shelf_path=shelf_path,
        )
    )
    hit = t.search(t.SearchInput(query="BGP", shelf_path=shelf_path))["hits"][0]
    assert hit["raw_url"] == (
        "https://gitlab.com/grp/proj/-/raw/main/docs/docs/sample.md"
    )
