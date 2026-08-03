"""End-to-end tests over the real stdio transport, with a real MCP client.

Everything else in this suite talks to ``docshelf_mcp.tools`` directly or pokes
``mcp.list_tools()`` in-process — see ``test_server.py``'s own docstring: *"We
don't spin up the stdio transport (that needs a client)."* That leaves the
transport itself untested, and "the module imports" has been standing in for
"the server answers" ever since. The CI smoke job says it outright: its whole
check is ``python -c "from docshelf_mcp.server import mcp"``.

The gap matters most exactly when it is most expensive to discover: a change to
how the server is *declared* — a different framework, a new SDK major (#83) —
can leave every in-process assertion green while no client can talk to the
thing. These tests spawn the console entry point as a subprocess and drive it
through a genuine handshake, so "works" means a client got an answer.

Kept deliberately few and slow-but-shallow: one handshake, one tool call whose
result must reflect real shelf state, one resource read. Depth belongs in the
fast in-process tests; this file exists to prove the wire.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="the MCP client SDK is needed to drive the transport")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from docshelf_mcp.core.shelf import Shelf  # noqa: E402

# A cold interpreter plus the handshake is seconds, not milliseconds, and CI
# runs this on Windows and macOS too. The cap is generous on purpose: a flaky
# timeout here would teach people to rerun the job, which is worse than the
# gap this file closes.
#
# It is passed to every ClientSession below, and that is the point of it being
# a named constant: a server that starts but never answers is exactly the
# failure these tests exist to catch, and without the cap the job would hang on
# it until GitHub's own six-hour limit — a red run nobody can read instead of a
# failed assertion. A constant nothing reads would have been the same defect
# this file is about, one level up.
# Seconds as a float: mcp 2.x types ``read_timeout_seconds`` that way, where
# 1.x took a ``timedelta``. Handing 2.x a timedelta does not get rejected at
# the call site — it raises TypeError deep inside anyio (#83).
WIRE_TIMEOUT = 60.0


def _flatten_exception(exc: BaseException) -> list[BaseException]:
    """Every exception in the tree: the group, its members, and their causes."""
    seen: list[BaseException] = []

    def walk(node: BaseException) -> None:
        if any(node is known for known in seen):
            return
        seen.append(node)
        for member in getattr(node, "exceptions", None) or ():
            walk(member)
        if node.__cause__ is not None:
            walk(node.__cause__)

    walk(exc)
    return seen


def _looks_like_timeout(exc: BaseException) -> bool:
    """True for "the wait ran out", whatever type the SDK wraps it in.

    Matched on the message rather than a concrete class on purpose: the class
    lives in the SDK (`mcp.shared.exceptions.MCPError` today) and pinning it
    here would make this file break on a rename that changes nothing about the
    behaviour under test.
    """
    return isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()


def _server(shelf_root: Path) -> StdioServerParameters:
    """Spawn the server the way a desktop client does — the module entry point.

    ``sys.executable -m docshelf_mcp`` rather than the ``docshelf-mcp`` script:
    the console script may not be on PATH in a bare checkout, and the module
    path exercises the same ``main()``.
    """
    env = dict(os.environ)
    env["DOCSHELF_ROOT"] = str(shelf_root)
    return StdioServerParameters(
        command=sys.executable, args=["-m", "docshelf_mcp"], env=env
    )


def _seeded_shelf(tmp_path: Path) -> Path:
    root = tmp_path / "shelf"
    shelf = Shelf(root)
    shelf.init(name="Protocol shelf", default_categories=["notes"])
    source = tmp_path / "quarterly.md"
    source.write_text(
        "# Quarterly\n\nThe reconciliation closed on the 14th.\n", encoding="utf-8"
    )
    shelf.add_document(source, category="notes", title="Quarterly", description="Q report")
    return root


@pytest.mark.asyncio
async def test_client_completes_the_handshake_and_sees_every_tool(tmp_path: Path):
    """The wire test: a client connects, initializes, and gets the tool list.

    Asserted as a superset rather than an exact set — this file is about the
    transport, and pinning the roster here would make it a second place to
    update whenever a tool is added. ``test_server.py`` owns the exact list.
    """
    async with stdio_client(_server(_seeded_shelf(tmp_path))) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=WIRE_TIMEOUT) as session:
            init = await session.initialize()
            assert init.server_info.name

            names = {tool.name for tool in (await session.list_tools()).tools}
            assert {
                "docshelf_list_documents",
                "docshelf_search",
                "docshelf_read_document",
                "docshelf_add_document",
            } <= names, sorted(names)


@pytest.mark.asyncio
async def test_tool_call_over_the_wire_returns_real_shelf_state(tmp_path: Path):
    """A call must come back with this shelf's content, not merely succeed.

    An empty-but-well-formed response would satisfy "the transport works" while
    telling us nothing, so the assertion is on the document that was seeded.
    """
    root = _seeded_shelf(tmp_path)
    async with stdio_client(_server(root)) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=WIRE_TIMEOUT) as session:
            await session.initialize()
            result = await session.call_tool(
                "docshelf_list_documents", {"params": {"shelf_path": str(root)}}
            )
            assert not result.is_error, result.content
            payload = "".join(
                block.text for block in result.content if getattr(block, "text", None)
            )
            assert "Quarterly" in payload, payload


@pytest.mark.asyncio
async def test_resources_are_served_over_the_wire(tmp_path: Path):
    """Resources are registered at startup, so only a live server can prove it.

    ``register_shelf_resources`` runs inside ``main()`` — the in-process tests
    call it by hand, which is precisely the arrangement that would keep passing
    if startup stopped calling it.
    """
    root = _seeded_shelf(tmp_path)
    async with stdio_client(_server(root)) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=WIRE_TIMEOUT) as session:
            await session.initialize()
            resources = (await session.list_resources()).resources
            uris = [str(resource.uri) for resource in resources]
            assert uris, "server registered no resources for a seeded shelf"

            index = next((u for u in uris if u.endswith("INDEX.md")), uris[0])
            contents = (await session.read_resource(index)).contents
            body = "".join(getattr(item, "text", "") for item in contents)
            assert body.strip(), f"{index} came back empty"


@pytest.mark.asyncio
async def test_a_server_that_never_answers_fails_instead_of_hanging():
    """The cap above must be load-bearing, not a comment.

    A server that starts and then says nothing is the failure this file exists
    to catch — and it is also the one that punishes an unarmed timeout hardest:
    the job would sit until GitHub's six-hour limit and come back as a red run
    with no assertion in it. Driving a deliberately silent process proves the
    ``read_timeout_seconds`` wiring is real; a shorter cap keeps the test itself
    quick, since what is under test is that the cap exists at all.

    The assertion has to name a *timeout*, not merely "something was raised".
    In its weaker form this test stayed green right through the mcp 2.x port
    while the cap was dead: 2.x types ``read_timeout_seconds`` as float
    seconds, a leftover ``timedelta`` blows up as ``TypeError`` deep inside
    anyio, and any exception satisfied ``pytest.raises(BaseException)``.

    Elapsed time does not separate the two either — measured on this very
    port, the dead cap came back in 2.02s and the live one in 4.03s, both far
    from instant, because spawning the child and tearing the task group down
    dominates. What does separate them is the leaf exception: ``MCPError:
    Request 'initialize' timed out`` against ``TypeError``. Exceptions arrive
    wrapped in nested ``ExceptionGroup``s, so the tree is flattened first.
    """
    silent = StdioServerParameters(
        command=sys.executable, args=["-c", "import time; time.sleep(3600)"]
    )
    started = time.monotonic()
    with pytest.raises(BaseException) as caught:
        async with stdio_client(silent) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=2.0) as session:
                await session.initialize()
    elapsed = time.monotonic() - started

    raised = _flatten_exception(caught.value)
    assert not any(isinstance(exc, AssertionError) for exc in raised)
    assert any(_looks_like_timeout(exc) for exc in raised), (
        "nothing in the failure says the request timed out, so the cap was not "
        "what stopped it: "
        + "; ".join(f"{type(exc).__name__}: {exc}" for exc in raised)
    )
    assert elapsed < 60, f"waited {elapsed:.0f}s — the cap did not fire at all"
