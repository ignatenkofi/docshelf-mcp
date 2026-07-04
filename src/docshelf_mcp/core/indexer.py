"""Generate ``INDEX.md`` — the navigation page for a shelf.

The index is the *one* file you attach to your AI chat / Claude project.
For every document in the shelf, it lists:

* The category bucket (e.g. ``## Motherboards``).
* A human title + short description.
* A `raw.githubusercontent.com` URL the model can fetch on demand.
* For split documents: every section as its own link.

The index is **regenerated** every time the shelf changes — the source of
truth is the on-disk shelf state, not the previous index.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

__all__ = [
    "DocumentEntry",
    "build_index",
    "build_subindex",
    "write_subindexes",
    "scan_shelf",
    "raw_github_url",
    "DEFAULT_PREAMBLE",
    "SUBINDEX_FILENAME",
]

#: Navigation page generated inside each split-document directory.
SUBINDEX_FILENAME = "SUBINDEX.md"

#: In ``index_style="auto"``, split documents with more sections than this
#: are rendered in INDEX.md as a single SUBINDEX link instead of inlining
#: every section — keeps the index small for large shelves.
DEFAULT_SUBINDEX_THRESHOLD = 10


@dataclass
class DocumentEntry:
    """One document in a shelf."""

    category: str
    title: str
    description: str
    #: Path relative to the shelf root, e.g. ``"docs/motherboards/asus-x870.md"``.
    relative_path: str
    size_bytes: int
    #: Section files (relative paths) if the document was split. Empty list
    #: means the document is a single self-contained file.
    section_paths: list[str] = field(default_factory=list)


DEFAULT_PREAMBLE = (
    "This is the navigation index for the document shelf. "
    "Each entry below links to a Markdown file on GitHub (raw URL) — "
    "an AI assistant can fetch only the section it needs instead of "
    "loading the entire collection. Large documents are split by chapter; "
    "follow the section links for those."
)


def raw_github_url(remote: str, branch: str, relative_path: str) -> str:
    """Build a ``raw.githubusercontent.com`` URL.

    Args:
        remote: GitHub URL of the form ``https://github.com/owner/repo`` or
            ``git@github.com:owner/repo.git``.
        branch: Branch name (e.g. ``"main"``).
        relative_path: Path relative to the repo root, forward-slashed.

    Returns:
        Empty string if ``remote`` cannot be parsed (so the index still renders).
    """
    owner_repo = _parse_owner_repo(remote)
    if owner_repo is None:
        return ""
    owner, repo = owner_repo
    # Percent-encode path segments (spaces, #, ?, …) while keeping the slashes.
    path = quote(relative_path, safe="/")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


# owner and repo are each a run of non-slash, non-space characters — so a repo
# name may legitimately contain dots (``my.repo``). A trailing ``.git`` (clone
# suffix) or a trailing prose dot is stripped afterwards.
_GITHUB_REMOTE = re.compile(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)")


def _parse_owner_repo(remote: str) -> tuple[str, str] | None:
    m = _GITHUB_REMOTE.search(remote)
    if not m:
        return None
    repo = m.group("repo").rstrip(".")  # drop a trailing prose dot
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo:
        return None
    return m.group("owner"), repo


def scan_shelf(shelf_root: Path) -> list[DocumentEntry]:
    """Walk ``shelf_root/docs/`` and produce a :class:`DocumentEntry` list.

    Conventions:

    * ``docs/<category>/<doc>.md`` — a regular single-file document.
    * ``docs/<category>/<doc>/<NNN>-<slug>.md`` — a split document (the
      sibling directory of ``<doc>.md`` if both exist).
    * ``docs/<category>/.meta.json`` — optional override file with the
      shape ``{"<doc>.md": {"title": "...", "description": "..."}}``.
    """
    docs_root = shelf_root / "docs"
    entries: list[DocumentEntry] = []
    if not docs_root.exists():
        return entries

    for category_dir in sorted(p for p in docs_root.iterdir() if p.is_dir()):
        meta = _load_meta(category_dir)
        for md_file in sorted(category_dir.glob("*.md")):
            name = md_file.name
            override = meta.get(name, {})
            title = override.get("title") or _title_from_filename(md_file.stem)
            description = override.get("description", "")

            # Look for a sibling directory of the same stem — split sections.
            # SUBINDEX.md is navigation, not content, so it's not a section.
            split_dir = category_dir / md_file.stem
            section_paths: list[str] = []
            if split_dir.is_dir():
                section_paths = sorted(
                    str(p.relative_to(shelf_root).as_posix())
                    for p in split_dir.glob("*.md")
                    if p.name != SUBINDEX_FILENAME
                )

            entries.append(
                DocumentEntry(
                    category=category_dir.name,
                    title=title,
                    description=description,
                    relative_path=str(md_file.relative_to(shelf_root).as_posix()),
                    size_bytes=md_file.stat().st_size,
                    section_paths=section_paths,
                )
            )
    return entries


def _load_meta(category_dir: Path) -> dict[str, dict]:
    meta_path = category_dir / ".meta.json"
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _title_from_filename(stem: str) -> str:
    """Best-effort: ``asus-x870-plus_ug`` → ``Asus X870 Plus Ug``."""
    parts = re.split(r"[-_]+", stem)
    return " ".join(p.capitalize() if p.islower() else p for p in parts if p)


def _pretty_section(section_relpath: str) -> str:
    """``docs/foo/bar/003-power-supplies.md`` → ``Power supplies``."""
    stem = Path(section_relpath).stem
    stem = re.sub(r"^\d+-", "", stem)
    text = stem.replace("-", " ").replace("_", " ").strip()
    return text.capitalize() if text else stem


def _subindex_relpath(entry: DocumentEntry) -> str:
    """``docs/cat/foo.md`` → ``docs/cat/foo/SUBINDEX.md``."""
    stem_dir = entry.relative_path[: -len(".md")] if entry.relative_path.endswith(".md") else entry.relative_path
    return f"{stem_dir}/{SUBINDEX_FILENAME}"


def build_subindex(
    entry: DocumentEntry,
    *,
    remote: str = "",
    branch: str = "main",
    section_sizes: dict[str, int] | None = None,
) -> str:
    """Render the SUBINDEX.md text for one split document.

    Links use raw GitHub URLs when ``remote`` is set; otherwise they are
    relative to the split directory, so the page stays navigable in local
    editors and the GitHub web UI.
    """
    sizes = section_sizes or {}
    lines: list[str] = []
    lines.append(f"# {entry.title} — sections")
    lines.append("")
    desc = entry.description.strip()
    if desc:
        lines.append(desc)
        lines.append("")

    doc_name = Path(entry.relative_path).name
    if remote:
        doc_link = f"[`{doc_name}`]({raw_github_url(remote, branch, entry.relative_path)})"
    else:
        doc_link = f"[`{doc_name}`](../{doc_name})"
    lines.append(
        f"Full document: {doc_link} (~{entry.size_bytes // 1024} KB — "
        "prefer the individual sections below)."
    )
    lines.append("")

    for sect in entry.section_paths:
        label = _pretty_section(sect)
        target = raw_github_url(remote, branch, sect) if remote else Path(sect).name
        size = sizes.get(sect)
        suffix = f" (~{size // 1024} KB)" if size is not None else ""
        lines.append(f"- [{label}]({target}){suffix}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Auto-generated by [docshelf-mcp]"
        "(https://github.com/ignatenkofi/docshelf-mcp) — "
        "regenerated on every `rebuild_index`. See `INDEX.md` at the shelf root.*"
    )
    lines.append("")
    return "\n".join(lines)


def write_subindexes(
    shelf_root: Path,
    entries: list[DocumentEntry],
    *,
    remote: str = "",
    branch: str = "main",
) -> list[Path]:
    """Write a SUBINDEX.md into every split-document directory.

    Returns the written paths. Documents without sections are skipped.
    """
    written: list[Path] = []
    for entry in entries:
        if not entry.section_paths:
            continue
        sizes: dict[str, int] = {}
        for sect in entry.section_paths:
            try:
                sizes[sect] = (shelf_root / sect).stat().st_size
            except OSError:
                continue
        text = build_subindex(entry, remote=remote, branch=branch, section_sizes=sizes)
        path = shelf_root / _subindex_relpath(entry)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def build_index(
    shelf_name: str,
    entries: list[DocumentEntry],
    *,
    remote: str = "",
    branch: str = "main",
    preamble: str = DEFAULT_PREAMBLE,
    category_order: list[str] | None = None,
    index_style: str = "auto",
    subindex_threshold: int = DEFAULT_SUBINDEX_THRESHOLD,
) -> str:
    """Render the INDEX.md text.

    Args:
        shelf_name: Human-readable shelf name, used as the H1.
        entries: From :func:`scan_shelf`.
        remote: GitHub remote URL. Empty string disables raw URL links.
        branch: Branch for raw URLs.
        preamble: Intro paragraph below the H1.
        category_order: Optional pinned order for the first N categories.
            Unknown categories follow in alphabetical order.
        index_style: How split documents are rendered — ``"inline"`` lists
            every section link in INDEX.md, ``"subindex"`` links the
            document's SUBINDEX.md instead, ``"auto"`` (default) inlines
            small splits and defers to SUBINDEX beyond ``subindex_threshold``
            sections.
        subindex_threshold: Section count above which ``"auto"`` switches
            to the SUBINDEX link.

    Returns:
        The full Markdown text of ``INDEX.md``.
    """
    lines: list[str] = []
    lines.append(f"# {shelf_name}")
    lines.append("")
    if remote:
        lines.append(f"Repo: <{remote}>")
        lines.append("")
    if preamble:
        lines.append(preamble)
        lines.append("")

    by_cat: dict[str, list[DocumentEntry]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)

    seen: set[str] = set()
    ordered: list[str] = []
    for cat in category_order or []:
        if cat in by_cat:
            ordered.append(cat)
            seen.add(cat)
    for cat in sorted(by_cat.keys()):
        if cat not in seen:
            ordered.append(cat)

    if not ordered:
        lines.append("_No documents yet. Use the `add_document` tool to start your shelf._")
        lines.append("")
        return "\n".join(lines)

    for cat in ordered:
        lines.append(f"## {_humanize_category(cat)}")
        lines.append("")
        for entry in sorted(by_cat[cat], key=lambda e: e.title.lower()):
            _render_entry(
                lines,
                entry,
                remote,
                branch,
                index_style=index_style,
                subindex_threshold=subindex_threshold,
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Auto-generated by [docshelf-mcp]"
        "(https://github.com/ignatenkofi/docshelf-mcp). "
        "Edit the source files in `docs/` and call `rebuild_index` to regenerate.*"
    )
    lines.append("")
    return "\n".join(lines)


def _humanize_category(cat: str) -> str:
    return cat.replace("-", " ").replace("_", " ").strip().title()


def _render_entry(
    lines: list[str],
    entry: DocumentEntry,
    remote: str,
    branch: str,
    *,
    index_style: str = "auto",
    subindex_threshold: int = DEFAULT_SUBINDEX_THRESHOLD,
) -> None:
    url = raw_github_url(remote, branch, entry.relative_path) if remote else ""
    label = f"`{Path(entry.relative_path).name}`"
    if url:
        full_link = f"[{label}]({url})"
    else:
        full_link = label

    desc = entry.description.strip()
    desc_suffix = f" — {desc}" if desc else ""

    if not entry.section_paths:
        lines.append(f"- **{entry.title}**{desc_suffix} — {full_link}")
        return

    use_subindex = index_style == "subindex" or (
        index_style == "auto" and len(entry.section_paths) > subindex_threshold
    )

    lines.append(f"### {entry.title}{desc_suffix}")
    lines.append("")
    size_kb = entry.size_bytes // 1024
    lines.append(
        f"Full document: {full_link} "
        f"(~{size_kb} KB — prefer pulling individual sections below)."
    )
    lines.append("")
    if use_subindex:
        sub_rel = _subindex_relpath(entry)
        if remote:
            sub_link = f"[SUBINDEX]({raw_github_url(remote, branch, sub_rel)})"
        else:
            sub_link = f"[SUBINDEX]({sub_rel})"
        lines.append(
            f"Sections ({len(entry.section_paths)}): see the {sub_link} "
            "for the per-chapter list."
        )
        lines.append("")
    else:
        for sect in entry.section_paths:
            sect_label = _pretty_section(sect)
            if remote:
                sect_url = raw_github_url(remote, branch, sect)
                lines.append(f"- [{sect_label}]({sect_url})")
            else:
                lines.append(f"- {sect_label} (`{sect}`)")
        lines.append("")
        lines.append(f"  *(sections: {len(entry.section_paths)})*")
        lines.append("")
