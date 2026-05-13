# Changelog

All notable changes to docshelf-mcp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-13

Initial public release.

### Added
- `init_shelf` tool — bootstrap a new shelf directory.
- `add_document` tool — PDF/Markdown ingestion with auto-split and INDEX
  regeneration.
- `rebuild_index` tool — regenerate `INDEX.md` from on-disk state.
- `search` tool — plain-text grep with raw-URL enrichment.
- `list_documents` tool — categorized catalogue with size & section counts.
- `convert_pdf` tool — standalone PDF → Markdown utility.
- `pymupdf4llm` as the default conversion engine; optional `marker-pdf`
  via `pip install docshelf-mcp[high-quality]`.
- `Shelf` class for direct library use (no MCP needed).
- Test suite (slugify, splitter, indexer, shelf, tool smoke).
- GitHub Actions CI (ruff + pytest on Python 3.10–3.12).
- Three example shelves: homelab, recipes, research-papers.

### Notes
- Origin: this tool started life as a private script
  (`outputs/homelab-encyclopedia.py`) that managed a homelab manuals repo.
  v0.1.0 is the first generalised, course-agnostic release.
