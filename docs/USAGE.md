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

Bootstrap a new shelf directory. Idempotent — safe to call against an existing shelf to update metadata.

```jsonc
{
  "shelf_path": "/Users/me/Documents/my-docs",
  "name": "My Documentation",
  "github_remote": "https://github.com/me/my-docs",
  "branch": "main",
  "default_categories": ["guides", "specs", "tutorials"]
}
```

After running this, the directory contains `.docshelf.json`, `INDEX.md`, `.gitignore`, and `docs/{guides,specs,tutorials}/`.

### `docshelf_add_document`

Add a PDF or Markdown file to the shelf.

```jsonc
{
  "source_path": "/Users/me/Downloads/router-manual.pdf",
  "category": "routers",
  "title": "Mikrotik RouterOS — full manual",
  "description": "Official RouterOS reference, split by chapter.",
  "split": true,
  "quality": "fast"
}
```

The response includes `document_path`, `section_paths`, and `next_steps` (the suggested git command). When a document is split, the response also carries `warnings` (+ `warning_count`) — heuristic flags for section headings that look like PDF-extraction artefacts (`toc-leak`, `unit-fragment`, `table-residue`, `near-duplicate`). These are detection only; nothing is rewritten. `rebuild_index` reports the same warnings across the whole shelf.

### `docshelf_add_directory`

Onboard a whole folder in one call. Scans `source_dir` (non-recursively) for `patterns` (PDFs and Markdown by default), adds each file under `category` with a title derived from its filename, and rebuilds `INDEX.md` **once** for the whole batch.

```jsonc
{
  "source_dir": "/Users/me/Downloads/manuals",
  "category": "routers",
  "patterns": ["*.pdf", "*.md"],
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

The response lists `removed_paths` relative to the shelf root. As with `add_document`, the git commit / push step stays with you.

### `docshelf_rebuild_index`

Regenerate `INDEX.md` from the on-disk state. Use after manual edits to `docs/` or `.docshelf.json`.

```jsonc
{}
```

### `docshelf_doctor`

Check the shelf for drift and optionally apply the safe fixes. Read-only by default.

```jsonc
{
  "fix": false  // true = prune stale meta entries, delete orphaned split dirs, rebuild INDEX
}
```

Reports `findings` (each with `rule`, `severity`, `path`, `detail`, `suggested_fix`, `fixed`) plus a `by_rule` summary. Rules: `stale-meta-entry`, `orphaned-split-dir`, `split-out-of-sync`, `stale-index`, `duplicate-title`, `empty-category`, `corrupt-meta`. Findings are sorted so runs diff cleanly. With `fix=true`, only the safe subset is applied; everything else stays report-only.

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

`add_document` overwrites. Re-running it on the same source updates the entry in place. Re-running `rebuild_index` is a pure render — safe to call as often as you like.
