# memshelf — Manifest

> Put your agent's memory on a shelf, hand it the index.

Working title: **memshelf**. Naming alternatives (`chatshelf`, `recall-shelf`,
`context-shelf`) are tracked in the Open questions section of
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## The problem

Long-running agent sessions accumulate context faster than they consume it:
conversation turns, research results, verbose tool output, intermediate
artifacts. Three bad things follow:

1. **Token burn.** The same accumulated history is re-sent and re-processed on
   every turn. Most of it is never referenced again.
2. **Context rot.** Model attention degrades as the window fills; the
   important 5% drowns in the transient 95%.
3. **Lossy, opaque forgetting.** When the window overflows, auto-compaction
   summarizes with no user control, no durable artifact, and no way to get
   the detail back. Ask "what did we decide about X three weeks ago?" and the
   honest answer is *gone*.

Chat projects have the mirror problem: users re-upload and re-explain the
same background in every project because there is no cheap, navigable place
for a conversation's residue to live.

## The bet

The docshelf pattern — **tiny index in context, bodies fetched on demand** —
is not specific to documents. It works for anything that can be serialized to
Markdown and addressed by a stable path. The agent's own memory qualifies.

The economics are already measured on the document side:
[docshelf's benchmark](../demo.md) shows ~3.7K tokens per answered question vs
1.2M for dumping the collection. memshelf inherits that math; the only new
costs are the one-time digest written at offload time and the occasional
recall fetch.

## Principles

1. **Memory is a git repo.** Plain Markdown + JSON sidecars: human-diffable,
   greppable, editable in any editor, portable across tools and vendors. No
   black-box memory store. If all memshelf tooling disappears tomorrow, the
   shelf remains a legible project chronicle.
2. **The index lives in context; the memory does not.** The only artifact
   permanently in the window is `INDEX.md` (kilobytes). Everything else is
   fetched by address, section-sized, on demand.
3. **The agent writes its own memory.** Digests are composed *at offload
   time, by the agent that still has the full context* — not by a separate
   summarizer service reading transcripts after the fact. Context locality is
   the cheapest and most accurate summarization there is; the tool layer only
   validates the contract (see ARCHITECTURE → Digest contract).
4. **Digest-first.** An episode is exactly as useful as its digest. A digest
   must preserve decisions, rejected alternatives (with reasons), produced
   artifacts, and open threads — because those are what future turns actually
   ask about. Bad digests turn the shelf into write-only memory; the design
   treats digest quality as the top risk.
5. **Private by default.** Conversations contain PII and secrets. The default
   shelf is private/local and is read over MCP (`read_document`), never via
   public raw URLs. The raw-URL path is an explicit opt-in for shelves that
   are genuinely public. A redaction pass runs before anything is written.
6. **Compose with docshelf, don't fork it.** Storage layout, splitting,
   indexing, search, reading, URL providers — all docshelf, used as a library
   and/or MCP server. memshelf adds the three layers docshelf deliberately
   doesn't have: capture, digesting, and trigger policy.
7. **Explicit over magic (v1).** Offloading is a visible action with a
   visible result; recall is a deliberate index-guided fetch. No auto-RAG
   injection of "relevant memories" into every prompt — that reintroduces the
   token burn and pollutes context with false positives.
8. **Persistence at write time.** Unlike docshelf (which stays out of git on
   purpose), a memory shelf auto-commits its own repo on every shelve:
   sessions are ephemeral, and memory that isn't persisted the moment it is
   written is memory lost. This is a deliberate, documented departure from
   docshelf's non-goal — scoped strictly to the shelf's own repo.
9. **Host-agnostic core, thin adapters.** v1 ships a Claude Code adapter
   (hooks + skill), but the core library, the episode format, and the
   MCP/CLI surfaces contain nothing Claude-specific. The shelf a Claude
   session writes today must be recallable from any other MCP client — or
   any LLM with mere file access — tomorrow. See ARCHITECTURE → Portability
   model.

## Non-goals

- **Not a RAG pipeline.** No vector DB, no embedding infra in v1 (kept as an
  extension point, same as docshelf).
- **Not automatic memory injection.** The agent navigates to memory; memory
  is not pushed into the agent.
- **Not a transcript archiver.** Raw logs are allowed as an *optional*
  episode section, but the primary artifact is the curated episode. Full
  verbatim history is the platform's job, not memshelf's.
- **Not a CMS, not multi-user, no UI.** Same posture as docshelf.
- **Not a replacement for platform memory features** (Claude Code
  auto-compaction, claude.ai project memory, memory plugins). memshelf's
  differentiators: user-owned, inspectable, git-versioned, cross-session,
  cross-tool. It composes with platform features rather than fighting them —
  e.g. shelving *before* auto-compaction fires, so compaction has less to
  destroy.

## Relationship to docshelf

| | docshelf | memshelf |
|---|---|---|
| Content | Documents a human curates (manuals, papers, recipes) | Episodes the agent curates (topics, investigations, session digests) |
| Write path | Passive: human drops a file | Active loop: triggers decide when to offload |
| Summaries | Human-written titles/descriptions | LLM-written digests under a validated contract |
| Git | Deliberately hands-off | Auto-commit on shelve (own repo only) |
| Visibility default | Public raw-URL friendly | Private, MCP read path |
| Reused as-is | — | splitter, indexer, SUBINDEX, search, read, doctor, providers |

## Success criteria

1. A working session that has produced >200K tokens of history keeps its live
   context under a configured budget **and** still answers "what did we
   decide about X and why" correctly via recall.
2. Token savings measured on ≥2 real projects with the methodology of
   docshelf's `benchmarks/token_savings.py` (shelved-and-recalled vs
   carried-in-context).
3. A human opening the shelf cold can reconstruct the project's history from
   INDEX + digests alone, without reading raw sections.
