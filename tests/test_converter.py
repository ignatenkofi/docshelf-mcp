"""Tests for the multi-format source → Markdown dispatcher.

The DOCX/HTML/EPUB backends are optional; each test skips cleanly if its
backend isn't installed (they are in the dev extra, so they run in CI).
"""

from pathlib import Path

import pytest

from docshelf_mcp.core.converter import (
    ConversionError,
    source_to_markdown,
)


def test_markdown_passthrough(tmp_path: Path):
    src = tmp_path / "a.md"
    src.write_text("# Title\n\nbody\n", encoding="utf-8")
    assert source_to_markdown(src) == "# Title\n\nbody\n"


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
