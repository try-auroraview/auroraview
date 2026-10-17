# -*- coding: utf-8 -*-
"""End-to-end tool invocation: the "drive" half of the acceptance criteria.

Discovery (a registry row exists) and semantics (a skill loads and declares
its tools) are both necessary but not sufficient. An agent that calls
``eval_js`` must get a real value back. This suite proves that by invoking
tools through the same dispatch path a skill script uses.

It is the regression guard for a failure mode that is otherwise invisible:
``load_skill`` and ``get_skill_info`` both stay green while every actual call
returns ``{"ok": false, "error": "No live AuroraView adapter found..."}``.

Requires the optional ``dcc-mcp-core`` dependency; skipped when absent.
"""

from __future__ import annotations

import os
import sys

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
    from auroraview.dcc_mcp import adapter_registry
    from auroraview.dcc_mcp.adapter import AuroraViewAdapter
    from auroraview.dcc_mcp.server import start_server

SKILL_NAME = "auroraview-webview"
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "skills", "auroraview-webview", "scripts"
)
SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "skills", "auroraview-webview"
)


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _FakeCore:
    """Minimal stand-in for the Rust core's JavaScript round-trip API."""

    def __init__(self, result='"hello"'):
        self.result = result
        self.scripts = []

    def eval_js_future(self, script, timeout_ms):
        self.scripts.append((script, timeout_ms))
        return "cb-1"

    def get_js_result(self, callback_id):
        return {"status": "complete", "result": self.result}


class _FakeWebView:
    """Minimal stand-in for an AuroraView WebView."""

    def __init__(self, core=None):
        self._core = core if core is not None else _FakeCore()
        self.title = "AuroraView"
        self.current_url = "http://localhost:3000/"
        self.loaded_urls = []
        self.loaded_html = []
        self.processed = 0

    def eval_js(self, script):
        self._core.scripts.append((script, None))

    def load_url(self, url):
        self.loaded_urls.append(url)

    def load_html(self, html):
        self.loaded_html.append(html)

    def process_events(self):
        self.processed += 1
        return True


@pytest.fixture()
def started(tmp_path):
    """A started server with its adapter reachable from skill dispatch."""
    registry = str(tmp_path / "registry")
    os.makedirs(registry, exist_ok=True)
    old = os.environ.get("DCC_MCP_REGISTRY_DIR")
    os.environ["DCC_MCP_REGISTRY_DIR"] = registry
    old_override = os.environ.pop("AURORAVIEW_ADAPTER", None)

    adapter_registry.clear()
    adapter = AuroraViewAdapter(_FakeWebView(), host_dcc="maya")
    server = start_server(
        adapter,
        gateway_port=_free_port(),
        registry_dir=registry,
        skill_paths=[SKILLS_DIR],
        enable_telemetry=False,
    )
    server.start()
    try:
        yield adapter, server
    finally:
        try:
            server.stop()
        except Exception:  # noqa: BLE001 - teardown must not mask failures
            pass
        adapter_registry.clear()
        if old is None:
            os.environ.pop("DCC_MCP_REGISTRY_DIR", None)
        else:
            os.environ["DCC_MCP_REGISTRY_DIR"] = old
        if old_override is not None:
            os.environ["AURORAVIEW_ADAPTER"] = old_override


def test_start_server_makes_the_adapter_discoverable(started):
    """start_server registers the adapter, which is what dispatch reads."""
    adapter, _server = started
    assert adapter_registry.current() is adapter


def test_skill_dispatch_reaches_the_adapter(started):
    """A skill script resolves the live adapter and executes a tool.

    Runs the dispatcher that every script in the skill package calls, so this
    covers the path an agent actually triggers rather than only the adapter
    method. Skill scripts execute in-process under the host, which is the
    documented execution model.
    """
    adapter, _server = started
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import _dispatch

        result = _dispatch.run_tool("eval_js", {"script": "document.title"})
    finally:
        if SCRIPTS_DIR in sys.path:
            sys.path.remove(SCRIPTS_DIR)

    assert result["ok"] is True, result
    assert result["result"] == '"hello"'
    assert adapter._view._core.scripts, "eval_js was never dispatched to the WebView"


def test_skill_dispatch_reports_errors_instead_of_raising(started):
    """A failed tool call yields a structured error, not a traceback."""
    _adapter, _server = started
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import _dispatch

        result = _dispatch.run_tool("load_url", {})
    finally:
        if SCRIPTS_DIR in sys.path:
            sys.path.remove(SCRIPTS_DIR)

    assert result["ok"] is False
    assert "required" in result["error"]


def test_tool_invocation_returns_a_value(started):
    """adapter.execute returns the evaluated value, not an error."""
    adapter, _server = started
    result = adapter.execute("eval_js", {"script": "document.title"})
    assert result["ok"] is True, result
    assert result["result"] == '"hello"'


def test_tool_invocation_reaches_the_webview(started):
    """load_url and load_html actually mutate the WebView."""
    adapter, _server = started
    assert adapter.execute("load_url", {"url": "https://example.com"})["ok"] is True
    assert adapter._view.loaded_urls == ["https://example.com"]
    assert adapter.execute("load_html", {"html": "<h1>hi</h1>"})["ok"] is True
    assert adapter._view.loaded_html == ["<h1>hi</h1>"]


