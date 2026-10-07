"""Owner-thread regressions using an unsendable native-core stand-in.

These tests intentionally reject foreign get_proxy(), not only foreign close().
They exercise Python routing; they do not establish native GUI support.
"""

from __future__ import annotations

import sys
import threading
from collections import UserDict
from types import MappingProxyType, ModuleType, SimpleNamespace

import pytest

from auroraview.core import webview as webview_module
from auroraview.core.factory import WebViewFactory
from auroraview.core.mixins import lifecycle
from auroraview.utils.event_timer import EventTimer
from auroraview.utils.timer_backends import ThreadTimerBackend, TimerBackend


class PanicException(BaseException):
    """Match PyO3's unsendable access failure, outside Exception."""


class Proxy:
    def __init__(self, core):
        self.core = core

    def emit(self, name, data):
        if not isinstance(data, dict):
            raise TypeError("WebViewProxy.emit requires a dict")
        self.core.commands.append(("emit", name, data))

    def eval_js(self, script):
        self.core.commands.append(("eval_js", script))

    def load_url(self, url):
        self.core.commands.append(("load_url", url))

    def load_html(self, html):
        self.core.commands.append(("load_html", html))

    def close(self):
        self.core.commands.append(("close",))
        self.core.close_requested.set()


class Emitter:
    """Model the native EventEmitter's PyAny/.items contract, not Proxy's PyDict."""

    def __init__(self, core):
        self.core = core

    def emit(self, name, data):
        payload = dict(data.items()) if hasattr(data, "items") else {}
        self.core.commands.append(("emitter", name, payload))


class Core:
    def __init__(self, **config):
        self.owner = threading.get_ident()
        self.config = config
        self.handlers = {}
        self.api_methods = {}
        self.protocols = {}
        self.commands = []
        self.proxy = Proxy(self)
        self.emitter = Emitter(self)
        self.proxy_requests = 0
        self.emitter_requests = 0
        self.shown = threading.Event()
        self.close_requested = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.hwnd_callback = None

    def assert_owner(self):
        if threading.get_ident() != self.owner:
            raise PanicException("Native core accessed from a foreign thread")

    def get_proxy(self):
        self.assert_owner()
        self.proxy_requests += 1
        return self.proxy

    def create_emitter(self):
        self.assert_owner()
        self.emitter_requests += 1
        return self.emitter

    @classmethod
    def create_embedded(cls, **config):
        return cls(**config)

    def set_title(self, title):
        self.assert_owner()
        self.config["title"] = title

    def set_on_hwnd_created(self, callback):
        self.assert_owner()
        self.hwnd_callback = callback

    def on(self, name, callback):
        self.assert_owner()
        assert name not in self.handlers, "Duplicate native event registration"
        self.handlers[name] = callback

    def register_api_methods(self, namespace, names):
        self.assert_owner()
        self.api_methods.setdefault(namespace, []).extend(names)

    def register_protocol(self, scheme, handler):
        self.assert_owner()
        self.protocols[scheme] = handler

    def show(self):
        self.assert_owner()
        if self.hwnd_callback:
            self.hwnd_callback(1234)
        self.shown.set()
        assert self.close_requested.wait(5), "Test failed to close its native fake"
        assert self.release.wait(5), "Test failed to release owner teardown"

    def close(self):
        self.assert_owner()
        self.commands.append(("native_close",))
        self.close_requested.set()

    def emit(self, name, data):
        self.assert_owner()
        self.commands.append(("native_emit", name, data))

    def eval_js(self, script):
        self.assert_owner()
        self.commands.append(("native_eval_js", script))

    def load_url(self, url):
        self.assert_owner()
        self.commands.append(("native_load_url", url))

    def load_html(self, html):
        self.assert_owner()
        self.commands.append(("native_load_html", html))

    def process_events(self):
        self.assert_owner()
        self.commands.append(("native_pump",))
        return self.close_requested.is_set()

    process_ipc_only = process_events


@pytest.fixture
def windows_view(monkeypatch):
    cores = []
    views = []

    def factory(**kwargs):
        core = Core(**kwargs)
        cores.append(core)
        return core

    monkeypatch.setattr(webview_module, "_CoreWebView", factory)
    monkeypatch.setattr(lifecycle, "sys", SimpleNamespace(platform="win32"))

    def create(**kwargs):
        view = webview_module.WebView(dcc_mode=False, **kwargs)
        views.append(view)
        return view

    yield create, cores

    for core in cores:
        core.release.set()
    for view in views:
        view.close()
        assert view.wait(5)


