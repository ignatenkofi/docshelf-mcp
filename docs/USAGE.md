# Usage

A tour of every tool with concrete examples.

## Server config

The MCP server resolves the shelf root in this order:

1. The `shelf_path` parameter on each tool call (if provided).
2. The `DOCSHELF_ROOT` environment variable.
3. The current working directory.

Every tool **except** `docshelf_init_shelf` (and `docshelf_convert_pdf`, which doesn't use a shelf) requires the resolved root to be an initialized shelf — i.e. to contain a `.docshelf.json`. If it doesn't, the tool returns a structured error (`type: "NotAShelfError"`) instead of silently scaffolding a shelf in the wrong directory:

```jsonc
{
  "status": "error",
  "type": "NotAShelfError",
  "error": "/some/dir is not an initialized docshelf (no .docshelf.json). Run init_shelf to create a shelf there, or set DOCSHELF_ROOT / pass shelf_path to point at an existing shelf."
}
```

Run `docshelf_init_shelf` once (it's the only tool that scaffolds), or point `shelf_path` / `DOCSHELF_ROOT` at an existing shelf.

For Claude Desktop, set `DOCSHELF_ROOT` in the server's env block — see the [README](../README.md#1-add-to-claude-desktop) for a JSON snippet.

## Tools

### `docshelf_init_shelf`

Bootstrap a new shelf directory. Safe to call against an existing shelf to update metadata — but pass `provider` and `branch` again every time (see the re-run note below).

```jsonc
{
  "shelf_path": "/Users/me/Documents/my-docs",
  "name": "My Documentation",
  "github_remote": "https://github.com/me/my-docs",
  "branch": "main",
  "default_categories": ["guides", "specs", "tutorials"],
  "provider": "github",  // how links are built: github, gitlab, gitea, custom, none
  "url_template": "",    // provider "custom" only
  "manifest": false  // true also scaffolds a shelf.yml (shelf-spec v0 manifest)
}
```

After running this, the directory contains `.docshelf.json`, `INDEX.md`, `.gitignore`, and `docs/{guides,specs,tutorials}/`.

`provider` decides the link every `INDEX.md` entry gets (and `SUBINDEX.md`, and the URL in `search` / `read_document` responses). Host, owner and repo come from `github_remote` — despite the name, any host's https or ssh remote (`git@gitlab.com:me/my-docs.git` works the same). For `docs/guides/router-setup.md` on branch `main`:

| `provider` | `github_remote` | link |
|---|---|---|
| `github` (default) | `https://github.com/me/my-docs` | `https://raw.githubusercontent.com/me/my-docs/main/docs/guides/router-setup.md` |
| `gitlab` | `https://gitlab.com/me/my-docs` | `https://gitlab.com/me/my-docs/-/raw/main/docs/guides/router-setup.md` |
| `gitea` | `https://gitea.example.org/me/my-docs` | `https://gitea.example.org/me/my-docs/raw/branch/main/docs/guides/router-setup.md` |
| `custom` | `https://github.com/me/my-docs` | `url_template` filled in — see below |
| `none` | not needed | `docs/guides/router-setup.md`, relative to the shelf root, for a shelf read offline |

Without `github_remote`, `github`, `gitlab` and `gitea` have nothing to build a link from: entries render as title and filename, with no link.

`custom` covers S3, R2 or any static host. `url_template` takes four placeholders: `{owner}` and `{repo}` (parsed from `github_remote`), `{branch}`, and `{path}` (the shelf-relative path, URL-quoted). For example `"url_template": "https://docs.example.org/{repo}/{branch}/{path}"` with the remote above links that entry to `https://docs.example.org/my-docs/main/docs/guides/router-setup.md`; a template that uses only `{path}` (`https://cdn.example.org/{path}`) needs no remote. `custom` without `url_template` is refused, as is a provider outside the list above. A template with any other placeholder (`{bucket}`) is accepted but renders every entry without a link, so stick to these four.

Re-running `init_shelf` on an existing shelf updates `.docshelf.json` and re-renders `INDEX.md` with the new links. It applies `provider` and `branch` as passed, and they default to `github` and `main`: a re-run with only `shelf_path` turns a `gitlab` shelf on `develop` into `github` on `main` (its entries lose their links — `github` builds none from a gitlab remote), and a `custom` shelf into `github`. `github_remote`, `url_template` and `name` left out keep their stored values. `doctor` reports a hand-edited `.docshelf.json` with an unknown provider (`unknown-provider`) or `custom` without a template (`custom-without-template`).

Set `"manifest": true` to also write a **`shelf.yml`** — the [openshelf shelf-spec v0](https://github.com/ignatenkofi/openshelf) manifest (`spec_version "0.1"`, `mode: single`, `profile: document`, `index.generated_by: docshelf-mcp`) — next to `.docshelf.json`, making the shelf conformant to the spec. It's off by default, never overwrites an existing `shelf.yml`, and leaves categories implicit; a shelf without one stays valid. Once a manifest exists, `doctor` reconciles it against `.docshelf.json` (see `docshelf-config-conflict` below).

### `docshelf_add_document`

Add a PDF or Markdown file to the shelf.

```jsonc
{
  "source_path": "/Users/me/Downloads/router-manual.pdf",
  "category": "routers",
  "title": "Mikrotik RouterOS — full manual",
  "description": "Official RouterOS reference, split by chapter.",
  "split": true,
  "quality": "fast",
  "overwrite": false  // true = replace a DIFFERENT document at the same path
}
```

The response includes `document_path`, `section_paths`, and `next_steps` (the suggested git command). When a document is split, the response also carries `warnings` (+ `warning_count`) — heuristic flags for section headings that look like PDF-extraction artefacts (`toc-leak`, `unit-fragment`, `table-residue`, `near-duplicate`). These are detection only; nothing is rewritten. `rebuild_index` reports the same warnings across the whole shelf.

Pass an optional `slug` to decouple the on-disk filename from the display title. By default the filename is the slugified `title`, so a non-latin title yields a non-latin filename. With `slug` set, the document is written to `docs/<category>/<slug>.md` (the slug is itself slugified for filesystem safety) while `title` stays the INDEX/heading text untouched — e.g. `"slug": "2026-07-22-m1-build-sprint"` with `"title": "Сессия: M1 собран за день"` lands a latin, date-prefixed file with the Cyrillic title in `INDEX.md`. A `null`/blank slug keeps the title-derived filename.

`overwrite` (default `false`) matters only when another document already holds the target path. Re-adding the **same** title in the same category is an in-place update and needs no flag. A **different** title that slugifies to the same path — `"Router setup!"` after `"Router Setup"`, both `docs/guides/router-setup.md` — fails with `DocumentExistsError` naming the existing title, before anything is written; with `"overwrite": true` the file and its `.meta.json` title are replaced. The response's `overwritten` is `true` whenever an existing file was replaced, by either route.

A document's sections live in `docs/<category>/<stem>/`, and docshelf rewrites that directory wholesale — on a re-split, and by deleting it when re-added content no longer qualifies for splitting. So `add_document` refuses with `SplitDirConflictError` when a directory of that name already exists and is **not** a docshelf split directory: it holds anything besides `NNN-*.md` section files and `SUBINDEX.md` (an `images/` folder, a sidecar of originals, your own notes), or a subdirectory. The check runs before conversion, nothing is written, and `overwrite: true` does not lift it — `overwrite` replaces a document, not a directory. Pick a distinct title/`slug`, or move the directory aside.

### `docshelf_add_directory`

Onboard a whole folder in one call. Scans `source_dir` (non-recursively) for `patterns` — **every supported input type by default** (Markdown, PDF, DOCX, HTML, EPUB; the globs are derived from the same `SUPPORTED_INPUT_SUFFIXES` the converter dispatches on) — adds each file under `category` with a title derived from its filename, and rebuilds `INDEX.md` **once** for the whole batch. Pass your own `patterns` to narrow the set (e.g. `["*.pdf"]` for PDFs only).

```jsonc
{
  "source_dir": "/Users/me/Downloads/manuals",
  "category": "routers",
  "patterns": ["*.md", "*.markdown", "*.pdf", "*.docx", "*.html", "*.htm", "*.epub"],
  "split": true,
  "quality": "fast"
}
```

The response reports `added` and `failed` per file — one corrupt PDF is listed under `failed` without aborting the rest of the import.

### `docshelf_remove_document`

Remove a document — its file, its split-section directory, and its `.meta.json` entry. `INDEX.md` is regenerated automatically. `document` accepts the filename, the slug, or the human title used at add time.

```jsonc
{
  "category": "routers",
  "document": "Mikrotik RouterOS — full manual",
  "dry_run": false   // true = report what would be removed, delete nothing
}
```

The response lists `removed_paths` relative to the shelf root. As with `add_document`, the git commit / push step stays with you. A same-name directory next to the document that is not a docshelf split directory (anything besides `NNN-*.md` sections and `SUBINDEX.md` inside) is not treated as the document's sections: it stays in place, is not listed in `removed_paths`, and `was_split` is `false` — under `dry_run` too.

### `docshelf_rename_document`

Retitle, recategorize or re-describe a document without re-adding it: no source file, no re-conversion. `document` accepts the filename, the slug, or the current title, as in `remove_document`. Give at least one of `new_title`, `new_category`, `new_description`.

```jsonc
{
  "category": "manuals",
  "document": "Big Manual",         // filename, slug or current title
  "new_title": "Router Manual",     // re-slugifies the filename
  "new_category": "network-gear",   // moves it there; created if missing
  "new_description": "New desc",    // omit to keep the current one
  "dry_run": false                  // true = report the move, change nothing
}
```

A new title moves `docs/manuals/big-manual.md` to `docs/manuals/router-manual.md` together with its split directory (sections and `SUBINDEX.md`), and re-keys its `.meta.json` entry under the new title; the description is kept unless `new_description` is given. A new category moves the same set into that category's directory (slugified, created if missing), and the entry leaves the old `.meta.json`, which is deleted once empty. A description-only change moves nothing (`moved: false`). `INDEX.md` is regenerated in the same call; the git commit stays with you.

The response carries `old_path`, `new_path`, `moved`, `was_split` and `dry_run`; with `dry_run` nothing on disk changes. A target path another document already holds fails with `DocumentExistsError`, a call with nothing to change with `ValueError`, an unknown document with `FileNotFoundError` — nothing is moved in any of them. A same-name directory next to the document moves with it even if docshelf did not write it (`was_split` is then `true` as well); `doctor` names such a directory `split-dir-conflict`.

Re-adding under the new title is not the same thing: `add_document` needs the source again, converts it again and writes a second document, while the old file, its sections and its INDEX entry stay until `remove_document`.

### `docshelf_rebuild_index`

Regenerate `INDEX.md` from the on-disk state. Use after manual edits to `docs/` or `.docshelf.json`.

```jsonc
{}
```

### `docshelf_doctor`

Check the shelf for drift and optionally apply the safe fixes. Read-only by default.

```jsonc
{
  "fix": false  // true = prune stale meta entries, delete orphaned split dirs (split-shaped only), rebuild INDEX
}
```

Reports `findings` (each with `rule`, `severity`, `path`, `detail`, `suggested_fix`, `fixed`) plus a `by_rule` summary. Rules: `stale-meta-entry`, `orphaned-split-dir`, `split-out-of-sync`, `split-dir-conflict`, `uncommitted-split-dir`, `stale-index`, `duplicate-title`, `empty-category`, `corrupt-meta`, `meta-shape`, `colliding-category-dirs`, `unknown-provider`, `custom-without-template`, and `docshelf-config-conflict`. Findings are sorted so runs diff cleanly. With `fix=true`, only the safe subset is applied; everything else stays report-only.

`orphaned-split-dir` (warning) names any directory under a category that has no parent `<stem>.md`. `fix=true` deletes it **only when it is shaped like a docshelf split** — nothing but `NNN-*.md` section files and `SUBINDEX.md` (plus `.DS_Store`-style OS litter), no subdirectories. Any other orphaned directory — an `images/` folder, a sidecar of originals — is reported with the same rule but left in place with `fixed: false`; the finding says so. So is a directory docshelf cannot read: it is reported, not a reason for the run to fail. `split-out-of-sync` likewise only compares a document against a same-name directory of that shape. Since this means `fix=true` can delete directories, the tool is annotated `destructiveHint: true`.

Directories a [shelf-spec](https://github.com/ignatenkofi/openshelf) `shelf.yml` declares in `extra_dirs` (shelf-root-relative, e.g. `docs/attachments` or `docs/guides/originals/`) are skipped the way the spec's validator skips them: never reported as an orphaned split, a split conflict, an empty category or a colliding category directory, and never deleted. Declare a sidecar there to keep it next to the documents without a finding.

`split-dir-conflict` (warning) names the path a document's sections would live at — `docs/<category>/<stem>/` next to `<stem>.md` — when something other than a docshelf split sits there: an `images/` folder next to `images.md`, a split someone dropped their own `notes.md` into, a plain file, a directory docshelf cannot read. It is not read as the document's sections (no section links in `INDEX.md`, no `SUBINDEX.md` written into it, no `uncommitted-split-dir`), and re-adding the document fails with `SplitDirConflictError` whatever `overwrite` says — the finding announces that refusal in advance. Move it aside (for a split, just the files docshelf did not write), or declare it in `extra_dirs`; `fix=true` never deletes it.

`uncommitted-split-dir` (warning) fires on a git shelf when a split directory next to a document (one shaped like a split, see above) has nothing tracked inside it — the sections exist only in that working copy, so an `INDEX.md` rendered there can never equal one rendered from the committed tree. While it is present, `stale-index` is not reported and `fix=true` does not rebuild the index: the rebuild would write links no other checkout can follow. Commit the directory, or delete it and re-add the document with `split=false` — the sections are a copy of the parent, which keeps all of them. A shelf that committed its sections, and a shelf that is not a git repository, are never flagged.

`docshelf-config-conflict` (warning) only fires when a [shelf-spec v0](https://github.com/ignatenkofi/openshelf) `shelf.yml` manifest is present next to `.docshelf.json` and the two disagree on an overlapping field — the manifest `name` vs the config `name`, or the manifest's explicit `categories` vs the config's `category_order`. The manifest is the contract; align `.docshelf.json` to it. A shelf without a `shelf.yml` is never flagged.

### `docshelf_search`

Plain-text search across every Markdown file in the shelf.

```jsonc
{
  "query": "BGP route reflector",
  "max_results": 5
}
```

Each hit includes the file's relative path, a 200-char snippet, and (if a remote is configured) the raw URL — so the model can immediately fetch the file.

### `docshelf_read_document`

Read a document or section's content directly over MCP — the private-shelf counterpart to the raw-URL fetch. Pass a `relative_path` from `search` / `list_documents`.

```jsonc
{
  "relative_path": "docs/routers/mikrotik/003-firewall.md",
  "max_bytes": 100000,  // truncate beyond this; response flags truncated=true
  "offset": 0           // byte offset, for paging a large file
}
```

The response returns `content`, `size_bytes`, `truncated`, and (if a remote is configured) `raw_url`. Paths that resolve outside the shelf's `docs/` directory are rejected.

### `docshelf_list_documents`

List documents grouped by category.

```jsonc
{
  "category": "routers"  // omit to list everything
}
```

### `docshelf_convert_pdf`

Standalone PDF → Markdown. Doesn't touch any shelf; useful for one-off conversions.

```jsonc
{
  "pdf_path": "/tmp/paper.pdf",
  "out_dir": "/tmp/converted",
  "quality": "fast",
  "split": false
}
```

Writes `<out_dir>/<stem>.md`, replacing a file of that name. With `"split": true` (and content that qualifies for splitting) the H2 sections go to `<out_dir>/<stem>/`, which is rewritten on every run — so a re-run over its own output is idempotent, but the call refuses with `SplitDirConflictError` (and writes nothing, not even `<stem>.md`) when `<stem>/` already exists and is not a split from an earlier run: it holds anything besides `NNN-*.md` section files. With `"split": false` an existing `<stem>/` is never touched.

## MCP Resources

Besides the tools above, the server publishes every shelf file as a **read-only MCP resource**. Clients that understand MCP resources (Claude Desktop, Claude Code, …) can list, browse, and attach them the same way they attach any other resource — no tool call in the loop.

- **URI scheme:** `docshelf:///<relative-path>` — for example `docshelf:///INDEX.md` and `docshelf:///docs/routers/mikrotik/003-firewall.md`. The path is exactly the shelf-relative path `search` / `list_documents` return.
- **What's exposed:** `INDEX.md` plus every document and every split section under `docs/`, one resource per file (mime type `text/markdown`). A split document lists both its whole-file parent and its section files, so a client can attach the whole chapter or a single section.
- **1 MB cap:** each read is capped at 1,000,000 bytes. An oversized file comes back truncated at a UTF-8 character boundary with a trailing `[docshelf: truncated …]` notice that points at `docshelf_read_document`; use that tool's `offset` / `next_offset` paging to read the remainder.
- **Re-sync trigger:** the resource set is (re)registered on server start and again after every **mutating** tool call — `init_shelf`, `add_document`, `add_directory`, `remove_document`, `rename_document`, `rebuild_index` — so it always reflects the current shelf. Content itself is read fresh from disk on each access, and reads that would escape the shelf root are refused.

Only an initialized shelf (one with a `.docshelf.json`) registers resources; pointing `DOCSHELF_ROOT` at a plain directory exposes none. This is the resource-native counterpart to `docshelf_read_document`: the tool is imperative ("read this path"), the resources are declarative (the client sees the whole shelf and picks).

## Python library

Skip the MCP layer entirely:

```python
from docshelf_mcp import Shelf

shelf = Shelf("~/Documents/my-docs").init(
    name="My Docs",
    remote="https://github.com/me/my-docs",
)

# Add a PDF
shelf.add_document(
    "manual.pdf",
    category="routers",
    title="Mikrotik RouterOS",
    description="Full reference.",
)

# Add a Markdown file
shelf.add_document(
    "notes.md",
    category="howto",
    title="VLAN setup notes",
)

# Search
for hit in shelf.search("BGP route reflector"):
    print(hit["relative_path"], hit["score"])

# List
for entry in shelf.scan():
    print(entry.category, entry.title)

# Rebuild INDEX.md
shelf.rebuild_index()
```

### Your own wording in INDEX.md

Three lines of the rendered navigation name docshelf's tools: an empty shelf's INDEX says "Use the `add_document` tool to start your shelf", and the footer of INDEX.md and of every SUBINDEX.md says to call `rebuild_index`. A program that serves the shelf under other tools passes its own lines, so an agent reading the index is not sent to tools it does not have:

```python
from docshelf_mcp import Shelf
from docshelf_mcp.core.indexer import IndexHints

hints = IndexHints(
    empty="_Nothing here yet. Use `mytool add` to start._",
    index_footer="*Generated by mytool. Run `mytool rebuild` to regenerate.*",
    subindex_footer="*Generated by mytool. See `INDEX.md` at the shelf root.*",
)
Shelf("~/Documents/my-docs", hints=hints).rebuild_index()
```

A field left out keeps docshelf's line; an empty string drops the line, and a footer's `---` rule with it. The hints belong to the `Shelf` object, not to one call: every render through it uses them, and so does `doctor`, so its `stale-index` check and `doctor(fix=True)` agree with the wording on disk. A `Shelf` made without them — the MCP server's included — renders docshelf's own lines: `docshelf_doctor` reports such a shelf as `stale-index`, and `docshelf_rebuild_index` writes docshelf's wording back. There is no `.docshelf.json` key for them.

## Manual workflows

You can edit anything by hand and call `rebuild_index`:

- Add files to `docs/<category>/` — they'll appear in INDEX.
- Edit `docs/<category>/.meta.json` to change titles/descriptions.
- Edit `.docshelf.json` to reorder categories or change the shelf name.
- Delete a file — its INDEX entry disappears on rebuild.

## Common patterns

### One shelf per topic

Avoid a single mega-shelf. Run multiple — one per knowledge domain — and attach the relevant `INDEX.md` to the relevant chat project.

### Public shelf, private notes

Keep the shelf repo public so raw URLs work. If you have private notes that shouldn't be on GitHub, keep them in a separate (private) shelf and use only `docshelf_search` against it.

### Idempotent re-runs

Re-running `add_document` with the same title and category updates the entry in place (its own split directory included; a same-name directory docshelf did not write is refused, never overwritten — see `docshelf_add_document`). A different title that lands on the same path is refused unless `overwrite: true`. Re-running `rebuild_index` is a pure render — safe to call as often as you like.
