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

1. **Convert** — PDFs → clean Markdown via `pymupdf4llm`.
2. **Split** — large manuals split by chapter into 1–10 KB sections.
3. **Index** — auto-generated `INDEX.md` lists every document with raw GitHub URLs.
4. **Fetch on demand** — AI reads the small index, then fetches only the section it needs over HTTPS.

You drop the 5 KB `INDEX.md` into your AI project. The 50 MB of source stays on GitHub.

---

## Install

```bash
pip install docshelf-mcp
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

## What an INDEX.md looks like

After running docshelf on a folder of manuals, the auto-generated `INDEX.md`
is the only file you hand the AI:

```markdown
# My Shelf — Index

## 🌐 Network gear
- [Router admin manual](https://raw.githubusercontent.com/you/shelf/main/docs/network/router-admin.md)
- [Switch configuration guide](https://raw.githubusercontent.com/you/shelf/main/docs/network/switch.md)

## 🖥 Hardware datasheets (split by chapter)
### NIC datasheet — 240+ sections
- [Chapter 1 — Overview](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/01-overview.md)
- [Chapter 8 — Device registers](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/08-device-registers.md)
- [Chapter 9 — PCIe register map](https://raw.githubusercontent.com/you/shelf/main/docs/hardware/nic/09-pcie-register-map.md)
…
```

The AI sees ~5 KB of structure and 200 raw URLs. When asked
"how do I configure PCIe BARs?", it fetches **only** `09-pcie-register-map.md`
(~80 KB) and answers from that — not the whole 4 MB original PDF.

---

## Resources

- 📦 [PyPI](https://pypi.org/project/docshelf-mcp/) — `pip install docshelf-mcp`
- 🐙 [GitHub repo](https://github.com/ignatenkofi/docshelf-mcp) — source, issues, contributing
- 🌐 [Glama listing](https://glama.ai/mcp/servers/ignatenkofi/docshelf-mcp) — install button + security score
- 📋 [Project prompts](https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/PROJECT_PROMPT.md) — ready-to-paste instructions for Claude / ChatGPT / API
- 📖 [Architecture](https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/ARCHITECTURE.md) — how it works internally

---

## License

MIT — © [ignatenkofi](https://github.com/ignatenkofi)
