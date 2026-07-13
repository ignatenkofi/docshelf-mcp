# RFC-0001: memshelf — agent memory on a docshelf

> **Moved.** This RFC was adopted and the design now lives in
> [**ignatenkofi/memshelf-mcp**](https://github.com/ignatenkofi/memshelf-mcp)
> (`docs/`), where it continues to evolve. The copy in this directory is a
> frozen historical snapshot as of adoption (2026-07-13) and will not be
> updated — notably, the storage-mode rework (local-first, no-remote
> default) and the positioning/hero-scenarios sections exist only in the
> new repo.

| | |
|---|---|
| **Status** | Adopted → moved to [memshelf-mcp](https://github.com/ignatenkofi/memshelf-mcp) |
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
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Concepts, layers, shelf layout, episode format, MCP tool surface, trigger policy, portability model, privacy, failure modes |
| [`LANDSCAPE.md`](LANDSCAPE.md) | Prior-art survey (2026-07), platform built-ins, positioning, alternative directions, risks |
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
| 2026-07-13 | Portability model merged (PR #43). Prior-art survey completed → `LANDSCAPE.md`: no existing project combines episodes+digests+git+INDEX-navigation; closest are claude-mem (loop, opaque substrate) and a long tail of ≤4-star siblings. Design amendments applied: mechanical eviction (design decision 6), injection budget / KV-cache discipline (7), prompt-injection-on-recall and platform-collision failure modes, subagent-deposit trigger (v2), memory-tool adapter in portability rings. Direction kept, scope sharpened; alternatives documented in `LANDSCAPE.md`. | draft, pending author review |
| 2026-07-13 | Adopted. Author created [memshelf-mcp](https://github.com/ignatenkofi/memshelf-mcp); design seeded there (with the storage-mode rework and positioning additions) and continues in that repo — see its `docs/DECISIONS.md`. This directory is frozen as a historical snapshot. | author |
