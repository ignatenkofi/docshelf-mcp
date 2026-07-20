"""FastMCP server entry point.

Run from a terminal::

    docshelf-mcp

Or from a Python module::

    python -m docshelf_mcp

The server uses **stdio transport** (the default for FastMCP) so it plugs
straight into a Claude Desktop ``mcpServers`` configuration. See README.md
for the exact JSON snippet.

Every tool wraps a helper in :mod:`docshelf_mcp.tools` — keep tool logic
out of this file, and you can unit-test the helpers without spinning up MCP.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import FunctionResource
from pydantic import AnyUrl

from docshelf_mcp import __version__
from docshelf_mcp import tools as t
from docshelf_mcp.config import default_shelf_root
from docshelf_mcp.core.shelf import SHELF_METADATA_FILENAME, Shelf, _utf8_safe_bounds

__all__ = ["mcp", "main", "register_shelf_resources"]


logger = logging.getLogger("docshelf_mcp")


mcp = FastMCP("docshelf_mcp")


# --------------------------------------------------------------- resources

#: URI scheme for shelf files exposed as MCP resources, e.g.
#: ``docshelf:///docs/routers/mikrotik/003-firewall.md``.
_RESOURCE_SCHEME = "docshelf"
#: Cap a resource payload so a giant datasheet can't blow up a context window.
_RESOURCE_MAX_BYTES = 1_000_000


def _resource_uri(relative_path: str) -> str:
    return f"{_RESOURCE_SCHEME}:///{relative_path}"


def _read_shelf_file(shelf: Shelf, relative_path: str) -> str:
    """Read a shelf file for a resource, capped and confined to the shelf root.

    The cap is snapped to a UTF-8 character boundary (#68 — the naive byte
    slice decoded a straddling multibyte character as U+FFFD, same defect #30
    fixed for ``read_document``), and a truncated read says so instead of
    silently ending at exactly the cap.
    """
    root = shelf.root.resolve()
    target = (shelf.root / relative_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"resource not available: {relative_path!r}")
    data = target.read_bytes()
    if len(data) <= _RESOURCE_MAX_BYTES:
        return data.decode("utf-8", errors="replace")
    start, end = _utf8_safe_bounds(data, 0, _RESOURCE_MAX_BYTES)
    return (
        data[start:end].decode("utf-8", errors="replace")
        + f"\n\n[docshelf: truncated at {_RESOURCE_MAX_BYTES} bytes — use the "
        "docshelf_read_document tool with paging for the rest]\n"
    )


def _add_file_resource(shelf: Shelf, relative_path: str, *, title: str) -> None:
    mcp.add_resource(
        FunctionResource(
            uri=AnyUrl(_resource_uri(relative_path)),
            name=relative_path,
            title=title,
            description=f"Shelf file {relative_path}",
            mime_type="text/markdown",
            fn=lambda rp=relative_path: _read_shelf_file(shelf, rp),
        )
    )


def register_shelf_resources(shelf: Shelf | str | None = None) -> int:
    """(Re)register one read-only MCP resource per shelf file and return the count.

    Exposes ``INDEX.md`` plus every document and split section under ``docs/`` as
    ``docshelf:///<relative-path>`` resources, so an MCP client can browse and
    attach them natively (content is read fresh, capped, and confined to the
    shelf). The set reflects the shelf at call time; it is re-synced on server
    start and after each mutating tool call. Previously-registered ``docshelf:``
    resources are cleared first, so removed documents drop out.
    """
    if shelf is None:
        shelf = Shelf(default_shelf_root())
    elif not isinstance(shelf, Shelf):
        shelf = Shelf(shelf)

    manager = mcp._resource_manager
    for uri in [u for u in list(manager._resources) if str(u).startswith(f"{_RESOURCE_SCHEME}:")]:
        del manager._resources[uri]

    # Only an initialized shelf has resources to expose.
    if not (shelf.root / SHELF_METADATA_FILENAME).is_file():
        return 0

    count = 0
    if (shelf.root / "INDEX.md").is_file():
        _add_file_resource(shelf, "INDEX.md", title=f"{shelf.config.name} — INDEX")
        count += 1
    for entry in shelf.scan():
        _add_file_resource(shelf, entry.relative_path, title=entry.title)
        count += 1
        for section in entry.section_paths:
            _add_file_resource(
                shelf, section, title=f"{entry.title} — {Path(section).name}"
            )
            count += 1
    return count


def _sync_resources_safe(shelf_path: str | None) -> None:
    """Re-sync resources for ``shelf_path`` after a mutating tool; never raises."""
    try:
        register_shelf_resources(Path(shelf_path).expanduser() if shelf_path else None)
    except Exception:  # noqa: BLE001 — resource sync must not break a tool call
        logger.debug("resource re-sync skipped", exc_info=True)


def _serialize(payload: Any) -> str:
    return t.to_json(payload)


def _error_response(exc: Exception, tool: str) -> str:
    """Serialize an exception as the standard error dict.

    Expected user errors (e.g. targeting a non-shelf) log a one-line warning;
    everything else logs a full traceback for debugging.
    """
    if isinstance(exc, t.NotAShelfError):
        logger.warning("%s: %s", tool, exc)
    else:
        logger.exception("%s failed", tool)
    return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


@mcp.tool(
    name="docshelf_init_shelf",
    annotations={
        "title": "Initialize a document shelf",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def init_shelf(params: t.InitShelfInput) -> str:
    """Bootstrap a new document shelf at ``shelf_path``.

    Creates the directory layout (``docs/``, ``INDEX.md``, ``.docshelf.json``,
    ``.gitignore``), pre-creates any ``default_categories``, and stores the
    ``github_remote`` so generated INDEX entries link to raw GitHub URLs.

    Idempotent — safe to call on an existing shelf to update metadata.
    """
    try:
        payload = t.init_shelf(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "init_shelf")


@mcp.tool(
    name="docshelf_add_document",
    annotations={
        "title": "Add a document to the shelf",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def add_document(params: t.AddDocumentInput) -> str:
    """Add a PDF or Markdown file to the shelf and refresh INDEX.md.

    * ``.pdf`` is converted to Markdown (``pymupdf4llm`` by default; pass
      ``quality='high'`` to use ``marker-pdf``).
    * Documents larger than 50 KB with multiple H2 headings are split into
      one file per section (turn this off with ``split=False``).
    * If a *different* title/category slugifies onto a path an existing
      document already occupies, the call errors instead of overwriting it —
      pass ``overwrite=true`` to replace it. Re-adding the same title updates
      in place. The response reports ``overwritten``.
    * The response ``warnings`` include suspicious section headings and an
      ``empty-conversion`` warning when the source yields little or no text
      (e.g. a scanned / image-only PDF — consider ``quality='high'`` / OCR).
    * INDEX.md is regenerated automatically. The caller still owns the git
      commit / push step.
    """
    try:
        payload = t.add_document(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "add_document")


@mcp.tool(
    name="docshelf_add_directory",
    annotations={
        "title": "Add every document in a directory",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def add_directory(params: t.AddDirectoryInput) -> str:
    """Add every matching file in a directory, rebuilding INDEX.md once.

    Scans ``source_dir`` (non-recursively) for ``patterns`` — every supported
    input type by default (Markdown, PDF, DOCX, HTML, EPUB) — adds each under
    ``category`` with a title derived from its filename, and regenerates
    INDEX.md a single time. A corrupt or unreadable file is reported in
    ``failed`` without aborting the batch.
    """
    try:
        payload = t.add_directory(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "add_directory")


@mcp.tool(
    name="docshelf_read_document",
    annotations={
        "title": "Read a document or section",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def read_document(params: t.ReadDocumentInput) -> str:
    """Read a document or section file from inside the shelf's ``docs/``.

    Returns the file content directly over MCP — useful for private or
    purely-local shelves where the ``raw.githubusercontent.com`` fetch
    trick doesn't apply. Pass a ``relative_path`` from ``search`` /
    ``list_documents``. Large files are truncated to ``max_bytes`` (default
    100 KB) with ``truncated: true``; page with the returned ``next_offset``
    (slices snap to UTF-8 character boundaries, so it may differ from
    ``offset + max_bytes`` — using it avoids splitting a multibyte character)
    or read the individual split sections. Paths that escape ``docs/`` are
    rejected.
    """
    try:
        return _serialize(t.read_document(params))
    except Exception as exc:
        return _error_response(exc, "read_document")


@mcp.tool(
    name="docshelf_remove_document",
    annotations={
        "title": "Remove a document from the shelf",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def remove_document(params: t.RemoveDocumentInput) -> str:
    """Remove a document — its file, split sections, and metadata entry.

    Accepts the filename, the slug, or the human title used at add time.
    INDEX.md is regenerated automatically. Pass ``dry_run=true`` to see
    what would be deleted without touching anything. The caller still owns
    the git commit / push step.
    """
    try:
        payload = t.remove_document(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "remove_document")


@mcp.tool(
    name="docshelf_rename_document",
    annotations={
        "title": "Rename or move a document",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def rename_document(params: t.RenameDocumentInput) -> str:
    """Retitle, recategorize, or re-describe a document — no re-conversion.

    Moves the document ``.md``, its split-section directory, and its
    ``.meta.json`` entry (changing the slug when the title changes, or the
    directory when the category changes), then regenerates INDEX.md. Give at
    least one of ``new_title`` / ``new_category`` / ``new_description``. Refuses
    to clobber an existing target. Pass ``dry_run=true`` to preview. The caller
    still owns the git commit / push step.
    """
    try:
        payload = t.rename_document(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "rename_document")


@mcp.tool(
    name="docshelf_rebuild_index",
    annotations={
        "title": "Rebuild INDEX.md",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def rebuild_index(params: t.RebuildIndexInput) -> str:
    """Regenerate ``INDEX.md`` from the current on-disk shelf state.

    Useful after manual edits to ``docs/`` or ``.docshelf.json``.
    """
    try:
        payload = t.rebuild_index(params)
        _sync_resources_safe(params.shelf_path)
        return _serialize(payload)
    except Exception as exc:
        return _error_response(exc, "rebuild_index")


@mcp.tool(
    name="docshelf_doctor",
    annotations={
        "title": "Check shelf integrity",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def doctor(params: t.DoctorInput) -> str:
    """Check the shelf for drift and optionally apply the safe fixes.

    Reports stale `.meta.json` entries, orphaned split directories, split
    sections out of sync with their parent, a stale `INDEX.md`, duplicate
    titles, and empty categories. Read-only by default; pass ``fix=true`` to
    prune stale meta entries, delete orphaned split dirs, and rebuild the
    index (other findings stay report-only). Findings are sorted for stable
    diffing.
    """
    try:
        return _serialize(t.doctor(params))
    except Exception as exc:
        return _error_response(exc, "doctor")


@mcp.tool(
    name="docshelf_search",
    annotations={
        "title": "Search the shelf",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def search(params: t.SearchInput) -> str:
    """Plain-text search across every Markdown file in the shelf.

    Tokens are space-split; each must appear (case-insensitive) for a hit
    to count. If no file contains all tokens, the search falls back to
    any-token matching and the response reports ``match_mode: "any"``.
    Heading/title matches are ranked above body-only matches, and for a
    split document the section files are returned rather than the
    whole-file parent. Results include the relative path, a
    word-boundary-trimmed snippet, and — if a remote is configured — the
    fetch URL so the model can pull the matching file directly.
    """
    try:
        return _serialize(t.search(params))
    except Exception as exc:
        return _error_response(exc, "search")


@mcp.tool(
    name="docshelf_list_documents",
    annotations={
        "title": "List shelf documents",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def list_documents(params: t.ListDocumentsInput) -> str:
    """List documents grouped by category.

    Pass a ``category`` to filter; omit it to list everything.
    """
    try:
        return _serialize(t.list_documents(params))
    except Exception as exc:
        return _error_response(exc, "list_documents")


@mcp.tool(
    name="docshelf_convert_pdf",
    annotations={
        "title": "Convert a PDF to Markdown",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def convert_pdf(params: t.ConvertPdfInput) -> str:
    """Standalone PDF → Markdown conversion (no shelf, no INDEX update).

    Use when you want the converted file but don't yet want to commit it
    to a shelf. Optionally splits the result by H2.
    """
    try:
        return _serialize(t.convert_pdf(params))
    except Exception as exc:
        return _error_response(exc, "convert_pdf")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docshelf-mcp",
        description=(
            "MCP server for AI-friendly document shelves. Run with no "
            "arguments to start the stdio server (the default for Claude "
            "Desktop / Claude Code). Tools: init_shelf, add_document, "
            "add_directory, read_document, remove_document, rename_document, "
            "rebuild_index, doctor, search, list_documents, convert_pdf."
        ),
        epilog="Docs: https://github.com/ignatenkofi/docshelf-mcp",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"docshelf-mcp {__version__}",
    )
    parser.add_argument(
        "--shelf",
        metavar="PATH",
        help="Default shelf root for this run (sets DOCSHELF_ROOT).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Console-script entry point.

    With no arguments (the common case — Claude Desktop / Code spawn it bare)
    this launches the stdio MCP server. ``--version`` / ``--help`` print and
    exit; ``--shelf PATH`` sets the default shelf root before starting.
    """
    args = _build_parser().parse_args(argv)
    if args.shelf:
        os.environ["DOCSHELF_ROOT"] = args.shelf

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logger.info("Starting docshelf-mcp %s", __version__)
    # Expose the default shelf's files as MCP resources (best-effort; a missing
    # or non-shelf DOCSHELF_ROOT just yields none). Tool calls re-sync after.
    try:
        n = register_shelf_resources()
        if n:
            logger.info("Registered %d shelf resource(s)", n)
    except Exception:  # noqa: BLE001 — never block startup on resource sync
        logger.debug("initial resource registration skipped", exc_info=True)
    mcp.run()


if __name__ == "__main__":
    main()
