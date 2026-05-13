# Usage

A tour of every tool with concrete examples.

## Server config

The MCP server resolves the shelf root in this order:

1. The `shelf_path` parameter on each tool call (if provided).
2. The `DOCSHELF_ROOT` environment variable.
3. The current working directory.

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

The response includes `document_path`, `section_paths`, and `next_steps` (the suggested git command).

### `docshelf_rebuild_index`

Regenerate `INDEX.md` from the on-disk state. Use after manual edits to `docs/` or `.docshelf.json`.

```jsonc
{}
```

### `docshelf_search`

Plain-text search across every Markdown file in the shelf.

```jsonc
{
  "query": "BGP route reflector",
  "max_results": 5
}
```

Each hit includes the file's relative path, a 200-char snippet, and (if a remote is configured) the raw URL — so the model can immediately fetch the file.

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
