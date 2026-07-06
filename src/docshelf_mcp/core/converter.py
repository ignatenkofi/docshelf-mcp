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

from pathlib import Path
from typing import Literal

__all__ = [
    "pdf_to_markdown",
    "source_to_markdown",
    "Quality",
    "ConversionError",
    "SUPPORTED_INPUT_SUFFIXES",
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


class ConversionError(RuntimeError):
    """Raised when conversion fails or a required engine is missing."""


def _convert_fast(pdf_path: Path) -> str:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "pymupdf4llm is required for quality='fast' but is not installed. "
            "Install it with: pip install pymupdf4llm"
        ) from exc

    return pymupdf4llm.to_markdown(str(pdf_path))


def _convert_high(pdf_path: Path) -> str:
    try:
        from marker.converters.pdf import PdfConverter  # type: ignore[import-not-found]
        from marker.models import create_model_dict  # type: ignore[import-not-found]
        from marker.output import text_from_rendered  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "marker-pdf is required for quality='high' but is not installed. "
            "Install it with: pip install 'docshelf-mcp[high-quality]' or "
            "pip install marker-pdf. Note: marker-pdf pulls in PyTorch (~2 GB)."
        ) from exc

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(pdf_path))
    text, _, _ = text_from_rendered(rendered)
    return text


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
    with path.open("rb") as fh:
        return mammoth.convert_to_markdown(fh).value


def _html_to_markdown(html: str) -> str:
    try:
        from markdownify import markdownify  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "markdownify is required for .html/.epub conversion but is not "
            "installed. Install it with: pip install 'docshelf-mcp[html]' "
            "(or '[epub]')"
        ) from exc
    return markdownify(html, heading_style="ATX")


def _convert_html(path: Path) -> str:
    return _html_to_markdown(path.read_text(encoding="utf-8", errors="replace"))


def _convert_epub(path: Path) -> str:
    try:
        import ebooklib  # type: ignore[import-not-found]
        from ebooklib import epub  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "ebooklib is required for .epub conversion but is not installed. "
            "Install it with: pip install 'docshelf-mcp[epub]'"
        ) from exc
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
        html = item.get_content().decode("utf-8", errors="replace")
        md = _html_to_markdown(html)
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
