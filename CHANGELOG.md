# Changelog

All notable changes to docshelf-mcp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- A shape-invalid `.meta.json` (valid JSON, wrong shape — e.g. a bare-string
  entry or a list top level) no longer crashes `scan_shelf` and every tool on
  top of it, including `doctor`. The scan coerces what it can (a bare string
  becomes the title, non-string fields are dropped) and `doctor` reports the
  deviation via the new `meta-shape` rule instead of dying. (#65)
- `rename_document` pre-flights the split-directory target: renaming onto an
  existing (e.g. orphaned) split dir now fails cleanly before disk is
  touched, and a mid-move failure rolls the parent `.md` back — no more
  half-renamed shelves. (#66)
- An unknown `provider` (or `custom` without `url_template`) is rejected at
  `init_shelf` / `Shelf.init` instead of silently rendering a link-less
  INDEX; `doctor` flags a hand-edited config via the new `unknown-provider` /
  `custom-without-template` rules. (#67)
- MCP resource reads snap the 1 MB cap to a UTF-8 character boundary (the
  same defect #30 fixed for `read_document`) and append a truncation notice,
  so an oversized file no longer ends in U+FFFD mid-character with no hint
  that more exists. (#68)

### Added
- `docshelf_rename_document` tool (+ `Shelf.rename_document`) — retitle,
  recategorize, or re-describe a document without re-adding it. Moves the
  `.md`, its split-section directory, and its `.meta.json` entry (no
  re-conversion), refuses to clobber an existing target, and supports
  `dry_run`. (#34)
- Shelf files are now exposed as read-only **MCP resources**
  (`docshelf:///<path>` for `INDEX.md` and every document / split section),
  so MCP clients can browse and attach them natively. The set is synced on
  server start and after each mutating tool call; content is read fresh,
  size-capped, and confined to the shelf. (#35)
- The `github` URL provider now also covers **GitHub Enterprise Server**: a
  self-hosted `github.<company>.com` remote gets the GHES raw form
  (`https://<host>/<owner>/<repo>/raw/<branch>/<path>`); `github.com` is
  unchanged. (#36)
- `add_document` / `add_directory` now emit an `empty-conversion` warning
  when a source converts to little or no text (e.g. a scanned / image-only
  PDF), so a silent empty document is visible; the file is still written.
  `add_directory` responses carry per-file `warnings`. (#33)
- **Measured demo + benchmark** — [`docs/demo.md`](docs/demo.md) quantifies
  the token savings on two real shelves (24 hardware manuals; a full novel),
  with a reproducible [`benchmarks/token_savings.py`](benchmarks/token_savings.py)
  you can run on any shelf. (#15)
- Ingest **DOCX / HTML / EPUB** in addition to PDF/Markdown, via a
  suffix-dispatched converter with deferred imports and new optional
  extras (`[docx]`, `[html]`, `[epub]`, `[formats]`). (#16)
- Console script now has real CLI args: `--version`, `--help`, and
  `--shelf PATH` (sets `DOCSHELF_ROOT`); bare invocation still starts the
  stdio server. (#13)
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
- EPUB ingestion now assembles chapters in **spine (reading) order** instead
  of manifest order, and skips the navigation / cover documents, so a book
  whose manifest differs from its spine no longer comes out shuffled. (#29)
- `read_document` slices now snap to **UTF-8 character boundaries**, so
  truncation and `offset` paging never emit replacement characters (`�`) on
  non-ASCII shelves; responses carry a `next_offset` to page losslessly. (#30)
- `list_documents` category filter matches slug-to-slug, so a hand-created
  category directory whose name isn't already a slug (e.g. `Mixed Case`) is
  found by its human form. (#31)
- `search` no longer re-reads the whole shelf on every call: file contents are
  cached in-process keyed by `(mtime, size)`, and the base + heading-boost
  counts are gathered in a single pass. (#37)
- Shelf metadata and index writes (`INDEX.md`, `SUBINDEX.md`,
  `.docshelf.json`, `.meta.json`) are now **atomic** (temp file + `fsync` +
  `os.replace`), so an interrupted write — kill, full disk, power loss — can
  no longer leave a truncated file that silently resets config or drops every
  title override. (#32)
- `add_document` no longer silently overwrites a document when a *different*
  title/category slugifies onto the same file path — it raises
  `DocumentExistsError` instead (pass `overwrite=True` to replace on purpose;
  the response reports `overwritten`). Re-adding the same title is still an
  in-place update. Prevents silent data loss on slug collisions. (#28)
- Search quality: split documents return their section files instead of the
  whole-file parent, heading/title matches rank above body-only matches,
  snippets snap to word boundaries, and `list_documents`' category filter
  accepts the human form (`"Research Papers"` → `research-papers`). (#14)
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
