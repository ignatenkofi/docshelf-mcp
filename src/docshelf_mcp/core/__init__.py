"""Core building blocks: PDF conversion, splitting, indexing, shelf state."""

from docshelf_mcp.core.shelf import Shelf
from docshelf_mcp.core.slugify import slugify

__all__ = ["Shelf", "slugify"]
