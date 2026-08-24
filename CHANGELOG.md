# Changelog

All notable changes to docshelf-mcp will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] — 2026-08-24

### Fixed
- **`doctor` no longer prescribes an action that publishes dead links** (#97).
  The `stale-index` finding compared `INDEX.md` on disk against a render of the
  *working tree* — and `scan()` walks the filesystem, so split directories that
  git does not track counted as shelf content. On a shelf whose caller commits
  the document path alone, the two sides of that comparison are structurally
  different trees: no rebuild can make them equal, the warning returns with the
  next render from the committed tree, and following the prescribed
  `run rebuild_index` writes INDEX links to files no other checkout has.
  Measured on the reproduction: 6 INDEX lines pointing into a directory with
  `git ls-files` returning 0 paths.

  Such sections are now reported as `uncommitted-split-dir`, naming the actual
  choice (commit them, or drop them and re-add with `split=False`). While the
  finding is present, `stale-index` is not raised and `fix=True` does not
  rebuild the index. A shelf that committed its sections, and a shelf that is
  not a git repository, are unaffected — and an index that has simply fallen
  behind is still `stale-index` with `run rebuild_index`, as before.

  The one git call this needs is a read (`git ls-files`), in the new
  `core.gitstate`; docshelf still never stages, commits or pushes.

## [0.4.0] — 2026-08-04

### Added
- **The PDF path finally has a test that converts a PDF.** Until now the suite
  touched PDFs only through invalid ones (`not a pdf` written to a `.pdf`
  name), which exercises the error branch and says nothing about conversion —
  the package's headline feature was verified by nothing. `test_converter.py`
  now generates a two-page PDF with PyMuPDF and asserts the Markdown carries
  text from *both* pages plus the heading level derived from font size.

  That gap mattered more than it looked: `pymupdf4llm` was pinned `>=0.0.17`
  with no ceiling and upstream has since moved to 1.x, so a breaking change in
  it would have reached users without CI noticing. The contract bug below was
  found on the first run of the new test.

- **CI conformance stage against shelf-spec** (#64, shelf-spec ADR-0005):
  `conformance.yml` scaffolds a fresh shelf with docshelf-mcp's own tools and
  runs `shelf-spec validate --ci` on it, so format drift between the
  reference implementation and the spec surfaces on PRs. Advisory while the
  spec is v0; skips explicitly (and stays green) when the `SHELF_SPEC_TOKEN`
  secret is absent, instead of failing the install under `continue-on-error`
  and looking covered while validating nothing. The committed candidate
  manifest `tests/fixtures/conformance.shelf.yml` stands in until `init`
  emits a `shelf.yml` itself.

- **Failure-path tests for the DOCX/HTML/EPUB backends**, which had none — the
  suite covered only successful conversions, so the contract breakage fixed
  below had nothing to trip over. Eleven tests: five backend failure shapes,
  the double-wrap guard on the shared HTML helper, the `FileNotFoundError`
  boundary, and the marker dependency case.

  Nine of them stub the backend rather than importing it. That is not a
  concession to bare containers: a stub is the only way to make a *healthy*
  backend fail on demand, and it keeps the contract under test where the
  optional extras aren't installed — `importorskip` there hands back a green
  run that verified nothing. Two more run against real mammoth and ebooklib,
  proving the stubs model failures that actually happen.

### Changed
- **The `pymupdf4llm` ceiling could not fire, and that is the same defect the
  ceilings exist to prevent.** The pin was `>=1.0,<2` — but this package does
  not use semver: it went `0.3.4` → `1.27.2.1`, adopting PyMuPDF's version
  numbers wholesale. Its breaking changes therefore ride in the *minor*
  position, and the major only moves when PyMuPDF's does. A `<2` bound could
  not have blocked anything pymupdf4llm actually does. Now `<1.29` (installed:
  1.28.0), so each minor bump arrives as a dependabot PR judged by the PDF
  conversion test. Found by an adversarial read of this branch's own diff.

- **Every optional extra got a major ceiling — the `mcp>=1.2.0` mistake was
  still live in five more places.** The core dependencies were bounded earlier
  in this release; the extras were not, and two of them already admitted a
  *released* breaking major: `marker-pdf>=1.0.0` while marker-pdf 2.0.0 is on
  PyPI, and `markdownify>=0.11` after that package crossed to 1.x. A fresh
  `pip install 'docshelf-mcp[high-quality]'` therefore pulled a major this code
  has never run against. Now `marker-pdf>=1.0.0,<2`, `mammoth>=1.6,<2`,
  `markdownify>=0.11,<2`, `ebooklib>=0.18,<1`, `python-docx>=1.1,<2`.

  Floors are deliberately left alone: raising them is a separate decision, and
  the declared floor being older than what CI actually installs is a different
  problem from the one fixed here. Dev tooling (`pytest`, `ruff`) is also left
  uncapped on purpose — a ruff release that adds lints *should* surface as a
  red dependabot PR rather than be silently excluded.

- **`quality='high'` no longer reports an incompatible marker-pdf as a missing
  one.** Both arrive as `ImportError`, and the handler answered both with
  "marker-pdf is required ... but is not installed. Install it with: pip
  install marker-pdf" — advice that cannot work when the package *is*
  installed: the install succeeds, the message repeats, and the real cause
  stays hidden. The two cases are now told apart with `find_spec`, and the
  mismatch branch names the installed version and quotes the underlying
  `ImportError`. Directly downstream of the missing ceiling above: environments
  resolved before this release still carry marker-pdf 2.x.

- **Ported the server to MCP SDK 2.x** (#83). `FastMCP`
  (`mcp.server.fastmcp`) became `MCPServer` (`mcp.server.mcpserver`) in
  2.0.0; the decorators, `add_resource` and `FunctionResource` carried over
  unchanged, and `FunctionResource.uri` became a plain `str` where 1.x
  required `AnyUrl`. The pin moves to `mcp>=2.0.0,<3` — a **floor**, not just
  a raised ceiling, because a 1.x install now fails at import — and the
  dependabot `ignore` rule for mcp majors is gone, since it existed only to
  stop the proposal that this change answers.

  The client side of `tests/test_stdio_protocol.py` moved with it:
  `read_timeout_seconds` takes float seconds instead of a `timedelta`, and
  the result models are snake_case (`server_info`, `is_error`). Judged by
  that protocol run, not by the import smoke check — after the three
  `server.py` edits alone the module imported and the server started while
  registering **zero** resources, which every in-process test happily missed.

  Release note: this is a **breaking** change for installers — an environment
  pinned to `mcp<2` can no longer resolve this package. The next release is a
  minor bump (0.4.0), not a patch. Releasing it is also the fix for #88: the
  published 0.3.0 declares `mcp>=1.2.0` with no ceiling and does not start on
  a fresh install today.

- **Ceilings by major on every runtime dependency** (`pydantic<3`,
  `pymupdf4llm<2`, `pyyaml<7`), for the reason the mcp pin already had one: an
  unbounded `>=X` silently admits a breaking major and the only signal is a
  user's traceback. `pymupdf4llm`'s floor moves to `1.0` — the 0.0.x line is a
  different major, two years old, and was never covered by a test.

### Fixed
- **A failing conversion escaped as the backend's own exception.**
  `pdf_to_markdown`'s docstring promises `ConversionError` "if the requested
  engine is missing or fails", and only the *missing* half was true: a damaged
  or mislabelled PDF surfaced as `pymupdf.FileDataError`, so a caller following
  the documented contract never caught it. Both engines now wrap their failure,
  chaining the cause so the backend detail is one `__cause__` away.

- **The same broken promise, in the three backends the PDF fix did not reach.**
  `source_to_markdown` makes the identical guarantee ("the backend is
  missing/fails" → `ConversionError`), and only its *missing* half was true for
  DOCX/HTML/EPUB: mammoth's `zipfile.BadZipFile` on a mislabelled file,
  ebooklib's `EpubException` on a corrupt archive, an unreadable HTML source's
  `IsADirectoryError`, and markdownify's own errors all escaped raw. In a
  directory scan that is the difference between one document being skipped and
  the whole run dying. All five sites now translate, chaining the cause.

  `_html_to_markdown` is shared by the html and epub paths and is wrapped
  once, inside itself — so an epub chapter is not wrapped twice with the real
  failure buried at `__cause__.__cause__`, and neither path is left uncovered.
  Failures now name what they were reading (`markdownify could not convert ch7
  in book.epub`), which in a 600-page EPUB is the difference between a
  diagnosis and a shrug.

  `FileNotFoundError` deliberately still escapes as itself: the docstring
  documents it as a separate outcome, and "that path does not exist" is fixed
  by passing a different path while "the backend could not read this file" is
  not. Every other `OSError` is a conversion failure and is wrapped.

- **A broken marker-pdf *dependency* was reported as an incompatible
  marker-pdf.** The `find_spec` split above answers "is marker there at all",
  which is a different question from "what failed to import" — and marker's
  import tree reaches far past marker, into PyTorch and the stack behind it.
  A missing or half-installed one of those raises from inside `from
  marker.converters.pdf import ...` exactly where a moved marker API would,
  and every clause of the version-mismatch advice was then false: the
  installed marker-pdf was inside the tested range, nothing was mismatched,
  and reinstalling — "will not help", said the message — was the one thing
  that would have. The reader was sent to pin a package that was never the
  problem while the module that actually failed went unnamed. The handler now
  reads `ImportError.name`, which the import machinery sets for every shape it
  raises, and anything outside marker's own namespace is reported as the
  dependency problem it is, named.

- **The wire-timeout test could pass with the timeout dead.** It asserted only
  that *something* was raised, so when the 2.x port turned a `timedelta` cap
  into an immediate `TypeError` inside anyio, the one test whose whole purpose
  is proving the cap is load-bearing stayed green. It now asserts on the leaf
  exception naming a timeout — elapsed time does not separate the cases.

- Pinned the MCP SDK by major (`mcp>=1.2.0,<2`): mcp 2.0.0 removed
  `mcp.server.fastmcp`, so fresh installs failed to import the server.
  (Superseded above: the port landed and the pin moved to `>=2.0.0,<3`.)

## [0.3.0] — 2026-07-24

The first release carrying runtime changes since 0.1.0 — 0.2.0 was a
packaging-only release, byte-identical to 0.1.0. Everything merged over the
two months since then ships here, including the slug-collision data-loss fix
(#28), the UTF-8 corruption fix (#30), the torn-write fix (#32), DOCX / HTML /
EPUB ingestion, `doctor`, `rename_document`, MCP resources, and shelf-spec v0
recognition.

### Added
- **shelf-spec v0 recognition** (docshelf-mcp is the spec's reference
  implementation, ADR-0005): `init_shelf` / `Shelf.init` gained an opt-in
  `manifest` flag that scaffolds a `shelf.yml` (the spec contract:
  `spec_version "0.1"`, `mode: single`, `profile: document`,
  `index.generated_by: docshelf-mcp`) next to `.docshelf.json`, and `doctor`
  gained a warning-level `docshelf-config-conflict` rule that flags a
  `shelf.yml` / `.docshelf.json` disagreement on an overlapping field
  (`name`, or `categories` vs `category_order`). Conservative and
  non-breaking: the manifest is off by default, never overwrites a hand-edited
  one, leaves categories implicit, and a shelf **without** a `shelf.yml` stays
  valid — the conflict rule simply stays silent. Mirrors openshelf's validator
  rule of the same name so both tools describe the drift identically. Adds a
  `pyyaml` runtime dependency. (#63)
- `add_document` (tool + `Shelf.add_document`) gained an optional `slug`
  parameter that decouples the on-disk filename from the display title: when
  set, the document is written to `docs/<category>/<slug>.md` (the slug is
  slugified for filesystem safety) while `title` stays the INDEX/heading text
  untouched — so a Cyrillic title can live at a latin, date-prefixed path in one
  call, with no `.meta.json` hand-off. A `None`/blank slug keeps today's
  title-derived filename exactly. (#75)

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
- `slugify()` now returns `""` (not the literal `"section"`) for unsluggable
  input, so the intended `or "uncategorized"` / `or "document"` fallbacks at
  its call sites actually fire — an unsluggable title lands on `document.md`
  instead of `section.md`. Previously-unguarded call sites (`rename_document`,
  the section splitter) grew explicit fallbacks so an empty slug can't produce
  a broken path. (#53)

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
- `add_directory` (tool + `Shelf.add_directory`) now defaults to matching
  **every** supported input type — Markdown, PDF, DOCX, HTML, EPUB — instead
  of just `*.pdf` / `*.md`, so batch-importing a folder of `.docx` / `.epub`
  no longer silently ingests nothing. The default is derived from
  `converter.SUPPORTED_INPUT_SUFFIXES`, so it can't drift. (#52)

- Every shelf tool except `docshelf_init_shelf` / `docshelf_convert_pdf`
  now fails fast with a `NotAShelfError` when the resolved root is not an
  initialized shelf, instead of silently scaffolding one in the wrong
  directory. (#7)
- `Shelf.add_document` gained a `rebuild_index` flag (default `True`) so
  batch callers can defer the index rebuild. (#11)

### Documentation
- Documented the read-only `docshelf:///` **MCP resources** feature (added in
  #35) across the README, `docs/USAGE.md`, and `docs/ARCHITECTURE.md`: the URI
  scheme, what's exposed (INDEX.md + every document / split section), the 1 MB
  cap, and the on-start / after-mutation re-sync trigger. (#51)

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
