"""Unit tests for WebView.close() behavior.

These tests must not require the native `_core` extension module.
"""

from __future__ import annotations

import threading


class PanicException(BaseException):
    """Stand-in for PyO3's ``PanicException``, which is a ``BaseException``."""


def test_close_prefers_async_core_when_present():
    from auroraview.core.webview import WebView

    calls = []

    class DummyCore:
        def __init__(self, name: str):
            self._name = name

        def close(self):
            calls.append(self._name)

    # Bypass __init__ so we don't need the native module.
    webview = WebView.__new__(WebView)
    webview._core = DummyCore("core")
    webview._async_core = DummyCore("async")
    webview._track_core_thread(webview._core)
    webview._track_core_thread(webview._async_core)
    webview._async_core_lock = threading.Lock()
    webview._show_thread = None
    webview._close_requested = False
    webview._window_id = None

    # Ensure singleton cleanup doesn't affect other tests.
    old_registry = WebView._singleton_registry
    WebView._singleton_registry = {}
    try:
        webview.close()
    finally:
        WebView._singleton_registry = old_registry

    assert "async" in calls


def _make_webview_with_cores(core, async_core=None):
    """Build a WebView instance without running __init__ (no native module)."""
    from auroraview.core.webview import WebView

    webview = WebView.__new__(WebView)
    webview._core = core
    webview._async_core = async_core
    webview._async_core_lock = threading.Lock()
    webview._show_thread = None
    webview._close_requested = False
    webview._window_id = None
    webview._core_threads = {}
    webview._track_core_thread(core)
    webview._track_core_thread(async_core)
    return webview


def _close_in_thread(webview, ready, started):
    """Run webview.close() on a thread that does not own the core."""
    started.set()
    ready.wait(5)
    webview.close()


def test_close_from_foreign_thread_uses_close_channel():
    """A close raised off the owner thread must go through the proxy."""
    calls = []

    class DummyCore:
        def __init__(self, name, fail_direct=False):
            self._name = name
            self._fail_direct = fail_direct

        def close(self):
            if self._fail_direct and threading.get_ident() != owner_ident:
                # Mirror PyO3: PanicException is a BaseException, so an
                # `except Exception` handler cannot swallow it.
                raise PanicException("AuroraView is unsendable, but sent to another thread")
            calls.append(("direct", self._name))

        def get_proxy(self):
            return _Proxy(self._name)

    class _Proxy:
        def __init__(self, name):
            self._name = name

        def close(self):
            calls.append(("channel", self._name))

    owner_ident = threading.get_ident()
    core = DummyCore("core", fail_direct=True)
    webview = _make_webview_with_cores(core)

    from auroraview.core.webview import WebView

    old_registry = WebView._singleton_registry
    WebView._singleton_registry = {}
    try:
        webview.close()
    finally:
        WebView._singleton_registry = old_registry

    assert ("direct", "core") in calls
    assert not any(kind == "channel" for kind, _ in calls)


def test_close_from_foreign_thread_routes_through_channel():
    """Same close, but raised on a thread that does not own the core."""
    calls = []
    owner_ident = threading.get_ident()

    class DummyCore:
        def __init__(self, name):
            self._name = name

        def close(self):
            if threading.get_ident() != owner_ident:
                raise PanicException("AuroraView is unsendable, but sent to another thread")
            calls.append(("direct", self._name))

        def get_proxy(self):
            return _Proxy(self._name)

    class _Proxy:
        def __init__(self, name):
            self._name = name

        def close(self):
            calls.append(("channel", self._name))

    core = DummyCore("core")
    webview = _make_webview_with_cores(core)

    from auroraview.core.webview import WebView

    old_registry = WebView._singleton_registry
    WebView._singleton_registry = {}
    errors = []

    def run():
        try:
            webview.close()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(10)
    WebView._singleton_registry = old_registry

    assert not errors, f"close() leaked an exception from a foreign thread: {errors}"
    assert ("channel", "core") in calls
    assert not any(kind == "direct" and name == "core" for kind, name in calls)


def test_close_reraises_control_flow_exceptions():
    """Only PyO3 panics may be swallowed; KeyboardInterrupt must propagate."""
    from auroraview.core.webview import WebView

    class DummyCore:
        def close(self):
            raise KeyboardInterrupt

        def get_proxy(self):
            raise AssertionError("proxy must not be used for control-flow exceptions")

    core = DummyCore()
    webview = _make_webview_with_cores(core)

    old_registry = WebView._singleton_registry
    WebView._singleton_registry = {}
    try:
        raised = None
        try:
            webview.close()
        except BaseException as e:  # noqa: BLE001
            raised = e
    finally:
        WebView._singleton_registry = old_registry

    assert isinstance(raised, KeyboardInterrupt), f"KeyboardInterrupt was swallowed: {raised!r}"


def test_close_swallows_pyo3_panic_and_routes_through_channel():
    """A PyO3 panic on the owner thread still falls back to the close channel."""
    from auroraview.core.webview import WebView

    calls = []

    class DummyCore:
        def close(self):
            raise PanicException("AuroraView is unsendable")

        def get_proxy(self):
            return _Proxy()

    class _Proxy:
        def close(self):
            calls.append("channel")

    webview = _make_webview_with_cores(DummyCore())

    old_registry = WebView._singleton_registry
    WebView._singleton_registry = {}
    try:
        webview.close()
    finally:
        WebView._singleton_registry = old_registry

    assert calls == ["channel"]
