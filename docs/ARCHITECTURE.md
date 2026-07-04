# Architecture

## Goals

1. **Make a large document collection legible to an LLM** without loading the whole thing into context.
2. **Stay close to a normal git repo.** Anything the tool produces should be plain Markdown / JSON that a human can edit, diff, and commit.
3. **Be cheap to run.** No vector DB, no remote service, no GPU required for the default path.

## Data flow

```
┌────────────┐       ┌──────────────┐       ┌──────────────┐
│ PDF or .md │  ──▶  │  converter   │  ──▶  │   splitter   │
└────────────┘       │ (pymupdf4llm │       │  (clean +    │
                     │ or marker)   │       │  H2 slice)   │
                     └──────────────┘       └──────┬───────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │ docs/<category>/ │
                                          │   <doc>.md       │
                                          │   <doc>/         │
                                          │     001-*.md     │
                                          │     002-*.md     │
                                          └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │   indexer        │
                                          │  (scan + build   │
                                          │   INDEX.md)      │
                                          └──────────────────┘
```

## Modules

| Module | Responsibility |
|---|---|
| `core.slugify` | Unicode-safe filename slug. Pure function. |
| `core.converter` | PDF → Markdown via pymupdf4llm (`fast`) or marker-pdf (`high`). Both engines imported lazily. |
| `core.splitter` | Cleanup heuristics + H2-based section split. Decides whether to split based on byte size + H2 count. |
| `core.indexer` | Walks the on-disk shelf, builds `INDEX.md`. Renders raw GitHub URLs when a remote is configured. |
| `core.shelf` | High-level facade (`Shelf` class). Coordinates the four modules above and persists shelf metadata. |
| `tools` | Pydantic input models + thin wrappers around `Shelf`. Returns plain dicts. |
| `server` | FastMCP server. Each `@mcp.tool` is a thin wrapper around `tools.py` that JSON-serialises the result. |
| `config` | Resolves `DOCSHELF_ROOT` env var → shelf root path. |

## Design choices

### Why a flat `docs/<category>/` layout instead of nested?

Two reasons:
1. Categories map naturally onto INDEX sections (`## Routers`, `## Switches`). Nested categories explode the surface area without adding clarity.
2. The raw GitHub URL is shorter and easier for the model to reason about: `…/main/docs/routers/foo.md` vs `…/main/docs/network/router/vendor/foo.md`.

If you need deeper hierarchy, you can always introduce sub-shelves and link them from a parent `INDEX.md`.

### Why split on H2 (not H1 or H3)?

In practice, the H1 of a converted PDF is "the document title" — there's exactly one, and splitting on it is pointless. H3 yields tiny fragments (every sub-section becomes a file). H2 maps to "chapter" in 90% of technical documents and gives natural ~5–50 KB chunks.

### Why generate `INDEX.md` from disk every time?

To keep the index trivially correct. The on-disk shape is the source of truth — the index is a render of it. Any tool can mutate `docs/` and call `rebuild_index` without needing to know what was there before.

### Why store metadata in `.meta.json` per category?

Document titles can be long, contain punctuation, and need editing. Putting them in a sidecar JSON keeps the *filename* slug stable (so links don't rot) while letting the human override the display string. The shelf-wide `.docshelf.json` only holds shelf-level config (name, remote, branch, category order).

### Why not git-aware?

A few reasons:
1. Agents calling tools shouldn't accidentally commit + push.
2. Different users want different git workflows (no commit, signed commits, conventional commits, …).
3. The shelf is useful even outside git (local scratch directory, S3-hosted, …).

The README + `add_document`'s response include the suggested git command, so the human / agent stays in the loop.

### Why FastMCP + Pydantic?

FastMCP auto-generates input schemas from Pydantic models — that's the modern MCP Python idiom and minimises the gap between "Python function" and "MCP tool". Tool implementations live in `tools.py` so they're testable without an MCP runtime.

## Extension points

- **Different conversion engines.** Add a branch in `core.converter:pdf_to_markdown`.
- **Different splitting strategies** (size-based, semantic, …). The `splitter` module exposes `should_split` and `split_by_h2` as orthogonal building blocks.
- **Different index renderers.** `core.indexer:build_index` is a pure function from `(name, entries, config) → str`. Subclass / replace it to emit JSON, HTML, an Astro site, etc.
- **Different URL providers.** `core.indexer:shelf_url` maps a shelf-relative path to a fetch URL per the configured `provider` (`github` / `gitlab` / `gitea` / `custom` / `none`). Add a branch there (or use `provider="custom"` with a `url_template`) to target a new host.
- **Embedding search.** Drop in a vector index next to the grep search. Same `Shelf.search` signature.

## Non-goals

- We don't replace [llamaindex](https://github.com/jerryjliu/llama_index) / [haystack](https://github.com/deepset-ai/haystack) / [LangChain](https://github.com/langchain-ai/langchain). They give you retrieval+generation pipelines. `docshelf-mcp` gives you a navigable static document collection. They compose fine.
- We don't try to be a CMS. There's no auth, no editor, no UI. The shelf is editable in any text editor / VS Code / GitHub.