def start(view):
    view.show_async()
    # This test-only wait never runs inside an actual DCC UI callback.
    while True:
        with view._async_core_lock:
            core = view._async_core
        if core is not None:
            assert core.shown.wait(5)
            return core
        if view.wait(0.001):
            pytest.fail(f"Owner failed to start: {view._startup_error}")


def test_async_creation_preserves_all_normalized_options(windows_view):
    create, cores = windows_view
    view = create(
        title="Host tool",
        width=933,
        height=721,
        html="<h1>Tool</h1>",
        context_menu=False,
        asset_root="assets",
        data_directory="profile",
        allow_file_protocol=False,
        capture_file_drop=True,
        auto_show=False,
        ipc_batch_size=7,
        icon="icon.png",
        new_window_mode="deny",
        splash_overlay=True,
        allow_downloads=False,
        download_prompt=True,
        download_directory="downloads",
        proxy_url="http://localhost:8080",
        user_agent="Test host",
        parent=42,
        mode="owner",
        remote_debugging_port=9224,
    )
    view.load_html("<h1>Latest</h1>")
    core = start(view)
    expected = dict(cores[0].config, html="<h1>Latest</h1>")
    assert core.config == expected
    assert core.owner != threading.get_ident()
    assert core.proxy_requests == 1


def test_public_commands_use_owner_cached_proxy(windows_view):
    create, _cores = windows_view
    view = create()
    core = start(view)
    assert view.get_proxy() is core.proxy
    view.emit("update", {"value": 1})
    view.eval_js("void 0")
    view.eval_js_async("void 1")
    view.load_url("https://example.com")
    assert view.get_current_url() == "https://example.com"
    view.load_html("<p>Updated</p>")
    assert view.emit_batch([("one", None), ("two", 2)]) == 2
    assert view.create_emitter() is core.emitter
    assert view.process_events() is False
    assert view.process_events_ipc_only() is False
    assert view.get_hwnd() == 1234
    assert core.proxy_requests == 1
    assert ("emit", "update", {"value": 1}) in core.commands
    assert ("eval_js", "void 0") in core.commands
    assert ("load_html", "<p>Updated</p>") in core.commands
    assert ("emit", "two", {"value": 2}) in core.commands
    with pytest.raises(RuntimeError, match="unavailable"):
        view.resize(400, 300)
    with pytest.raises(RuntimeError, match="unavailable"):
        view.title = "Foreign mutation"


def test_event_and_api_bindings_replay_before_show_and_rebind(windows_view):
    create, _cores = windows_view
    view = create()
    received = []
    scheduled = []
    view.on("changed", received.append)
    view.bind_call("api.echo", lambda value: "first:" + value)

    def protocol(_uri):
        return {"data": b"ok", "mime_type": "text/plain", "status": 200}

    view.register_protocol("asset", protocol)
    view.set_call_dispatcher(scheduled.append)
    core = start(view)
    assert "changed" in core.handlers
    assert "api.echo" in core.handlers
    assert core.api_methods["api"] == ["echo"]
    assert core.protocols == {"asset": protocol}
    view.on("changed", lambda value: received.append(("again", value)))
    core.handlers["changed"]("event")
    assert received == ["event", ("again", "event")]
    view.bind_call("api.echo", lambda value: "rebound:" + value)
    core.handlers["api.echo"]({"id": "call-1", "params": {"value": "ok"}})
    assert len(scheduled) == 1
    scheduled.pop()()
    results = [c[2] for c in core.commands if c[:2] == ("emit", "__auroraview_call_result")]
    assert results[-1] == {"id": "call-1", "ok": True, "result": "rebound:ok"}
    with pytest.raises(RuntimeError, match="Register new events"):
        view.on("new-event", received.append)
    with pytest.raises(RuntimeError, match="owner thread"):
        view.bind_call("api.new", lambda: None)


