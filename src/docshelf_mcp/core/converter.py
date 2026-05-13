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

__all__ = ["pdf_to_markdown", "Quality"]

Quality = Literal["fast", "high"]


class ConversionError(RuntimeError):
    """Raised when PDF conversion fails or a required engine is missing."""


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
