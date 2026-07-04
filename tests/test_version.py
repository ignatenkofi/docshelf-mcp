"""Guard against version drift between the package and its metadata.

pyproject.toml declares ``dynamic = ["version"]`` and hatch reads the value
from ``docshelf_mcp.__init__``. If someone reintroduces a hardcoded version
in pyproject.toml (or forgets to reinstall after a bump), this test catches
the mismatch.
"""

import importlib.metadata

import docshelf_mcp


def test_version_matches_installed_metadata():
    assert docshelf_mcp.__version__ == importlib.metadata.version("docshelf-mcp")


def test_version_looks_like_semver():
    parts = docshelf_mcp.__version__.split(".")
    assert len(parts) >= 3
    assert all(p.isdigit() for p in parts[:2])
