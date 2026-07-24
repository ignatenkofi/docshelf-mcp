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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from docshelf_mcp.config import default_shelf_root
from docshelf_mcp.core.converter import SUPPORTED_INPUT_GLOBS, Quality, pdf_to_markdown
from docshelf_mcp.core.shelf import SHELF_METADATA_FILENAME, Shelf
from docshelf_mcp.core.splitter import (
    clean_markdown,
    should_split,
    split_by_h2,
    write_split_files,
)

__all__ = [
    "AddDocumentInput",
    "AddDirectoryInput",
    "ReadDocumentInput",
    "RemoveDocumentInput",
    "RenameDocumentInput",
    "RebuildIndexInput",
    "DoctorInput",
    "SearchInput",
    "ListDocumentsInput",
    "ConvertPdfInput",
    "InitShelfInput",
    "NotAShelfError",
    "add_document",
    "add_directory",
    "read_document",
    "remove_document",
    "rename_document",
    "rebuild_index",
    "doctor",
    "search",
    "list_documents",
    "convert_pdf",
    "init_shelf",
]


class NotAShelfError(Exception):
    """A shelf tool was pointed at a directory that isn't an initialized shelf.

    Raised by :func:`_resolve_shelf` so tools never silently scaffold a shelf
    in whatever directory the server happens to be running in. ``init_shelf``
    (the scaffolder) and ``convert_pdf`` (no shelf) don't resolve a shelf, so
    they are unaffected.
    """


