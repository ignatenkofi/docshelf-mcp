# Project Prompt — drop-in instructions for AI projects

> Three ready-to-paste prompts that teach an AI assistant how to navigate a
> `docshelf-mcp`-style document collection without choking on it.

Pick the length that fits your tool. All three describe the same workflow —
they just differ in how much context you spend.

---

## TL;DR — what these prompts do

A docshelf is a public Git repository that contains:

- an auto-generated `INDEX.md` at the root (your single navigation file),
- a `docs/` folder of small Markdown chapters / sections,
- raw URLs that fetch any chapter on demand.

These prompts tell the AI: **don't load the whole repo. Read `INDEX.md`, then
pull exactly the section you need over HTTPS.** That's the entire point of the
shelf — turn a 50 MB collection into a 5 KB index.

---

## 1. Short prompt — for Claude Project Custom Instructions (< 500 chars)

```text
This project uses the docshelf pattern. INDEX.md is the entry point.
When answering: read INDEX → fetch ONLY the needed section file via its
GitHub raw URL (use WebFetch / fetch / curl). Don't load full source files
into context. For large manuals split into chapters, follow INDEX → chapter
SUBINDEX → section file.
```

---

## 2. Medium prompt — ~150 words

```text
This project uses the docshelf pattern (https://github.com/ignatenkofi/docshelf-mcp).

INDEX.md is the only file attached to this project. It lists every document
in the shelf with a category, a one-line description, and a `raw.githubusercontent.com`
URL. Large manuals are split into per-chapter section files; each chapter has
its own SUBINDEX.

When you need to answer a question:

1. Look up the topic in INDEX.md.
2. If the entry points to a single section file, fetch it via its raw URL.
3. If it points to a chapter with a SUBINDEX, fetch the SUBINDEX first, then
   the specific section.
4. Quote the section URL when citing.

Do NOT ask the user to upload the full PDF. Do NOT load entire long files into
context "just in case". Token economy and latency both depend on you fetching
the minimum slice.

Example: question about VLAN trunks → INDEX → "Mikrotik chapter 11 — Switching"
→ chapter SUBINDEX → fetch `0073-vlan-trunks.md` → answer with the URL as the
citation.
```

---

## 3. Full prompt — ~400 words

```text
This project uses the docshelf pattern (https://github.com/ignatenkofi/docshelf-mcp).
A docshelf is a public GitHub repository organised like this:

  shelf/
    INDEX.md              ← the one file attached here
    docs/
      <category>/
        <document>.md     ← short docs live as one file
        <document>/       ← long docs are split into chapters/sections
          SUBINDEX.md
          001-overview.md
          002-...md

INDEX.md groups documents by category and gives each one a `raw.githubusercontent.com`
URL. Split documents have their own SUBINDEX in their subdirectory, with raw
URLs for every section file.

## Navigation rules

1. Always start at INDEX.md. Find the category that matches the question.
2. For a small (single-file) document, fetch the file directly via its raw URL
   using whatever HTTP tool you have (WebFetch, fetch, curl, requests, etc.).
3. For a split document, fetch the SUBINDEX first, scan the section list, then
   fetch only the section(s) that contain the answer.
4. If two sections look relevant, fetch them in parallel rather than serially.
5. Always cite the raw URL of the section you actually used. Format:
   `[001-overview.md](raw URL)` so the user can click through to verify.

## Anti-patterns — please don't

- ❌ Don't ask the user to "attach the PDF" or upload the original source. The
  whole point of the shelf is that they don't have to.
- ❌ Don't fetch a full multi-megabyte document when a single section would do.
  Section files are 5–50 KB on purpose.
- ❌ Don't speculate from the section *title* — fetch the file and read it.
- ❌ Don't paraphrase without citing the section URL.

## What if the section isn't in INDEX?

If the user's question is about something the shelf doesn't cover yet, say so
plainly and suggest they add the document via the docshelf MCP tool:

  - Add to Claude Desktop / Claude Code (see docshelf-mcp README).
  - Use the `docshelf_add_document` tool with the source PDF or Markdown.
  - The shelf will regenerate INDEX.md; on the next session it'll be searchable.

Don't fabricate page numbers or invent sections. If it's not on the shelf, it
isn't on the shelf.
```

---

## How to use this with…

### Claude Project (web app)

1. Open your project → **Project Knowledge** → upload `INDEX.md` from the shelf.
2. Open **Custom Instructions** → paste the short or medium prompt.
3. New chats in this project will follow the rules automatically.

### Claude Code

Put the full prompt at the top of `CLAUDE.md` in the workspace root (or in
the shelf's own `CLAUDE.md` if you've checked the shelf out locally). Claude
Code reads it on session start.

```bash
echo '<paste the medium prompt here>' > CLAUDE.md
```

### Claude Desktop with the docshelf MCP server

The MCP server already exposes `docshelf_search` and `docshelf_list_documents`,
so the model can navigate the shelf without HTTP fetches. The prompt still
helps: it tells the model **to prefer those tools over re-asking the user**.

### Anthropic API / other LLM providers

Paste the full prompt into the `system` parameter. If your provider doesn't
have a native HTTP-fetch tool, add a simple one (Python `requests.get`,
JS `fetch`) before sending the prompt.

### Other MCP-aware clients (Continue, Zed, Cursor, etc.)

Same pattern: register `docshelf-mcp` as an MCP server, paste the medium
prompt as a system instruction.

---

## See also

- Repo + full docs: <https://github.com/ignatenkofi/docshelf-mcp>
- The `INDEX.md` format spec: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- End-to-end usage walkthrough: [`docs/USAGE.md`](USAGE.md)
- Back to the [README](../README.md)
