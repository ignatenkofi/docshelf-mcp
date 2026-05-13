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
        logger.exception("init_shelf failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


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
        logger.exception("add_document failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


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
        logger.exception("rebuild_index failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


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
    to count. Results include the relative path, a 200-char snippet, and —
    if a GitHub remote is configured — the raw URL so the model can fetch
    the matching file directly.
    """
    try:
        return _serialize(t.search(params))
    except Exception as exc:
        logger.exception("search failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


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
        logger.exception("list_documents failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


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
        logger.exception("convert_pdf failed")
        return _serialize({"status": "error", "error": str(exc), "type": type(exc).__name__})


def main() -> None:
    """Console-script entry point — launches the stdio server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting docshelf-mcp %s", __version__)
    mcp.run()


if __name__ == "__main__":
    main()
