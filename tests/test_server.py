"""Smoke tests for the MCP server module + tools wrappers.

We don't spin up the stdio transport (that needs a client) — we just verify
that the server module imports, all tools are registered, and the tool
wrappers in `docshelf_mcp.tools` are end-to-end callable.
"""

import json
from pathlib import Path

import pytest

from docshelf_mcp import tools as t
from docshelf_mcp.server import mcp

FIXTURE = Path(__file__).parent / "fixtures" / "sample.md"


@pytest.mark.asyncio
async def test_server_exposes_ten_tools():
    tool_list = await mcp.list_tools()
    names = sorted(tool.name for tool in tool_list)
    assert names == sorted(
        [
            "docshelf_add_document",
            "docshelf_add_directory",
            "docshelf_read_document",
            "docshelf_convert_pdf",
            "docshelf_doctor",
            "docshelf_init_shelf",
            "docshelf_list_documents",
            "docshelf_rebuild_index",
            "docshelf_remove_document",
            "docshelf_search",
        ]
    )


def test_init_shelf_wrapper(tmp_path: Path):
    out = t.init_shelf(
        t.InitShelfInput(
            shelf_path=str(tmp_path / "s"),
            name="Test",
            github_remote="https://github.com/me/r",
            default_categories=["alpha"],
        )
    )
    assert out["status"] == "ok"
    assert (tmp_path / "s" / ".docshelf.json").is_file()
    assert (tmp_path / "s" / "docs" / "alpha").is_dir()


def test_add_document_wrapper_then_search(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(
        t.InitShelfInput(
            shelf_path=shelf_path,
            name="T",
            github_remote="https://github.com/me/r",
            default_categories=["docs"],
        )
    )
    add_out = t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE),
            category="docs",
            title="Sample",
            description="A fixture.",
            split=False,
            shelf_path=shelf_path,
        )
    )
    assert add_out["status"] == "ok"
    assert add_out["index_path"] == "INDEX.md"

    search_out = t.search(
        t.SearchInput(query="BGP", max_results=5, shelf_path=shelf_path)
    )
    assert search_out["status"] == "ok"
    assert search_out["match_mode"] == "all"
    assert search_out["match_count"] >= 1
    hit = search_out["hits"][0]
    assert "raw.githubusercontent.com" in hit["raw_url"]

    # Over-specified query: no file has both tokens -> any-token fallback.
    fallback_out = t.search(
        t.SearchInput(query="BGP zzznosuchtoken", max_results=5, shelf_path=shelf_path)
    )
    assert fallback_out["match_mode"] == "any"
    assert fallback_out["match_count"] >= 1


def test_read_document_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(
        t.InitShelfInput(
            shelf_path=shelf_path, name="T", github_remote="https://github.com/me/r"
        )
    )
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE), category="docs", title="Sample",
            split=False, shelf_path=shelf_path,
        )
    )
    out = t.read_document(
        t.ReadDocumentInput(relative_path="docs/docs/sample.md", shelf_path=shelf_path)
    )
    assert out["status"] == "ok"
    assert "BGP" in out["content"]
    assert out["truncated"] is False
    assert "raw.githubusercontent.com" in out["raw_url"]


def test_read_document_wrapper_traversal_is_error(tmp_path: Path):
    from docshelf_mcp import server

    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    (Path(shelf_path) / "secret.txt").write_text("secret", encoding="utf-8")
    out = json.loads(
        server.read_document(
            t.ReadDocumentInput(relative_path="docs/../secret.txt", shelf_path=shelf_path)
        )
    )
    assert out["status"] == "error"
    assert out["type"] == "ValueError"


def test_add_directory_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.md").write_text("# A\n\nalpha\n", encoding="utf-8")
    (src / "b.md").write_text("# B\n\nbeta\n", encoding="utf-8")

    out = t.add_directory(
        t.AddDirectoryInput(source_dir=str(src), category="docs", shelf_path=shelf_path)
    )
    assert out["status"] == "ok"
    assert out["added_count"] == 2 and out["failed_count"] == 0
    assert {a["file"] for a in out["added"]} == {"a.md", "b.md"}


def test_add_directory_wrapper_reports_failures(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    src = tmp_path / "in"
    src.mkdir()
    (src / "ok.md").write_text("# Ok\n\ntext\n", encoding="utf-8")
    (src / "bad.pdf").write_text("not a pdf", encoding="utf-8")

    out = t.add_directory(
        t.AddDirectoryInput(source_dir=str(src), category="docs", shelf_path=shelf_path)
    )
    assert out["added_count"] == 1 and out["failed_count"] == 1
    assert out["failed"][0]["file"] == "bad.pdf"


def test_remove_document_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE),
            category="docs",
            title="Doomed",
            split=False,
            shelf_path=shelf_path,
        )
    )

    dry = t.remove_document(
        t.RemoveDocumentInput(
            category="docs", document="Doomed", dry_run=True, shelf_path=shelf_path
        )
    )
    assert dry["dry_run"] is True
    assert dry["removed_paths"] == ["docs/docs/doomed.md"]
    assert (Path(shelf_path) / "docs" / "docs" / "doomed.md").is_file()

    out = t.remove_document(
        t.RemoveDocumentInput(category="docs", document="Doomed", shelf_path=shelf_path)
    )
    assert out["status"] == "ok"
    assert not (Path(shelf_path) / "docs" / "docs" / "doomed.md").exists()
    assert "Doomed" not in (Path(shelf_path) / "INDEX.md").read_text(encoding="utf-8")


