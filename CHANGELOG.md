# Changelog

All notable changes to docshelf-mcp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docshelf_doctor` tool (+ `Shelf.doctor`) — check the shelf for drift
  (stale meta entries, orphaned split dirs, out-of-sync splits, stale
  index, duplicate titles, empty categories) and optionally apply the safe
  fixes with `fix=true`. (#10)
- Pluggable URL providers — `.docshelf.json` / `init_shelf` gain `provider`
  (`github` / `gitlab` / `gitea` / `custom` / `none`) and `url_template`,
  so GitLab/Gitea/S3/R2/any static host get correct links and offline
  shelves get relative ones. (#18)
- Suspicious-section-heading warnings during split / rebuild — `add_document`
  and `rebuild_index` responses carry `warnings` (`toc-leak`,
  `unit-fragment`, `table-residue`, `near-duplicate`); detection only. (#8)
- `docshelf_add_directory` tool (+ `Shelf.add_directory`) — add every
  PDF/Markdown in a folder in one call, rebuilding INDEX.md once and
  reporting per-file success/failure. (#11)
- `docshelf_read_document` tool (+ `Shelf.read_document`) — read a
  document/section's content directly over MCP (with byte-range paging and
  `docs/`-scoped path safety), so private/local shelves work end-to-end,
  not just public ones. (#9)
- `docshelf_remove_document` tool (+ `Shelf.remove_document`) — deletes a
  document, its split-section directory, and its `.meta.json` entry, then
  regenerates INDEX.md. Supports `dry_run`. (#4)
- Per-document `SUBINDEX.md` for split documents — the INDEX → SUBINDEX →
  section navigation the docs always described. New `.docshelf.json` keys:
  `index_style` (`"auto"` / `"inline"` / `"subindex"`) and
  `subindex_threshold_sections` (default 10). (#3)
- `search` responses now include `match_mode` (`"all"` or `"any"`). (#2)

### Fixed
- Adding a document no longer rebuilds INDEX.md twice (the tools layer no
  longer re-runs a rebuild that `Shelf.add_document` already did). (#11)
- The splitter is now **fence-aware**: `## ` / `# ` lines inside fenced
  code blocks (```` ``` ````/`~~~`) are no longer counted as headings,
  used as split boundaries, or demoted by the fake-H1 heuristic — so CLI
  dumps and config exports are no longer split mid-block or mangled. (#5)
- `raw_github_url` now handles repo names containing dots
  (`github.com/me/my.repo`), correctly strips a trailing `.git` on the
  https form, and percent-encodes path segments. (#6)
- `docshelf_search` now honours its documented AND semantics: every query
  token must appear for a hit to count, with an automatic any-token
  fallback when nothing matches all tokens. (#2)
- `docshelf_mcp.__version__` reported `0.1.0` while the package was
  `0.2.0`. The version is now single-sourced from `__init__.py` via
  hatch's dynamic version. (#1)

### Changed
- Every shelf tool except `docshelf_init_shelf` / `docshelf_convert_pdf`
  now fails fast with a `NotAShelfError` when the resolved root is not an
  initialized shelf, instead of silently scaffolding one in the wrong
  directory. (#7)
- `Shelf.add_document` gained a `rebuild_index` flag (default `True`) so
  batch callers can defer the index rebuild. (#11)

### CI / packaging
- CI now tests Python 3.13 and runs a smoke job on Windows and macOS, and
  enforces a test-coverage floor (`--cov-fail-under=85`). (#12)
- Added Dependabot (github-actions + pip, weekly) and shipped a `py.typed`
  marker so downstream type checkers honour the inline annotations. (#12)

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
