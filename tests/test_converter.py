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


def _synthetic_pdf(path: Path) -> Path:
    """Write a two-page PDF with known text, using PyMuPDF itself.

    Generated rather than committed as a binary fixture: the bytes stay
    readable in the diff, and the expected text lives next to the assertion
    instead of in a file nobody can grep.
    """
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    first = doc.new_page()
    first.insert_text((72, 100), "Quarterly Report", fontsize=20)
    first.insert_text((72, 140), "The reconciliation closed on the 14th.", fontsize=11)
    second = doc.new_page()
    second.insert_text((72, 100), "Appendix A", fontsize=16)
    second.insert_text((72, 140), "Line items follow in the table below.", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def test_pdf_conversion_carries_text_and_structure(tmp_path: Path):
    """The package's headline feature, converting an actual PDF.

    Until this test the whole suite touched PDFs only through invalid ones —
    `not a pdf` written to a `.pdf` name — which exercises the *error* path and
    says nothing about conversion. That left `pymupdf4llm`, an unbounded
    dependency (`>=0.0.17`) whose upstream has since moved to 1.x, completely
    unverified: a breaking change in it would have surfaced to users, not to
    CI.

    Asserted on both pages, because a converter that silently stopped after the
    first would satisfy any single-page check.
    """
    pytest.importorskip("pymupdf4llm")
    pdf = _synthetic_pdf(tmp_path / "report.pdf")

    md = source_to_markdown(pdf)

    assert "Quarterly Report" in md
    assert "The reconciliation closed on the 14th." in md
    assert "Appendix A" in md, "second page missing — conversion stopped early"
    # Font size is what pymupdf4llm turns into heading level; losing that would
    # make every shelved PDF one flat paragraph, which the splitter then cannot
    # break into sections.
    assert "# Quarterly Report" in md, md


def test_pdf_conversion_rejects_a_file_that_is_not_a_pdf(tmp_path: Path):
    """The error path stays an error — paired with the test above on purpose.

    A converter that returned empty Markdown for anything unreadable would pass
    "it converts" while quietly shelving blank documents.
    """
    pytest.importorskip("pymupdf4llm")
    fake = tmp_path / "broken.pdf"
    fake.write_text("not really a pdf", encoding="utf-8")

    with pytest.raises(ConversionError):
        source_to_markdown(fake)


def test_absent_marker_says_install_it(monkeypatch):
    """The plain case must keep its actionable install hint."""
    import importlib.util as _iu

    from docshelf_mcp.core.converter import _marker_import_message

    monkeypatch.setattr(_iu, "find_spec", lambda name: None)
    msg = _marker_import_message(ImportError("No module named 'marker'"))

    assert "is not installed" in msg
    assert "pip install" in msg


def test_incompatible_marker_is_not_reported_as_missing(monkeypatch):
    """An installed-but-wrong-major marker must not be called "not installed".

    The `high-quality` extra declared `marker-pdf>=1.0.0` with no ceiling while
    marker-pdf 2.0.0 was already on PyPI, so a fresh install pulled an untested
    major. If its API moved, the resulting ImportError used to be reported as
    "marker-pdf is required ... but is not installed", sending the reader to
    reinstall a package that is already there — the install succeeds, the
    message repeats, and the real cause never surfaces.
    """
    import importlib.util as _iu

    from docshelf_mcp.core import converter as conv

    monkeypatch.setattr(_iu, "find_spec", lambda name: object())
    monkeypatch.setattr(conv, "version", lambda name: "2.0.0")
    msg = conv._marker_import_message(
        ImportError("cannot import name 'PdfConverter' from 'marker.converters.pdf'")
    )

    assert "is not installed" not in msg, msg
    assert "2.0.0" in msg, "installed version must be named — it is the whole diagnosis"
    assert "version mismatch" in msg
    assert "PdfConverter" in msg, "the underlying ImportError must survive into the message"
