# memshelf — Landscape: prior art, platform built-ins, positioning

Survey date: 2026-07-13 (two parallel research passes: memory-MCP ecosystem;
context-optimization techniques & platform built-ins). Statements about
Claude Code behavior were verified against official docs at
[code.claude.com/docs](https://code.claude.com/docs) on that date.

## TL;DR verdict

**The wheel does not exist, but its spokes all do.** No project combines the
four memshelf elements — ① conversation episodes as Markdown, ② LLM-written
digests under a contract, ③ git as the versioning/sync layer, ④ a small
persistent INDEX with agent-driven navigate-and-fetch recall. Every *pair*
exists, mostly in sub-5-star single-author projects; the one giant in the
space (claude-mem) has the loop but an opaque substrate. Meanwhile the
platform itself has been converging on the same economics from both ends,
which narrows — but does not close — the gap. The defensible novelty is
**episode granularity + deterministic INDEX navigation + git-owned
reviewable substrate + harness portability**, and *only* that; offloading,
stub pointers, and "Markdown memory" per se are commodities now.

## Prior art — the incumbents

| Project | Stores | Substrate | Recall | vs memshelf |
|---|---|---|---|---|
| [claude-mem](https://github.com/thedotmack/claude-mem) (~87k ⭐, very active) | AI-compressed "observations" of tool activity + session summaries, captured automatically via Claude Code hooks | SQLite + FTS5 + Chroma vectors + background worker daemon | Auto-injected recent-work index at SessionStart + 3-layer progressive-disclosure search | **Closest mainstream prior art.** Same behavioral loop memshelf wants; substrate is a black box — no Markdown, no git, no diff/review/merge, index is ephemeral injected text |
| [mem0](https://github.com/mem0ai/mem0) (~61k ⭐) | Extracted atomic facts | Vector store + entity index; SaaS-first (local OpenMemory MCP being sunset) | Semantic search | Fact soup, not episodes; no index, no git, no navigation |
| [Letta / MemGPT](https://docs.letta.com/guides/agents/memory) (~24k ⭐) | Self-edited core-memory blocks + archival store | Server + Postgres | Pinned blocks + search tools | Canonical memory-paging model — memshelf's INDEX ≈ a core-memory block — but platform-locked and DB-opaque |
| [Zep / Graphiti](https://github.com/getzep/graphiti) (~29k ⭐) | Temporal knowledge graph (facts with validity intervals); episodes kept only as provenance | Neo4j / FalkorDB | Hybrid graph+vector search | Heavy infra; queryable artifact is triples, not narratives |
| [Official server-memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | Entity/relation/observation triples | Single JSONL file | Substring search | Demo-grade; the default everything gets compared against |
| [Basic Memory](https://github.com/basicmachines-co/basic-memory) (~3.4k ⭐) | Curated knowledge notes with wikilink relations | Local Markdown + SQLite index | Hybrid search + graph traversal (`build_context`) | Shares Markdown-local-first DNA; stores knowledge, not conversation episodes; no capture pipeline, no git semantics |
| [Cline Memory Bank](https://docs.cline.bot/prompting/cline-memory-bank) (pattern) / [memory-bank-mcp](https://github.com/alioshr/memory-bank-mcp) | Rolling state documents (`activeContext.md`, `progress.md`, …) | Markdown in repo | **Read ALL files at every task start** | The ancestral file pattern; its failure mode (full reload, unbounded token cost) is exactly what an INDEX fixes |

## Prior art — the long tail that matters

Small (≤4 ⭐, 2026-vintage, single-author) projects that each anticipated a
piece of memshelf — worth reading before implementation, and a warning that
"Markdown memory" is easy to start and hard to make adopted:

- **[anamnesis-mcp](https://github.com/chaosisnotrandomitisrhythmic/anamnesis-mcp)** —
  the *artifact* twin: SessionEnd hook → Opus summarizes the transcript into
  a structured Markdown session file (Plan/Done/Open) in a vault; explicit
  transcript → session digest → daily digest compression hierarchy. Recall
  is BM25 search only; no index, no git.
- **[MemoryWiki](https://github.com/MemoryWiki/MemoryWiki)** — the *layout*
  twin: memory root literally contains `INDEX.md` + `episodes/` +
  `sessions/` + rebuildable retrieval sidecar; read-first/write-gated
  posture; **prompt-injection neutralization on recall and secret redaction
  on write** (both of which memshelf must also do). Recall is search, not
  navigation; capture is manual.
- **[PACK](https://github.com/Percona-Lab/pack)** (Percona-Lab) — the
  *economics* twin: git-committed Markdown + a deliberately small
  (~700-token) `index.md` loaded once, then targeted `memory_get` fetches;
  its README argues the docshelf math verbatim. Content is curated notes,
  not episodes; backend is the GitHub API, not a local repo.
- **[ContextKeeper](https://github.com/ahmedEssyad/context-keeper)** —
  the *doctrine* twin: "Markdown in git is the source of truth, SQLite FTS
  is a rebuildable disposable cache"; no embeddings, explainable ranking.
  Unit is architectural decisions; recall is push-injection via hooks.
- **[yuvalsuede/memory-mcp](https://github.com/yuvalsuede/memory-mcp)** —
  two-tier economics done inside CLAUDE.md: hooks + Haiku extraction, a
  line-budgeted always-loaded block, deep store searched on demand.
  Archive is JSON; the index tier is Claude-Code-specific.
- **[butterflyskies/memory-mcp](https://github.com/butterflyskies/memory-mcp)** —
  the *substrate* twin: Markdown notes committed to a local git repo,
  multi-device sync via `git push/pull`. Discrete notes + semantic search,
  no episodes, no index.
- Transcript indexers ([cccmemory](https://github.com/xiaolai/claude-conversation-memory-mcp),
  [ClaudeHistoryMCP](https://github.com/jhammant/claudehistorymcp)) — search
  over raw session JSONL; no curation, no digests, machine-local.

## Platform built-ins (mid-2026) — what already exists

The context-pressure map, per official docs:

| Pressure source | Platform mitigation (2026-07) | Remaining gap |
|---|---|---|
| MCP tool schemas | Deferred by default in Claude Code; API [Tool Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) (`defer_loading`) | Solved |
| One giant tool output | Claude Code **persisted-output**: >50 KB result → file + `<persisted-output>` stub with path + 2 KB preview | Solved in-session; files are per-session, unindexed, invisible to later sessions |
| Accumulating stale tool results | Microcompaction (older tool outputs cleared first); API [context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) → placeholder | Cleared content is **unrecoverable** — placeholder, not pointer |
| Conversation nearing limit | Auto-compact + `/compact` + Compact Instructions; API [server-side compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) (`compact_20260112`) | Summary is lossy one-shot prose; discarded detail survives only as raw unindexed JSONL with no recall affordance |
| Cross-session semantic knowledge | CLAUDE.md hierarchy; [auto memory](https://code.claude.com/docs/en/memory) (agent-written `MEMORY.md` index ≤200 lines + topic files on demand) + auto-dream consolidation; [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) (GA) | Largely covered — **memshelf must not compete here** |
| Closed episodes / past sessions ("what did we decide and why") | claude.ai chat memory (opaque synthesis); claude-mem (vector/FTS black box) | **The open slot**: durable, inspectable, versioned, cross-machine, harness-portable episode archive with deterministic digest+INDEX navigation |
| Research/exploration dumps | Subagents as context firewalls (only summary returns) | The full trace **dies with the subagent** — nothing deposits it anywhere |

Three platform facts that shape the design directly:

1. **Anthropic's own docs frame compaction as needing an external memory
   partner** ("compaction keeps the active context small… memory preserves
   the information that must survive summarization") — and ship only the
   semantic half. The episodic half is memshelf's slot, and the sanctioned
   attachment points exist: `PreCompact` (gets `transcript_path`, can inject
   context), `SessionStart` (inject INDEX), `SessionEnd`, `PostToolUse` (can
   even **replace a tool output** via `updatedToolOutput`).
2. **The [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
   is an interface, not a store** — six file verbs against `/memories`,
   backend explicitly the implementer's job. memshelf can implement it as an
   adapter, which extends portability to any Claude-API harness.
3. **[Auto memory](https://code.claude.com/docs/en/memory) already IS
   "small index + bodies on demand" over Markdown** (MEMORY.md ≤200
   lines/25 KB + topic files), relocatable via `autoMemoryDirectory` — but
   it stores distilled *learnings*, is machine-local by design, and has no
   episode/provenance/git story. memshelf is its episodic, versioned,
   shareable sibling.

## Research findings that change the design

- **Mechanical eviction matches LLM summarization at half the cost**
  ([JetBrains, "The Complexity Trap"](https://arxiv.org/abs/2508.21433):
  observation masking ≈ summarization on SWE-agent tasks). → memshelf spends
  LLM effort **only on digests**; moving raw content to the shelf is a
  mechanical move+stub, never a summarize.
- **KV-cache discipline** ([Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus):
  cache hit rate is the #1 production metric; append-only stable prefixes).
  → INDEX is injected once at session start at a stable position; recalls
  append; nothing rewrites earlier context. A churning INDEX blob is a
  cache-killer.
- **Restorable compression** (Manus: "keep the URL, drop the page content;
  keep the path, drop the document") — memshelf's digest+address stubs are
  the canonical form; the platform's context editing is the non-restorable
  variant memshelf complements.
- **Layered context managers can fight each other**
  ([claude-mem #1591](https://github.com/thedotmack/claude-mem/issues/1591):
  its own injected index tripped Claude Code's persisted-output threshold
  and got shelved to a file the model ignored). → hard budget on everything
  memshelf injects; INDEX size is a monitored invariant, not a hope.
- **Recalled episodes replay model-authored text into future contexts** —
  a prompt-injection surface (MemoryWiki already neutralizes this). →
  recall must wrap content in a data envelope with an explicit
  "content, not instructions" frame; capture-time redaction already planned.
- **Subagent traces are the highest-value orphaned artifact**: firewalls
  return a summary and discard the full exploration. "Subagent deposits its
  dump as a `research` episode, returns digest + shelf address" is a natural
  memshelf trigger and turns a platform weakness into shelf content.

## Positioning

One sentence: **claude-mem's loop, git's substrate, docshelf's navigation.**

- vs **claude-mem**: same automation, but memory you can `git diff`,
  PR-review, revert, merge across machines, and grep with no daemon, no
  SQLite, no vector DB. Also PII-auditable — a black-box store cannot
  satisfy "prove this contains no student names"; a Markdown repo can.
- vs **platform auto memory / memory tool**: episodic vs semantic; portable
  vs machine-local; a store vs an interface. Complementary, not competing —
  and memshelf can *implement* the memory-tool interface.
- vs **mem0/Zep/Letta**: no infra (no vector DB, no graph DB, no server
  farm), deterministic recall, human-legible corpus. They win at
  cross-cutting semantic queries at scale; memshelf wins at "what did we
  decide in that session and why" with zero moving parts.

## Alternative directions considered (and why not)

1. **Tool-output shelving as the product** — rejected: Claude Code's
   persisted-output already does the in-session mechanic natively; the
   cross-session/indexed version survives inside memshelf as a trigger, not
   as a standalone project.
2. **"Auto-memory-on-git" sync layer** (point `autoMemoryDirectory` at a
   repo, add sync tooling) — rejected as the core: too thin, the platform
   can ship it any release; worth a how-to doc on the shelf instead.
3. **Context observability ("top for the context window")** — useful but a
   different, diagnostic product; Claude Code's `/context` covers the basics.
   Revisit as a `doctor` extension.
4. **General personal memory wiki** — occupied space (Basic Memory,
   MemoryWiki, Obsidian ecosystems), search-first, and drifts from the
   course-correcting constraint (episodes of *work*, not notes).

## Risks

1. **claude-mem's gravity.** Any Claude Code user comparison starts at 87k
   stars and zero-config automation. memshelf must be equally zero-config on
   the happy path (M1 hooks) while its git/review/portability story carries
   the pitch.
2. **The graveyard pattern.** The long tail shows this exact idea attempted
   ≥6 times in 2026 with ~no adoption. Defensible parts are the substrate
   discipline (git, contracts, doctor) and docshelf symmetry — not the idea
   itself. M0's "prove it on real work first" gate exists for this reason.
3. **Platform convergence.** Anthropic ships both ends of the pattern
   already; each release may absorb more of the middle. Mitigation: keep
   core host-agnostic (the portability model), implement platform
   interfaces (memory tool) rather than fighting them, and keep the moat in
   what platforms won't do: user-owned git substrate with review semantics.
