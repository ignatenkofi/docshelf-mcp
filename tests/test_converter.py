"""Tests for the multi-format source → Markdown dispatcher.

The DOCX/HTML/EPUB backends are optional; each test skips cleanly if its
backend isn't installed (they are in the dev extra, so they run in CI).
"""

from pathlib import Path

import pytest

from docshelf_mcp.core.converter import (
    SUPPORTED_INPUT_GLOBS,
    SUPPORTED_INPUT_SUFFIXES,
    ConversionError,
    source_to_markdown,
)


def test_markdown_passthrough(tmp_path: Path):
    src = tmp_path / "a.md"
    src.write_text("# Title\n\nbody\n", encoding="utf-8")
    assert source_to_markdown(src) == "# Title\n\nbody\n"


def test_input_globs_track_suffixes():
    # The directory-scan default (Shelf.add_directory) is derived from the
    # suffixes the converter dispatches on, so the two can never drift (#52).
    assert SUPPORTED_INPUT_GLOBS == tuple(f"*{s}" for s in SUPPORTED_INPUT_SUFFIXES)
    assert "*.docx" in SUPPORTED_INPUT_GLOBS and "*.epub" in SUPPORTED_INPUT_GLOBS


def test_unsupported_suffix_lists_supported_and_extra(tmp_path: Path):
    bad = tmp_path / "note.rtf"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(ConversionError) as exc:
        source_to_markdown(bad)
    msg = str(exc.value)
    assert ".docx" in msg and "docshelf-mcp[formats]" in msg


def test_missing_source_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        source_to_markdown(tmp_path / "nope.docx")


def test_html_conversion(tmp_path: Path):
    pytest.importorskip("markdownify")
    src = tmp_path / "page.html"
    src.write_text(
        "<html><body><h1>Heading</h1><p>Some <b>bold</b> text.</p>"
        "<h2>Section</h2><p>More.</p></body></html>",
        encoding="utf-8",
    )
    md = source_to_markdown(src)
    assert "# Heading" in md
    assert "## Section" in md
    assert "bold" in md


def test_docx_conversion(tmp_path: Path):
    pytest.importorskip("mammoth")
    docx = pytest.importorskip("docx")

    doc = docx.Document()
    doc.add_heading("Doc Title", level=1)
    doc.add_paragraph("First paragraph of the document.")
    doc.add_heading("Chapter", level=2)
    doc.add_paragraph("Chapter body text.")
    path = tmp_path / "sample.docx"
    doc.save(str(path))

    md = source_to_markdown(path)
    assert "Doc Title" in md and "Chapter body text" in md
    assert "#" in md  # headings became ATX


def test_epub_conversion(tmp_path: Path):
    pytest.importorskip("markdownify")
    ebooklib = pytest.importorskip("ebooklib")
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title("Test Book")
    book.set_language("en")
    ch = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
    ch.content = "<html><body><h1>Chapter One</h1><p>Epub body text here.</p></body></html>"
    book.add_item(ch)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", ch]
    path = tmp_path / "book.epub"
    epub.write_epub(str(path), book)

    md = source_to_markdown(path)
    assert "Chapter One" in md and "Epub body text here" in md
    assert isinstance(ebooklib.ITEM_DOCUMENT, int)  # sanity: constant exists


def test_epub_assembles_in_spine_order(tmp_path: Path):
    # Chapters must come out in reading (spine) order even when the manifest
    # lists them in a different order.
    pytest.importorskip("markdownify")
    pytest.importorskip("ebooklib")
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("ordered")
    book.set_title("Ordered")
    book.set_language("en")

    c1 = epub.EpubHtml(uid="c1", title="One", file_name="c1.xhtml", lang="en")
    c1.content = "<html><body><p>AlphaFirstChapter</p></body></html>"
    c2 = epub.EpubHtml(uid="c2", title="Two", file_name="c2.xhtml", lang="en")
    c2.content = "<html><body><p>BetaSecondChapter</p></body></html>"

    # Add to the manifest in REVERSE of the reading order…
    book.add_item(c2)
    book.add_item(c1)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    # …but the spine states the true reading order: c1 then c2.
    book.spine = [c1, c2]

    path = tmp_path / "ordered.epub"
    epub.write_epub(str(path), book)

    md = source_to_markdown(path)
    assert "AlphaFirstChapter" in md and "BetaSecondChapter" in md
    assert md.index("AlphaFirstChapter") < md.index("BetaSecondChapter")


def test_epub_skips_nav_document(tmp_path: Path):
    # The navigation page must not be interleaved as a body chapter.
    pytest.importorskip("markdownify")
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("navskip")
    book.set_title("NavSkip")
    book.set_language("en")
    ch = epub.EpubHtml(uid="c1", title="One", file_name="c1.xhtml", lang="en")
    ch.content = "<html><body><p>RealBodyText</p></body></html>"
    book.add_item(ch)
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    book.add_item(nav)
    book.spine = ["nav", ch]

    path = tmp_path / "navskip.epub"
    epub.write_epub(str(path), book)

    md = source_to_markdown(path)
    assert "RealBodyText" in md
    # ebooklib's default nav renders a "Table of Contents" heading — absent here.
    assert "Table of Contents" not in md
