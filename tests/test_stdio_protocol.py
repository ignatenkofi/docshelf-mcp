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
from datetime import timedelta
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
WIRE_TIMEOUT = timedelta(seconds=60)


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
            assert init.serverInfo.name

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
            assert not result.isError, result.content
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
    """
    silent = StdioServerParameters(
        command=sys.executable, args=["-c", "import time; time.sleep(3600)"]
    )
    with pytest.raises(BaseException) as caught:
        async with stdio_client(silent) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=2)
            ) as session:
                await session.initialize()
    assert not isinstance(caught.value, AssertionError)
