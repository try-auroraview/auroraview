from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Tuple

from auroraview import WebView

# Unit tests for WebView.bind_call and bind_api parameter handling.
# These tests exercise the pure-Python wrapper logic without requiring the
# compiled AuroraView core by injecting a dummy core into a WebView instance.


class DummyCore:
    """Minimal stub for the Rust core used by WebView in tests.

    It only implements the methods used by bind_call/bind_api and emit().
    """

    def __init__(self) -> None:
        self.handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self.emitted: List[Tuple[str, Dict[str, Any]]] = []
        self.registered_api_methods: Dict[str, List[str]] = {}

    def on(self, name: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        self.handlers[name] = callback

    def emit(self, name: str, payload: Dict[str, Any]) -> None:
        self.emitted.append((name, payload))

    def register_api_methods(self, namespace: str, methods: List[str]) -> None:
        """Register API methods (stub for Rust core method)."""
        self.registered_api_methods[namespace] = methods


def make_dummy_webview() -> WebView:
    """Create a WebView instance backed by DummyCore for unit testing."""

    webview = WebView.__new__(WebView)
    webview._core = DummyCore()  # type: ignore[attr-defined]
    webview._track_core_thread(webview._core)
    webview._async_core = None  # type: ignore[attr-defined]
    webview._async_core_lock = threading.RLock()  # type: ignore[attr-defined]
    webview._event_handlers = {}  # type: ignore[attr-defined]
    webview._show_thread = None  # type: ignore[attr-defined]
    return webview


def test_bind_call_no_params_invokes_zero_arg_callable() -> None:
    """auroraview.call("method") without params calls Python func() with no args.

    This specifically protects methods that do not expect a payload argument,
    such as bound API methods like API.get_scene_hierarchy(self).
    """

    webview = make_dummy_webview()
    calls: List[str] = []

    def zero_arg() -> str:
        calls.append("called")
        return "OK"

    webview.bind_call("api.zero_arg", zero_arg)
    handler = webview._core.handlers["api.zero_arg"]  # type: ignore[attr-defined]

    # Simulate JS payload without a "params" key
    handler({"id": "call-1"})

    assert calls == ["called"]
    assert webview._core.emitted == [  # type: ignore[attr-defined]
        ("__auroraview_call_result", {"id": "call-1", "ok": True, "result": "OK"})
    ]


def test_bind_call_explicit_null_param_is_forwarded() -> None:
    """If JS sends params: null, the callable receives None as a single argument."""

    webview = make_dummy_webview()

    def one_arg(value: Any) -> Dict[str, Any]:
        return {"value": value}

    webview.bind_call("api.one_arg", one_arg)
    handler = webview._core.handlers["api.one_arg"]  # type: ignore[attr-defined]

    # Simulate explicit null payload from JS
    handler({"id": "call-2", "params": None})

    assert webview._core.emitted == [  # type: ignore[attr-defined]
        ("__auroraview_call_result", {"id": "call-2", "ok": True, "result": {"value": None}})
    ]


class _API:
    def __init__(self) -> None:
        self.calls: List[Tuple[str]] = []

    def no_args(self) -> str:
        self.calls.append(("no_args",))
        return "ok"


def test_bind_api_zero_arg_method_supported() -> None:
    """bind_api exposes zero-argument methods that can be called without params."""

    webview = make_dummy_webview()
    api = _API()

    webview.bind_api(api, namespace="api")

    # The method name should be `api.no_args` according to bind_api logic
    handler = webview._core.handlers["api.no_args"]  # type: ignore[attr-defined]

    handler({"id": "call-3"})

    # API method should have been called exactly once without extra args
    assert api.calls == [("no_args",)]

    assert webview._core.emitted == [  # type: ignore[attr-defined]
        ("__auroraview_call_result", {"id": "call-3", "ok": True, "result": "ok"})
    ]
