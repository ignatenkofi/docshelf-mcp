# RFC-0001: memshelf — agent memory on a docshelf

| | |
|---|---|
| **Status** | Draft |
| **Author** | Philipp Ignatenko (concept), drafted with Claude |
| **Created** | 2026-07-13 |
| **Target** | New companion project (working title `memshelf`), separate repo once approved |
| **Depends on** | [docshelf-mcp](https://github.com/ignatenkofi/docshelf-mcp) as the storage/index layer |

## One paragraph

docshelf proved that a large *document* collection can live outside the
context window behind a 5 KB index (measured: [~3.7K tokens vs 1.2M per
question](../demo.md)). **memshelf applies the same pattern to the agent's
own working memory**: long conversations, research dumps, and bulky tool
output are periodically offloaded to a shelf as Markdown "episodes", each
replaced in live context by a short digest plus an INDEX entry. When the
agent needs a detail from the past, it walks INDEX → SUBINDEX → section and
fetches exactly that — instead of dragging the whole history through every
turn or losing it to lossy auto-compaction.

## Files in this RFC

| File | What it covers |
|---|---|
| [`MANIFEST.md`](MANIFEST.md) | Why the project exists, principles, non-goals, relationship to docshelf |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Concepts, layers, shelf layout, episode format, MCP tool surface, trigger policy, privacy, failure modes |
| [`ROADMAP.md`](ROADMAP.md) | Milestones M0–M3 with exit criteria |
| [`examples/episode-example.md`](examples/episode-example.md) | A realistic offloaded episode file |
| [`examples/INDEX-example.md`](examples/INDEX-example.md) | What the memory shelf's INDEX looks like |

## Why this lives here (for now)

This RFC transits in `docshelf-mcp/docs/rfc/` because the design leans
heavily on docshelf internals and there is no dedicated repo yet. The
recommendation in `MANIFEST.md` is a **separate companion project** — once
that decision is confirmed, this directory seeds the new repo and a short
pointer stays behind.

## Decision log

| Date | Decision | By |
|---|---|---|
| 2026-07-13 | Draft created; form = companion project over docshelf, primary surface v1 = Claude Code / Cowork. Both revisitable — see Open questions in `ARCHITECTURE.md`. | draft |
| 2026-07-13 | RFC base merged (PR #42). Author confirmed: v1 targets Claude Code, but the core must stay host-agnostic with room for other Claude surfaces and other LLMs → Portability model added to `ARCHITECTURE.md`, principle 9 to `MANIFEST.md`, CLI surface to M1. Direction itself open to discussion pending prior-art survey (`LANDSCAPE.md`, in progress). | author |
