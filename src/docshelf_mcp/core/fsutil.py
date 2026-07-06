"""Small filesystem helpers.

:func:`atomic_write_text` is the shelf's single write primitive for the files
whose corruption would be silently destructive — ``INDEX.md``,
``SUBINDEX.md``, ``.docshelf.json``, ``.meta.json``. A plain ``write_text``
truncates the target before writing, so an interrupted write (kill, full disk,
power loss) leaves a half-written or empty file — and the loaders swallow that
as "defaults" / "no overrides", quietly dropping config and titles. Writing to
a sibling temp file and ``os.replace``-ing it onto the target makes the swap
atomic: readers see either the old file or the new one, never a torn one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["atomic_write_text"]


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    Writes to a temp file in the same directory (so the final ``os.replace`` is
    a same-filesystem rename, which is atomic on POSIX and Windows), flushes and
    ``fsync``s it, then renames it onto ``path``. On any failure the target is
    left untouched and the temp file is cleaned up. Newline handling matches
    :meth:`pathlib.Path.write_text` (translation to ``os.linesep`` on Windows),
    so on-disk output is byte-identical to the previous non-atomic writes.
    """
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        # mkstemp creates the file 0600; reproduce the normal umask-based mode
        # so a file that may be committed / served isn't left owner-only.
        umask = os.umask(0)
        os.umask(umask)
        try:
            os.chmod(tmp_name, 0o666 & ~umask)
        except OSError:
            pass  # best-effort; not fatal (e.g. exotic filesystems)

        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Never leave the target torn; drop the temp file and re-raise.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
