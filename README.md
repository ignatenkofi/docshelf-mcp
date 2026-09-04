# docshelf-mcp

> Put your manuals on a shelf, hand the AI the index.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![CI](https://github.com/ignatenkofi/docshelf-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ignatenkofi/docshelf-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/docshelf-mcp.svg)](https://pypi.org/project/docshelf-mcp/)
[![Glama](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp/badges/score.svg)](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp)

📖 **Docs & landing page:** <https://ignatenkofi.github.io/docshelf-mcp/>

```text
     _                _          _  __
  __| | ___   ___ ___| |__   ___| |/ _|
 / _` |/ _ \ / __/ __| '_ \ / _ \ | |_
| (_| | (_) | (__\__ \ | | |  __/ |  _|
 \__,_|\___/ \___|___/_| |_|\___|_|_|
        MCP server for AI-friendly doc shelves
```

An [MCP](https://modelcontextprotocol.io/) server that turns a folder of PDFs and Markdown into a **chat-project-friendly document collection**: AI agents see a single `INDEX.md` and pull individual sections by raw GitHub URL on demand — instead of choking on a 4 MB datasheet.

---

## Why?

You have 30 hardware manuals, or 200 cooking recipes, or a stack of research PDFs.

You want Claude / ChatGPT / whatever to be able to answer questions across them — but:

- ❌ You can't dump 80 MB of PDFs into a chat project. It won't fit, and you'd burn the context window even if it did.
- ❌ You can manually copy-paste the relevant pages, but only after you remember which manual mentioned the thing you need.
- ❌ Long files mean retrieval is wasteful — the model loads the whole RouterOS guide just to answer a question about VLANs.

**docshelf-mcp** solves it like this:

1. You drop a PDF onto the shelf.
2. The shelf converts it to Markdown, splits big files chapter-by-chapter, and regenerates a navigation `INDEX.md`.
3. You commit and push to a **public GitHub repo**.
4. Add **only `INDEX.md`** to your Claude project. When the model needs a section, it fetches it via `raw.githubusercontent.com`.

Result: a 5 KB index pointing at a 50 MB collection. The model reads exactly the chapter it needs.

---

## 📦 Install

From PyPI (once the first tagged release is published):

```bash
# uv (recommended)
uv pip install docshelf-mcp

# or plain pip
pip install docshelf-mcp
```

Or straight from `main` (always-latest, no PyPI required):

```bash
pip install "git+https://github.com/ignatenkofi/docshelf-mcp"
```

That gives you Markdown shelves. Input formats beyond Markdown are extras —
pick the ones you ingest:

```bash
pip install "docshelf-mcp[pdf]"       # PDF via pymupdf4llm (the default engine)
pip install "docshelf-mcp[formats]"   # PDF + DOCX + HTML + EPUB; or [docx] / [html] / [epub]
```

The `pdf` extra pulls the PyMuPDF chain (~260 MB installed); a consumer that
only reads and writes Markdown does not need it, which is why it is not core.

Optional high-quality PDF engine (pulls ~2 GB of PyTorch — only if you need it):

```bash
pip install "docshelf-mcp[high-quality]"
```

---

## 📋 Project Prompt

Drop this into the **Custom Instructions** of any Claude project that consumes
a docshelf-style `INDEX.md`:

> This project uses the docshelf pattern. `INDEX.md` is the entry point.
> When answering: read INDEX → fetch ONLY the needed section file via its
> GitHub raw URL (use WebFetch / fetch / curl). Don't load full source files
> into context. For large manuals split into chapters, follow INDEX → chapter
> SUBINDEX → section file.

Medium (~150 words) and full (~400 words) versions, plus how-to snippets for
Claude Code, Claude Desktop, and the Anthropic API, live in
[`docs/PROJECT_PROMPT.md`](docs/PROJECT_PROMPT.md).

---

## Quickstart (Python library)

```python
from docshelf_mcp import Shelf

shelf = Shelf("~/Documents/my-homelab-docs").init(
    name="My HomeLab Docs",
    remote="https://github.com/me/my-homelab-docs",
    default_categories=["routers", "switches", "psu", "motherboards"],
)

shelf.add_document(
    "~/Downloads/MIKROTIK_RouterOS.pdf",
    category="routers",
    title="Mikrotik RouterOS — full manual",
    description="Official RouterOS reference, split by chapter.",
)
# → docs/routers/mikrotik-routeros-full-manual.md  +  docs/routers/.../001-..md, 002-..md, ...
# → INDEX.md is regenerated automatically.
```

Then in the shelf directory: `git add . && git commit -m "docs: add RouterOS" && git push`.

In your Claude project, attach **only `INDEX.md`**. Done.

---

## Quickstart (MCP server)

### 1. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows):

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

Restart Claude Desktop. You now have eleven new tools available:

| Tool | What it does |
|---|---|
| `docshelf_init_shelf` | Bootstrap a new shelf directory. |
| `docshelf_add_document` | Add a file (MD/PDF/DOCX/HTML/EPUB). Converts, splits, re-indexes. |
| `docshelf_add_directory` | Add every supported file (MD/PDF/DOCX/HTML/EPUB) in a folder in one call. Re-indexes once. |
| `docshelf_read_document` | Read a document/section's content over MCP (works on private shelves). |
| `docshelf_remove_document` | Remove a document, its sections, and metadata. Re-indexes. |
| `docshelf_rename_document` | Retitle / recategorize a document (moves file, sections, meta) — no re-conversion. |
| `docshelf_rebuild_index` | Regenerate `INDEX.md` from disk. |
| `docshelf_doctor` | Check shelf integrity; optionally auto-fix safe drift. |
| `docshelf_search` | Plain-text search across the shelf, with raw URLs. |
| `docshelf_list_documents` | List documents by category. |
| `docshelf_convert_pdf` | Standalone PDF → Markdown (no shelf). |

The shelf files are **also** exposed as read-only MCP resources, so a client can browse and attach them natively — see [MCP Resources](#mcp-resources) below.

### 2. Add to Claude Code

```bash
claude mcp add docshelf -- docshelf-mcp

# Optional: pin a default shelf for this server
printf 'Path to your docshelf shelf: '; read -r shelf
shelf=${shelf/#\~/$HOME}                  # read does not expand a typed ~
shelf=$(cd "$shelf" && pwd) || exit 1     # absolute, and fails loudly if absent
claude mcp add docshelf --env DOCSHELF_ROOT="$shelf" -- docshelf-mcp
```

### 3. Test from the command line

```bash
# Sanity check — should print the server version then wait on stdin
docshelf-mcp
```

---

## MCP Resources

Alongside the tools, every shelf file is exposed as a **read-only MCP resource**, so an MCP client (Claude Desktop, Claude Code, …) can browse and attach shelf content natively — no tool call required.

- **Scheme:** `docshelf:///<relative-path>`, e.g. `docshelf:///INDEX.md` or `docshelf:///docs/routers/mikrotik/003-firewall.md`.
- **What's exposed:** `INDEX.md` plus every document and every split section under `docs/` — one resource each. A split document exposes both its whole-file parent and its individual section files.
- **Size cap:** a resource read is capped at **1 MB** (1,000,000 bytes). A larger file is truncated at a UTF-8 character boundary and ends with a notice pointing at the `docshelf_read_document` tool, which pages the rest.
- **Freshness:** content is read from disk on every access, and the resource *set* is re-synced when the server starts and after each mutating tool call (`add_document`, `add_directory`, `remove_document`, `rename_document`, `rebuild_index`, `init_shelf`) — so newly added files appear and removed ones drop out. Reads are confined to the shelf root.

Resources are only registered for an initialized shelf (one that has a `.docshelf.json`); a non-shelf `DOCSHELF_ROOT` simply exposes none.

---

## The shelf layout

```text
my-shelf/
├── .docshelf.json        ← shelf metadata: name, remote, category order
├── INDEX.md              ← auto-generated navigation (your chat-project file)
├── .gitignore
└── docs/
    ├── routers/
    │   ├── .meta.json    ← per-document title/description overrides
    │   ├── mikrotik-routeros.md       (full document, lightly cleaned)
    │   └── mikrotik-routeros/         (auto-split sections)
    │       ├── SUBINDEX.md            (per-document navigation page)
    │       ├── 001-overview.md
    │       ├── 002-bridging.md
    │       └── 003-firewall.md
    └── switches/
        └── cudy-gs1010pe.md
```

Everything in `docs/` is committed; everything is fetchable via raw URL once you push to GitHub.

---

## How splitting works

A document is split when **both** conditions hold:

1. UTF-8 size > 50 KB (configurable via `.docshelf.json:split_threshold_bytes`).
2. The document has at least two `## ` (H2) headings.

The splitter:

- Cleans PDF-extraction noise (collapses runaway blank lines, demotes CLI dumps mistaken for H1s).
- Slices on H2 boundaries.
- Names files `NNN-<slug>.md` so they sort naturally and survive title changes.
- Wipes the previous split directory before regenerating — fully idempotent.
- Writes a `SUBINDEX.md` navigation page into the split directory (title,
  description, per-section links) — regenerated on every `rebuild_index`.

In `INDEX.md`, split documents with up to 10 sections list every section
inline; bigger splits get a single link to their `SUBINDEX.md` so the index
stays small. Control this via `.docshelf.json`:
`"index_style": "auto" | "inline" | "subindex"` and
`"subindex_threshold_sections": 10`.

If you want to keep a document whole, pass `split=False`.

---

## Examples

See the [`examples/`](examples) directory for three concrete use cases:

- **`examples/homelab/`** — original use case, hardware manuals for a home lab.
- **`examples/recipes/`** — a cookbook with one recipe per file.
- **`examples/research-papers/`** — academic PDFs with abstracts in `.meta.json`.

Each example shows the directory layout and the `INDEX.md` you'd end up with.

---

## Optional: high-quality PDF conversion

The default engine (`pymupdf4llm`, installed by the `pdf` extra) is fast and good enough for ~95% of technical documents. For papers with complex tables, math, or scanned content, install the `marker-pdf` backend:

```bash
pip install "docshelf-mcp[high-quality]"
```

Then pass `quality="high"`:

```python
shelf.add_document("paper.pdf", category="research", title="...", quality="high")
```

⚠️  `marker-pdf` pulls in PyTorch (~2 GB) and is significantly slower (10–60 s per document on CPU). The library import is **deferred** — if you don't use `quality="high"`, the dependency is never loaded.

---

## FAQ

**Why GitHub raw URLs and not embeddings / RAG?**
Because it's dead simple, costs nothing to host, and the AI is already good at chasing links. You can layer embedding search on top later if you want — the on-disk shape is a normal git repo.

**Does this work with private repos?**
Partly. The raw-URL trick needs a public repo — `raw.githubusercontent.com` won't serve private ones without auth. But `docshelf_search` **and** `docshelf_read_document` both work over MCP on private (or purely local, non-git) shelves: the model searches, then reads the exact section's content directly from the server, no raw URL required. You only lose the ability to hand a bare `INDEX.md` to a chat project and have it fetch by URL — with the MCP server attached, the full flow works either way. Make the doc repo public if you want the URL-fetch path too.

**Do I have to use GitHub?**
No. Set `provider` in `.docshelf.json` (or at `init_shelf`): `github` (default), `gitlab`, `gitea`, `custom`, or `none`. The `github` provider also covers **GitHub Enterprise Server**: a self-hosted `github.<company>.com` remote gets the GHES raw form (`https://<host>/<owner>/<repo>/raw/<branch>/<path>`) automatically. `custom` takes a `url_template` with `{owner}`, `{repo}`, `{branch}`, `{path}` placeholders, so you can point at S3, Cloudflare R2, GitLab/Gitea raw, a GHES deployment on a fully custom domain, or any static host — the generated URLs are correct everywhere, no post-processing. `none` renders **relative** links in `INDEX.md`, which stay navigable offline / in a local checkout.

**Does it edit the source PDFs?**
No. PDFs are converted on `add_document` and the source is left in place. The shelf only writes inside its own directory.

**What about non-English documents?**
Slugify is Unicode-aware (NFKD-normalized, with `\w` under `re.UNICODE`). Cyrillic / CJK titles slug down to ASCII-ish forms; the body Markdown is preserved as-is.

**Can I use it without MCP?**
Yes — `from docshelf_mcp import Shelf` and use the class directly. See [`docs/USAGE.md`](docs/USAGE.md).

---

## Limitations

- **Public GitHub only** for the raw-URL trick (or whatever public static host you wire up).
- **Single repo per shelf.** If you outgrow one repo, run multiple shelves and attach multiple `INDEX.md`s.
- **Heuristic splitting.** The PDF→Markdown extract isn't always clean enough to split cleanly. For pathological cases (some 4+ MB datasheets), keep the file whole and rely on `docshelf_search`.
- **No automatic git commit.** Tools regenerate `INDEX.md` on disk, but the caller (you, or an agent) is responsible for `git add / commit / push`. This is intentional — staying out of git's way keeps the tool safe to call from agents.

---

## Demo — does it actually save tokens?

Measured on two real shelves (24 hardware manuals; a full novel split by
chapter): answering a question the docshelf way costs **~3.7K tokens vs 1.2M**
to dump the collection — **99.7% fewer** — and the biggest manual (RouterOS,
~1.05M tokens) doesn't even fit in a 200K context window, while a section fetch
always does.

📊 **Full write-up with the numbers, chart, and a reproducible benchmark:
[`docs/demo.md`](docs/demo.md)** (run [`benchmarks/token_savings.py`](benchmarks/token_savings.py) on your own shelf).

---

## Architecture

For a deeper dive, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module layout, data flow, design rationale.

---

## Related projects

- **[memshelf-mcp](https://github.com/ignatenkofi/memshelf-mcp)** — the sibling project: the same index-and-fetch pattern applied to an **AI agent's own working memory**. Conversation episodes get offloaded to a private shelf with LLM-written digests; the agent keeps only `INDEX.md` in context and recalls sections on demand. Born as [RFC-0001](docs/rfc/0001-memshelf/) in this repo; uses docshelf as its storage/index layer.

---

## Contributing

Bug reports and PRs welcome. To set up a dev env:

```bash
git clone https://github.com/ignatenkofi/docshelf-mcp
cd docshelf-mcp
uv pip install -e ".[dev]"
ruff check src tests
pytest -v
```

---

## License

MIT — see [`LICENSE`](LICENSE).

## Origin

`docshelf-mcp` started life as a 350-line Python script (`homelab-encyclopedia.py`) that managed a single homelab manuals repo. The split / index / clean logic is the same code, generalised to work for any category-organised document collection.
