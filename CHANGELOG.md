# Changelog

All notable changes to docshelf-mcp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docshelf_remove_document` tool (+ `Shelf.remove_document`) — deletes a
  document, its split-section directory, and its `.meta.json` entry, then
  regenerates INDEX.md. Supports `dry_run`. (#4)
- Per-document `SUBINDEX.md` for split documents — the INDEX → SUBINDEX →
  section navigation the docs always described. New `.docshelf.json` keys:
  `index_style` (`"auto"` / `"inline"` / `"subindex"`) and
  `subindex_threshold_sections` (default 10). (#3)
- `search` responses now include `match_mode` (`"all"` or `"any"`). (#2)

### Fixed
- `docshelf_search` now honours its documented AND semantics: every query
  token must appear for a hit to count, with an automatic any-token
  fallback when nothing matches all tokens. (#2)
- `docshelf_mcp.__version__` reported `0.1.0` while the package was
  `0.2.0`. The version is now single-sourced from `__init__.py` via
  hatch's dynamic version. (#1)

## [0.2.0] — 2026-05-14

Documentation, distribution, and community-onboarding pass. No runtime
changes — the library and MCP tools are byte-identical to v0.1.0.

### Added
- `docs/PROJECT_PROMPT.md` — ready-to-use AI prompts (short / medium / full)
  for projects that consume a docshelf via `INDEX.md`. Includes how-to
  snippets for Claude Project, Claude Code, Claude Desktop, and the
  Anthropic API.
- `.github/workflows/release.yml` — tag-triggered release workflow:
  builds sdist + wheel, publishes to PyPI via **trusted publishing**
  (OIDC, no API tokens), and creates a GitHub Release with the
  matching CHANGELOG entry attached.
- `docs/community/` — submission materials for OSS distribution:
  - `awesome-mcp-pr.md` — one-liner for the `awesome-mcp-servers` registry.
  - `smithery-listing.md` — Smithery (smithery.ai) submission draft.
  - `reddit-show-hn.md` — Reddit (`/r/ClaudeAI`, `/r/mcp`) and Show HN
    announcement drafts.
- README: new **📋 Project Prompt** section linking to `docs/PROJECT_PROMPT.md`.
- README: PyPI install badge placeholder.

### Changed
- `pyproject.toml` — version bumped to `0.2.0`.
- README install section expanded with the PyPI command + the git-source
  fallback for users on `main`.

### Notes
- First PyPI release will be cut by pushing the `v0.2.0` tag. The trusted
  publisher needs to be configured once on the PyPI side
  (`https://pypi.org/manage/account/publishing/` → add this repo, env name
  `pypi`, workflow file `release.yml`).

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