def test_close_is_nonblocking_idempotent_and_observable(windows_view):
    create, _cores = windows_view
    view = create()
    core = start(view)
    core.release.clear()
    view.close()
    view.request_close()
    assert view.wait(0) is False
    assert core.commands.count(("close",)) == 1
    assert core.proxy_requests == 1
    core.release.set()
    assert view.wait(5)
    assert view.get_hwnd() is None
    with pytest.raises(RuntimeError, match="fresh WebView"):
        view.show_async()
    fresh = create()
    assert start(fresh) is not core


def test_close_before_async_core_is_ready(windows_view):
    create, cores = windows_view
    view = create()
    entered = threading.Event()
    release = threading.Event()
    original = view._core_factory

    def delayed(**config):
        entered.set()
        assert release.wait(5)
        return original(**config)

    view._core_factory = delayed
    view.show_async()
    assert entered.wait(5)
    with pytest.raises(RuntimeError, match="starting"):
        view.emit("too_soon", {})
    with pytest.raises(RuntimeError, match="starting"):
        view.get_proxy()
    view.close()
    assert view.wait(0) is False
    release.set()
    assert view.wait(5)
    assert not cores[-1].shown.is_set()
    assert cores[-1].close_requested.is_set()


def test_close_cancels_pending_host_call(windows_view):
    create, _cores = windows_view
    view = create()
    scheduled = []
    effects = []
    view.set_call_dispatcher(scheduled.append)
    view.bind_call("api.mutate", lambda: effects.append("mutated"))
    core = start(view)
    core.handlers["api.mutate"]({"id": "pending", "params": {}})
    view.close()
    scheduled.pop()()
    assert effects == []
    results = [c[2] for c in core.commands if c[:2] == ("emit", "__auroraview_call_result")]
    assert len(results) == 1
    assert results[0]["id"] == "pending"
    assert results[0]["ok"] is False
    assert results[0]["error"]["name"] == "CancelledError"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_unproven_background_platform_fails_before_thread(windows_view, monkeypatch, platform):
    create, cores = windows_view
    view = create()
    monkeypatch.setattr(lifecycle, "sys", SimpleNamespace(platform=platform))
    with pytest.raises(RuntimeError, match="only supported on Windows"):
        view.show_async()
    assert view._show_thread is None
    assert not view._is_running
    assert len(cores) == 1


def test_foreign_commands_on_synchronous_core_never_reacquire_proxy(windows_view):
    create, cores = windows_view
    view = create()
    errors = []

    def worker():
        try:
            assert view.get_proxy() is cores[0].proxy
            view.emit("foreign", {})
            view.eval_js("void 0")
            view.close()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert errors == []
    assert cores[0].proxy_requests == 1
    assert ("close",) in cores[0].commands


def test_startup_failure_reports_completion_and_error(windows_view):
    create, _cores = windows_view
    view = create()

    def fail(**_config):
        raise RuntimeError("Native creation failed")

    view._core_factory = fail
    view.show_async()
    assert view.wait(5)
    assert str(view.startup_error) == "Native creation failed"
    assert not view.is_alive() or view._close_requested
    with pytest.raises(RuntimeError, match="fresh WebView"):
        view.show_async()


def test_same_thread_embedded_event_pump_remains_usable(windows_view):
    create, cores = windows_view
    view = create(parent=42, mode="child")
    core = cores[0]

    def embedded_show():
        core.assert_owner()
        core.shown.set()  # Embedded native show returns to the host event loop.

    core.show = embedded_show
    view.show_blocking()
    view.emit("host_update", {})
    view.eval_js("void 0")
    assert ("native_emit", "host_update", {}) in core.commands
    assert ("native_eval_js", "void 0") in core.commands
    view.request_close()
    assert view.wait(0) is False
    assert view.process_events_ipc_only() is True
    assert view.wait(0) is True


def test_owner_callback_can_close_without_self_join(windows_view):
    create, _cores = windows_view
    view = create()
    original = view._core_factory
    completed = threading.Event()

    def factory(**config):
        core = original(**config)

        def owner_show():
            core.assert_owner()
            assert view.wait(0) is False
            with pytest.raises(RuntimeError, match="cannot wait for itself"):
                view.wait(1)
            view.close()
            completed.set()

        core.show = owner_show
        return core

    view._core_factory = factory
    view.show_async()
    assert view.wait(5)
    assert completed.is_set()
    assert view.startup_error is None


