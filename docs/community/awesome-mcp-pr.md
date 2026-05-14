# Submission to `awesome-mcp-servers`

Repo: <https://github.com/punkpeye/awesome-mcp-servers>

## Where to put it

The README is grouped by category. `docshelf-mcp` is a documentation /
knowledge-base server, so the best home is one of these (whichever the README
has at the time of submission):

- **📚 Knowledge & Memory** — first choice; closest semantic fit.
- **📂 File Systems** — acceptable fallback if the knowledge category doesn't
  exist or is too crowded.
- **🗄 Databases / Indexes** — only if the above two are unavailable.

Format used elsewhere in the README:

```text
- [name](url) - description.
```

## One-liner — copy/paste this into the PR

```markdown
- [ignatenkofi/docshelf-mcp](https://github.com/ignatenkofi/docshelf-mcp) - Turn a folder of PDFs and Markdown into an AI-friendly shelf: convert, split by chapter, auto-generate `INDEX.md`. Lets Claude/ChatGPT answer across a 50 MB collection from a 5 KB index by fetching only the section it needs over raw GitHub URLs. (Python, MIT)
```

## Alternative shorter form (if maintainers prefer < 200 chars)

```markdown
- [ignatenkofi/docshelf-mcp](https://github.com/ignatenkofi/docshelf-mcp) - Convert PDFs + Markdown into a chapter-split shelf with an auto-generated `INDEX.md`. AI fetches only the section it needs via raw GitHub URLs. (Python, MIT)
```

## PR description

Title:

```text
Add docshelf-mcp — chapter-split document shelves for AI projects
```

Body:

```markdown
Hi! Adding `docshelf-mcp` to the list.

**What it does:** turns a folder of PDFs / Markdown into a chat-project-friendly
document collection. Converts PDFs, splits long files chapter-by-chapter,
regenerates `INDEX.md`. Designed so a Claude / ChatGPT project can attach a
single 5 KB `INDEX.md` and fetch any chapter on demand via
`raw.githubusercontent.com`.

**Why it's useful:**
- Avoids dumping 50 MB of PDFs into a chat project.
- No embeddings infra needed — uses public GitHub raw URLs.
- Works as a Python library too (`from docshelf_mcp import Shelf`).

**Status:** v0.2.0 on PyPI, CI green on 3.10–3.12, MIT, examples for homelab
manuals / recipes / research papers in the repo.

Happy to adjust the placement or wording.
```

## Checklist before submitting

- [ ] README on the project root has CI badge passing.
- [ ] PyPI release exists (so the install line in the description is honest).
- [ ] At least one example shelf is browseable from the README.
- [ ] License is in the repo root (MIT, already there).
- [ ] Description is one sentence, ends in a period, mentions language + license.
