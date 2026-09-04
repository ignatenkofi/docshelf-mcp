"""Tests for the multi-format source → Markdown dispatcher.

The DOCX/HTML/EPUB backends are optional. Tests of *successful* conversion
need the real library and skip cleanly without it (they are in the dev extra,
so they run in CI).

Tests of the *failure* contract do not skip: they stub the backend, because a
stub is the only way to make a healthy backend fail on demand, and because a
contract that is only checked where the extras happen to be installed is a
contract nobody is checking.
"""

import sys
import types
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


def test_absent_pymupdf4llm_names_the_pdf_extra(monkeypatch, tmp_path: Path):
    """The fast path's ImportError branch, unreachable until #93.

    pymupdf4llm was a core dependency, so no environment this package could be
    installed into ever hit this handler. Now that it is the `pdf` extra, a
    bare install does — and the message must name the extra, not just the
    package (which the reader would otherwise have to know about).

    Does not skip: `sys.modules[name] = None` makes `import name` raise
    ImportError whether or not the real library is installed, so the branch
    is checked in CI (where the dev extra has it) as well as in a bare
    checkout.
    """
    monkeypatch.setitem(sys.modules, "pymupdf4llm", None)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ConversionError) as exc:
        source_to_markdown(pdf)

    msg = str(exc.value)
    assert "is not installed" in msg
    assert "docshelf-mcp[pdf]" in msg, msg


# --------------------------------------------------------------------------
# Backend failure must arrive as ConversionError
#
# source_to_markdown documents ConversionError as the failure a caller catches
# ("the backend is missing/fails"). The PDF engines keep that promise; the
# DOCX/HTML/EPUB paths did not, and let mammoth's zipfile.BadZipFile,
# ebooklib's EpubException and markdownify's own errors escape raw — so one
# unreadable file in a directory scan took down the whole run.
#
# These tests stub the backends instead of importing them. Not a workaround
# for a bare container: a stub is the only way to make a *healthy* backend
# fail on demand, and it keeps the contract under test in environments where
# the optional extras aren't installed, where importorskip would hand back a
# green run that verified nothing. The real-backend pair below proves the
# stubs model something that actually happens.
# --------------------------------------------------------------------------

_STUB_ITEM_DOCUMENT = 9  # ebooklib's real constant is an int; the stub need only agree with itself


class _Boom(Exception):
    """Stand-in for whatever a backend raises — deliberately not an OSError."""


def _stub_module(monkeypatch, name: str, **attrs):
    mod = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


def _stub_ebooklib(monkeypatch, read_epub):
    epub_mod = types.ModuleType("ebooklib.epub")
    epub_mod.read_epub = read_epub
    _stub_module(monkeypatch, "ebooklib", ITEM_DOCUMENT=_STUB_ITEM_DOCUMENT, epub=epub_mod)
    monkeypatch.setitem(sys.modules, "ebooklib.epub", epub_mod)


class _StubChapter:
    def __init__(self, content=b"<p>body</p>", boom=None):
        self._content = content
        self._boom = boom

    def get_type(self):
        return _STUB_ITEM_DOCUMENT

    def get_id(self):
        return "ch1"

    def get_content(self):
        if self._boom is not None:
            raise self._boom
        return self._content


class _StubBook:
    def __init__(self, item):
        self._item = item
        self.spine = [("ch1", "yes")]

    def get_item_with_id(self, idref):
        return self._item

    def get_items(self):
        return [self._item]


def _failing_docx(monkeypatch, tmp_path: Path, boom: Exception) -> Path:
    def convert_to_markdown(fileobj):
        raise boom

    _stub_module(monkeypatch, "mammoth", convert_to_markdown=convert_to_markdown)
    src = tmp_path / "report.docx"
    src.write_bytes(b"PK\x03\x04 pretend")
    return src


def _failing_markdownify_html(monkeypatch, tmp_path: Path, boom: Exception) -> Path:
    def markdownify(html, **kwargs):
        raise boom

    _stub_module(monkeypatch, "markdownify", markdownify=markdownify)
    src = tmp_path / "page.html"
    src.write_text("<p>hi</p>", encoding="utf-8")
    return src


def _failing_epub_open(monkeypatch, tmp_path: Path, boom: Exception) -> Path:
    def read_epub(path):
        raise boom

    _stub_ebooklib(monkeypatch, read_epub)
    src = tmp_path / "book.epub"
    src.write_bytes(b"PK\x03\x04 pretend")
    return src


def _failing_epub_chapter(monkeypatch, tmp_path: Path, boom: Exception) -> Path:
    _stub_ebooklib(monkeypatch, lambda path: _StubBook(_StubChapter(boom=boom)))
    src = tmp_path / "book.epub"
    src.write_bytes(b"PK\x03\x04 pretend")
    return src


def _failing_markdownify_epub(monkeypatch, tmp_path: Path, boom: Exception) -> Path:
    def markdownify(html, **kwargs):
        raise boom

    _stub_module(monkeypatch, "markdownify", markdownify=markdownify)
    _stub_ebooklib(monkeypatch, lambda path: _StubBook(_StubChapter()))
    src = tmp_path / "book.epub"
    src.write_bytes(b"PK\x03\x04 pretend")
    return src