def test_untracked_core_never_authorizes_native_access(windows_view):
    create, cores = windows_view
    view = create()
    core = cores[0]
    view._core_threads.clear()
    view.emit("untracked", {})
    assert ("emit", "untracked", {}) in core.commands
    assert not any(command[0] == "native_emit" for command in core.commands)
    with pytest.raises(RuntimeError, match="owner thread"):
        view.show_blocking()


def queue_dcc_callbacks(monkeypatch):
    from auroraview.utils import thread_dispatcher

    queued = []

    def wrap(callback):
        def schedule(*args, **kwargs):
            queued.append(lambda: callback(*args, **kwargs))

        return schedule

    monkeypatch.setattr(thread_dispatcher, "wrap_callback_for_dcc", wrap)
    return queued


def test_queued_and_late_events_are_cancelled_on_close(windows_view, monkeypatch):
    create, cores = windows_view
    view = create()
    view._dcc_mode = True
    queued = queue_dcc_callbacks(monkeypatch)
    effects = []
    view.on("mutate", effects.append)
    view.on_loaded(effects.append)
    native_callback = cores[0].handlers["mutate"]
    native_callback({"before": "close"})
    view.signals.page_loaded.emit()
    assert len(queued) == 2
    view.close()
    for callback in queued:
        callback()
    native_callback({"after": "close"})
    assert effects == []
    assert len(queued) == 2
    assert view._event_handlers == {}
    assert view._event_connections == {}
    assert view.signals.custom.get("mutate").handler_count == 0
    # A fresh host generation can run while retained old callbacks stay inert.
    fresh = create()
    fresh.on("mutate", effects.append)
    cores[-1].handlers["mutate"]("fresh")
    for callback in queued:
        callback()
    assert effects == ["fresh"]


def test_disconnect_updates_native_and_signal_dispatch_and_queued_work(windows_view, monkeypatch):
    create, cores = windows_view
    view = create()
    view._dcc_mode = True
    queued = queue_dcc_callbacks(monkeypatch)
    effects = []
    first = view.on("mutate", lambda data: effects.append(("first", data)))
    second = view.on("mutate", lambda data: effects.append(("second", data)))
    cores[0].handlers["mutate"](1)
    assert len(queued) == 2
    assert not view.disconnect("wrong_name", first)
    assert view.disconnect("mutate", first)
    assert not view.disconnect("mutate", first)
    assert len(view._event_handlers["mutate"]) == 1
    assert view.signals.custom.get("mutate").handler_count == 1
    for callback in queued:
        callback()
    assert effects == [("second", 1)]
    queued.clear()
    cores[0].handlers["mutate"](2)
    view.signals.custom.emit("mutate", 3)
    for callback in queued:
        callback()
    assert effects == [("second", 1), ("second", 2), ("second", 3)]
    assert view.disconnect("mutate", second)
    assert "mutate" not in view._event_handlers


class OwnerTimerBackend(TimerBackend):
    """Manually pumped backend with Qt-like strict owner-thread teardown."""

    def __init__(self):
        self.owner = None
        self.stops = []
        self.fail_start = False
        self.fail_stop = False

    def is_available(self):
        return True

    def start(self, _interval, callback):
        if self.fail_start:
            raise RuntimeError("Timer start failed")
        self.owner = threading.get_ident()
        self.callback = callback
        return object()

    def stop(self, _handle):
        assert threading.get_ident() == self.owner, "Foreign native timer stop"
        if self.fail_stop:
            raise RuntimeError("Timer stop failed")
        self.stops.append(threading.get_ident())


@pytest.mark.parametrize("finish_with", ["owner_tick", "owner_close"])
def test_foreign_close_leaves_timer_pending_until_owner_cleanup(windows_view, finish_with):
    create, _cores = windows_view
    view = create()
    start(view)
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    timer.start()
    effects = []
    timer.on_tick(lambda: effects.append("late host mutation"))
    closer = threading.Thread(target=view.close)
    closer.start()
    closer.join(5)
    assert not closer.is_alive()
    assert view._closed_event.wait(5)
    # A stopped Qt pump must remain observably pending, even after native exit.
    assert view.cleanup_pending
    assert view.wait(0) is False
    assert timer.is_running
    assert backend.stops == []
    if finish_with == "owner_tick":
        timer._tick()
    else:
        view.request_close()
    assert backend.stops == [threading.get_ident()]
    assert effects == []
    assert view.wait(0)
    assert not view.cleanup_pending
    assert view._auto_timer is None
    assert timer._webview is None
    assert timer._tick_callbacks == []


