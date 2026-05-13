"""Tests for the indexer (scan + build_index + raw_github_url)."""

from pathlib import Path

from docshelf_mcp.core.indexer import (
    DocumentEntry,
    build_index,
    raw_github_url,
    scan_shelf,
)


def test_raw_github_url_https():
    url = raw_github_url(
        "https://github.com/me/myrepo", "main", "docs/foo.md"
    )
    assert url == "https://raw.githubusercontent.com/me/myrepo/main/docs/foo.md"


def test_raw_github_url_strips_dot_git():
    url = raw_github_url(
        "git@github.com:me/myrepo.git", "main", "docs/foo.md"
    )
    assert url == "https://raw.githubusercontent.com/me/myrepo/main/docs/foo.md"


def test_raw_github_url_returns_empty_for_non_github():
    assert raw_github_url("https://gitlab.com/me/repo", "main", "x.md") == ""
    assert raw_github_url("", "main", "x.md") == ""


def test_build_index_empty_shelf():
    out = build_index("Test Shelf", [], remote="https://github.com/me/r")
    assert "# Test Shelf" in out
    assert "No documents yet" in out


def test_build_index_categorisation():
    entries = [
        DocumentEntry(
            category="routers",
            title="Mikrotik Router",
            description="Manual",
            relative_path="docs/routers/mikrotik.md",
            size_bytes=2048,
        ),
        DocumentEntry(
            category="switches",
            title="Cudy Switch",
            description="",
            relative_path="docs/switches/cudy.md",
            size_bytes=1024,
        ),
    ]
    out = build_index(
        "My Shelf",
        entries,
        remote="https://github.com/me/myrepo",
        category_order=["routers"],
    )
    assert "## Routers" in out
    assert "## Switches" in out
    # routers should come first because of category_order.
    assert out.index("Routers") < out.index("Switches")
    # raw URL is in there
    assert "raw.githubusercontent.com/me/myrepo/main/docs/routers/mikrotik.md" in out


def test_build_index_renders_split_sections():
    entries = [
        DocumentEntry(
            category="routers",
            title="RouterOS",
            description="",
            relative_path="docs/routers/routeros.md",
            size_bytes=4_000_000,
            section_paths=[
                "docs/routers/routeros/001-overview.md",
                "docs/routers/routeros/002-firewall.md",
            ],
        ),
    ]
    out = build_index("S", entries, remote="https://github.com/me/r")
    assert "### RouterOS" in out
    # Pretty-printed labels are rendered as link text (not the slug).
    assert "[Overview]" in out
    assert "[Firewall]" in out
    assert "sections: 2" in out
    # The raw URL of course preserves the original filename — that's fine.
    assert "001-overview.md" in out


def test_scan_shelf_picks_up_meta_overrides(tmp_path: Path):
    docs = tmp_path / "docs" / "routers"
    docs.mkdir(parents=True)
    (docs / "mikrotik.md").write_text("# hi\n", encoding="utf-8")
    (docs / ".meta.json").write_text(
        '{"mikrotik.md": {"title": "Mikrotik Router", "description": "The big one."}}',
        encoding="utf-8",
    )

    entries = scan_shelf(tmp_path)
    assert len(entries) == 1
    assert entries[0].title == "Mikrotik Router"
    assert entries[0].description == "The big one."
    assert entries[0].category == "routers"


def test_scan_shelf_detects_split_sections(tmp_path: Path):
    docs = tmp_path / "docs" / "routers"
    docs.mkdir(parents=True)
    (docs / "routeros.md").write_text("# big doc", encoding="utf-8")
    split_dir = docs / "routeros"
    split_dir.mkdir()
    (split_dir / "001-overview.md").write_text("## overview", encoding="utf-8")
    (split_dir / "002-firewall.md").write_text("## firewall", encoding="utf-8")

    entries = scan_shelf(tmp_path)
    assert len(entries) == 1
    assert len(entries[0].section_paths) == 2
    assert all("docs/routers/routeros/" in p for p in entries[0].section_paths)


def test_scan_shelf_empty_returns_empty(tmp_path: Path):
    assert scan_shelf(tmp_path) == []
