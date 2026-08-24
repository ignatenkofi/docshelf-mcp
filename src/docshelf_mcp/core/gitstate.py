"""Read-only questions about the git state under a shelf (#97).

docshelf never stages, commits or pushes — that stays the caller's job, and
this module does not change it: every call here is a query. But one diagnosis
cannot be made from the filesystem alone.

``doctor`` compares ``INDEX.md`` on disk against a render of the *working
tree*, and :meth:`Shelf.scan` walks the filesystem, so anything present counts
as shelf content. On a shelf whose split directories were never committed —
the caller staged the document path alone, which is exactly what memshelf's
``shelve`` used to do — the two sides of that comparison are structurally
different trees. No rebuild can make them equal: the warning returns the moment
the index is rendered from the committed tree again, and running the
prescribed ``rebuild_index`` locally publishes INDEX links to files no other
checkout has.

Telling that case from an index that has simply fallen behind takes exactly one
question — *does git track anything in here* — and there is no filesystem
answer to it. A ``.gitignore`` rule is not the answer either: an ignored
directory and an unstaged one are equally untracked, and shelves in the wild
have both.

Detection is deliberately narrow, mirroring memshelf's ``local-split-dir``:

* only a directory sitting next to a document of the same stem (one without a
  parent is ``orphaned-split-dir``, a different finding);
* only on a git shelf — "exists only in this working copy" means nothing
  without a repository, and a plain shelf renders and reads its own splits
  consistently;
* only when git tracks nothing inside it. A shelf that *committed* its sections
  is coherent — every checkout has them — and is left alone.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: docshelf's per-split navigation file — it lives inside the split directory.
SUBINDEX_FILENAME = "SUBINDEX.md"


def is_git_repo(root: Path) -> bool:
    """True when ``root`` carries a git directory (or worktree pointer file)."""
    return (root / ".git").exists()


def _tracks_anything(root: Path, rel: str) -> bool:
    """Does git track at least one path under ``rel``?

    An *ignored* file is untracked, which is the point: shelves that hit this
    ignore ``docs/*/*/`` outright.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", rel],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:  # not a repository after all — treat as untracked
        return False
    return any(line.strip() for line in proc.stdout.splitlines())


def uncommitted_split_dirs(shelf_root: str | Path) -> list[str]:
    """Split directories git does not track, relative to the root, sorted.

    Empty for a plain (non-git) shelf and for one that committed its sections —
    both are coherent, and neither should be reported.
    """
    root = Path(shelf_root).expanduser().resolve()
    if not is_git_repo(root):
        return []
    docs_root = root / "docs"
    if not docs_root.is_dir():
        return []

    out: list[str] = []
    for document in sorted(docs_root.glob("*/*.md")):
        if document.name == SUBINDEX_FILENAME:
            continue
        split_dir = document.with_suffix("")
        if not split_dir.is_dir():
            continue
        rel = split_dir.relative_to(root).as_posix()
        if not _tracks_anything(root, rel):
            out.append(rel)
    return sorted(out)