@pytest.mark.parametrize(
    "arrange",
    [
        _failing_docx,
        _failing_markdownify_html,
        _failing_epub_open,
        _failing_epub_chapter,
        _failing_markdownify_epub,
    ],
    ids=[
        "docx: mammoth raises",
        "html: markdownify raises",
        "epub: read_epub raises",
        "epub: chapter content raises",
        "epub: markdownify raises on a chapter",
    ],
)
def test_backend_failure_becomes_conversion_error(monkeypatch, tmp_path: Path, arrange):
    boom = _Boom("engine exploded")
    src = arrange(monkeypatch, tmp_path, boom)

    with pytest.raises(ConversionError) as exc:
        source_to_markdown(src)

    # Chained, not swallowed: the backend detail must survive the translation,
    # or the wrap trades one unusable error for another.
    assert exc.value.__cause__ is boom, "the backend's own exception must be the __cause__"
    assert "engine exploded" in str(exc.value)


def test_epub_chapter_failure_is_not_wrapped_twice(monkeypatch, tmp_path: Path):
    """_html_to_markdown is shared by the html and epub paths — wrap it once.

    The epub path calls it per chapter. If both the shared helper and the epub
    caller wrapped, the real failure would land at `__cause__.__cause__`, one
    level below where anyone (including the assertion above) looks, and the
    message would read as a conversion error caused by a conversion error.
    """
    boom = _Boom("engine exploded")
    src = _failing_markdownify_epub(monkeypatch, tmp_path, boom)

    with pytest.raises(ConversionError) as exc:
        source_to_markdown(src)

    assert not isinstance(exc.value.__cause__, ConversionError), (
        "double-wrapped: a ConversionError caused by a ConversionError"
    )


def test_unreadable_html_source_becomes_conversion_error(tmp_path: Path):
    """A directory wearing an .html name — exists, is not readable as text.

    Needs no backend at all: the read happens before markdownify is even
    imported, so this one runs everywhere and covers the read that
    `_convert_html` used to leave bare (it escaped as IsADirectoryError).
    """
    src = tmp_path / "page.html"
    src.mkdir()

    with pytest.raises(ConversionError):
        source_to_markdown(src)


def test_missing_docx_stays_file_not_found(monkeypatch, tmp_path: Path):
    """FileNotFoundError is deliberately NOT folded into ConversionError.

    source_to_markdown documents the two as separate outcomes, and they mean
    different things to a caller: "that path does not exist" is fixed by
    passing a different path, "the backend could not read this file" is not.
    _convert_docx opens the file *inside* the wrap, so this is the path where
    the distinction could most easily have been lost.
    """
    from docshelf_mcp.core.converter import _convert_docx

    _stub_module(monkeypatch, "mammoth", convert_to_markdown=lambda fh: None)

    with pytest.raises(FileNotFoundError):
        _convert_docx(tmp_path / "gone.docx")


def test_real_mammoth_failure_becomes_conversion_error(tmp_path: Path):
    """The stubs above, against the actual library (mammoth raises BadZipFile)."""
    pytest.importorskip("mammoth")
    src = tmp_path / "not-really.docx"
    src.write_text("plain text wearing a .docx name", encoding="utf-8")

    with pytest.raises(ConversionError):
        source_to_markdown(src)


def test_real_ebooklib_failure_becomes_conversion_error(tmp_path: Path):
    """Same, for ebooklib (which raises its own EpubException)."""
    pytest.importorskip("ebooklib")
    src = tmp_path / "not-really.epub"
    src.write_text("plain text wearing an .epub name", encoding="utf-8")

    with pytest.raises(ConversionError):
        source_to_markdown(src)


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
    # `name` set the way the import machinery sets it: for "cannot import name
    # X from Y" it is Y, the module that was found but lacked the attribute.
    msg = conv._marker_import_message(
        ImportError(
            "cannot import name 'PdfConverter' from 'marker.converters.pdf'",
            name="marker.converters.pdf",
        )
    )

    assert "is not installed" not in msg, msg
    assert "2.0.0" in msg, "installed version must be named — it is the whole diagnosis"
    assert "version mismatch" in msg
    assert "PdfConverter" in msg, "the underlying ImportError must survive into the message"


def test_broken_marker_dependency_is_not_called_a_version_mismatch(monkeypatch):
    """A third case the missing/incompatible split does not cover.

    marker-pdf pulls in PyTorch and a large stack behind it. When one of those
    is missing or half-installed, the failure surfaces from inside `from
    marker.converters.pdf import ...` exactly like a moved marker API does —
    same exception type, same import statement, and find_spec("marker") says
    "present" for both.

    Reported as a version mismatch, every clause of the advice is false: the
    installed marker-pdf is inside the tested range, nothing is mismatched,
    and reinstalling is the one thing that *would* help. The reader is sent to
    pin a package that was never the problem while the missing dependency goes
    unnamed.
    """
    import importlib.util as _iu

    from docshelf_mcp.core import converter as conv

    monkeypatch.setattr(_iu, "find_spec", lambda name: object())
    monkeypatch.setattr(conv, "version", lambda name: "1.8.2")  # squarely inside `>=1.0,<2`
    msg = conv._marker_import_message(ModuleNotFoundError("No module named 'torch'", name="torch"))

    assert "torch" in msg, "the module that actually failed must be named — it is the fix"
    assert "version mismatch" not in msg, msg
    assert "reinstalling will not help" not in msg, msg
    assert "marker-pdf>=1.0,<2" not in msg, "pinning marker-pdf cannot fix a missing torch"
    assert "is not installed" not in msg, "marker-pdf is installed; only its dependency is not"
