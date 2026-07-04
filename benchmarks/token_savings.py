#!/usr/bin/env python3
"""Measure the token cost of answering a question from a docshelf, three ways.

For a question whose answer lives in one section of one document, an LLM can:

  A. **Dump the whole collection** into context — every document.
  B. **Load the whole containing document** — the full manual/book.
  C. **The docshelf way** — read ``INDEX.md`` (tiny), then fetch just the one
     section it needs.

This script computes the token cost of each on a real shelf, so the savings
are measured, not asserted.

Token counting is network-free by default: it uses OpenAI's published rule of
thumb of ~4 characters per token. Because all three measures use the *same*
counter, the tokenizer cancels out of the savings ratios — the percentages are
estimator-independent; only the absolute token counts shift (±10-20%) between
tokenizers. Pass ``--tiktoken`` to count with ``tiktoken`` (cl100k_base)
instead, if it's installed and can fetch its vocabulary.

Usage::

    python benchmarks/token_savings.py /path/to/shelf [/path/to/another] ...
    python benchmarks/token_savings.py --json /path/to/shelf     # machine-readable
    python benchmarks/token_savings.py --tiktoken /path/to/shelf # exact GPT tokens

A "shelf" is any directory with an ``INDEX.md`` and a ``docs/`` (or ``DOCS/``)
tree. Point it at your own shelf to get your own numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

#: Common working context budgets, for the "does it even fit?" check.
_CONTEXT_WINDOWS = {"200K (Claude)": 200_000, "1M (Claude Sonnet)": 1_000_000}

#: A tiktoken Encoding when ``--tiktoken`` is used, else None (char/4 estimate).
_ENCODER = None
COUNTER_NAME = "chars/4 estimate"


def _make_counter(use_tiktoken: bool) -> None:
    """Select the token counter, updating the module globals."""
    global _ENCODER, COUNTER_NAME
    _ENCODER, COUNTER_NAME = None, "chars/4 estimate"
    if not use_tiktoken:
        return
    try:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("cl100k_base")
        COUNTER_NAME = "tiktoken/cl100k_base"
    except Exception as exc:  # noqa: BLE001 — fall back to the estimate
        print(
            f"warning: tiktoken unavailable ({exc}); using char/4 estimate",
            file=sys.stderr,
        )


def _count(text: str) -> int:
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    # OpenAI's published rule of thumb: ~4 characters per token (English).
    return max(1, round(len(text) / 4))


def _tokens(path: Path) -> int:
    return _count(path.read_text(encoding="utf-8", errors="replace"))


def _find_docs_root(root: Path) -> Path:
    for name in ("docs", "DOCS"):
        if (root / name).is_dir():
            return root / name
    return root


def _classify(docs_root: Path) -> tuple[list[Path], list[Path]]:
    """Split every content ``.md`` into (full documents, split sections).

    A *document* is a full manual/book at ``<docs_root>/<category>/<doc>.md``.
    Anything nested deeper (``…/<doc>/…/NNN-*.md``) is a *section* fragment.
    ``INDEX.md`` / ``SUBINDEX.md`` (navigation) and ``*.pymupdf.md`` (raw
    pre-clean duplicates some older shelves keep) are ignored.
    """
    documents: list[Path] = []
    sections: list[Path] = []
    for p in sorted(docs_root.rglob("*.md")):
        if p.name in ("INDEX.md", "SUBINDEX.md") or p.name.endswith(".pymupdf.md"):
            continue
        if p.parent.parent == docs_root:
            documents.append(p)  # docs_root/<category>/<doc>.md
        else:
            sections.append(p)  # deeper == a split section fragment
    return documents, sections


@dataclass
class ShelfReport:
    shelf: str
    index_tokens: int
    document_count: int
    section_count: int
    collection_tokens: int          # A: sum of all full documents
    median_document_tokens: int     # B: a typical whole manual
    largest_document_tokens: int
    median_section_tokens: int      # C ingredient
    #: C: cost to answer one question the docshelf way.
    docshelf_query_tokens: int
    #: Savings of C vs dumping the collection (A) and vs loading the biggest
    #: single document whole (the case where chapter-splitting pays off).
    savings_vs_collection_pct: float
    savings_vs_largest_pct: float
    #: Documents that overflow each context window if loaded whole.
    overflow: dict


def analyze(shelf: Path) -> ShelfReport:
    docs_root = _find_docs_root(shelf)
    documents, sections = _classify(docs_root)
    if not documents:
        raise SystemExit(f"No documents found under {docs_root}")

    index_path = shelf / "INDEX.md"
    index_tokens = _tokens(index_path) if index_path.is_file() else 0

    doc_tokens = [_tokens(p) for p in documents]
    sec_tokens = [_tokens(p) for p in sections] or doc_tokens
    collection = sum(doc_tokens)
    largest_doc = max(doc_tokens)
    median_doc = int(statistics.median(doc_tokens))
    median_sec = int(statistics.median(sec_tokens))
    docshelf_query = index_tokens + median_sec

    overflow = {
        label: sum(1 for t in doc_tokens if t > limit)
        for label, limit in _CONTEXT_WINDOWS.items()
    }

    return ShelfReport(
        shelf=shelf.name,
        index_tokens=index_tokens,
        document_count=len(documents),
        section_count=len(sections),
        collection_tokens=collection,
        median_document_tokens=median_doc,
        largest_document_tokens=largest_doc,
        median_section_tokens=median_sec,
        docshelf_query_tokens=docshelf_query,
        savings_vs_collection_pct=round(100 * (1 - docshelf_query / collection), 2),
        savings_vs_largest_pct=round(100 * (1 - docshelf_query / largest_doc), 2),
        overflow=overflow,
    )


def _fmt(n: int) -> str:
    return f"{n:,}"


def _print_human(r: ShelfReport) -> None:
    print(f"\n=== {r.shelf} ===")
    print(f"  documents: {r.document_count} | split sections: {r.section_count}")
    print(f"  INDEX.md: {_fmt(r.index_tokens)} tokens")
    print(f"  whole collection (A): {_fmt(r.collection_tokens)} tokens")
    print(f"  median document (B):  {_fmt(r.median_document_tokens)} tokens")
    print(f"  largest document:     {_fmt(r.largest_document_tokens)} tokens")
    print(f"  median section:       {_fmt(r.median_section_tokens)} tokens")
    print(
        f"  docshelf query (C = INDEX + 1 section): "
        f"{_fmt(r.docshelf_query_tokens)} tokens"
    )
    print(f"  → {r.savings_vs_collection_pct}% cheaper than dumping the collection")
    print(f"  → {r.savings_vs_largest_pct}% cheaper than loading the biggest document")
    for label, n in r.overflow.items():
        if n:
            print(f"  ⚠ {n} document(s) overflow a {label} context window if loaded whole")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shelves", nargs="+", help="Shelf directories to analyze.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    ap.add_argument(
        "--tiktoken",
        action="store_true",
        help="Count with tiktoken (cl100k_base) instead of the char/4 estimate.",
    )
    args = ap.parse_args(argv)
    _make_counter(args.tiktoken)

    reports = [analyze(Path(s).expanduser().resolve()) for s in args.shelves]
    if args.json:
        print(
            json.dumps(
                {"counter": COUNTER_NAME, "shelves": [asdict(r) for r in reports]},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"token counter: {COUNTER_NAME}")
        for r in reports:
            _print_human(r)


if __name__ == "__main__":
    sys.exit(main())
