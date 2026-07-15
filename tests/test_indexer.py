"""Tests for the indexer (scan + build_index + subindex + raw_github_url)."""

from pathlib import Path

from docshelf_mcp.core.indexer import (
    SUBINDEX_FILENAME,
    DocumentEntry,
    _is_roman_numeral,
    _pretty_section,
    build_index,
    build_subindex,
    raw_github_url,
    scan_shelf,
    shelf_url,
    write_subindexes,
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
    assert raw_github_url("https://bitbucket.org/me/repo", "main", "x.md") == ""
    assert raw_github_url("", "main", "x.md") == ""


def test_raw_github_url_github_enterprise_server():
    # A self-hosted GHES host serves raw content from the same host under
    # /<owner>/<repo>/raw/<branch>/<path> — not raw.githubusercontent.com.
    assert (
        raw_github_url("https://github.acme.com/team/docs", "main", "docs/x.md")
        == "https://github.acme.com/team/docs/raw/main/docs/x.md"
    )
    # SSH form, and path segments are percent-encoded like the public path.
    assert (
        raw_github_url("git@github.corp.io:team/docs.git", "dev", "a b.md")
        == "https://github.corp.io/team/docs/raw/dev/a%20b.md"
    )
    # github.com itself is unaffected (public raw host).
    assert (
        raw_github_url("https://github.com/me/repo", "main", "x.md")
        == "https://raw.githubusercontent.com/me/repo/main/x.md"
    )


def test_raw_github_url_dotted_repo_name():
    # The headline bug: repo name with a dot used to truncate at the dot.
    assert (
        raw_github_url("https://github.com/me/my.repo", "main", "docs/foo.md")
        == "https://raw.githubusercontent.com/me/my.repo/main/docs/foo.md"
    )


def test_raw_github_url_strips_dot_git_https():
    # Proves the previously-dead .git-stripping branch is now live for https.
    assert (
        raw_github_url("https://github.com/me/myrepo.git", "main", "docs/foo.md")
        == "https://raw.githubusercontent.com/me/myrepo/main/docs/foo.md"
    )


def test_raw_github_url_dotted_repo_with_dot_git():
    assert (
        raw_github_url("https://github.com/me/my.repo.git", "main", "x.md")
        == "https://raw.githubusercontent.com/me/my.repo/main/x.md"
    )


def test_raw_github_url_ssh_without_git():
    assert (
        raw_github_url("git@github.com:me/myrepo", "main", "x.md")
        == "https://raw.githubusercontent.com/me/myrepo/main/x.md"
    )


def test_raw_github_url_trailing_slash_and_path_following():
    assert (
        raw_github_url("https://github.com/me/myrepo/", "main", "x.md")
        == "https://raw.githubusercontent.com/me/myrepo/main/x.md"
    )
    # A URL with more path after the repo: repo is still just 'my.repo'.
    assert (
        raw_github_url("https://github.com/me/my.repo/tree/main", "main", "x.md")
        == "https://raw.githubusercontent.com/me/my.repo/main/x.md"
    )


def test_raw_github_url_trailing_prose_dot():
    assert (
        raw_github_url("See https://github.com/me/myrepo.", "main", "x.md")
        == "https://raw.githubusercontent.com/me/myrepo/main/x.md"
    )


def test_raw_github_url_missing_repo_returns_empty():
    assert raw_github_url("https://github.com/me", "main", "x.md") == ""
    assert raw_github_url("https://github.com/", "main", "x.md") == ""


def test_raw_github_url_ignores_query_and_fragment():
    # A pasted browser URL must not fold ?query / #fragment into the repo name.
    assert (
        raw_github_url("https://github.com/me/myrepo?tab=readme", "main", "x.md")
        == "https://raw.githubusercontent.com/me/myrepo/main/x.md"
    )
    assert (
        raw_github_url("https://github.com/me/my.repo#readme", "main", "x.md")
        == "https://raw.githubusercontent.com/me/my.repo/main/x.md"
    )


def test_raw_github_url_encodes_path_segments():
    assert (
        raw_github_url("https://github.com/me/r", "main", "docs/my file.md")
        == "https://raw.githubusercontent.com/me/r/main/docs/my%20file.md"
    )
    assert (
        raw_github_url("https://github.com/me/r", "main", "docs/notes#1.md")
        == "https://raw.githubusercontent.com/me/r/main/docs/notes%231.md"
    )
    # Slashes are preserved as path separators.
    assert (
        raw_github_url("https://github.com/me/r", "main", "docs/sub dir/x.md")
        == "https://raw.githubusercontent.com/me/r/main/docs/sub%20dir/x.md"
    )


def test_raw_github_url_plain_path_unchanged():
    # Slug-safe paths (what docshelf itself writes) must be byte-identical.
    assert (
        raw_github_url("https://github.com/me/r", "main", "docs/routers/mikrotik.md")
        == "https://raw.githubusercontent.com/me/r/main/docs/routers/mikrotik.md"
    )


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


def test_shelf_url_github_default():
    assert (
        shelf_url("github", "https://github.com/me/r", "main", "", "docs/a.md")
        == "https://raw.githubusercontent.com/me/r/main/docs/a.md"
    )


def test_shelf_url_gitlab():
    assert (
        shelf_url("gitlab", "https://gitlab.com/grp/proj", "main", "", "docs/a.md")
        == "https://gitlab.com/grp/proj/-/raw/main/docs/a.md"
    )


def test_shelf_url_gitea_self_hosted_host():
    assert (
        shelf_url("gitea", "https://git.example.com/u/r", "trunk", "", "docs/a.md")
        == "https://git.example.com/u/r/raw/branch/trunk/docs/a.md"
    )


def test_shelf_url_custom_template():
    tmpl = "https://cdn.example.com/{repo}/{branch}/{path}"
    assert (
        shelf_url("custom", "https://github.com/me/shelf", "v2", tmpl, "docs/a b.md")
        == "https://cdn.example.com/shelf/v2/docs/a%20b.md"
    )
    # A template that needs no remote still works (path/branch only).
    assert (
        shelf_url("custom", "", "main", "https://s3/{path}", "docs/a.md")
        == "https://s3/docs/a.md"
    )


def test_shelf_url_none_returns_relative():
    assert shelf_url("none", "", "main", "", "docs/a b.md") == "docs/a%20b.md"


def test_shelf_url_empty_when_unbuildable():
    # gitlab/gitea need a parseable remote.
    assert shelf_url("gitlab", "", "main", "", "docs/a.md") == ""
    # custom with no template.
    assert shelf_url("custom", "https://github.com/me/r", "main", "", "docs/a.md") == ""


def test_build_index_none_provider_relative_links():
    entries = [
        DocumentEntry("routers", "R", "", "docs/routers/r.md", 2048),
    ]
    out = build_index("S", entries, provider="none")
    # Relative link to the doc, no absolute host.
    assert "(docs/routers/r.md)" in out
    assert "raw.githubusercontent.com" not in out


def test_build_subindex_gitlab_provider():
    entry = DocumentEntry(
        "routers", "R", "", "docs/routers/r.md", 4000,
        section_paths=["docs/routers/r/001-a.md", "docs/routers/r/002-b.md"],
    )
    out = build_subindex(entry, remote="https://gitlab.com/g/p", provider="gitlab")
    assert "gitlab.com/g/p/-/raw/main/docs/routers/r/001-a.md" in out


def _split_entry(n_sections: int) -> DocumentEntry:
    return DocumentEntry(
        category="routers",
        title="RouterOS",
        description="Full manual.",
        relative_path="docs/routers/routeros.md",
        size_bytes=4_000_000,
        section_paths=[
            f"docs/routers/routeros/{i:03d}-part-{i}.md" for i in range(1, n_sections + 1)
        ],
    )


def test_build_subindex_with_remote():
    out = build_subindex(
        _split_entry(3),
        remote="https://github.com/me/r",
        section_sizes={"docs/routers/routeros/001-part-1.md": 5120},
    )
    assert "# RouterOS — sections" in out
    assert "Full manual." in out
    assert "raw.githubusercontent.com/me/r/main/docs/routers/routeros/001-part-1.md" in out
    assert "(~5 KB)" in out


def test_build_subindex_without_remote_uses_relative_links():
    out = build_subindex(_split_entry(2))
    assert "raw.githubusercontent.com" not in out
    assert "(001-part-1.md)" in out  # link relative to the split dir
    assert "(../routeros.md)" in out  # full doc one level up


def test_build_index_auto_style_switches_to_subindex_link():
    # Below the threshold: sections are inlined, no SUBINDEX link.
    small = build_index("S", [_split_entry(3)], remote="https://github.com/me/r")
    assert "SUBINDEX" not in small
    assert "sections: 3" in small

    # Above the threshold: single SUBINDEX link, no per-section list.
    big = build_index("S", [_split_entry(12)], remote="https://github.com/me/r")
    assert "raw.githubusercontent.com/me/r/main/docs/routers/routeros/SUBINDEX.md" in big
    assert "Sections (12)" in big
    assert "001-part-1.md" not in big


def test_build_index_explicit_styles_override_threshold():
    inline = build_index("S", [_split_entry(12)], index_style="inline")
    assert "SUBINDEX" not in inline
    forced = build_index("S", [_split_entry(3)], index_style="subindex")
    assert "SUBINDEX.md" in forced


def test_write_subindexes_and_scan_exclusion(tmp_path: Path):
    docs = tmp_path / "docs" / "routers"
    split_dir = docs / "routeros"
    split_dir.mkdir(parents=True)
    (docs / "routeros.md").write_text("# big doc", encoding="utf-8")
    (split_dir / "001-overview.md").write_text("## overview", encoding="utf-8")
    (split_dir / "002-firewall.md").write_text("## firewall", encoding="utf-8")

    entries = scan_shelf(tmp_path)
    written = write_subindexes(tmp_path, entries, remote="https://github.com/me/r")
    assert written == [split_dir / SUBINDEX_FILENAME]
    text = written[0].read_text(encoding="utf-8")
    assert "[Overview]" in text and "[Firewall]" in text

    # Re-scanning after the write must NOT count SUBINDEX.md as a section.
    entries2 = scan_shelf(tmp_path)
    assert len(entries2[0].section_paths) == 2
    # And regeneration is idempotent.
    write_subindexes(tmp_path, entries2, remote="https://github.com/me/r")
    assert written[0].read_text(encoding="utf-8") == text


def test_is_roman_numeral():
    assert _is_roman_numeral("ii") is True
    assert _is_roman_numeral("iii") is True
    assert _is_roman_numeral("iv") is True
    assert _is_roman_numeral("vi") is True
    assert _is_roman_numeral("vii") is True
    assert _is_roman_numeral("viii") is True
    assert _is_roman_numeral("ix") is True
    assert _is_roman_numeral("xiv") is True
    assert _is_roman_numeral("xix") is True
    assert _is_roman_numeral("xxiv") is True
    # Not Roman numerals
    assert _is_roman_numeral("") is False
    assert _is_roman_numeral("power") is False
    assert _is_roman_numeral("section1") is False
    assert _is_roman_numeral("ii-intro") is False
    assert _is_roman_numeral("a") is False


def test_pretty_section_normal_words():
    assert _pretty_section("001-power-supplies.md") == "Power supplies"
    assert _pretty_section("002-firewall.md") == "Firewall"
    assert _pretty_section("overview.md") == "Overview"


def test_pretty_section_roman_numerals():
    assert _pretty_section("ii.md") == "II"
    assert _pretty_section("iii.md") == "III"
    assert _pretty_section("004-vii.md") == "VII"
    assert _pretty_section("xiv.md") == "XIV"
    assert _pretty_section("007-ix.md") == "IX"
    assert _pretty_section("xix.md") == "XIX"
