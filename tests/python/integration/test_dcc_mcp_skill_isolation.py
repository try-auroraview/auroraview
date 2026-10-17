# -*- coding: utf-8 -*-
"""Skill isolation: an agent must not confuse AuroraView tools with DCC tools.

The point of the integration is that an agent asking "operate Maya through
dcc-mcp" finds Maya tools, and asking about the AuroraView panel finds
AuroraView tools -- without the two sets bleeding into each other.

Asserted here:
1. The ``auroraview-webview`` skill declares its four WebView tools plus route discovery
   and no scene/selection/rigging tools.
2. The skill is tagged to the ``auroraview`` DCC, not to a DCC host.
3. A WebView-specific query resolves to the AuroraView skill.
4. AuroraView tools are never advertised as Maya scene operations: no tool
   name collides with the Maya scene vocabulary.

Requires the optional ``dcc-mcp-core`` dependency; skipped when absent.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "python"))

from auroraview.dcc_mcp import DCC_MCP_CORE_IMPORT_ERROR  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        DCC_MCP_CORE_IMPORT_ERROR is not None,
        reason="dcc-mcp-core not installed (pip install auroraview[dcc-mcp])",
    ),
]

if DCC_MCP_CORE_IMPORT_ERROR is None:
    from auroraview.dcc_mcp.adapter import AuroraViewAdapter
    from auroraview.dcc_mcp.server import start_server

SKILL_NAME = "auroraview-webview"
SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "skills", "auroraview-webview"
)

#: The tool set AuroraView intentionally exposes.
EXPECTED_TOOLS = {"eval_js", "screenshot", "load_url", "load_html", "list_views"}

#: Vocabulary belonging to DCC scene work. None of these may be advertised as
#: an AuroraView tool, otherwise an agent looking for Maya scene operations
#: would be routed to a WebView panel.
DCC_SCENE_VOCABULARY = {
    "create_polygon",
    "create_joint",
    "delete_object",
    "export_fbx",
    "list_objects",
    "get_selection",
    "set_selection",
    "create_sphere",
    "parent_object",
}


@pytest.fixture()
def server(tmp_path):
    registry = str(tmp_path / "registry")
    os.makedirs(registry, exist_ok=True)
    old = os.environ.get("DCC_MCP_REGISTRY_DIR")
    os.environ["DCC_MCP_REGISTRY_DIR"] = registry
    view = types.SimpleNamespace(title="AuroraView", current_url="http://localhost:3000/")
    srv = start_server(
        AuroraViewAdapter(view, host_dcc="maya"),
        gateway_port=_free_port(),
        registry_dir=registry,
        skill_paths=[SKILLS_DIR],
        enable_telemetry=False,
    )
    srv.start()
    try:
        yield srv
    finally:
        try:
            srv.stop()
        except Exception:  # noqa: BLE001 - teardown must not mask failures
            pass
        if old is None:
            os.environ.pop("DCC_MCP_REGISTRY_DIR", None)
        else:
            os.environ["DCC_MCP_REGISTRY_DIR"] = old


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_skill_declares_exactly_the_webview_tools(server):
    """The AuroraView skill exposes four WebView tools plus route discovery and nothing else."""
    server.load_skill(SKILL_NAME)
    info = server.get_skill_info(SKILL_NAME)
    tools = {t.get("name") if isinstance(t, dict) else t for t in info.get("tools", [])}
    assert tools == EXPECTED_TOOLS, "unexpected AuroraView tool set: %r" % sorted(tools)


def test_skill_is_scoped_to_auroraview(server):
    """The skill is tagged to auroraview, not to the embedding DCC."""
    server.load_skill(SKILL_NAME)
    info = server.get_skill_info(SKILL_NAME)
    assert info.get("dcc") == "auroraview", info.get("dcc")


def test_skill_does_not_advertise_dcc_scene_operations(server):
    """AuroraView tools must never masquerade as DCC scene operations."""
    server.load_skill(SKILL_NAME)
    info = server.get_skill_info(SKILL_NAME)
    tools = {t.get("name") if isinstance(t, dict) else t for t in info.get("tools", [])}
    collisions = tools & DCC_SCENE_VOCABULARY
    assert not collisions, "AuroraView advertises DCC scene tools: %r" % sorted(collisions)


def test_webview_query_finds_the_auroraview_skill(server):
    """A WebView-specific query resolves to the AuroraView skill."""
    results = server.search_skills("eval_js")
    names = [r.get("name") if isinstance(r, dict) else r for r in results]
    assert SKILL_NAME in names, "eval_js query missed the auroraview skill: %r" % names
