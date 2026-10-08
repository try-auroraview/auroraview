# -*- coding: utf-8 -*-
"""Integration tests for AuroraView DCC-MCP discovery.

These cover the discovery half of the end-to-end acceptance criteria:

1. Starting a server writes a FileRegistry row for ``dcc_type == "auroraview"``.
2. The row carries a live PID, a sentinel lock, and a heartbeat timestamp.
3. A skill package can be discovered and loaded (semantic layer), not just
   discovered at the transport layer.

They require the optional ``dcc-mcp-core`` dependency and are skipped when it
is absent. No display, Qt binding, or compiled Rust core is needed -- the
adapter is driven by a fake WebView, while the server and registry are real.
"""

from __future__ import annotations

import json
import os
import sys
import time

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


class _FakeCore:
    """Minimal stand-in for the Rust core's JavaScript round-trip API."""

    def __init__(self, result='"hello"', status="complete"):
        self.result = result
        self.status = status
        self.scripts = []

    def eval_js_future(self, script, timeout_ms):
        self.scripts.append((script, timeout_ms))
        return "cb-1"

    def get_js_result(self, callback_id):
        return {"status": self.status, "result": self.result}


class _FakeWebView:
    """Minimal stand-in for an AuroraView WebView.

    Defined locally rather than imported from the unit tests: the suite is
    collected with the installed wheel in CI, where ``tests`` is not an
    importable package.
    """

    def __init__(self, core=None, title="AuroraView", url="http://localhost:3000/"):
        self._core = core if core is not None else _FakeCore()
        self.title = title
        self.current_url = url
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


SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "skills", "auroraview-webview"
)


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_services(registry_dir: str):
    """Load and return the FileRegistry rows from ``services.json``."""
    path = os.path.join(registry_dir, "services.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else data.get("services", [])


def _heartbeat_seconds(row):
    """Normalise a registry heartbeat value to a comparable float.

    ``services.json`` serialises ``SystemTime`` as a dict with
    ``secs_since_epoch`` / ``nanos_since_epoch`` rather than a scalar, so
    comparisons need explicit flattening.
    """
    value = row.get("last_heartbeat")
    if isinstance(value, dict):
        return float(value.get("secs_since_epoch", 0)) + (
            float(value.get("nanos_since_epoch", 0)) / 1e9
        )
    return float(value)


def _wait_for_row(registry_dir: str, dcc_type: str, timeout: float = 10.0):
    """Poll the registry until a row for ``dcc_type`` appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for row in _read_services(registry_dir):
            if row.get("dcc_type") == dcc_type:
                return row
        time.sleep(0.2)
    return None


@pytest.fixture()
def registry_dir(tmp_path):
    """Isolated registry directory so tests never touch the live registry."""
    path = str(tmp_path / "registry")
    os.makedirs(path, exist_ok=True)
    old = os.environ.get("DCC_MCP_REGISTRY_DIR")
    os.environ["DCC_MCP_REGISTRY_DIR"] = path
    try:
        yield path
    finally:
        if old is None:
            os.environ.pop("DCC_MCP_REGISTRY_DIR", None)
        else:
            os.environ["DCC_MCP_REGISTRY_DIR"] = old


@pytest.fixture()
def server(registry_dir):
    """A started DCC-MCP server backed by a fake AuroraView WebView."""
    adapter = AuroraViewAdapter(_FakeWebView(), host_dcc="maya", cdp_port=9222)
    srv = start_server(
        adapter,
        gateway_port=_free_port(),
        registry_dir=registry_dir,
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


def test_server_registers_auroraview_row_in_file_registry(server, registry_dir):
    """Q4 step 1-2: the instance becomes visible in the FileRegistry."""
    row = _wait_for_row(registry_dir, "auroraview")
    assert row is not None, "auroraview row was never written to services.json"
    assert row["dcc_type"] == "auroraview"
    assert row["adapter_dcc"] == "auroraview"
    assert row["pid"] == os.getpid()


def test_registry_row_has_sentinel_and_heartbeat(server, registry_dir):
    """Q4 step 4: liveness is crash-resilient via a sentinel lock + heartbeat."""
    row = _wait_for_row(registry_dir, "auroraview")
    assert row is not None
    # Sentinel lock: an OS-held file that dies with the process.
    assert row.get("sentinel_path"), "no sentinel_path -> no crash-resilient liveness"
    # Heartbeat: proves the row is maintained, not written once and abandoned.
    assert row.get("last_heartbeat"), "no last_heartbeat timestamp"


def test_heartbeat_advances_while_server_runs(server, registry_dir):
    """The heartbeat timestamp moves forward while the instance is alive."""
    first = _wait_for_row(registry_dir, "auroraview")
    assert first is not None
    # The registry heartbeat period is ~5s, so wait past one full interval.
    time.sleep(7.0)
    second = _wait_for_row(registry_dir, "auroraview")
    assert second is not None
    assert _heartbeat_seconds(second) > _heartbeat_seconds(first), (
        "heartbeat did not advance; a frozen heartbeat must not pass"
    )


def test_gateway_port_zero_is_rejected():
    """gateway_port=0 silently disables registration, so it must be refused."""
    adapter = AuroraViewAdapter(_FakeWebView())
    with pytest.raises(ValueError, match="gateway_port=0"):
        start_server(adapter, gateway_port=0, registry_dir=None)


def test_skill_package_is_discoverable(server):
    """Q4 step 3: the semantic layer must load, not just the transport row."""
    names = [s.get("name") for s in server.list_skills()]
    assert "auroraview-webview" in names, f"skill not discovered, saw: {names}"


def test_skill_can_be_loaded_and_exposes_tools(server):
    """Discovery without a loadable skill does not satisfy acceptance."""
    server.load_skill("auroraview-webview")
    assert server.is_skill_loaded("auroraview-webview")


def test_stop_releases_the_registered_adapter(server):
    from auroraview.dcc_mcp import adapter_registry

    owned = server._adapter
    assert owned in adapter_registry.adapters()
    server.stop()
    assert owned not in adapter_registry.adapters()
    assert server._adapter is None


def test_failed_start_does_not_leave_a_registered_adapter(monkeypatch, registry_dir):
    from dcc_mcp_core.server_base import DccServerBase

    from auroraview.dcc_mcp import adapter_registry

    adapter = AuroraViewAdapter(_FakeWebView())
    server = start_server(adapter, gateway_port=_free_port(), registry_dir=registry_dir)

    def fail_start(self, **kwargs):
        raise RuntimeError("startup failed")

    monkeypatch.setattr(DccServerBase, "start", fail_start)
    with pytest.raises(RuntimeError, match="startup failed"):
        server.start()
    assert adapter not in adapter_registry.adapters()
    assert server._adapter is None
    server.stop()


def test_partial_start_failure_closes_the_live_transport(monkeypatch, registry_dir):
    from dcc_mcp_core.server_base import DccServerBase

    from auroraview.dcc_mcp import adapter_registry

    adapter = AuroraViewAdapter(_FakeWebView())
    server = start_server(adapter, gateway_port=_free_port(), registry_dir=registry_dir)
    base_start = DccServerBase.start
    started = {}

    def fail_after_start(self, **kwargs):
        started["handle"] = base_start(self, **kwargs)
        started["row"] = _wait_for_row(registry_dir, "auroraview")
        raise RuntimeError("post-start failure")

    monkeypatch.setattr(DccServerBase, "start", fail_after_start)
    try:
        with pytest.raises(RuntimeError, match="post-start failure"):
            server.start()
        assert started["handle"] is not None
        assert started["row"] is not None
        assert not server.is_running
        assert not any(row.get("dcc_type") == "auroraview" for row in _read_services(registry_dir))
        assert adapter not in adapter_registry.adapters()
        assert server._adapter is None
    finally:
        server.stop()


def test_failed_start_cleanup_retains_the_adapter_until_stop_retry(monkeypatch, registry_dir):
    import gc
    import weakref

    from dcc_mcp_core.server_base import DccServerBase

    from auroraview.dcc_mcp import adapter_registry
    from auroraview.dcc_mcp.server import logger as server_logger

    adapter = AuroraViewAdapter(_FakeWebView())
    adapter_ref = weakref.ref(adapter)
    server = start_server(adapter, gateway_port=_free_port(), registry_dir=registry_dir)
    base_start = DccServerBase.start
    runtime = server._runtime
    shutdown_handle = runtime.shutdown_server_handle
    attempts = []
    cleanup_errors = []

    def record_cleanup_error(message):
        # A captured logging traceback would itself keep the adapter alive.
        cleanup_errors.append((message, str(sys.exc_info()[1])))

    def fail_after_start(self, **kwargs):
        base_start(self, **kwargs)
        raise RuntimeError("post-start failure")

    def fail_cleanup_once():
        attempts.append(True)
        if len(attempts) == 1:
            # Core already ran the quit hook, which releases the adapter,
            # before it reaches transport cleanup. The wrapper must restore it.
            raise RuntimeError("transport cleanup failed")
        return shutdown_handle()

    monkeypatch.setattr(DccServerBase, "start", fail_after_start)
    monkeypatch.setattr(runtime, "shutdown_server_handle", fail_cleanup_once)
    monkeypatch.setattr(server_logger, "exception", record_cleanup_error)
    try:
        with pytest.raises(RuntimeError, match="post-start failure"):
            server.start()
        assert len(cleanup_errors) == 1
        assert "adapter retained" in cleanup_errors[0][0]
        assert cleanup_errors[0][1] == "transport cleanup failed"
        assert server.is_running
        assert server._adapter is adapter
        assert adapter in adapter_registry.adapters()
        del adapter
        gc.collect()
        assert adapter_ref() is not None
        server.stop()
        assert len(attempts) == 2
        assert not server.is_running
        assert server._adapter is None
        assert adapter_ref() not in adapter_registry.adapters()
        gc.collect()
        assert adapter_ref() is None
    finally:
        server.stop()
