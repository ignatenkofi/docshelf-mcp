"""Markdown cleanup + H2 splitter.

The PDF→Markdown step (e.g. ``pymupdf4llm``) routinely produces a few
artefacts that make the result hard for an LLM (or a human) to read:

* Stray ``# ...`` "headings" that are really CLI dumps or table rows.
* 5–20 consecutive blank lines from page breaks.

:func:`clean_markdown` smooths those out. :func:`split_by_h2` then breaks
a long document into one section per ``## `` heading, returning
``[(title, body), ...]`` so the caller can write each section to its own
file. :func:`write_split_files` is the on-disk variant that handles
collisions, numbered prefixes, and an idempotent directory rewrite.

All three of cleanup, H2 counting, and H2 slicing are **fence-aware**: a
``## `` or ``# `` line inside a fenced code block (```` ``` ```` or
``~~~``) is code, not structure, so it is never counted as a heading, never
used as a split boundary, and never demoted by the fake-H1 heuristic. This
matters for the CLI dumps and config exports this project routinely
ingests, where ``## `` comment lines are common.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from docshelf_mcp.core.slugify import slugify

__all__ = [
    "clean_markdown",
    "split_by_h2",
    "write_split_files",
    "should_split",
    "lint_sections",
    "SectionWarning",
]

# Heuristic for "this `# ...` line is not really a chapter heading":
# CLI output and routing tables that the PDF extractor mistook for H1.
# Real H1s start with a letter/word; CLI noise starts with a digit + uppercase
# flag (e.g. "# 0 X chain=...", "# 12 ADC ...", "# 0 R ether1 ...").
_FAKE_H1 = re.compile(
    r"^# (?:"
    r"\d+\s+[A-Z]+\b"      # # 12 ADC ...
    r"|\d+\s+[A-Z]\b"      # # 0 X ...
    r")",
)

_H2_RE = re.compile(r"^## (.+?)\s*$")

#: A fenced-code delimiter line: up to 3 leading spaces, then a run of >=3
#: backticks or tildes, then an optional info string. Follows CommonMark
#: closely enough for PDF-extracted Markdown.
_FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<marker>`{3,}|~{3,})(?P<info>.*)$")

#: Files smaller than this are not auto-split. 50 KB is a good empirical
#: cutoff — small enough that a Claude project tolerates the whole file,
#: large enough that we don't fragment a normal user guide.
DEFAULT_SPLIT_THRESHOLD_BYTES = 50 * 1024


def _iter_code_flags(lines: Iterable[str]) -> Iterator[tuple[str, bool]]:
    """Yield ``(line, in_code)`` for each input line.

    ``in_code`` is True for every line inside a fenced code block, *including*
    the opening and closing fence-marker lines themselves — so a caller can
    treat "``in_code`` is False" as "this line is eligible to be a heading".

    Fence rules (CommonMark, trimmed for robustness on messy extractor
    output): a fence opens on a line of >=3 backticks or tildes indented <=3
    spaces; a backtick opener whose info string contains a backtick is not a
    valid fence. It closes on a later line using the *same* character, a run
    at least as long as the opener, and only whitespace after the run (a
    closing fence carries no info string). An unterminated fence runs to EOF.
    """
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in lines:
        m = _FENCE_RE.match(line)
        if not in_fence:
            if m:
                marker = m.group("marker")
                char = marker[0]
                # A backtick opener's info string may not contain a backtick.
                if char == "`" and "`" in m.group("info"):
                    yield line, False
                    continue
                in_fence, fence_char, fence_len = True, char, len(marker)
                yield line, True  # the opener line is itself code
            else:
                yield line, False
        else:
            if (
                m
                and m.group("marker")[0] == fence_char
                and len(m.group("marker")) >= fence_len
                and not m.group("info").strip()
            ):
                in_fence, fence_char, fence_len = False, "", 0
                yield line, True  # the closer line is itself code
            else:
                yield line, True  # still inside the fence


def _clean_lines(lines: Iterable[str]) -> list[str]:
    """Run the line-level cleanup heuristics. Returns the cleaned list."""
    out: list[str] = []
    blank_run = 0
    for line, in_code in _iter_code_flags(raw.rstrip("\n") for raw in lines):
        # Demote fake H1s to indented code (preserves content, kills the false
        # header) — but never touch lines inside a fenced block, where a
        # "# 12 ADC ..." is verbatim CLI output, not a stray heading.
        if not in_code and _FAKE_H1.match(line):
            line = "    " + line[2:]

        # Collapse 3+ blank lines into one — but preserve blank lines inside
        # fences, where they are meaningful code formatting.
        if not in_code and not line.strip():
            blank_run += 1
            if blank_run >= 2:
                continue
        else:
            blank_run = 0

        out.append(line)
    return out


def clean_markdown(text: str) -> str:
    """Smooth out common PDF-extraction artefacts in a Markdown string.

    Returns the cleaned text (always ends with a single trailing newline).
    """
    return "\n".join(_clean_lines(text.splitlines())) + "\n"


def should_split(text: str, threshold_bytes: int = DEFAULT_SPLIT_THRESHOLD_BYTES) -> bool:
    """Heuristic: does this document warrant a chapter-by-chapter split?

    True if the UTF-8 byte length exceeds ``threshold_bytes`` AND the document
    has at least two H2 headings to split on. Returning False here means the
    caller should keep the document as a single file.
    """
    if len(text.encode("utf-8")) <= threshold_bytes:
        return False
    h2_count = sum(
        1
        for line, in_code in _iter_code_flags(text.splitlines())
        if not in_code and _H2_RE.match(line)
    )
    return h2_count >= 2


def split_by_h2(text: str) -> list[tuple[str, str]]:
    """Split a Markdown string on H2 boundaries.

    Returns a list of ``(title, body)`` pairs. Content before the first H2
    is returned with title ``"preamble"`` and is omitted if it is entirely
    whitespace.

    Each body starts at its ``## `` heading line — so writing the body verbatim
    to a file preserves the heading.
    """
    sections: list[tuple[str, list[str]]] = [("preamble", [])]
    for line, in_code in _iter_code_flags(text.splitlines()):
        m = None if in_code else _H2_RE.match(line)
        if m:
            title = m.group(1).strip()
            sections.append((title, [line]))
        else:
            # Fenced ``## `` lines and both fence markers land here, so each
            # section body keeps balanced fences (no orphan closer next door).
            sections[-1][1].append(line)

    if not "\n".join(sections[0][1]).strip():
        sections.pop(0)

    return [(title, "\n".join(body).rstrip() + "\n") for title, body in sections]


def write_split_files(
    sections: list[tuple[str, str]],
    target_dir: Path,
    *,
    clean_existing: bool = True,
) -> list[Path]:
    """Write each ``(title, body)`` section to ``target_dir/NNN-slug.md``.

    Args:
        sections: Output of :func:`split_by_h2`.
        target_dir: Output directory. Created if missing.
        clean_existing: If True (default), nukes ``target_dir`` first so the
            split is fully idempotent on re-run.

    Returns:
        List of written :class:`Path` objects, in section order.
    """
    if clean_existing and target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    used_slugs: set[str] = set()
    for idx, (title, body) in enumerate(sections, start=1):
        slug = slugify(title)
        if slug in used_slugs:
            slug = f"{slug}-{idx:03d}"
        used_slugs.add(slug)

        filename = f"{idx:03d}-{slug}.md"
        path = target_dir / filename

        # If the body doesn't already start with a heading and the slice has a
        # real title (not "preamble"), prepend one so the standalone file is
        # self-explanatory.
        if title != "preamble" and not body.lstrip().startswith("#"):
            body = f"# {title}\n\n{body}"

        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


# --------------------------------------------------------------- section lint

#: A run of dotted leaders (``......``) as a table-of-contents artefact leaks in.
_TOC_LEADER_RE = re.compile(r"\.{4,}|(?:\.\s){3,}")
#: A leading section number like ``2.5`` / ``5.6.1`` followed by the heading text.
_LEADING_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\s+(.*)$")
#: A bare measurement/token that reads like body text, not a chapter title.
_SENTENCE_TAIL_RE = re.compile(r"\.\s+\w")


@dataclass
class SectionWarning:
    """A heuristic warning that a split section's heading looks like junk.

    ``index`` is the 1-based section number — it matches the ``NNN`` prefix
    that :func:`write_split_files` assigns, so a warning maps straight onto a
    section file.
    """

    index: int
    heading: str
    rule: str
    detail: str


def _looks_like_toc_leak(title: str) -> bool:
    return bool(_TOC_LEADER_RE.search(title))


def _looks_like_unit_fragment(title: str) -> bool:
    # A real heading may start with a section number ("2.5 Bridging"); the junk
    # case is a number followed by prose that runs into a sentence
    # ("2.5 Gb/s. Full duplex is supported.").
    m = _LEADING_NUMBER_RE.match(title)
    if not m:
        return False
    rest = m.group(1).strip()
    return bool(_SENTENCE_TAIL_RE.search(rest) or rest.endswith("."))


def _looks_like_table_residue(title: str) -> bool:
    if "|" in title or "\t" in title:
        return True
    tokens = title.split()
    if len(tokens) < 3:
        return False
    numeric = sum(1 for t in tokens if re.fullmatch(r"[\d.,%/+-]+", t))
    return numeric / len(tokens) > 0.5


def _normalize_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def lint_sections(sections: list[tuple[str, str]]) -> list[SectionWarning]:
    """Flag split sections whose heading looks like a PDF-extraction artefact.

    Detection only — nothing is rewritten or dropped. Rules:

    * ``toc-leak`` — dotted table-of-contents leader (``5.6 LTR ....... 42``).
    * ``unit-fragment`` — a body sentence mistaken for a heading
      (``2.5 Gb/s. Full duplex ...``).
    * ``table-residue`` — a table row (pipes, tabs, or mostly numbers).
    * ``near-duplicate`` — a heading whose normalized form repeats an earlier
      section in the same document.

    Args:
        sections: Output of :func:`split_by_h2` — the same list handed to
            :func:`write_split_files`, so warning ``index`` values line up with
            the written ``NNN-*.md`` files.

    Returns:
        Warnings in section order.
    """
    warnings: list[SectionWarning] = []
    seen: dict[str, int] = {}
    for idx, (title, _body) in enumerate(sections, start=1):
        if title == "preamble":
            continue
        if _looks_like_toc_leak(title):
            warnings.append(SectionWarning(idx, title, "toc-leak",
                "heading contains a dotted table-of-contents leader"))
        elif _looks_like_unit_fragment(title):
            warnings.append(SectionWarning(idx, title, "unit-fragment",
                "heading reads like a body sentence, not a chapter title"))
        elif _looks_like_table_residue(title):
            warnings.append(SectionWarning(idx, title, "table-residue",
                "heading looks like a table row (pipes/tabs or mostly numbers)"))

        norm = _normalize_title(title)
        if norm:
            if norm in seen:
                warnings.append(SectionWarning(idx, title, "near-duplicate",
                    f"heading duplicates section {seen[norm]:03d}"))
            else:
                seen[norm] = idx
    return warnings