def _resolve_shelf(shelf_path: str | None) -> Shelf:
    """Resolve the target shelf, requiring it to already be initialized.

    Raises:
        NotAShelfError: The resolved root has no ``.docshelf.json``.
    """
    shelf = Shelf(Path(shelf_path).expanduser() if shelf_path else default_shelf_root())
    if not (shelf.root / SHELF_METADATA_FILENAME).is_file():
        raise NotAShelfError(
            f"{shelf.root} is not an initialized docshelf "
            f"(no {SHELF_METADATA_FILENAME}). Run init_shelf to create a shelf "
            f"there, or set DOCSHELF_ROOT / pass shelf_path to point at an "
            f"existing shelf."
        )
    return shelf


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
        description="Absolute path to the source file. Supported: .md, .pdf, "
        ".docx, .html/.htm, .epub (DOCX/HTML/EPUB need the matching extra, "
        "e.g. pip install 'docshelf-mcp[formats]').",
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
        "(slugified) as the filename unless 'slug' is given.",
        min_length=1,
        max_length=200,
    )
    slug: str | None = Field(
        default=None,
        description="Optional filename stem, decoupling the on-disk file from the "
        "display title. When set, the document is written to "
        "docs/<category>/<slug>.md (the slug is slugified for filesystem safety) "
        "while 'title' stays the INDEX/heading text untouched — e.g. a Cyrillic "
        "title at a latin, date-prefixed path like '2026-07-22-m1-build-sprint'. "
        "Defaults to deriving the filename from the title.",
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
    overwrite: bool = Field(
        default=False,
        description="Replace an existing document when a different title/category "
        "slugifies onto the same file path. Off by default so a slug collision "
        "can't silently destroy an earlier document — the call errors instead. "
        "Re-adding the same title is always an in-place update and needs no flag.",
    )
    shelf_path: str | None = Field(
        default=None,
        description="Path to the shelf root directory. Defaults to $DOCSHELF_ROOT "
        "or the server's working directory.",
    )


class AddDirectoryInput(_BaseInput):
    """Input for ``add_directory``."""

    source_dir: str = Field(
        ...,
        description="Directory to scan (non-recursive) for documents to add.",
        min_length=1,
    )
    category: str = Field(
        ...,
        description="Category bucket for every file found. Created if missing.",
        min_length=1,
        max_length=80,
    )
    patterns: list[str] = Field(
        default_factory=lambda: list(SUPPORTED_INPUT_GLOBS),
        description="Glob patterns to include. Defaults to every supported input "
        "type (Markdown, PDF, DOCX, HTML, EPUB).",
        max_length=16,
    )
    split: bool = Field(
        default=True,
        description="Auto-split large documents (>50 KB) by H2 heading.",
    )
    quality: Quality = Field(
        default="fast",
        description="PDF conversion quality: 'fast' (default) or 'high'.",
    )
    shelf_path: str | None = Field(
        default=None,
        description="Path to the shelf root directory. Defaults to $DOCSHELF_ROOT "
        "or the server's working directory.",
    )


class ReadDocumentInput(_BaseInput):
    """Input for ``read_document``."""

    relative_path: str = Field(
        ...,
        description="Path relative to the shelf root, as returned by search / "
        "list_documents (e.g. 'docs/routers/mikrotik/003-firewall.md').",
        min_length=1,
        max_length=1000,
    )
    max_bytes: int = Field(
        default=100_000,
        description="Maximum bytes to return. Larger files are truncated and the "
        "response sets truncated=true — page with 'offset' or read the "
        "individual split sections instead.",
        ge=1,
        le=5_000_000,
    )
    offset: int = Field(
        default=0,
        description="Byte offset to start reading from (for paging a large file). "
        "Use the previous response's 'next_offset' rather than offset+max_bytes — "
        "slices snap to UTF-8 character boundaries, so next_offset may differ.",
        ge=0,
    )
    shelf_path: str | None = Field(default=None)


class RemoveDocumentInput(_BaseInput):
    """Input for ``remove_document``."""

    category: str = Field(
        ...,
        description="Category the document lives in (same value as at add time).",
        min_length=1,
        max_length=80,
    )
    document: str = Field(
        ...,
        description="Filename ('foo.md'), slug ('foo'), or the human title "
        "used at add time.",
        min_length=1,
        max_length=200,
    )
    dry_run: bool = Field(
        default=False,
        description="If true, only report what would be removed — delete nothing.",
    )
    shelf_path: str | None = Field(
        default=None,
        description="Path to the shelf root directory. Defaults to $DOCSHELF_ROOT "
        "or the server's working directory.",
    )


class RenameDocumentInput(_BaseInput):
    """Input for ``rename_document``."""

    category: str = Field(
        ...,
        description="Current category the document lives in.",
        min_length=1,
        max_length=80,
    )
    document: str = Field(
        ...,
        description="Filename ('foo.md'), slug ('foo'), or current title.",
        min_length=1,
        max_length=200,
    )
    new_title: str | None = Field(
        default=None,
        description="New display title (re-slugifies the filename).",
        max_length=200,
    )
    new_category: str | None = Field(
        default=None,
        description="New category bucket. Created if missing.",
        max_length=80,
    )
    new_description: str | None = Field(
        default=None,
        description="New one-line description.",
        max_length=500,
    )
    dry_run: bool = Field(
        default=False,
        description="If true, report the planned move without touching anything.",
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


class DoctorInput(_BaseInput):
    fix: bool = Field(
        default=False,
        description="Apply the safe fixes (prune stale meta entries, delete "
        "orphaned split dirs, rebuild INDEX). Other findings stay report-only.",
    )
    shelf_path: str | None = Field(
        default=None, description="Path to the shelf root directory."
    )


class SearchInput(_BaseInput):
    query: str = Field(
        ...,
        description="Plain-text search query. Tokens are space-split; each "
        "must appear (case-insensitive) for a hit to count. If nothing "
        "matches all tokens, the search falls back to any-token matching "
        "and the response marks match_mode='any'.",
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
    # Keep the Literal in sync with indexer.URL_PROVIDERS (asserted in tests):
    # a typo'd provider must fail at the tool boundary, not render a link-less
    # INDEX with no warning (#67).
    provider: Literal["github", "gitlab", "gitea", "custom", "none"] = Field(
        default="github",
        description="URL provider for generated links: 'github' (default), "
        "'gitlab', 'gitea', 'custom' (uses url_template), or 'none' (relative "
        "links for offline/local shelves).",
    )
    url_template: str = Field(
        default="",
        description="For provider='custom': URL template with {owner}, {repo}, "
        "{branch}, {path} placeholders. Covers S3, R2, or any static host.",
        max_length=500,
    )
    manifest: bool = Field(
        default=False,
        description="Also scaffold a shelf.yml manifest (shelf-spec v0: "
        "spec_version 0.1, mode single, profile document) next to .docshelf.json, "
        "making the shelf conformant to openshelf's shelf-spec. Off by default; a "
        "shelf without one stays valid. Never overwrites an existing manifest.",
    )

    @model_validator(mode="after")
    def _custom_needs_template(self) -> InitShelfInput:
        if self.provider == "custom" and not self.url_template:
            raise ValueError(
                "provider 'custom' needs url_template with {owner}/{repo}/"
                "{branch}/{path} placeholders"
            )
        return self


# --------------------------------------------------------------- wrappers


def _warning_dict(w) -> dict:
    return {"index": w.index, "heading": w.heading, "rule": w.rule, "detail": w.detail}


def add_document(params: AddDocumentInput) -> dict:
    """Implementation of the ``add_document`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    result = shelf.add_document(
        params.source_path,
        category=params.category,
        title=params.title,
        slug=params.slug,
        description=params.description,
        split=params.split,
        quality=params.quality,
        overwrite=params.overwrite,
    )
    # Shelf.add_document already rebuilt INDEX.md — no second rebuild here.
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "document_path": result.document_path.relative_to(shelf.root).as_posix(),
        "section_paths": [
            p.relative_to(shelf.root).as_posix() for p in result.section_paths
        ],
        "was_split": result.was_split,
        "section_count": len(result.section_paths),
        "converted_from_pdf": result.converted_from_pdf,
        "overwritten": result.overwritten,
        "unsplit": result.unsplit,
        "warning_count": len(result.warnings),
        "warnings": [_warning_dict(w) for w in result.warnings],
        "index_path": "INDEX.md",
        "next_steps": (
            f"Commit the changes ('git add . && git commit -m \"docs: add {params.title}\"') "
            "to make the new entry visible via raw URLs."
        ),
    }


def add_directory(params: AddDirectoryInput) -> dict:
    """Implementation of the ``add_directory`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    results = shelf.add_directory(
        params.source_dir,
        category=params.category,
        pattern=params.patterns,
        split=params.split,
        quality=params.quality,
    )

    added, failed = [], []
    for r in results:
        if r["status"] == "ok":
            res = r["result"]
            added.append(
                {
                    "file": r["file"],
                    "document_path": res.document_path.relative_to(shelf.root).as_posix(),
                    "was_split": res.was_split,
                    "section_count": len(res.section_paths),
                    "warning_count": len(res.warnings),
                    "warnings": [_warning_dict(w) for w in res.warnings],
                }
            )
        else:
            failed.append({"file": r["file"], "error": r["error"]})

    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "category": params.category,
        "added_count": len(added),
        "failed_count": len(failed),
        "added": added,
        "failed": failed,
        "index_path": "INDEX.md",
        "next_steps": (
            "Commit the changes ('git add . && git commit') to publish the new "
            "entries via raw URLs."
        ),
    }


def read_document(params: ReadDocumentInput) -> dict:
    """Implementation of the ``read_document`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    result = shelf.read_document(
        params.relative_path, max_bytes=params.max_bytes, offset=params.offset
    )
    cfg = shelf.config
    url = cfg.url_for(result.relative_path)
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "relative_path": result.relative_path,
        "content": result.content,
        "size_bytes": result.size_bytes,
        "truncated": result.truncated,
        "next_offset": result.next_offset,
        "raw_url": url,
    }


def remove_document(params: RemoveDocumentInput) -> dict:
    """Implementation of the ``remove_document`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    result = shelf.remove_document(
        category=params.category,
        document=params.document,
        dry_run=params.dry_run,
    )
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "removed_paths": [
            p.relative_to(shelf.root).as_posix() for p in result.removed_paths
        ],
        "was_split": result.was_split,
        "dry_run": result.dry_run,
        "index_path": "INDEX.md",
        "next_steps": (
            "Nothing was deleted (dry run)."
            if result.dry_run
            else "Commit the removal ('git add -A && git commit') to update the "
            "published shelf. INDEX.md has already been regenerated."
        ),
    }


def rename_document(params: RenameDocumentInput) -> dict:
    """Implementation of the ``rename_document`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    result = shelf.rename_document(
        category=params.category,
        document=params.document,
        new_title=params.new_title,
        new_category=params.new_category,
        new_description=params.new_description,
        dry_run=params.dry_run,
    )
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "old_path": result.old_path,
        "new_path": result.new_path,
        "moved": result.moved,
        "was_split": result.was_split,
        "dry_run": result.dry_run,
        "index_path": "INDEX.md",
        "next_steps": (
            "Nothing was changed (dry run)."
            if result.dry_run
            else "Commit the move ('git add -A && git commit') to update the "
            "published shelf. INDEX.md has already been regenerated."
        ),
    }


def rebuild_index(params: RebuildIndexInput) -> dict:
    """Implementation of the ``rebuild_index`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    index_path = shelf.rebuild_index()
    entries = shelf.scan()
    warnings = [
        {"document": doc, **_warning_dict(w)}
        for doc, ws in shelf.lint_shelf().items()
        for w in ws
    ]
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "index_path": index_path.relative_to(shelf.root).as_posix(),
        "document_count": len(entries),
        "category_count": len({e.category for e in entries}),
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def doctor(params: DoctorInput) -> dict:
    """Implementation of the ``doctor`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    findings = shelf.doctor(fix=params.fix)
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "fix": params.fix,
        "finding_count": len(findings),
        "fixed_count": sum(1 for f in findings if f.fixed),
        "by_rule": by_rule,
        "findings": [
            {
                "rule": f.rule,
                "severity": f.severity,
                "path": f.path,
                "detail": f.detail,
                "suggested_fix": f.suggested_fix,
                "fixed": f.fixed,
            }
            for f in findings
        ],
    }


def search(params: SearchInput) -> dict:
    """Implementation of the ``search`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    hits = shelf.search(params.query, max_results=params.max_results)
    match_mode = "all"
    if not hits:
        # Over-specified query — retry requiring only some tokens, and say so.
        hits = shelf.search(params.query, max_results=params.max_results, mode="any")
        if hits:
            match_mode = "any"

    cfg = shelf.config
    enriched = []
    for h in hits:
        enriched.append({**h, "raw_url": cfg.url_for(h["relative_path"])})

    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "query": params.query,
        "match_mode": match_mode,
        "match_count": len(enriched),
        "hits": enriched,
    }


def list_documents(params: ListDocumentsInput) -> dict:
    """Implementation of the ``list_documents`` MCP tool."""
    shelf = _resolve_shelf(params.shelf_path)
    entries = shelf.scan()
    cfg = shelf.config

    # Match the filter against the *slugified* on-disk category, so the human
    # form ("Research Papers") finds the "research-papers" directory — and a
    # hand-created directory whose name isn't already a slug ("Mixed Case")
    # is matched too (slug-to-slug), not just the generated ones.
    from docshelf_mcp.core.slugify import slugify

    filter_slug = slugify(params.category, max_len=80) if params.category else None

    grouped: dict[str, list[dict]] = {}
    for e in entries:
        if filter_slug and slugify(e.category, max_len=80) != filter_slug:
            continue
        url = cfg.url_for(e.relative_path)
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
        provider=params.provider,
        url_template=params.url_template,
        manifest=params.manifest,
    )
    return {
        "status": "ok",
        "shelf_root": str(shelf.root),
        "name": shelf.config.name,
        "remote": shelf.config.remote,
        "branch": shelf.config.branch,
        "provider": shelf.config.provider,
        "categories": params.default_categories,
        "manifest": params.manifest,
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
