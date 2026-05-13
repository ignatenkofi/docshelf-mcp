"""Server-level configuration (env vars).

Right now the only knob is ``DOCSHELF_ROOT`` — the default shelf directory
used when an MCP tool is called without an explicit ``shelf_path``. Override
it via env to point at your shelf:

.. code-block:: shell

    export DOCSHELF_ROOT="$HOME/Documents/my-docs"

If unset, tools fall back to ``$PWD``, which is the right behaviour when the
server is started from a shelf directory.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["default_shelf_root"]


def default_shelf_root() -> Path:
    """Resolve the default shelf root for tool calls without an explicit path."""
    env = os.environ.get("DOCSHELF_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()
