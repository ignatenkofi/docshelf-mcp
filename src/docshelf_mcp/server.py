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

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from docshelf_mcp import __version__
from docshelf_mcp import tools as t

__all__ = ["mcp", "main"]


logger = logging.getLogger("docshelf_mcp")


mcp = FastMCP("docshelf_mcp")


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
        return _serialize(t.init_shelf(params))
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
    * INDEX.md is regenerated automatically. The caller still owns the git
      commit / push step.
    """
    try:
        return _serialize(t.add_document(params))
    except Exception as exc:
        return _error_response(exc, "add_document")


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
        return _serialize(t.remove_document(params))
    except Exception as exc:
        return _error_response(exc, "remove_document")


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
        return _serialize(t.rebuild_index(params))
    except Exception as exc:
        return _error_response(exc, "rebuild_index")


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
    Results include the relative path, a 200-char snippet, and — if a
    GitHub remote is configured — the raw URL so the model can fetch the
    matching file directly.
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


def main() -> None:
    """Console-script entry point — launches the stdio server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting docshelf-mcp %s", __version__)
    mcp.run()


if __name__ == "__main__":
    main()
