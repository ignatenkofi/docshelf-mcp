"""PDF → Markdown conversion.

Two engines:

* ``"fast"`` — `pymupdf4llm <https://pypi.org/project/pymupdf4llm/>`__.
  Pure-Python, no GPU, ~1 second per 100 pages. Good enough for most
  technical manuals. **Default.**
* ``"high"`` — `marker-pdf <https://pypi.org/project/marker-pdf/>`__.
  Higher fidelity (tables, equations), but heavy (PyTorch). Optional —
  only imported if requested.

Both code paths are deferred imports: importing ``docshelf_mcp`` doesn't
pull in PyMuPDF or marker until you actually call :func:`pdf_to_markdown`.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

__all__ = [
    "pdf_to_markdown",
    "source_to_markdown",
    "Quality",
    "ConversionError",
    "SUPPORTED_INPUT_SUFFIXES",
    "SUPPORTED_INPUT_GLOBS",
]

Quality = Literal["fast", "high"]

#: Input suffixes :func:`source_to_markdown` can ingest. Markdown and PDF work
#: out of the box; DOCX / HTML / EPUB need the matching optional extra.
SUPPORTED_INPUT_SUFFIXES = (
    ".md",
    ".markdown",
    ".pdf",
    ".docx",
    ".html",
    ".htm",
    ".epub",
)

#: Glob patterns matching :data:`SUPPORTED_INPUT_SUFFIXES`, one per suffix. The
#: default include set for directory scans (e.g. :meth:`Shelf.add_directory`),
#: derived here so it can never drift behind the suffixes it mirrors.
SUPPORTED_INPUT_GLOBS = tuple(f"*{suffix}" for suffix in SUPPORTED_INPUT_SUFFIXES)


class ConversionError(RuntimeError):
    """Raised when conversion fails or a required engine is missing."""


@contextmanager
def _as_conversion_error(detail: str) -> Iterator[None]:
    """Re-raise whatever a backend raises as :class:`ConversionError`.

    :func:`source_to_markdown` documents ConversionError as *the* failure a
    caller catches, and the PDF engines already keep that promise. The other
    backends did not: a mislabelled ``.docx`` reached mammoth as a non-zip and
    came back as ``zipfile.BadZipFile``, a corrupt ``.epub`` as
    ``ebooklib.epub.EpubException``. A caller following the documented contract
    caught neither, so one bad file took down a whole shelf run. The original
    is chained (``raise ... from``), leaving the backend detail one
    ``__cause__`` away rather than lost.

    Two exceptions pass through untouched, both deliberately:

    * ``ConversionError`` — already ours. :func:`_html_to_markdown` is shared
      by the html and epub paths and wraps its own engine call, so an epub
      chapter must not come back wrapped twice with the real cause buried a
      level deeper.
    * ``FileNotFoundError`` — :func:`source_to_markdown` documents it as a
      *separate* outcome. "That path does not exist" is the caller's mistake;
      "the backend could not read this file" is the document's. Only the first
      is fixed by passing a different path, so collapsing the two would cost
      the caller the one distinction it can act on. Every other ``OSError``
      (permission, is-a-directory, I/O) *is* a conversion failure and is
      wrapped.

    Each ``with`` block stays around the backend call itself. Wrapping whole
    function bodies would also swallow bugs in this module, and a ``TypeError``
    of our own making must not arrive dressed as a broken document.
    """
    try:
        yield
    except (ConversionError, FileNotFoundError):
        raise
    except Exception as exc:  # noqa: BLE001 — the backend's exception type is its own
        raise ConversionError(f"{detail}: {exc}") from exc


def _convert_fast(pdf_path: Path) -> str:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "pymupdf4llm is required for quality='fast' but is not installed. "
            "Install it with: pip install pymupdf4llm"
        ) from exc

    try:
        return pymupdf4llm.to_markdown(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 — the engine's exception type is its own
        # The docstring on pdf_to_markdown promises ConversionError "if the
        # requested engine is missing or fails", and only the *missing* half
        # was true: a damaged or mislabelled PDF surfaced as
        # pymupdf.FileDataError, so a caller following the documented contract
        # never caught it. The cause is chained, so the backend detail is one
        # `__cause__` away rather than lost.
        raise ConversionError(f"pymupdf4llm could not read {pdf_path.name}: {exc}") from exc


_MARKER_ABSENT = (
    "marker-pdf is required for quality='high' but is not installed. "
    "Install it with: pip install 'docshelf-mcp[high-quality]' or "
    "pip install marker-pdf. Note: marker-pdf pulls in PyTorch (~2 GB)."
)


def _marker_import_message(exc: ImportError) -> str:
    """Three different problems arrive here as the same ``ImportError``.

    "Not installed", "installed but incompatible", and "installed, compatible,
    but one of its dependencies is broken" all reach this handler identically,
    and each has different advice. Reporting the second as the first sends the
    reader to reinstall a package that is already there — the install succeeds,
    the message repeats, and the real cause stays hidden.

    Not hypothetical: the ``high-quality`` extra declared ``marker-pdf>=1.0.0``
    with no upper bound while marker-pdf 2.0.0 was already released, so a fresh
    install pulled a major this code has never run against. The bound is fixed
    in ``pyproject.toml``; existing environments resolved before the fix still
    carry 2.x, and this is what they will see.
    """
    try:
        present = importlib.util.find_spec("marker") is not None
    except (ImportError, ValueError):
        # A half-installed or broken parent package: treat as absent rather
        # than letting the probe raise over the original failure.
        present = False
    if not present:
        return _MARKER_ABSENT
    try:
        installed = version("marker-pdf")
    except PackageNotFoundError:
        installed = "unknown"

    # find_spec answered "is marker there at all". It cannot answer *what*
    # failed to import, and marker's import tree reaches far past marker:
    # PyTorch and a dozen more packages load behind `from
    # marker.converters.pdf import ...`. A missing or half-installed one of
    # those raises exactly where a moved marker API would, and blaming
    # marker-pdf's version for it makes every clause below false — the version
    # is fine, it is not a mismatch, and reinstalling is precisely what helps.
    #
    # The import machinery does say which module it was: ImportError.name is
    # set for every shape it raises — ModuleNotFoundError names the module it
    # could not find ('torch'), and "cannot import name X from Y" names Y.
    # Anything outside marker's own namespace is a dependency problem.
    failed = getattr(exc, "name", None)
    if failed and failed != "marker" and not failed.startswith("marker."):
        return (
            f"marker-pdf is installed (version {installed}), but importing it failed inside "
            f"{failed!r}, which is not part of marker-pdf: {exc}. That points at a missing or "
            f"broken dependency of marker-pdf, not at marker-pdf's own version — so reinstalling "
            f"is worth trying here: pip install --force-reinstall 'docshelf-mcp[high-quality]' "
            f"(or repair {failed!r} directly). marker-pdf pulls in PyTorch and its stack, which "
            "is where this usually goes wrong."
        )

    # Either the failure came from inside marker itself, or `name` is unset —
    # which the machinery does not do, only hand-built ImportErrors. Both land
    # on the version reading, already narrowed by find_spec to "marker is here".
    return (
        f"marker-pdf is installed (version {installed}) but does not expose the API "
        f"docshelf-mcp uses: {exc}. This is a version mismatch, not a missing package — "
        "reinstalling will not help. docshelf-mcp is tested against marker-pdf 1.x; "
        "pin it with: pip install 'marker-pdf>=1.0,<2'."
    )


def _convert_high(pdf_path: Path) -> str:
    try:
        from marker.converters.pdf import PdfConverter  # type: ignore[import-not-found]
        from marker.models import create_model_dict  # type: ignore[import-not-found]
        from marker.output import text_from_rendered  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(_marker_import_message(exc)) from exc

    try:
        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(str(pdf_path))
        text, _, _ = text_from_rendered(rendered)
        return text
    except Exception as exc:  # noqa: BLE001 — same contract as the fast path
        raise ConversionError(f"marker-pdf could not read {pdf_path.name}: {exc}") from exc


def pdf_to_markdown(pdf_path: Path | str, quality: Quality = "fast") -> str:
    """Convert a PDF file to Markdown.

    Args:
        pdf_path: Path to the source PDF.
        quality: ``"fast"`` (default, pymupdf4llm) or ``"high"`` (marker-pdf).

    Returns:
        The extracted Markdown text. NOT cleaned —
        run :func:`docshelf_mcp.core.splitter.clean_markdown` to remove
        PDF-extraction artefacts.

    Raises:
        FileNotFoundError: If ``pdf_path`` doesn't exist.
        ConversionError: If the requested engine is missing or fails.
    """
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ConversionError(
            f"Expected a .pdf file, got {pdf_path.suffix or '<no extension>'}"
        )

    if quality == "fast":
        return _convert_fast(pdf_path)
    if quality == "high":
        return _convert_high(pdf_path)
    raise ConversionError(f"Unknown quality preset: {quality!r}")


def _convert_docx(path: Path) -> str:
    try:
        import mammoth  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "mammoth is required for .docx conversion but is not installed. "
            "Install it with: pip install 'docshelf-mcp[docx]'"
        ) from exc
    # The open() is inside the wrap on purpose: a directory or an unreadable
    # file wearing a .docx name is a conversion failure like any other. A
    # genuinely missing path still raises FileNotFoundError — see
    # _as_conversion_error.
    with _as_conversion_error(f"mammoth could not read {path.name}"), path.open("rb") as fh:
        return mammoth.convert_to_markdown(fh).value


def _html_to_markdown(html: str, origin: str = "the HTML") -> str:
    """Render an HTML string as Markdown.

    ``origin`` names what the string came from — a file name, or an epub
    chapter id — so a failure says *which* chapter of a 600-page book broke.
    Shared by the html and epub paths, and the single place the markdownify
    call is wrapped, so neither caller has to wrap it again.
    """
    try:
        from markdownify import markdownify  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "markdownify is required for .html/.epub conversion but is not "
            "installed. Install it with: pip install 'docshelf-mcp[html]' "
            "(or '[epub]')"
        ) from exc
    with _as_conversion_error(f"markdownify could not convert {origin}"):
        return markdownify(html, heading_style="ATX")


def _convert_html(path: Path) -> str:
    with _as_conversion_error(f"could not read {path.name}"):
        html = path.read_text(encoding="utf-8", errors="replace")
    # Deliberately outside the block above: _html_to_markdown wraps its own
    # engine call, and re-wrapping would bury the real cause a level deeper.
    return _html_to_markdown(html, origin=path.name)


def _convert_epub(path: Path) -> str:
    try:
        import ebooklib  # type: ignore[import-not-found]
        from ebooklib import epub  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "ebooklib is required for .epub conversion but is not installed. "
            "Install it with: pip install 'docshelf-mcp[epub]'"
        ) from exc
    with _as_conversion_error(f"ebooklib could not read {path.name}"):
        book = epub.read_epub(str(path))

    # Classes that are documents but not body chapters — the navigation page
    # (EPUB3 nav / ToC) and the HTML cover — must not be interleaved as text.
    skip_classes = tuple(
        c
        for c in (getattr(epub, "EpubNav", None), getattr(epub, "EpubCoverHtml", None))
        if c is not None
    )

    parts: list[str] = []
    seen: set[str] = set()

    def render(item) -> None:
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            return
        if skip_classes and isinstance(item, skip_classes):
            return
        item_id = item.get_id()
        if item_id in seen:
            return
        seen.add(item_id)
        with _as_conversion_error(f"ebooklib could not read {item_id} in {path.name}"):
            html = item.get_content().decode("utf-8", errors="replace")
        md = _html_to_markdown(html, origin=f"{item_id} in {path.name}")
        if md.strip():
            parts.append(md)

    # Assemble in *spine* (reading) order — the manifest order that
    # ``get_items`` yields is not guaranteed to match it. Skip non-linear
    # items (``linear="no"`` — notes, popups) so they don't land mid-book.
    for entry in getattr(book, "spine", None) or []:
        if isinstance(entry, (tuple, list)):
            idref = entry[0]
            linear = entry[1] if len(entry) > 1 else "yes"
        else:
            idref, linear = entry, "yes"
        if str(linear).lower() in ("no", "false", "0"):
            continue
        render(book.get_item_with_id(idref))

    # Fallback: an EPUB with an empty/unusable spine still yields its documents
    # (manifest order) rather than nothing.
    if not parts:
        for item in book.get_items():
            render(item)

    return "\n\n".join(parts)


#: Suffix → converter. Markdown is read verbatim; the rest are extracted.
_CONVERTERS = {
    ".pdf": None,  # handled specially (carries the quality preset)
    ".docx": _convert_docx,
    ".html": _convert_html,
    ".htm": _convert_html,
    ".epub": _convert_epub,
}


def source_to_markdown(source: Path | str, quality: Quality = "fast") -> str:
    """Convert any supported source file to (uncleaned) Markdown.

    Dispatches by suffix: ``.md``/``.markdown`` are read as-is, ``.pdf`` uses
    the PDF engines, and ``.docx``/``.html``/``.htm``/``.epub`` use their
    optional backends (imported lazily). Run
    :func:`docshelf_mcp.core.splitter.clean_markdown` on the result.

    Raises:
        FileNotFoundError: ``source`` doesn't exist.
        ConversionError: Unsupported suffix, or the backend is missing/fails.
    """
    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    suffix = source.suffix.lower()
    if suffix in (".md", ".markdown"):
        return source.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return pdf_to_markdown(source, quality=quality)
    converter = _CONVERTERS.get(suffix)
    if converter is None:
        raise ConversionError(
            f"Unsupported source type {suffix or '<no extension>'!r}. "
            f"Supported: {', '.join(SUPPORTED_INPUT_SUFFIXES)}. "
            "DOCX/HTML/EPUB need the matching extra, e.g. "
            "pip install 'docshelf-mcp[formats]'."
        )
    return converter(source)
