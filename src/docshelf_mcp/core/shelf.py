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
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from docshelf_mcp.core.converter import Quality, pdf_to_markdown
from docshelf_mcp.core.indexer import (
    DEFAULT_PREAMBLE,
    DocumentEntry,
    build_index,
    scan_shelf,
)
from docshelf_mcp.core.slugify import slugify
from docshelf_mcp.core.splitter import (
    DEFAULT_SPLIT_THRESHOLD_BYTES,
    clean_markdown,
    should_split,
    split_by_h2,
    write_split_files,
)

__all__ = ["Shelf", "ShelfConfig", "AddResult"]


SHELF_METADATA_FILENAME = ".docshelf.json"


@dataclass
class ShelfConfig:
    """Persistent shelf metadata, stored as ``.docshelf.json`` at the root."""

    name: str = "Document Shelf"
    remote: str = ""
    branch: str = "main"
    preamble: str = DEFAULT_PREAMBLE
    category_order: list[str] = field(default_factory=list)
    split_threshold_bytes: int = DEFAULT_SPLIT_THRESHOLD_BYTES

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
        split_dir = category_dir / doc_stem
        if split and should_split(cleaned, self.config.split_threshold_bytes):
            sections = split_by_h2(cleaned)
            if len(sections) >= 2:
                section_paths = write_split_files(sections, split_dir)
                was_split = True
        elif split_dir.is_dir():
            # Document is no longer large enough — wipe the stale split.
            import shutil

            shutil.rmtree(split_dir)

        # Record title/description in .meta.json for the indexer.
        self._update_category_meta(category_dir, doc_path.name, title, description)

        # Auto-rebuild INDEX.md so the on-disk state and the index stay in sync.
        # Callers that need batch performance can short-circuit by going one
        # layer down (write files manually, then call rebuild_index once).
        self.rebuild_index()

        return AddResult(
            document_path=doc_path,
            section_paths=section_paths,
            was_split=was_split,
            converted_from_pdf=converted_from_pdf,
        )

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

    def rebuild_index(self) -> Path:
        """(Re)generate ``INDEX.md`` from the on-disk state. Returns its path."""
        cfg = self.config
        entries = self.scan()
        text = build_index(
            cfg.name,
            entries,
            remote=cfg.remote,
            branch=cfg.branch,
            preamble=cfg.preamble,
            category_order=cfg.category_order,
        )
        index_path = self.root / "INDEX.md"
        index_path.write_text(text, encoding="utf-8")
        return index_path

    # ------------------------------------------------------------- search

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Plain-text grep over all Markdown files in the shelf.

        Returns a list of hit dicts ordered by score (descending). Each hit
        has ``relative_path``, ``score`` (number of distinct matches),
        ``snippet`` (first 200 chars around the first match), and ``size``.
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
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lower = text.lower()
            score = sum(lower.count(n) for n in needles)
            if score == 0:
                continue
            first_pos = min((lower.find(n) for n in needles if n in lower), default=0)
            snippet_start = max(first_pos - 80, 0)
            snippet = text[snippet_start : snippet_start + 200].replace("\n", " ")
            hits.append(
                {
                    "relative_path": str(md_file.relative_to(self.root).as_posix()),
                    "score": score,
                    "snippet": snippet,
                    "size": md_file.stat().st_size,
                }
            )
        hits.sort(key=lambda h: (-h["score"], h["relative_path"]))
        return hits[:max_results]