def test_timer_owner_is_successful_start_thread_not_constructor(windows_view):
    create, _cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    started = threading.Event()
    finish = threading.Event()

    def owner():
        timer.start()
        started.set()
        assert finish.wait(5)
        timer._tick()

    thread = threading.Thread(target=owner)
    thread.start()
    assert started.wait(5)
    assert timer.owner_thread_id == thread.ident
    with pytest.raises(RuntimeError, match="owning thread"):
        timer.stop()
    view.close()
    assert view.cleanup_pending
    assert not view.wait(0)
    finish.set()
    thread.join(5)
    assert not thread.is_alive()
    assert backend.stops == [thread.ident]
    assert view.wait(0)


def test_failed_timer_start_does_not_claim_owner(windows_view):
    create, _cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    backend.fail_start = True
    timer = view._auto_timer = EventTimer(view, backend=backend)
    with pytest.raises(RuntimeError, match="Timer start failed"):
        timer.start()
    assert timer.owner_thread_id is None
    view.close()
    assert view.wait(0)
    assert backend.stops == []
    assert timer._webview is None


def test_failed_timer_stop_remains_pending_and_owner_can_retry(windows_view):
    create, _cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    timer.start()
    backend.fail_stop = True
    view.close()
    assert view.cleanup_pending
    assert timer.is_running
    assert not view.wait(0)
    backend.fail_stop = False
    view.close()
    assert view.wait(0)
    assert backend.stops == [threading.get_ident()]


def test_thread_timer_can_cleanup_from_foreign_close_without_join(windows_view):
    create, _cores = windows_view
    view = create()
    timer = view._auto_timer = EventTimer(view, backend=ThreadTimerBackend())
    timer.start()
    closer = threading.Thread(target=view.close)
    closer.start()
    closer.join(5)
    assert not closer.is_alive()
    assert view.wait(0)
    assert not view.cleanup_pending
    assert not timer.is_running
    assert timer._webview is None


@pytest.mark.parametrize("observe_native_close", [False, True])
def test_close_during_timer_start_keeps_cleanup_pending(windows_view, observe_native_close):
    create, cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    notifications = []
    timer.on_close(lambda: notifications.append(threading.get_ident()))
    entered = threading.Event()
    release = threading.Event()
    original = backend.start

    def delayed(interval, callback):
        entered.set()
        assert release.wait(5)
        return original(interval, callback)

    backend.start = delayed

    def owner():
        timer.start()
        timer._tick()

    thread = threading.Thread(target=owner)
    thread.start()
    assert entered.wait(5)
    if observe_native_close:
        cores[0].close_requested.set()
        assert view.process_events()
    else:
        view.close()
    assert view.cleanup_pending
    assert not view.wait(0)
    assert timer._webview is view
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert view.wait(0)
    assert backend.stops == [thread.ident]
    assert notifications == ([thread.ident] if observe_native_close else [])


@pytest.mark.parametrize("factory", ["mixin", "legacy"])
def test_embedded_factories_bootstrap_public_api_and_close(monkeypatch, factory):
    native = ModuleType("auroraview._core")
    native.WebView = Core
    monkeypatch.setitem(sys.modules, "auroraview._core", native)
    if factory == "mixin":
        view = webview_module.WebView.create_embedded(parent_hwnd=42, title="Embedded")
    else:
        view = WebViewFactory.create_embedded(
            webview_module.WebView, parent_hwnd=42, title="Embedded"
        )
    core = view._core
    try:
        assert view.title == "Embedded"
        view.title = "Renamed"
        assert core.config["title"] == "Renamed"
        view.emit("owner", {})
        assert not view.process_events_ipc_only()
        assert ("native_pump",) in core.commands
        received = []
        view.on("changed", received.append)
        core.handlers["changed"]("data")
        assert received == ["data"]
        view.bind_call("api.echo", lambda: "ok")
        core.handlers["api.echo"]({"id": "embedded"})
        assert any(c[:2] == ("native_emit", "__auroraview_call_result") for c in core.commands)
        errors = []

        def foreign():
            try:
                view.emit("foreign", {})
                view.eval_js("void 0")
                assert view.get_proxy() is core.proxy
                assert view.create_emitter() is core.emitter
                assert not view.process_events()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=foreign)
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
        assert errors == []
        assert ("emit", "foreign", {}) in core.commands
    finally:
        view.close()
        view.process_events_ipc_only()
    assert ("native_close",) in core.commands
    assert view.wait(0)
    with pytest.raises(RuntimeError, match="fresh WebView"):
        view.show_async()