def test_list_documents_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(
        t.InitShelfInput(shelf_path=shelf_path, name="T", default_categories=["x"])
    )
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE),
            category="x",
            title="A",
            split=False,
            shelf_path=shelf_path,
        )
    )
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE),
            category="x",
            title="B",
            split=False,
            shelf_path=shelf_path,
        )
    )

    out = t.list_documents(t.ListDocumentsInput(shelf_path=shelf_path))
    assert out["status"] == "ok"
    assert out["total_documents"] == 2
    assert "x" in out["categories"]


def test_doctor_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    t.add_document(
        t.AddDocumentInput(
            source_path=str(FIXTURE), category="docs", title="Keeper",
            split=False, shelf_path=shelf_path,
        )
    )
    # Clean shelf: no findings.
    clean = t.doctor(t.DoctorInput(shelf_path=shelf_path))
    assert clean["status"] == "ok" and clean["finding_count"] == 0

    # Inject an orphan, then fix it.
    orphan = Path(shelf_path) / "docs" / "docs" / "orphan"
    orphan.mkdir()
    (orphan / "001-x.md").write_text("## x\n", encoding="utf-8")
    out = t.doctor(t.DoctorInput(fix=True, shelf_path=shelf_path))
    assert out["by_rule"].get("orphaned-split-dir", 0) >= 1
    assert out["fixed_count"] >= 1
    assert not orphan.exists()


def test_rebuild_index_wrapper(tmp_path: Path):
    shelf_path = str(tmp_path / "s")
    t.init_shelf(t.InitShelfInput(shelf_path=shelf_path, name="T"))
    out = t.rebuild_index(t.RebuildIndexInput(shelf_path=shelf_path))
    assert out["status"] == "ok"
    assert out["index_path"] == "INDEX.md"


@pytest.mark.parametrize(
    "call",
    [
        lambda p: t.search(t.SearchInput(query="x", shelf_path=p)),
        lambda p: t.rebuild_index(t.RebuildIndexInput(shelf_path=p)),
        lambda p: t.list_documents(t.ListDocumentsInput(shelf_path=p)),
        lambda p: t.remove_document(
            t.RemoveDocumentInput(category="c", document="d", shelf_path=p)
        ),
        lambda p: t.add_document(
            t.AddDocumentInput(
                source_path=str(FIXTURE), category="c", title="T", shelf_path=p
            )
        ),
    ],
)
def test_shelf_tools_reject_uninitialized_directory(tmp_path: Path, call):
    with pytest.raises(t.NotAShelfError) as excinfo:
        call(str(tmp_path))
    msg = str(excinfo.value)
    assert str(tmp_path.resolve()) in msg
    assert "init_shelf" in msg and "DOCSHELF_ROOT" in msg


def test_add_document_on_non_shelf_creates_nothing(tmp_path: Path):
    with pytest.raises(t.NotAShelfError):
        t.add_document(
            t.AddDocumentInput(
                source_path=str(FIXTURE),
                category="docs",
                title="T",
                shelf_path=str(tmp_path),
            )
        )
    # The silent-scaffold bug is fixed: nothing was written.
    assert not (tmp_path / ".docshelf.json").exists()
    assert not (tmp_path / "docs").exists()
    assert not (tmp_path / "INDEX.md").exists()


def test_nonexistent_shelf_path_is_not_created(tmp_path: Path):
    target = tmp_path / "nope"
    with pytest.raises(t.NotAShelfError):
        t.list_documents(t.ListDocumentsInput(shelf_path=str(target)))
    assert not target.exists()


def test_docshelf_root_env_pointing_at_non_shelf(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DOCSHELF_ROOT", str(tmp_path))
    with pytest.raises(t.NotAShelfError) as excinfo:
        t.search(t.SearchInput(query="x"))  # no shelf_path -> falls back to env
    assert str(tmp_path.resolve()) in str(excinfo.value)


def test_cwd_fallback_non_shelf_is_guarded(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DOCSHELF_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(t.NotAShelfError):
        t.rebuild_index(t.RebuildIndexInput())  # no shelf_path, no env -> CWD


def test_server_serializes_not_a_shelf_error(tmp_path: Path):
    from docshelf_mcp import server

    out = json.loads(server.search(t.SearchInput(query="x", shelf_path=str(tmp_path))))
    assert out["status"] == "error"
    assert out["type"] == "NotAShelfError"
    assert "init_shelf" in out["error"]


def test_init_shelf_not_guarded(tmp_path: Path):
    # init_shelf is the scaffolder — it must work on a bare directory.
    out = t.init_shelf(t.InitShelfInput(shelf_path=str(tmp_path / "fresh")))
    assert out["status"] == "ok"
    assert (tmp_path / "fresh" / ".docshelf.json").is_file()


def test_convert_pdf_not_guarded(tmp_path: Path):
    # convert_pdf uses no shelf; a non-.pdf input fails on its own validation,
    # NOT on a NotAShelfError, proving it never resolves a shelf.
    from docshelf_mcp.core.converter import ConversionError

    bad = tmp_path / "not.txt"
    bad.write_text("x")
    with pytest.raises((ConversionError, ValueError)):
        t.convert_pdf(
            t.ConvertPdfInput(pdf_path=str(bad), out_dir=str(tmp_path / "out"))
        )


def test_input_validation_rejects_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        t.AddDocumentInput(
            source_path="x",
            category="y",
            title="z",
            split=True,
            quality="fast",
            extra_unexpected_field=True,  # type: ignore[call-arg]
        )


def test_input_validation_rejects_empty_title():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        t.AddDocumentInput(source_path="x", category="y", title="")


def test_tools_to_json_is_human_readable():
    out = t.to_json({"status": "ok", "items": [1, 2, 3]})
    parsed = json.loads(out)
    assert parsed["status"] == "ok"
    assert "\n" in out  # pretty-printed (indent=2)
