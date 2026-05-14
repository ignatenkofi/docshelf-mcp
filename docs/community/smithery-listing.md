# Smithery submission — docshelf-mcp

Submission destination: <https://smithery.ai/> (server registry for MCP).

## Server identity

| Field | Value |
|---|---|
| **Name** | `docshelf-mcp` |
| **Display name** | docshelf — AI-friendly document shelves |
| **Author** | Filipp Ignatenko (`@ignatenkofi`) |
| **Homepage** | <https://github.com/ignatenkofi/docshelf-mcp> |
| **Repository** | <https://github.com/ignatenkofi/docshelf-mcp> |
| **License** | MIT |
| **Language** | Python (3.10+) |
| **Transport** | stdio (standard MCP server) |
| **Latest version** | 0.2.0 |

## One-line description

> An MCP server that turns a folder of PDFs and Markdown into a chat-project-friendly
> shelf: convert, split by chapter, auto-generate `INDEX.md`.

## Long description (one paragraph)

`docshelf-mcp` solves a specific pain point for Claude / ChatGPT projects: you
want the model to answer across a stack of manuals, but the PDFs are too big to
attach. The server takes a folder, converts every PDF to clean Markdown, splits
long documents on `H2` boundaries into ~5–50 KB section files, and regenerates a
navigation `INDEX.md` with raw `githubusercontent.com` URLs. You commit and push
the folder to a public GitHub repo; you attach **only `INDEX.md`** to your chat
project. The AI then fetches exactly the section it needs — turning a 50 MB
collection into a 5 KB working set. Six MCP tools: `init_shelf`, `add_document`,
`rebuild_index`, `search`, `list_documents`, `convert_pdf`.

## Categories / tags

- `documentation`
- `pdf`
- `markdown`
- `knowledge-base`
- `rag-alternative`
- `productivity`
- `python`

## Install command

```bash
pip install docshelf-mcp
```

Claude Desktop config snippet:

```json
{
  "mcpServers": {
    "docshelf": {
      "command": "docshelf-mcp",
      "env": {
        "DOCSHELF_ROOT": "/Users/me/Documents/my-homelab-docs"
      }
    }
  }
}
```

Claude Code one-liner:

```bash
claude mcp add docshelf --env DOCSHELF_ROOT=/path/to/shelf -- docshelf-mcp
```

## Sample tool use

**Add a PDF to a shelf:**

```jsonc
{
  "tool": "docshelf_add_document",
  "arguments": {
    "shelf_path": "/Users/me/Documents/my-homelab-docs",
    "source": "/Users/me/Downloads/MIKROTIK_RouterOS.pdf",
    "category": "routers",
    "title": "Mikrotik RouterOS — full manual",
    "description": "Official RouterOS reference, split by chapter.",
    "split": true
  }
}
```

Result: PDF → cleaned Markdown → split into `docs/routers/mikrotik-routeros/001-….md`
through `NNN-….md`, `INDEX.md` regenerated.

**Search across the shelf:**

```jsonc
{
  "tool": "docshelf_search",
  "arguments": {
    "shelf_path": "/Users/me/Documents/my-homelab-docs",
    "query": "VLAN trunk"
  }
}
```

Returns matching section files with their raw GitHub URLs.

## Use cases

1. **Homelab manuals.** 30+ datasheets and configuration guides for switches,
   routers, PSUs. Chat project asks "how do I set up MTU on a Cudy GS1010PE?" —
   model finds the right section in seconds.
2. **Recipe book.** Hundreds of recipes from scanned cookbooks; one file per
   recipe. "What can I make with chickpeas and tahini?" → INDEX → recipe file.
3. **Research papers.** Dropping PDF papers into a `papers/` shelf with their
   abstracts in `.meta.json`. Lets the model triage what's worth reading.
4. **Project-specific knowledge bases.** Customer-support runbooks, on-call
   playbooks, vendor docs — anything where you'd otherwise paste fragments.

## Why this rather than a vector DB?

It's deliberately the **simplest** thing: a folder + git + raw URLs. No
embeddings to maintain, no infra to host, the artefact is human-readable, and
diff-able. You can upgrade to embeddings later — the shelf is a normal repo.

## Screenshots / demo

- Repo README has the full architecture diagram and three example shelves
  (`examples/homelab`, `examples/recipes`, `examples/research-papers`).
- Demo video: *planned (link will go in the next revision)*.

## Maintainer commitment

- CI on every push (ruff + pytest, Python 3.10/3.11/3.12).
- Tag-triggered release workflow → automatic PyPI publishing via trusted
  publishing (no API tokens).
- Issues are read; response within ~3 days for non-urgent items.
