# Announcement drafts

Two drafts: one for Reddit (friendly, problem-led), one for Show HN
(technical, dense, no fluff). Pick a launch window where you can babysit the
comments for ~6 hours.

---

## Reddit — `/r/ClaudeAI` and `/r/mcp`

### Title

> I got tired of "your project is too large" — wrote an MCP server that turns a folder of PDFs into a 5 KB index

Alternate titles:

- *docshelf-mcp: feed Claude 50 MB of manuals with a single INDEX.md*
- *Stop stuffing PDFs into Claude projects — give it a shelf instead*

### Body

```markdown
**The problem.**

I have ~30 hardware manuals for my homelab, plus a stack of recipes, plus
research PDFs. I want Claude to be able to answer questions across all of it.
But:

- You can't drop 80 MB of PDFs into a Claude project — it doesn't fit, and
  even if it did, the context window would melt.
- Copy-pasting the right pages works, but only after I remember *which*
  manual mentioned the thing.
- Splitting docs by hand is fine. Splitting 30 docs by hand is not.

**The tool.**

`docshelf-mcp` is an MCP server (Python, MIT) that:

1. Converts PDFs to Markdown.
2. Splits anything > 50 KB into chapter-by-chapter section files
   (5–50 KB each).
3. Regenerates an `INDEX.md` at the root that maps `category → document →
   chapter → section`, with `raw.githubusercontent.com` URLs.

You commit the folder to a public GitHub repo. You attach **only `INDEX.md`**
to your Claude project. The model fetches sections on demand. 50 MB shelf,
5 KB working set, no embeddings, no infra.

It also works as a plain Python library (`from docshelf_mcp import Shelf`)
if you don't want to wire it up to an MCP client.

**What's in v0.2.0:**

- Six MCP tools (`init_shelf`, `add_document`, `rebuild_index`, `search`,
  `list_documents`, `convert_pdf`).
- Ready-to-paste **project prompt** in three lengths
  (`docs/PROJECT_PROMPT.md`).
- Three example shelves: homelab manuals, recipes, research papers.
- CI on Python 3.10/3.11/3.12, MIT.

**Links:**

- Repo: https://github.com/ignatenkofi/docshelf-mcp
- PyPI: https://pypi.org/project/docshelf-mcp/ (`pip install docshelf-mcp`)
- Project prompt: https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/PROJECT_PROMPT.md

Happy to answer questions or take feature requests. The thing I'm most curious
about: what *non-obvious* document collections would benefit from this shape?
```

### Posting checklist

- [ ] Use the subreddit's "Project / Tool" or "Show & Tell" flair where it
      exists.
- [ ] No affiliate / tracking links.
- [ ] Plain text, no emoji-heavy headers (this hits the "AI slop" filter).
- [ ] Reply to the first 5–10 comments within the first hour.

---

## Show HN

### Title (HN headline rules: ≤ 80 chars, no clickbait, no "Show HN:" yourself — the form adds it)

> docshelf-mcp – an MCP server that gives Claude a shelf instead of 80 MB of PDFs

If the form trims it, fallback:

> An MCP server that turns a folder of PDFs into a chapter-split shelf for AI

### URL field

```
https://github.com/ignatenkofi/docshelf-mcp
```

### Text field (optional but recommended)

```text
Hey HN — small Python/MCP tool I'd been running as a 350-line script for
homelab manuals, generalised and released.

The idea: a Claude project can attach one file. PDFs are too big. Embeddings
are too much infra for the problem. So instead, you convert PDFs to Markdown,
split anything large on H2 boundaries into 5–50 KB section files, and
auto-generate an INDEX.md with raw.githubusercontent.com URLs. Attach the
INDEX to the project, point the model at it, and it fetches exactly the
section it needs. 50 MB collection → 5 KB working set.

Six MCP tools (init_shelf, add_document, rebuild_index, search,
list_documents, convert_pdf). Also usable as a library
(`from docshelf_mcp import Shelf`).

Design choices worth noting:

- pymupdf4llm by default (fast, ~95% good enough); marker-pdf is opt-in
  behind an extra (it pulls 2 GB of PyTorch).
- Splitter is idempotent — re-running on the same doc wipes and regenerates
  the split subdir.
- No automatic git commit. The tool stays out of git's way so it's safe to
  call from an agent.
- Slugify is Unicode-aware (NFKD + \w/UNICODE), so Cyrillic / CJK titles
  produce stable filenames.

CI on 3.10/3.11/3.12, MIT. v0.2.0 ships PyPI via trusted publishing and a
project-prompt doc you can paste into Custom Instructions.

Curious where the design breaks: very long single-H2 PDFs (some 4 MB
datasheets) are the obvious failure case — for those it falls back to
keeping the file whole and using grep-based search.

Repo: https://github.com/ignatenkofi/docshelf-mcp
Project prompt: https://github.com/ignatenkofi/docshelf-mcp/blob/main/docs/PROJECT_PROMPT.md
```

### Posting tips

- HN time-of-day matters. **8–10am ET on a weekday** is the broadest
  audience; **6–8am ET Saturday** is friendlier for niche tooling.
- Be in the thread for the first 90 minutes. First-page survival depends on
  early engagement.
- Don't argue. Reply with code, links, or "you're right, fixed it in PR #N".

---

## After the launch

- Cross-post the Reddit thread to `/r/selfhosted` and `/r/homelab` IF the
  homelab example resonated.
- Add quotes / use cases from comments to the README's "Examples" section.
- Open issues for everything that came up — even the "nice-to-have"s. It
  signals you're listening.
