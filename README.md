# docshelf-mcp

> Put your manuals on a shelf, hand the AI the index.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![CI](https://github.com/ignatenkofi/docshelf-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ignatenkofi/docshelf-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/docshelf-mcp.svg)](https://pypi.org/project/docshelf-mcp/)

```text
   ___  __  ____  ____  _  _  ____  __    ____
  / __)/  \(_  _)/ ___)/ )( \(  __)(  )  (  __)
 ( (_ \(  O ) )(  \___ \) __ ( ) _) / (_/\ ) _)
  \___/ \__/ (__) (____/\_)(_/(____)\____/(__)
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

Restart Claude Desktop. You now have six new tools available:

| Tool | What it does |
|---|---|
| `docshelf_init_shelf` | Bootstrap a new shelf directory. |
| `docshelf_add_document` | Add a PDF/MD file. Converts, splits, re-indexes. |
| `docshelf_rebuild_index` | Regenerate `INDEX.md` from disk. |
| `docshelf_search` | Plain-text search across the shelf, with raw URLs. |
| `docshelf_list_documents` | List documents by category. |
| `docshelf_convert_pdf` | Standalone PDF → Markdown (no shelf). |

### 2. Add to Claude Code

```bash
claude mcp add docshelf -- docshelf-mcp
# Optional: set the default shelf
claude mcp add docshelf --env DOCSHELF_ROOT=/path/to/shelf -- docshelf-mcp
```

### 3. Test from the command line

```bash
# Sanity check — should print the server version then wait on stdin
docshelf-mcp
```

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

The default engine (`pymupdf4llm`) is fast and good enough for ~95% of technical documents. For papers with complex tables, math, or scanned content, install the `marker-pdf` backend:

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
Not for the raw-URL trick — `raw.githubusercontent.com` won't serve them without auth. The local search tool works fine on private shelves; you just lose the "AI fetches sections directly" benefit. Make the doc repo public (separate from your code repo).

**Do I have to use GitHub?**
No. The shelf is just a directory. If you don't set a `github_remote`, INDEX.md still gets generated — entries just won't have URLs. You can host the static files anywhere that serves raw text (S3, Cloudflare R2, GitLab raw, Gitea, …) and post-process URLs yourself.

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

## Demo

A short walkthrough video / GIF is planned: <https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/demo.md> *(coming soon)*

---

## Architecture

For a deeper dive, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module layout, data flow, design rationale.

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