def test_loaded_skill_tools_are_invocable(started):
    """Every tool the skill advertises can actually be executed.

    Guards against a skill declaring tools the dispatch path cannot reach.
    """
    _adapter, server = started
    server.load_skill(SKILL_NAME)
    info = server.get_skill_info(SKILL_NAME)
    tools = {t.get("name") if isinstance(t, dict) else t for t in info.get("tools", [])}
    assert tools, "skill declared no tools"

    params = {
        "eval_js": {"script": "1+1"},
        "screenshot": {},
        "load_url": {"url": "https://example.com"},
        "load_html": {"html": "<p>x</p>"},
    }
    # The adapter owns four panel operations; route discovery belongs to the
    # skill dispatcher. Exercise each advertised tool through that real script
    # path rather than assuming every skill tool is an adapter method.
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import _dispatch

        discovered = _dispatch.run_tool("list_views", {})
        assert discovered["ok"] is True
        assert len(discovered["views"]) == 1
        route = discovered["views"][0]
        for name in sorted(tools):
            payload = dict(params.get(name, {}))
            if name != "list_views":
                payload.update(route)
            result = _dispatch.run_tool(name, payload)
            assert result["ok"] is True, "tool %r failed: %r" % (name, result)
    finally:
        if SCRIPTS_DIR in sys.path:
            sys.path.remove(SCRIPTS_DIR)


def test_registered_dispatcher_satisfies_core_protocol(started):
    """Whatever start_server registers must satisfy core's dispatch protocol.

    Direct guard against the regression this suite once missed. Core's
    HostExecutionBridge._dispatch_raw accepts only a dispatcher exposing
    `is_host_thread`, `dispatch_callable`, or the post/tick queue API. Anything
    else raises TypeError, which core converts into an error envelope -- so
    every tool call would fail while still looking like a successful call.
    """
    _adapter, server = started
    # Read core's own registration state, not an attribute we set ourselves:
    # register_inprocess_executor() writes owner._dcc_dispatcher, and that is
    # the object HostExecutionBridge._dispatch_raw actually consults.
    dispatcher = getattr(server, "_dcc_dispatcher", None)
    if dispatcher is None:
        # Unset is the supported configuration: core runs the callable inline.
        # Confirm nothing registered an executor behind our back.
        assert (
            getattr(server, "_execution_bridge", None) is None
            or getattr(getattr(server, "_execution_bridge", None), "dispatcher", None) is None
        ), "an executor was registered but _dcc_dispatcher is unset"
        return

    ok = (
        callable(getattr(dispatcher, "is_host_thread", None))
        or callable(getattr(dispatcher, "dispatch_callable", None))
        or (
            callable(getattr(dispatcher, "post", None))
            and callable(getattr(dispatcher, "tick", None))
        )
    )
    assert ok, (
        "registered dispatcher %r does not implement any protocol core accepts; "
        "tool execution would raise TypeError" % type(dispatcher).__name__
    )


def test_tool_call_through_core_executor_returns_a_value(started):
    """A tool executed through core's HostExecutionBridge must really run.

    Drives the real entry point an agent hits -- executing the skill's
    source_file through the bridge using the dispatcher start_server
    configured -- and asserts the script actually ran rather than returning
    an error envelope.
    """
    import json

    from dcc_mcp_core import HostExecutionBridge

    adapter, server = started
    server.load_skill(SKILL_NAME)

    info = server.get_skill_info(SKILL_NAME)
    tools = {t.get("name") if isinstance(t, dict) else t for t in info.get("tools", [])}
    assert "eval_js" in tools

    script = os.path.join(SCRIPTS_DIR, "eval_js.py")
    # Use the bridge the server actually registered when one exists, so the
    # call goes through the dispatcher core really consults. Falling back to a
    # locally built bridge would bypass it and hide a broken registration.
    bridge = getattr(server, "_execution_bridge", None)
    if not isinstance(bridge, HostExecutionBridge):
        bridge = HostExecutionBridge(dispatcher=getattr(server, "_dcc_dispatcher", None))
    result = bridge.execute_script(
        script,
        {"script": "document.title"},
        action_name="eval_js",
        skill_name=SKILL_NAME,
    )

    text = result if isinstance(result, str) else json.dumps(result, default=str)
    assert "No live AuroraView adapter" not in text, (
        "skill script could not resolve the adapter: %s" % text
    )
    assert "HostExecutionBridge dispatcher must expose" not in text, (
        "core rejected the dispatcher; tool execution is broken: %s" % text
    )
    assert adapter._view._core.scripts, "the tool never reached the WebView"


def test_registry_does_not_keep_adapters_alive():
    """The registry must not pin an adapter (and its WebView) in memory."""
    import gc

    adapter_registry.clear()

    class _Doomed:
        pass

    adapter_registry.register(_Doomed())
    gc.collect()
    # The only strong reference went out of scope immediately, so the
    # registry must have released it.
    assert adapter_registry.current() is None, "registry kept a dropped adapter alive"
    assert adapter_registry.adapters() == []


def test_unregister_removes_the_adapter():
    """unregister() actually removes an entry."""
    adapter_registry.clear()
    sentinel = AuroraViewAdapter(_FakeWebView())
    adapter_registry.register(sentinel)
    assert adapter_registry.current() is sentinel
    adapter_registry.unregister(sentinel)
    assert adapter_registry.current() is None
