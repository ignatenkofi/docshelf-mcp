"""Pydantic input models + thin wrappers around :class:`Shelf` methods.

The actual MCP tool registration lives in :mod:`docshelf_mcp.server`. Keeping
the implementation here (rather than directly inside the ``@mcp.tool``
decorators) makes the logic easy to unit-test without spinning up an MCP
server.

Every wrapper returns a **JSON-serialisable dict**. The server module converts
it to a JSON string for the MCP response.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from docshelf_mcp.config import default_shelf_root
from docshelf_mcp.core.converter import Quality, pdf_to_markdown
from docshelf_mcp.core.shelf import Shelf
from docshelf_mcp.core.splitter import (
    clean_markdown,
    should_split,
    split_by_h2,
    write_split_files,
)

__all__ = [
    "AddDocumentInput",
    "RebuildIndexInput",
    "SearchInput",
    "ListDocumentsInput",
    "ConvertPdfInput",
    "InitShelfInput",
    "add_document",
    "rebuild_index",
    "search",
    "list_documents",
    "convert_pdf",
    "init_shelf",
]


def _resolve_shelf(shelf_path: str | None) -> Shelf:
    return Shelf(Path(shelf_path).expanduser() if shelf_path else default_shelf_root())


class _BaseInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


# -------------------------------------------------------------------- inputs


class AddDocumentInput(_BaseInput):
    """Input for ``add_document``."""

    source_path: str = Field(
        ...,
        description="Absolute path to the source .pdf or .md file on disk.",
        min_length=1,
    )
    category: str = Field(
        ...,
        description="Category bucket — e.g. 'laptops', 'recipes', 'research-papers'. "
        "Created if missing.",
        min_length=1,
        max_length=80,
    )
    title: str = Field(
        ...,
        description="Human-readable document title. Used as the INDEX entry and "
        "(slugified) as the filename.",
        min_length=1,
        max_length=200,
    )
    description: str = Field(
        default="",
        description="Optional one-sentence description shown next to the entry "
        "in INDEX.md.",
        max_length=500,
    )
    split: bool = Field(
        default=True,
        description="Auto-split large documents (>50 KB) by H2 heading. "
        "Recommended unless the source is already small.",
    )
    quality: Quality = Field(
        default="fast",
        description="PDF conversion quality: 'fast' (pymupdf4llm, default) or "
        "'high' (marker-pdf, requires optional install).",
    )
    shelf_path: str | None = Field(
        default=None,
        description="Path to the shelf root directory. Defaults to $DOCSHELF_ROOT "
        "or the server's working directory.",
    )


class RebuildIndexInput(_BaseInput):
    shelf_path: str | None = Field(
        default=None, description="Path to the shelf root directory."
    )


class SearchInput(_BaseInput):
    query: str = Field(
        ...,
        description="Plain-text search query. Tokens are space-split; each "
        "must appear (case-insensitive) for a hit to count.",
        min_length=1,
        max_length=500,
    )
    max_results: int = Field(
        default=10,
        description="Maximum number of hits to return.",
        ge=1,
        le=100,
    )
    shelf_path: str | None = Field(default=None)


class ListDocumentsInput(_BaseInput):
    category: str | None = Field(
        default=None,
        description="Filter to a single category. Omit to list everything.",
    )
    shelf_path: str | None = Field(default=None)


class ConvertPdfInput(_BaseInput):
    pdf_path: str = Field(
        ...,
        description="Absolute path to the source .pdf file.",
        min_length=1,
    )
    out_dir: str = Field(
        ...,
        description="Output directory. Created if missing. The resulting .md file "
        "uses the PDF's stem as its filename.",
        min_length=1,
    )
    quality: Quality = Field(
        default="fast",
        description="'fast' (pymupdf4llm) or 'high' (marker-pdf).",
    )
    split: bool = Field(
        default=False,
        description="If True, also split the converted Markdown by H2 into "
        "a sibling subdirectory.",
    )


class InitShelfInput(_BaseInput):
    shelf_path: str = Field(
        ...,
        description="Directory to initialize as a shelf. Created if missing.",
        min_length=1,
    )
    name: str = Field(
        default="Document Shelf",
        description="Human-readable shelf name (used as INDEX.md H1).",
        max_length=200,
    )
    github_remote: str = Field(
        default="",
        description="GitHub remote URL (https or ssh form). Required for raw-URL "
        "links in INDEX.md.",
        max_length=500,
    )
    default_categories: list[str] = Field(
        default_factory=list,
        description="Category directories to pre-create. They will appear in "
        "INDEX.md in the listed order.",
        max_length=64,
    )
    branch: str = Field(
        default="main",
        description="Branch name used in raw GitHub URLs.",
        min_length=1,
        max_length=100,
    )


# --------------------------------------------------------------- wrappers


def add_document(params: AddDocumentInput) -> dict:
    """Implementation of the ``add_document`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    result = shelf.add_document(
        params.source_path,
        category=params.category,
        title=params.title,
        description=params.description,
        split=params.split,
        quality=params.quality,
    )
    shelf.rebuild_index()
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "document_path": str(result.document_path.relative_to(shelf.root)),
        "section_paths": [str(p.relative_to(shelf.root)) for p in result.section_paths],
        "was_split": result.was_split,
        "section_count": len(result.section_paths),
        "converted_from_pdf": result.converted_from_pdf,
        "index_path": "INDEX.md",
        "next_steps": (
            f"Commit the changes ('git add . && git commit -m \"docs: add {params.title}\"') "
            "to make the new entry visible via raw URLs."
        ),
    }


def rebuild_index(params: RebuildIndexInput) -> dict:
    """Implementation of the ``rebuild_index`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    index_path = shelf.rebuild_index()
    entries = shelf.scan()
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "index_path": str(index_path.relative_to(shelf.root)),
        "document_count": len(entries),
        "category_count": len({e.category for e in entries}),
    }