def test_real_wrapper_timer_notifies_close_once_before_final_cleanup(windows_view):
    create, cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend, check_window_validity=False)
    timer._is_core_ready = lambda: True
    observed = []
    timer.on_close(lambda: observed.append(("closed", view._auto_timer is timer)))
    timer.start()
    cores[0].close_requested.set()  # Native window close discovered by wrapper pump.
    timer._tick()
    timer._tick()
    view.close()
    assert observed == [("closed", True)]
    assert len(backend.stops) == 1
    assert timer._close_callbacks == []
    assert timer._webview is None
    assert view._auto_timer is None
    assert view.wait(0)


def test_native_close_failure_retries_and_cleans_independent_targets(windows_view):
    create, cores = windows_view
    view = create()
    core = cores[0]
    other = Core()
    view._async_core = other
    view._track_core_thread(other)
    calls = []
    original = other.close

    def fail_once():
        calls.append("attempt")
        if len(calls) == 1:
            raise RuntimeError("temporary native close failure")
        original()

    other.close = fail_once
    view._singleton_registry["retry-test"] = view
    window_id = view.window_id
    with pytest.raises(RuntimeError, match="temporary native"):
        view.request_close()
    assert view.close_pending
    assert not view.wait(0)
    assert ("native_close",) in core.commands  # Other core was not skipped.
    assert "retry-test" not in view._singleton_registry
    from auroraview.core.window_manager import get_window_manager

    assert get_window_manager().get(window_id) is None
    view.request_close()
    view.request_close()
    assert len(calls) == 2
    assert core.commands.count(("native_close",)) == 1
    assert view.wait(0)
    assert not view.close_pending


def test_foreign_proxy_close_failure_stays_pending_and_can_retry(windows_view):
    create, cores = windows_view
    view = create()
    core = cores[0]
    attempts = []
    original = core.proxy.close
    errors = []

    def fail_once():
        attempts.append("attempt")
        if len(attempts) == 1:
            raise RuntimeError("temporary channel failure")
        original()

    core.proxy.close = fail_once

    def foreign():
        try:
            view.close()
        except RuntimeError as exc:
            errors.append(str(exc))

    first = threading.Thread(target=foreign)
    first.start()
    first.join(5)
    assert errors and "cached proxy" in errors[0]
    assert view.close_pending and not view.wait(0)
    second = threading.Thread(target=foreign)
    second.start()
    second.join(5)
    assert len(errors) == 1
    assert len(attempts) == 2
    assert core.proxy_requests == 1
    assert not view.close_pending
    assert view.wait(0)


@pytest.mark.parametrize(
    "payload", [{"value": 1}, MappingProxyType({"value": 2}), UserDict(value=3)]
)
def test_cached_event_emitter_preserves_mapping_contract(windows_view, payload):
    create, _cores = windows_view
    view = create()
    core = start(view)
    emitter = view.create_emitter()
    assert emitter is core.emitter
    assert emitter is not core.proxy
    emitter.emit("mapping", payload)
    assert ("emitter", "mapping", dict(payload)) in core.commands
    assert view.create_emitter() is emitter
    assert core.emitter_requests == 1


