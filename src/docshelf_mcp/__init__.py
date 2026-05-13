"""docshelf-mcp — MCP server for managing AI-friendly document collections.

A document collection (`shelf`) is a git-tracked folder that:

* Holds source documents (PDF or Markdown) organized into categories.
* Auto-converts PDFs to Markdown and splits oversized files by H2 heading.
* Generates an `INDEX.md` navigation page with raw GitHub URLs so an LLM
  can fetch only the section it needs instead of swallowing the whole file.

Use `docshelf_mcp.server:main` (or the `docshelf-mcp` console script) to
launch the MCP server. Use `docshelf_mcp.core.shelf:Shelf` for direct
library access.
"""

from __future__ import annotations

from docshelf_mcp.core.shelf import Shelf

__version__ = "0.1.0"
__all__ = ["Shelf", "__version__"]