def search(params: SearchInput) -> dict:
    """Implementation of the ``search`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    hits = shelf.search(params.query, max_results=params.max_results)

    cfg = shelf.config
    from docshelf_mcp.core.indexer import raw_github_url

    enriched = []
    for h in hits:
        url = raw_github_url(cfg.remote, cfg.branch, h["relative_path"]) if cfg.remote else ""
        enriched.append({**h, "raw_url": url})

    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "query": params.query,
        "match_count": len(enriched),
        "hits": enriched,
    }


def list_documents(params: ListDocumentsInput) -> dict:
    """Implementation of the ``list_documents`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    entries = shelf.scan()
    cfg = shelf.config
    from docshelf_mcp.core.indexer import raw_github_url

    grouped: dict[str, list[dict]] = {}
    for e in entries:
        if params.category and e.category != params.category:
            continue
        url = raw_github_url(cfg.remote, cfg.branch, e.relative_path) if cfg.remote else ""
        grouped.setdefault(e.category, []).append(
            {
                "title": e.title,
                "description": e.description,
                "path": e.relative_path,
                "raw_url": url,
                "size_bytes": e.size_bytes,
                "split_into": len(e.section_paths),
            }
        )

    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "shelf_name": cfg.name,
        "remote": cfg.remote,
        "category_filter": params.category,
        "categories": grouped,
        "total_documents": sum(len(v) for v in grouped.values()),
    }


def convert_pdf(params: ConvertPdfInput) -> dict:
    """Implementation of the ``convert_pdf`` MCP tool."""
    pdf_path = Path(params.pdf_path).expanduser().resolve()
    out_dir = Path(params.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = pdf_to_markdown(pdf_path, quality=params.quality)
    cleaned = clean_markdown(raw)
    out_md = out_dir / f"{pdf_path.stem}.md"
    out_md.write_text(cleaned, encoding="utf-8")

    section_paths: list[Path] = []
    if params.split and should_split(cleaned):
        sections = split_by_h2(cleaned)
        if len(sections) >= 2:
            section_paths = write_split_files(sections, out_dir / pdf_path.stem)

    return {
        "status": "ok",
        "source_pdf": str(pdf_path),
        "output_markdown": str(out_md),
        "size_bytes": out_md.stat().st_size,
        "split_into": len(section_paths),
        "section_paths": [str(p) for p in section_paths],
    }


def init_shelf(params: InitShelfInput) -> dict:
    """Implementation of the ``init_shelf`` MCP tool."""
    shelf = Shelf(params.shelf_path)
    shelf.init(
        name=params.name,
        remote=params.github_remote,
        branch=params.branch,
        default_categories=params.default_categories,
    )
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "name": shelf.config.name,
        "remote": shelf.config.remote,
        "branch": shelf.config.branch,
        "categories": params.default_categories,
        "next_steps": (
            "1. cd into the shelf and `git init && git remote add origin <url>` if not done yet.\n"
            "2. Use `add_document` to add your first PDF or Markdown file.\n"
            "3. Commit and push — INDEX.md is regenerated on every add."
        ),
    }


# Re-exported for ergonomic library use.
def to_json(payload: dict) -> str:
    """Pretty-print a tool response dict as JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False)
