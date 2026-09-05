---
layout: default
title: docshelf-mcp
description: "Put your manuals on a shelf, hand the AI the index."
---

# docshelf-mcp

> Put your manuals on a shelf, hand the AI the index.

[![PyPI](https://img.shields.io/pypi/v/docshelf-mcp.svg)](https://pypi.org/project/docshelf-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/ignatenkofi/docshelf-mcp/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![Glama](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp/badges/score.svg)](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp)

An [MCP](https://modelcontextprotocol.io/) server that turns a folder of PDFs and Markdown into a chat-project-friendly document collection.

AI agents see a single `INDEX.md` and pull individual sections by raw GitHub URL on demand — instead of choking on a 4 MB datasheet.

---

## The problem

You have 30 hardware manuals, or 200 cooking recipes, or a stack of research PDFs. You want Claude / ChatGPT to answer questions across them — but:

- ❌ You can't dump 80 MB of PDFs into a chat project. It won't fit, and you'd burn the context window even if it did.
- ❌ Copy-pasting the relevant pages works only after you remember which manual mentioned the thing.
- ❌ Long files mean wasteful retrieval — the model loads a whole RouterOS guide just to answer about VLANs.

## The fix

**docshelf-mcp** turns any folder of documents into a navigable shelf:

1. **Convert** — PDFs → clean Markdown via `pymupdf4llm` (the `pdf` extra).
2. **Split** — large manuals split by chapter into 1–10 KB sections.
3. **Index** — auto-generated `INDEX.md` lists every document with raw GitHub URLs.
4. **Fetch on demand** — AI reads the small index, then fetches only the section it needs over HTTPS.

You drop the 5 KB `INDEX.md` into your AI project. The 50 MB of source stays on GitHub.

---

## Install

```bash
pip install docshelf-mcp            # Markdown shelves
pip install "docshelf-mcp[pdf]"     # + PDF conversion (pymupdf4llm)
```

Or via Smithery-style MCP config in your Claude Desktop:

```json
{
  "mcpServers": {
    "docshelf": {
      "command": "docshelf-mcp",
      "env": { "DOCSHELF_ROOT": "/path/to/your/shelf" }
    }
  }
}
```

---

## Quick start

```python
from docshelf_mcp import Shelf

shelf = Shelf("/path/to/your/repo")
shelf.add_document("manuals/router.pdf", category="network", title="Mikrotik RouterOS")
shelf.rebuild_index()
```

Or via MCP tools from inside a Claude chat:

- `docshelf_add_document(...)` — convert + split + index a new file
- `docshelf_rebuild_index()` — regenerate the navigation page
- `docshelf_search(query, max_results=10)` — grep across all sections
- `docshelf_list_documents(category=None)` — catalog view
- `docshelf_convert_pdf(pdf_path, out_dir, quality="fast")` — one-shot conversion

---

## Use cases

- **🏠 Homelab manuals** — Mikrotik, Cudy, ASUS, Intel datasheets. AI answers "how do I configure VLAN trunks on RouterOS?" with the exact section quoted.
- **🍲 Cooking recipes** — a folder of 200 family recipes. AI suggests dinner based on what's in your fridge.
- **📚 Research papers** — a stack of arXiv PDFs. AI synthesizes findings across them.
- **🧑‍🏫 Course materials** — lectures, slides, homework. AI helps students find specific topics.
- **📑 Compliance documentation** — internal SOPs, audit reports. AI surfaces the relevant policy.

---

## Try it on a real shelf

There's a live, public docshelf at
<https://github.com/ignatenkofi/gh.project.homelab> — a homelab manuals
collection covering routers, switches, NICs, PSUs, RAM, NAS, racks, and more.

Open the [`INDEX.md`](https://github.com/ignatenkofi/gh.project.homelab/blob/main/INDEX.md)
— that's the only file a chat project needs. From there an AI agent can
follow links into chapter SUBINDEXes for the big manuals (RouterOS, X550)
or fetch the small per-device files directly.

A simplified `INDEX.md` looks like this:

```markdown
# My Shelf — Index

## 🌐 Network gear
- [Router admin manual](https://raw.githubusercontent.com/you/shelf/main/docs/network/router-admin.md)
- [Switch configuration guide](https://raw.githubusercontent.com/you/shelf/main/docs/network/switch.md)

## 🖥 Hardware datasheets (split by chapter)
### NIC datasheet
- [Chapter 1 — Overview](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/01-overview.md)
- [Chapter 8 — Device registers](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/08-device-registers.md)
- [Chapter 9 — PCIe register map](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/09-pcie-register-map.md)
…
```

The AI sees a few KB of structure and the raw URLs. When asked
"how do I configure PCIe BARs?", it fetches **only**
`09-pcie-register-map.md` and answers from that — not the whole 4 MB
original PDF.

---

## Does it actually save tokens? (measured)

On this very homelab shelf, answering a question the docshelf way costs
**~3.7K tokens** — versus **1.22M** to dump the collection (99.7% fewer), and
the RouterOS manual alone (~1.05M tokens) doesn't fit in a 200K context window
at all. See the **[measured demo →](demo.md)** for the full breakdown, chart,
and a benchmark you can run on your own shelf.

---

## The same pattern for an agent's own memory — memshelf

[memshelf-mcp](https://ignatenkofi.github.io/memshelf-mcp/) is the sibling
project: closed conversation topics are offloaded to a private docshelf shelf
as digest-indexed episodes, the agent keeps only `INDEX.md` in context and
recalls one section when it needs it. Measured over one week on the author's
live shelf: 34 episodes, ~8.6K tokens of standing cost per session against
~1.9M tokens of shelved mass — **≈220 : 1** — and a fresh agent answered
5 / 5 recall questions from the index alone. Numbers and method:
**[memshelf's measured demo →](https://github.com/ignatenkofi/memshelf-mcp/blob/main/docs/demo.md)**.

## Resources

- 📦 [PyPI](https://pypi.org/project/docshelf-mcp/) — `pip install docshelf-mcp`
- 🐙 [GitHub repo](https://github.com/ignatenkofi/docshelf-mcp) — source, issues, contributing
- 🌐 [Glama listing](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp) — install button + security score
- 📋 [Project prompts](https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/PROJECT_PROMPT.md) — ready-to-paste instructions for Claude / ChatGPT / API
- 📖 [Architecture](https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/ARCHITECTURE.md) — how it works internally
- 🧠 [memshelf-mcp](https://github.com/ignatenkofi/memshelf-mcp) — the sibling: an AI agent's own working memory on a docshelf shelf

---

## License

MIT — © [ignatenkofi](https://github.com/ignatenkofi)