def test_failed_async_close_retains_send_safe_target_after_owner_exit(windows_view):
    create, cores = windows_view
    view = create()
    original = view._core_factory
    proxy_fails = [True]
    owner_attempts = []
    proxy_attempts = []

    def factory(**config):
        core = original(**config)

        def show():
            core.assert_owner()
            raise RuntimeError("Injected owner startup failure")

        def close():
            core.assert_owner()  # Any foreign retry here must fail the test.
            owner_attempts.append(threading.get_ident())
            raise RuntimeError("Injected native close failure")

        send_close = core.proxy.close

        def proxy_close():
            proxy_attempts.append(threading.get_ident())
            if proxy_fails[0]:
                raise RuntimeError("Injected send-safe channel failure")
            send_close()

        core.show = show
        core.close = close
        core.proxy.close = proxy_close
        return core

    view._core_factory = factory
    view.show_async()
    view._show_thread.join(5)
    assert not view._show_thread.is_alive()
    failed = cores[-1]
    assert view._async_core is None
    assert view.close_pending and not view.wait(0)
    attempts = len(owner_attempts)
    # Pending ownership is independent even of the general proxy cache.
    view._core_proxies.pop(id(failed))
    with pytest.raises(RuntimeError, match="retained send-safe proxy"):
        view.request_close()
    assert view.close_pending and not view.wait(0)
    proxy_fails[0] = False
    view.request_close()
    assert len(owner_attempts) == attempts
    assert proxy_attempts == [threading.get_ident(), threading.get_ident()]
    assert not view.close_pending
    assert view.wait(0)
    # Request acceptance is not a fabricated native-resource-destroyed flag.
    assert not view._native_close_observed


@pytest.mark.parametrize("stop_fails", [False, True])
def test_native_close_notification_survives_send_and_cleanup_errors(windows_view, stop_fails):
    create, cores = windows_view
    view = create()
    core = cores[0]
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend, check_window_validity=False)
    timer._is_core_ready = lambda: True
    notifications = []
    timer.on_close(lambda: notifications.append(threading.get_ident()))
    timer.start()
    backend.fail_stop = stop_fails
    attempts = []
    original = core.close

    def fail_once():
        core.assert_owner()
        attempts.append("send")
        if len(attempts) == 1:
            raise RuntimeError("Injected close send failure")
        original()

    core.close = fail_once
    core.close_requested.set()
    timer._tick()
    assert view._native_close_observed
    assert view.close_pending and not view.wait(0)
    assert notifications == ([] if stop_fails else [threading.get_ident()])
    if stop_fails:
        assert view.cleanup_pending
    backend.fail_stop = False
    view.request_close()
    timer._tick()
    view.request_close()
    assert notifications == [threading.get_ident()]
    assert len(attempts) == 2
    assert len(backend.stops) == 1
    assert view.wait(0)


@pytest.mark.parametrize("pump", ["process_events", "process_events_ipc_only"])
def test_direct_pump_keeps_close_observation_when_send_raises(windows_view, pump):
    create, cores = windows_view
    view = create()
    core = cores[0]
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    observed = []
    timer.on_close(lambda: observed.append("closed"))
    timer.start()
    original = core.close

    def fail():
        core.assert_owner()
        raise RuntimeError("Injected send failure")

    core.close = fail
    core.close_requested.set()
    with pytest.raises(RuntimeError, match="Injected send failure"):
        getattr(view, pump)()
    assert view._native_close_observed
    assert observed == ["closed"]
    assert view.close_pending and not view.wait(0)
    core.close = original
    view.request_close()
    assert observed == ["closed"]
    assert view.wait(0)


def test_foreign_retry_cannot_consume_pending_owner_close_notification(windows_view):
    create, cores = windows_view
    view = create()
    core = cores[0]
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend)
    observed = []
    timer.on_close(lambda: observed.append(threading.get_ident()))
    timer.start()
    # Emulate the interval after the owner pump observed close and stopped its
    # timer, but before the timer tick reaches its notification/final cleanup.
    timer._processing_events = True
    core.close_requested.set()
    view.process_events()
    timer._processing_events = False
    assert not timer.is_running
    assert observed == []
    foreign = threading.Thread(target=view.request_close)
    foreign.start()
    foreign.join(5)
    assert not foreign.is_alive()
    assert observed == []
    assert view.cleanup_pending and not view.wait(0)
    view.request_close()
    assert observed == [threading.get_ident()]
    assert view.wait(0)


