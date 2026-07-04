"""The :class:`Shelf` — high-level façade for one document collection.

A shelf is a directory shaped like::

    my-shelf/
    ├── .docshelf.json        # metadata: name, remote, branch, category order
    ├── INDEX.md              # auto-generated navigation page
    ├── docs/
    │   ├── motherboards/
    │   │   ├── .meta.json    # optional title/description overrides
    │   │   ├── asus-x870.md
    │   │   └── asus-x870/    # split sections if asus-x870.md is large
    │   │       ├── 001-preamble.md
    │   │       └── 002-bios.md
    │   └── psu/
    │       └── seasonic-gx-1000.md
    └── .gitignore

This module never invokes git directly — the user (or the caller) is in
charge of staging, committing, and pushing. The shelf only manages the
disk state.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from docshelf_mcp.core.converter import Quality, pdf_to_markdown
from docshelf_mcp.core.indexer import (
    DEFAULT_PREAMBLE,
    DEFAULT_SUBINDEX_THRESHOLD,
    SUBINDEX_FILENAME,
    DocumentEntry,
    _title_from_filename,
    build_index,
    scan_shelf,
    write_subindexes,
)
from docshelf_mcp.core.slugify import slugify
from docshelf_mcp.core.splitter import (
    DEFAULT_SPLIT_THRESHOLD_BYTES,
    SectionWarning,
    _expected_split_names,
    clean_markdown,
    lint_sections,
    should_split,
    split_by_h2,
    write_split_files,
)

__all__ = [
    "Shelf",
    "ShelfConfig",
    "AddResult",
    "RemoveResult",
    "ReadResult",
    "DoctorFinding",
]


SHELF_METADATA_FILENAME = ".docshelf.json"

#: Extra weight per query-token occurrence found on a heading line, so a
#: document whose title/chapter names the query ranks above body-only matches.
_HEADING_BOOST = 5


def _make_snippet(text: str, pos: int, width: int = 200) -> str:
    """Return a whitespace-collapsed excerpt around ``pos``, snapped to word
    boundaries and marked with ellipses when truncated."""
    start = max(pos - width // 3, 0)
    end = min(pos + (2 * width) // 3, len(text))
    frag = text[start:end]
    # Drop partial words at the trimmed edges.
    if start > 0 and " " in frag:
        frag = frag[frag.find(" ") + 1 :]
    if end < len(text) and " " in frag:
        frag = frag[: frag.rfind(" ")]
    frag = re.sub(r"\s+", " ", frag).strip()
    return f"{'…' if start > 0 else ''}{frag}{'…' if end < len(text) else ''}"


@dataclass
class ShelfConfig:
    """Persistent shelf metadata, stored as ``.docshelf.json`` at the root."""

    name: str = "Document Shelf"
    remote: str = ""
    branch: str = "main"
    preamble: str = DEFAULT_PREAMBLE
    category_order: list[str] = field(default_factory=list)
    split_threshold_bytes: int = DEFAULT_SPLIT_THRESHOLD_BYTES
    #: How split documents render in INDEX.md: "inline" lists every section,
    #: "subindex" links the per-document SUBINDEX.md, "auto" (default)
    #: inlines small splits and switches to SUBINDEX beyond the threshold.
    index_style: str = "auto"
    subindex_threshold_sections: int = DEFAULT_SUBINDEX_THRESHOLD
    #: URL provider for generated links: "github" (default), "gitlab",
    #: "gitea", "custom" (uses ``url_template``), or "none" (relative links).
    provider: str = "github"
    #: Template for ``provider="custom"`` — placeholders {owner}/{repo}/
    #: {branch}/{path}. Covers S3, R2, or any static host.
    url_template: str = ""

    def url_for(self, relative_path: str) -> str:
        """Resolve a shelf-relative path to a fetch URL under this config."""
        from docshelf_mcp.core.indexer import shelf_url

        return shelf_url(
            self.provider, self.remote, self.branch, self.url_template, relative_path
        )

    @classmethod
    def load(cls, shelf_root: Path) -> ShelfConfig:
        meta_path = shelf_root / SHELF_METADATA_FILENAME
        if not meta_path.is_file():
            return cls()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, shelf_root: Path) -> None:
        meta_path = shelf_root / SHELF_METADATA_FILENAME
        meta_path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


@dataclass
class AddResult:
    """Outcome of :meth:`Shelf.add_document`."""

    document_path: Path
    section_paths: list[Path]
    was_split: bool
    converted_from_pdf: bool
    #: Heuristic warnings about suspicious section headings (detection only).
    warnings: list[SectionWarning] = field(default_factory=list)


@dataclass
class RemoveResult:
    """Outcome of :meth:`Shelf.remove_document`."""

    #: Everything that was (or, for a dry run, would be) deleted.
    removed_paths: list[Path]
    was_split: bool
    dry_run: bool


@dataclass
class ReadResult:
    """Outcome of :meth:`Shelf.read_document`."""

    #: Normalized path relative to the shelf root.
    relative_path: str
    content: str
    size_bytes: int
    #: True if the file is larger than the returned slice.
    truncated: bool


@dataclass
class DoctorFinding:
    """One integrity issue found by :meth:`Shelf.doctor`."""

    rule: str
    severity: str  # "error" | "warning" | "info"
    #: Path (relative to the shelf root, posix) the finding is about.
    path: str
    detail: str
    suggested_fix: str
    #: Set True when ``doctor(fix=True)`` resolved this finding.
    fixed: bool = False


class Shelf:
    """High-level shelf operations.

    Instantiate with the path to a shelf directory (the directory itself need
    not exist — :meth:`init` will create it).

    >>> shelf = Shelf("~/Documents/my-docs").init(name="My Docs",
    ...     remote="https://github.com/me/my-docs")
    >>> shelf.add_document("manual.pdf", category="laptops", title="ThinkPad X1")
    >>> shelf.rebuild_index()
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self._config: ShelfConfig | None = None

    # ------------------------------------------------------------------ config

    @property
    def config(self) -> ShelfConfig:
        if self._config is None:
            self._config = ShelfConfig.load(self.root)
        return self._config

    def save_config(self) -> None:
        self.config.save(self.root)

    # ------------------------------------------------------------- bootstrap

    def init(
        self,
        *,
        name: str = "Document Shelf",
        remote: str = "",
        branch: str = "main",
        default_categories: Iterable[str] | None = None,
        provider: str = "",
        url_template: str = "",
    ) -> Shelf:
        """Create the shelf directory layout if it doesn't already exist.

        Idempotent: existing files and directories are preserved.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(exist_ok=True)

        config = ShelfConfig.load(self.root)
        config.name = config.name or name
        if name and config.name == "Document Shelf":
            config.name = name
        if remote:
            config.remote = remote
        if branch:
            config.branch = branch
        if provider:
            config.provider = provider
        if url_template:
            config.url_template = url_template
        if default_categories:
            for cat in default_categories:
                (self.root / "docs" / cat).mkdir(exist_ok=True)
                if cat not in config.category_order:
                    config.category_order.append(cat)
        config.save(self.root)
        self._config = config

        # .gitignore — keep the shelf friendly with git users.
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# docshelf — local-only artefacts\n"
                ".DS_Store\n"
                "*.swp\n"
                "__pycache__/\n",
                encoding="utf-8",
            )

        # Seed INDEX.md so a fresh shelf is browsable immediately.
        self.rebuild_index()
        return self

    # --------------------------------------------------------- add document

    def add_document(
        self,
        source: Path | str,
        *,
        category: str,
        title: str,
        description: str = "",
        split: bool = True,
        quality: Quality = "fast",
        rebuild_index: bool = True,
    ) -> AddResult:
        """Add (or replace) a document in the shelf.

        Args:
            source: Path to a ``.pdf`` or ``.md`` file.
            category: Category bucket (e.g. ``"laptops"``). Created if missing.
            title: Human-readable title — used in the INDEX entry.
            description: Short description (one sentence). Empty by default.
            split: If True (default) and the document is large enough, split it
                by H2 into a sibling subdirectory.
            quality: PDF conversion quality preset (``"fast"`` or ``"high"``).
            rebuild_index: If True (default), regenerate INDEX.md after writing
                the document. Batch callers can pass False and call
                :meth:`rebuild_index` once at the end for O(N) instead of
                O(N²) index rebuilds.

        Returns:
            :class:`AddResult` with the on-disk paths.

        Raises:
            FileNotFoundError: ``source`` doesn't exist.
            ValueError: ``source`` is not a .pdf or .md file.
        """
        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        suffix = source.suffix.lower()
        if suffix not in {".pdf", ".md"}:
            raise ValueError(
                f"Unsupported source type {suffix!r}; expected .pdf or .md"
            )

        category_slug = slugify(category, max_len=80) or "uncategorized"
        category_dir = self.root / "docs" / category_slug
        category_dir.mkdir(parents=True, exist_ok=True)

        doc_stem = slugify(title, max_len=80) or "document"
        doc_path = category_dir / f"{doc_stem}.md"

        if suffix == ".pdf":
            raw_md = pdf_to_markdown(source, quality=quality)
            converted_from_pdf = True
        else:
            raw_md = source.read_text(encoding="utf-8", errors="replace")
            converted_from_pdf = False

        cleaned = clean_markdown(raw_md)
        if not cleaned.lstrip().startswith("#"):
            cleaned = f"# {title}\n\n{cleaned}"
        doc_path.write_text(cleaned, encoding="utf-8")

        section_paths: list[Path] = []
        was_split = False
        warnings: list[SectionWarning] = []
        split_dir = category_dir / doc_stem
        if split and should_split(cleaned, self.config.split_threshold_bytes):
            sections = split_by_h2(cleaned)
            if len(sections) >= 2:
                section_paths = write_split_files(sections, split_dir)
                was_split = True
                warnings = lint_sections(sections)
        elif split_dir.is_dir():
            # Document is no longer large enough — wipe the stale split.
            import shutil

            shutil.rmtree(split_dir)

        # Record title/description in .meta.json for the indexer.
        self._update_category_meta(category_dir, doc_path.name, title, description)

        # Auto-rebuild INDEX.md so the on-disk state and the index stay in sync.
        # Batch callers pass rebuild_index=False and rebuild once at the end.
        if rebuild_index:
            self.rebuild_index()

        return AddResult(
            document_path=doc_path,
            section_paths=section_paths,
            was_split=was_split,
            converted_from_pdf=converted_from_pdf,
            warnings=warnings,
        )

    # ------------------------------------------------------ add directory

    def add_directory(
        self,
        source_dir: Path | str,
        *,
        category: str,
        pattern: Iterable[str] = ("*.pdf", "*.md"),
        split: bool = True,
        quality: Quality = "fast",
    ) -> list[dict]:
        """Add every matching file in a directory, rebuilding the index once.

        Each file's title defaults to a humanized version of its filename
        stem. Files are processed in sorted order; a per-file failure (e.g. a
        corrupt PDF) is captured and reported, and the remaining files are
        still ingested.

        Args:
            source_dir: Directory to scan (non-recursive).
            category: Category bucket for every file. Created if missing.
            pattern: Glob patterns to include. Defaults to PDFs and Markdown.
            split: Passed through to :meth:`add_document`.
            quality: PDF conversion quality preset.

        Returns:
            One result dict per file, each with ``file`` and ``status``
            (``"ok"`` or ``"error"``); ``ok`` entries carry the
            :class:`AddResult`, ``error`` entries carry an ``error`` string.

        Raises:
            FileNotFoundError: ``source_dir`` doesn't exist or isn't a directory.
        """
        source_dir = Path(source_dir).expanduser().resolve()
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Not a directory: {source_dir}")

        matches: list[Path] = []
        seen: set[Path] = set()
        for pat in pattern:
            for p in source_dir.glob(pat):
                if p.is_file() and p not in seen:
                    seen.add(p)
                    matches.append(p)
        matches.sort()

        results: list[dict] = []
        for path in matches:
            title = _title_from_filename(path.stem)
            try:
                result = self.add_document(
                    path,
                    category=category,
                    title=title,
                    split=split,
                    quality=quality,
                    rebuild_index=False,  # defer — rebuild once below
                )
                results.append({"file": path.name, "status": "ok", "result": result})
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the batch
                results.append(
                    {"file": path.name, "status": "error", "error": str(exc)}
                )

        # A single rebuild reflects every successfully-added file.
        self.rebuild_index()
        return results

    # -------------------------------------------------------- read document

    def read_document(
        self,
        relative_path: str,
        *,
        max_bytes: int = 100_000,
        offset: int = 0,
    ) -> ReadResult:
        """Read a document or section file from inside the shelf's ``docs/``.

        Lets an agent fetch exact content over MCP even when the shelf isn't a
        public GitHub repo (the raw-URL trick only works for public repos).

        Args:
            relative_path: Path relative to the shelf root, as returned by
                :meth:`search` / :func:`scan_shelf` (e.g.
                ``"docs/routers/mikrotik/003-firewall.md"``).
            max_bytes: Cap the returned slice so a huge datasheet can't blow up
                the caller's context window. ``truncated`` flags when hit.
            offset: Byte offset to start from, for paging through a big file.

        Raises:
            ValueError: ``offset``/``max_bytes`` negative, or the path resolves
                outside the shelf's ``docs/`` directory (traversal / symlink
                escape).
            FileNotFoundError: No such file under ``docs/``.
        """
        if offset < 0 or max_bytes < 0:
            raise ValueError("offset and max_bytes must be non-negative")

        docs_root = (self.root / "docs").resolve()
        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(docs_root):
            raise ValueError(
                f"Path escapes the shelf docs/ directory: {relative_path!r}"
            )
        if not target.is_file():
            raise FileNotFoundError(f"Document not found under docs/: {relative_path!r}")

        data = target.read_bytes()
        size = len(data)
        chunk = data[offset : offset + max_bytes] if max_bytes else data[offset:]
        return ReadResult(
            relative_path=target.relative_to(self.root).as_posix(),
            content=chunk.decode("utf-8", errors="replace"),
            size_bytes=size,
            truncated=offset + len(chunk) < size,
        )

    # ------------------------------------------------------ remove document

    def remove_document(
        self,
        *,
        category: str,
        document: str,
        dry_run: bool = False,
    ) -> RemoveResult:
        """Remove a document — and everything the shelf created for it.

        Deletes the document file, its split-section directory (if any),
        and its ``.meta.json`` entry, then rebuilds INDEX.md. With
        ``dry_run=True`` nothing is touched; the result lists what would go.

        Args:
            category: Category the document lives in (same form as used
                at ``add_document`` time — it is slugified identically).
            document: Filename (``foo.md``), slug (``foo``), or the
                human title used at add time (it is slugified to find
                the file).
            dry_run: Report without deleting.

        Raises:
            FileNotFoundError: The category or document doesn't exist.
        """
        category_slug = slugify(category, max_len=80) or "uncategorized"
        category_dir = self.root / "docs" / category_slug
        if not category_dir.is_dir():
            raise FileNotFoundError(
                f"Category not found: {category_slug!r} (under {self.root / 'docs'})"
            )

        doc_path = self._resolve_document(category_dir, document)
        if doc_path is None:
            raise FileNotFoundError(
                f"Document not found in {category_slug!r}: {document!r} "
                "(tried the literal filename and its slugified form)"
            )

        split_dir = category_dir / doc_path.stem
        was_split = split_dir.is_dir()
        removed: list[Path] = [doc_path] + ([split_dir] if was_split else [])

        if not dry_run:
            doc_path.unlink()
            if was_split:
                import shutil

                shutil.rmtree(split_dir)
            self._prune_category_meta(category_dir, doc_path.name)
            self.rebuild_index()

        return RemoveResult(removed_paths=removed, was_split=was_split, dry_run=dry_run)

    def _resolve_document(self, category_dir: Path, document: str) -> Path | None:
        """Find a document file by filename, slug, or (slugified) title.

        Matches against the real directory entries and returns the actual
        on-disk path. That keeps a case-insensitive filesystem (macOS /
        Windows) from resolving ``"Doomed.md"`` to a non-canonical path that
        no longer matches the ``doomed.md`` key in ``.meta.json``. Because only
        real files directly inside ``category_dir`` are eligible, a crafted
        ``"../../other.md"`` can never resolve to anything.
        """
        candidates = [document if document.endswith(".md") else f"{document}.md"]
        slug = slugify(document, max_len=80)
        if slug:
            candidates.append(f"{slug}.md")

        existing = {p.name: p for p in category_dir.glob("*.md") if p.is_file()}
        for name in candidates:  # exact (case-sensitive) match wins
            if name in existing:
                return existing[name]
        lower = {n.lower(): p for n, p in existing.items()}
        for name in candidates:  # then case-insensitive
            hit = lower.get(name.lower())
            if hit is not None:
                return hit
        return None

    def _prune_category_meta(self, category_dir: Path, filename: str) -> None:
        meta_path = category_dir / ".meta.json"
        if not meta_path.is_file():
            return
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if filename not in data:
            return
        del data[filename]
        if data:
            meta_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        else:
            meta_path.unlink()

    def _update_category_meta(
        self,
        category_dir: Path,
        filename: str,
        title: str,
        description: str,
    ) -> None:
        meta_path = category_dir / ".meta.json"
        data: dict = {}
        if meta_path.is_file():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        data[filename] = {"title": title, "description": description}
        meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ------------------------------------------------------- index helpers

    def scan(self) -> list[DocumentEntry]:
        """List every document currently on the shelf."""
        return scan_shelf(self.root)

    def _index_text(self, entries: list[DocumentEntry]) -> str:
        """Render the INDEX.md text from ``entries`` — no side effects."""
        cfg = self.config
        return build_index(
            cfg.name,
            entries,
            remote=cfg.remote,
            branch=cfg.branch,
            preamble=cfg.preamble,
            category_order=cfg.category_order,
            index_style=cfg.index_style,
            subindex_threshold=cfg.subindex_threshold_sections,
            provider=cfg.provider,
            url_template=cfg.url_template,
        )

    def rebuild_index(self) -> Path:
        """(Re)generate ``INDEX.md`` — and a ``SUBINDEX.md`` per split
        document — from the on-disk state. Returns the INDEX path."""
        cfg = self.config
        entries = self.scan()
        write_subindexes(
            self.root,
            entries,
            remote=cfg.remote,
            branch=cfg.branch,
            provider=cfg.provider,
            url_template=cfg.url_template,
        )
        index_path = self.root / "INDEX.md"
        index_path.write_text(self._index_text(entries), encoding="utf-8")
        return index_path

    def lint_shelf(self) -> dict[str, list[SectionWarning]]:
        """Scan every split document for suspicious section headings.

        Re-splits each split document's parent ``.md`` (the same input the
        original split saw) and runs :func:`lint_sections`, so the result
        matches what :meth:`add_document` reported. Returns a mapping of
        document relative path → warnings, omitting documents with none.
        """
        result: dict[str, list[SectionWarning]] = {}
        for entry in self.scan():
            if not entry.section_paths:
                continue
            try:
                text = (self.root / entry.relative_path).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            warnings = lint_sections(split_by_h2(text))
            if warnings:
                result[entry.relative_path] = warnings
        return result

    # ------------------------------------------------------------- doctor

    def doctor(self, *, fix: bool = False) -> list[DoctorFinding]:
        """Check the shelf for drift and (optionally) apply the safe fixes.

        Detects: stale ``.meta.json`` entries, orphaned split directories,
        split sections out of sync with their parent document, a stale
        ``INDEX.md``, duplicate titles within a category, and empty
        categories. With ``fix=True`` the *safe* subset is applied — prune
        stale meta entries, delete orphaned split dirs, and rebuild the index
        — and those findings are marked ``fixed``. Everything else is
        report-only. Findings are returned sorted for stable diffing.
        """
        import shutil

        findings: list[DoctorFinding] = []
        docs_root = self.root / "docs"
        if not docs_root.is_dir():
            return findings

        def rel(p: Path) -> str:
            return p.relative_to(self.root).as_posix()

        structural_fix = False
        for category_dir in sorted(p for p in docs_root.iterdir() if p.is_dir()):
            md_files = sorted(category_dir.glob("*.md"))
            stems = {p.stem for p in md_files}

            if not md_files:
                findings.append(DoctorFinding(
                    "empty-category", "info", rel(category_dir),
                    "category directory contains no documents",
                    "remove the empty directory"))

            # stale-meta-entry: a .meta.json key with no matching file.
            meta_path = category_dir / ".meta.json"
            if meta_path.is_file():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = None
                    findings.append(DoctorFinding(
                        "corrupt-meta", "error", rel(meta_path),
                        "`.meta.json` is not valid JSON",
                        "fix or delete the file, then rebuild_index"))
                if isinstance(data, dict):
                    stale = sorted(k for k in data if not (category_dir / k).is_file())
                    for k in stale:
                        f = DoctorFinding(
                            "stale-meta-entry", "warning", rel(meta_path),
                            f"entry '{k}' has no matching document file",
                            "prune the entry")
                        findings.append(f)
                    if fix and stale:
                        for k in stale:
                            del data[k]
                        if data:
                            meta_path.write_text(
                                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
                        else:
                            meta_path.unlink()
                        for f in findings:
                            if f.rule == "stale-meta-entry" and f.path == rel(meta_path):
                                f.fixed = True
                        structural_fix = True

            # orphaned-split-dir: a subdir with no parent <stem>.md.
            for sub in sorted(p for p in category_dir.iterdir() if p.is_dir()):
                if sub.stem not in stems:
                    f = DoctorFinding(
                        "orphaned-split-dir", "warning", rel(sub),
                        "split directory has no parent document",
                        "delete the directory")
                    if fix:
                        shutil.rmtree(sub)
                        f.fixed = True
                        structural_fix = True
                    findings.append(f)

            # split-out-of-sync: on-disk sections differ from a fresh split.
            for md in md_files:
                split_dir = category_dir / md.stem
                if not split_dir.is_dir():
                    continue
                try:
                    text = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                expected = _expected_split_names(split_by_h2(text))
                actual = sorted(
                    p.name for p in split_dir.glob("*.md")
                    if p.name != SUBINDEX_FILENAME
                )
                if expected != actual:
                    findings.append(DoctorFinding(
                        "split-out-of-sync", "warning", rel(md),
                        "section files differ from a fresh split of the parent",
                        "re-add the document to regenerate its sections"))

        # duplicate-title within a category (from the resolved entries).
        by_cat_title: dict[tuple[str, str], list[str]] = {}
        for e in self.scan():
            by_cat_title.setdefault((e.category, e.title.strip().lower()), []).append(
                e.relative_path)
        for (cat, _title), paths in by_cat_title.items():
            if len(paths) > 1:
                for p in sorted(paths)[1:]:
                    findings.append(DoctorFinding(
                        "duplicate-title", "warning", p,
                        f"title duplicates another document in '{cat}'",
                        "give one of the documents a distinct title"))

        # stale-index: INDEX.md content differs from a fresh render.
        index_path = self.root / "INDEX.md"
        current = index_path.read_text(encoding="utf-8") if index_path.is_file() else None
        if current != self._index_text(self.scan()):
            f = DoctorFinding(
                "stale-index", "warning", "INDEX.md",
                "INDEX.md is out of date with the shelf contents",
                "run rebuild_index")
            if fix:
                f.fixed = True
            findings.append(f)

        if fix and (structural_fix or any(
                x.rule == "stale-index" for x in findings)):
            self.rebuild_index()

        findings.sort(key=lambda x: (x.path, x.rule))
        return findings

    # ------------------------------------------------------------- search

    def search(
        self,
        query: str,
        max_results: int = 10,
        *,
        mode: Literal["all", "any"] = "all",
    ) -> list[dict]:
        """Plain-text grep over all Markdown files in the shelf.

        Query tokens are space-split and matched case-insensitively. With
        ``mode="all"`` (default) a file must contain **every** token to count
        as a hit; ``mode="any"`` relaxes that to at-least-one token.

        Returns a list of hit dicts ordered by score (descending). Each hit
        has ``relative_path``, ``score`` (occurrence count, with heading matches
        weighted higher), ``snippet`` (a word-boundary-trimmed excerpt around
        the first match), and ``size``.

        For a split document the whole-file parent is skipped in favour of its
        section files — they are the targeted units an agent should fetch.
        """
        if not query.strip():
            return []
        needles = [n.lower() for n in query.split() if n]
        if not needles:
            return []

        docs_root = self.root / "docs"
        hits: list[dict] = []
        if not docs_root.is_dir():
            return hits

        for md_file in docs_root.rglob("*.md"):
            if md_file.name == SUBINDEX_FILENAME:
                # Navigation pages would only echo the titles back as noise.
                continue
            # Skip a split document's whole-file parent — its content is fully
            # covered by the section files, which are the better fetch targets.
            split_dir = md_file.parent / md_file.stem
            if split_dir.is_dir() and any(split_dir.glob("*.md")):
                continue
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lower = text.lower()
            if mode == "all" and not all(n in lower for n in needles):
                continue
            base = sum(lower.count(n) for n in needles)
            if base == 0:
                continue
            # Boost matches that land on a heading line (title / ## chapter).
            heading_hits = sum(
                line.count(n)
                for line in lower.splitlines()
                if line.lstrip().startswith("#")
                for n in needles
            )
            score = base + _HEADING_BOOST * heading_hits
            first_pos = min((lower.find(n) for n in needles if n in lower), default=0)
            hits.append(
                {
                    "relative_path": md_file.relative_to(self.root).as_posix(),
                    "score": score,
                    "snippet": _make_snippet(text, first_pos),
                    "size": md_file.stat().st_size,
                }
            )
        hits.sort(key=lambda h: (-h["score"], h["relative_path"]))
        return hits[:max_results]