@pytest.mark.parametrize("outer_path", ["timer_tick", "owner_pump"])
def test_foreign_retry_stays_pending_until_all_close_observers_exit(windows_view, outer_path):
    create, cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend, check_window_validity=False)
    timer._is_core_ready = lambda: True
    entered = threading.Event()
    released = threading.Event()
    results = []
    observed = []
    errors = []

    def first_observer():
        observed.append("first")
        entered.set()
        assert released.wait(2), "Foreign close blocked behind a user callback"
        assert not view.wait(0)

    def second_observer():
        observed.append("second")
        assert not view.wait(0)
        assert not timer._close_notified

    def foreign():
        try:
            assert entered.wait(2)
            view.request_close()
            results.append(view.wait(0))
            # Direct cleanup must also return immediately without releasing
            # observers or claiming that the outer cleanup has completed.
            results.append(timer.cleanup())
            assert len(timer._close_callbacks) == 2
        except BaseException as exc:
            errors.append(exc)
        finally:
            released.set()

    timer.on_close(first_observer)
    timer.on_close(second_observer)
    timer.start()
    cores[0].close_requested.set()
    worker = threading.Thread(target=foreign)
    worker.start()
    if outer_path == "timer_tick":
        timer._tick()
    else:
        assert view.process_events()
    worker.join(2)
    assert not worker.is_alive()
    assert errors == []
    assert results == [False, False]
    assert observed == ["first", "second"]
    assert timer._close_notified and not timer._close_notifying
    assert not timer._cleanup_active
    assert view.wait(0)
    assert view._auto_timer is None
    assert len(backend.stops) == 1


@pytest.mark.parametrize("outer_path", ["timer_tick", "owner_pump"])
def test_owner_reentrant_close_and_direct_cleanup_remain_pending(windows_view, outer_path):
    create, cores = windows_view
    view = create()
    backend = OwnerTimerBackend()
    timer = view._auto_timer = EventTimer(view, backend=backend, check_window_validity=False)
    timer._is_core_ready = lambda: True
    results = []

    def observer():
        view.request_close()
        results.append(view.wait(0))
        results.append(timer.cleanup())
        assert view._auto_timer is timer
        assert not timer._close_notified
        assert timer._close_notifying
        assert len(timer._close_callbacks) == 2
        # Timer state locks are not retained while user code executes.
        assert timer._cleanup_lock.acquire(blocking=False)
        timer._cleanup_lock.release()

    timer.on_close(observer)
    timer.on_close(observer)
    timer.start()
    cores[0].close_requested.set()
    if outer_path == "timer_tick":
        timer._tick()
    else:
        assert view.process_events()
    assert results == [False, False, False, False]
    assert view.wait(0)
    assert not view.cleanup_pending
    assert timer._close_callbacks == []
    assert timer.cleanup() is True
    assert len(backend.stops) == 1


def test_exception_in_close_observer_does_not_complete_before_remaining_observers(windows_view):
    create, cores = windows_view
    view = create()
    timer = view._auto_timer = EventTimer(view, backend=OwnerTimerBackend())
    timer._is_core_ready = lambda: True
    results = []

    def raises():
        results.append(view.wait(0))
        raise RuntimeError("Injected observer failure")

    def finishes():
        view.request_close()
        results.append(view.wait(0))
        results.append(timer.cleanup())

    timer.on_close(raises)
    timer.on_close(finishes)
    timer.start()
    cores[0].close_requested.set()
    timer._tick()
    assert results == [False, False, False]
    assert timer._close_notified
    assert view.wait(0)


def test_native_close_publication_keeps_observers_pending_before_they_start(windows_view):
    create, cores = windows_view
    view = create()
    timer = view._auto_timer = EventTimer(view, backend=OwnerTimerBackend())
    results = []
    original = timer._observe_close

    def observe():
        results.append(view.wait(0))
        original()

    timer._observe_close = observe
    timer.on_close(lambda: results.append(view.wait(0)))
    timer.start()
    cores[0].close_requested.set()
    assert view.process_events()
    assert results and not any(results)
    assert view.wait(0)


@pytest.mark.parametrize("observer_result", [False, True])
def test_close_observer_return_is_not_a_veto_or_completion_flag(windows_view, observer_result):
    create, cores = windows_view
    view = create()
    timer = view._auto_timer = EventTimer(view, backend=OwnerTimerBackend())
    timer._is_core_ready = lambda: True
    results = []

    def observer():
        results.append(view.wait(0))
        return observer_result

    timer.on_close(observer)
    timer.on_close(lambda: results.append(view.wait(0)))
    timer.start()
    cores[0].close_requested.set()
    timer._tick()
    assert results == [False, False]
    assert timer._close_notified
    assert view.wait(0)
