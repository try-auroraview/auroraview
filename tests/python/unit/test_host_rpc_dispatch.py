# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""Host RPC scheduling contracts without a GUI or compiled extension."""

from __future__ import annotations

import json
import threading

import pytest

from auroraview.core.mixins.api import WebViewApiMixin


class NativeCore:
    """Additive native callbacks; registration is restricted to the owner."""

    def __init__(self):
        self.owner = threading.get_ident()
        self.handlers = {}
        self.methods = {}
        self.protocols = {}
        self.protocol_registrations = 0

    def on(self, method, handler):
        assert threading.get_ident() == self.owner
        self.handlers.setdefault(method, []).append(handler)

    def on_batch(self, handlers):
        for method, handler in handlers:
            self.on(method, handler)

    def register_api_methods(self, namespace, names):
        assert threading.get_ident() == self.owner
        self.methods.setdefault(namespace, []).extend(names)

    def receive(self, method, raw):
        for handler in self.handlers[method]:
            handler(raw)

    def register_protocol(self, scheme, handler):
        assert threading.get_ident() == self.owner
        self.protocols[scheme] = handler
        self.protocol_registrations += 1


class HostView(WebViewApiMixin):
    def __init__(self, dcc_mode=False):
        self._core = NativeCore()
        self._async_core = None
        self._dcc_mode = dcc_mode
        self.results = []
        self._init_api_registry()

    def _get_active_core(self):
        return self._async_core if self._async_core is not None else self._core

    def _is_core_owner(self, core):
        return core.owner == threading.get_ident()

    def emit(self, event, payload):
        assert event == "__auroraview_call_result"
        # Model the thread-safe result path, and require valid bridge JSON.
        self.results.append(json.loads(json.dumps(payload, allow_nan=False)))


@pytest.fixture
def queued_view():
    view = HostView()
    queue = []
    view.set_call_dispatcher(queue.append)
    return view, queue


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({}, {"args": [], "kwargs": {}}),
        ({"params": None}, {"args": [None], "kwargs": {}}),
        ({"params": []}, {"args": [], "kwargs": {}}),
        ({"params": [1, "two"]}, {"args": [1, "two"], "kwargs": {}}),
        ({"params": {}}, {"args": [], "kwargs": {}}),
        ({"params": {"value": 3}}, {"args": [], "kwargs": {"value": 3}}),
        ({"params": "hello"}, {"args": ["hello"], "kwargs": {}}),
        ({"params": False}, {"args": [False], "kwargs": {}}),
    ],
)
def test_host_dispatch_preserves_params(queued_view, raw, expected):
    view, queue = queued_view
    calls = []

    def target(*args, **kwargs):
        calls.append(threading.get_ident())
        return {"args": list(args), "kwargs": kwargs}

    view.bind_call("api.target", target)
    raw["id"] = "request"
    native_thread = threading.Thread(target=view._core.receive, args=("api.target", raw))
    native_thread.start()
    native_thread.join(timeout=2)

    assert not native_thread.is_alive(), "Native IPC must not wait for the host callback"
    assert calls == []
    assert view.results == []
    assert len(queue) == 1
    queue.pop()()
    assert calls == [threading.get_ident()]
    assert view.results == [{"id": "request", "ok": True, "result": expected}]


def test_bind_api_uses_same_dispatcher(queued_view):
    view, queue = queued_view

    class API:
        def echo(self, value):
            return value

        def count(self):
            return 2

    view.bind_api(API(), namespace="host")
    view._core.receive("host.echo", {"id": "echo", "params": {"value": 9}})
    assert view.results == []
    queue.pop()()
    assert view.results == [{"id": "echo", "ok": True, "result": 9}]
    assert sorted(view._core.methods["host"]) == ["count", "echo"]


def test_dcc_mode_uses_existing_deferred_dispatcher(monkeypatch):
    from auroraview.utils.thread_dispatcher import registry
    from auroraview.utils.thread_dispatcher.base import ThreadDispatcherBackend

    queue = []

    class HostBackend(ThreadDispatcherBackend):
        def is_available(self):
            return True

        def run_deferred(self, func, *args, **kwargs):
            queue.append(func)

        def run_sync(self, func, *args, **kwargs):
            pytest.fail("RPC must not use blocking host dispatch")

    monkeypatch.setattr(registry, "_cached_backend", HostBackend())
    view = HostView(dcc_mode=True)
    view.bind_call("host.answer", lambda: 42)
    view._core.receive("host.answer", {"id": "answer"})
    assert view.results == []
    queue.pop()()
    assert view.results == [{"id": "answer", "ok": True, "result": 42}]


def test_dcc_mode_rejects_unsafe_fallback(isolated_dispatcher):
    view = HostView(dcc_mode=True)
    calls = []
    view.bind_call("host.mutate", lambda: calls.append(True))
    view._core.receive("host.mutate", {"id": "unsafe"})
    assert calls == []
    assert view.results[0]["ok"] is False
    assert "set_call_dispatcher" in view.results[0]["error"]["message"]


def test_dcc_dispatcher_cannot_silently_run_on_foreign_thread(monkeypatch):
    from auroraview.utils.thread_dispatcher import registry
    from auroraview.utils.thread_dispatcher.base import ThreadDispatcherBackend

    class BrokenHostBackend(ThreadDispatcherBackend):
        def is_available(self):
            return True

        def run_deferred(self, func, *args, **kwargs):
            func()

        def run_sync(self, func, *args, **kwargs):
            pytest.fail("RPC must not use blocking host dispatch")

    monkeypatch.setattr(registry, "_cached_backend", BrokenHostBackend())
    view = HostView(dcc_mode=True)
    calls = []
    view.bind_call("host.mutate", lambda: calls.append(True))
    native_thread = threading.Thread(
        target=view._core.receive, args=("host.mutate", {"id": "unsafe"})
    )
    native_thread.start()
    native_thread.join(timeout=2)
    assert not native_thread.is_alive()
    assert calls == []
    assert view.results[0]["error"]["message"] == (
        "Host dispatcher did not execute on the main thread"
    )


def test_explicit_dispatcher_takes_precedence_over_dcc_default(isolated_dispatcher):
    view = HostView(dcc_mode=True)
    queue = []
    view.set_call_dispatcher(queue.append)
    view.bind_call("host.answer", lambda: 42)
    view._core.receive("host.answer", {"id": "answer"})
    queue.pop()()
    assert view.results[0]["result"] == 42


def test_default_non_dcc_calls_remain_synchronous():
    view = HostView()
    view.bind_call("echo", lambda value: value)
    view._core.receive("echo", {"id": "echo", "params": 0})
    assert view.results == [{"id": "echo", "ok": True, "result": 0}]


def test_dispatcher_can_be_reset(queued_view):
    view, queue = queued_view
    view.bind_call("echo", lambda: "done")
    view.set_call_dispatcher(None)
    view._core.receive("echo", {"id": "echo"})
    assert queue == []
    assert view.results[0]["result"] == "done"


def test_invalid_dispatcher_is_rejected(queued_view):
    view, _queue = queued_view
    with pytest.raises(TypeError, match="callable"):
        view.set_call_dispatcher(42)


def test_handler_exception_rejects_promise(queued_view):
    view, queue = queued_view

    def fail():
        raise ValueError("Host operation failed")

    view.bind_call("fail", fail)
    view._core.receive("fail", {"id": "failure"})
    queue.pop()()
    assert view.results == [
        {
            "id": "failure",
            "ok": False,
            "error": {"name": "ValueError", "message": "Host operation failed"},
        }
    ]
    assert not view._pending_calls


@pytest.mark.parametrize("result", [object(), {"unserializable"}, float("nan")])
def test_serialization_failure_rejects_promise(queued_view, result):
    view, queue = queued_view
    view.bind_call("result", lambda: result)
    view._core.receive("result", {"id": "json"})
    queue.pop()()
    assert view.results[0]["id"] == "json"
    assert view.results[0]["ok"] is False
    assert view.results[0]["error"]["name"] in ("TypeError", "ValueError")
    assert not view._pending_calls


def test_result_is_normalized_before_native_emit(queued_view):
    view, queue = queued_view
    native_payloads = []
    view.emit = lambda event, payload: native_payloads.append(payload)
    view.bind_call("result", lambda: {1: ("first", "second")})
    view._core.receive("result", {"id": "json"})
    queue.pop()()
    assert native_payloads == [{"id": "json", "ok": True, "result": {"1": ["first", "second"]}}]


def test_scheduler_failure_invalidates_already_queued_callback(queued_view):
    view, queue = queued_view
    calls = []

    def broken_dispatcher(callback):
        queue.append(callback)
        raise RuntimeError("Host is unavailable")

    view.set_call_dispatcher(broken_dispatcher)
    view.bind_call("mutate", lambda: calls.append(True))
    view._core.receive("mutate", {"id": "dispatch"})
    queue.pop()()
    assert calls == []
    assert len(view.results) == 1
    assert view.results[0]["error"]["message"] == "Host is unavailable"


def test_rebind_uses_one_native_callback_and_latest_callable(queued_view):
    view, queue = queued_view
    view.bind_call("answer", lambda: 1)
    view._core.receive("answer", {"id": "answer"})
    view.bind_call("answer", lambda: 2)
    assert len(view._core.handlers["answer"]) == 1
    queue.pop()()
    assert view.results == [{"id": "answer", "ok": True, "result": 2}]


def test_namespace_rebind_does_not_duplicate_native_callbacks(queued_view):
    view, queue = queued_view

    class API:
        def __init__(self, value):
            self.value = value

        def answer(self):
            return self.value

    view.bind_api(API(1))
    view.bind_api(API(2), allow_rebind=True)
    view._core.receive("api.answer", {"id": "answer"})
    assert len(view._core.handlers["api.answer"]) == 1
    assert view._core.methods["api"] == ["answer"]
    queue.pop()()
    assert view.results[0]["result"] == 2


def test_failed_js_registration_can_retry_without_duplicate_callbacks(queued_view, monkeypatch):
    view, queue = queued_view
    register = view._core.register_api_methods

    def fail(namespace, methods):
        raise RuntimeError("Registration unavailable")

    monkeypatch.setattr(view._core, "register_api_methods", fail)
    with pytest.raises(RuntimeError, match="Registration unavailable"):
        view.bind_call("api.answer", lambda: 1)
    monkeypatch.setattr(view._core, "register_api_methods", register)
    view.bind_call("api.answer", lambda: 2)
    assert len(view._core.handlers["api.answer"]) == 1
    assert view._core.methods["api"] == ["answer"]
    view._core.receive("api.answer", {"id": "retry"})
    queue.pop()()
    assert view.results[0]["result"] == 2


def test_replay_registers_once_per_native_core(queued_view):
    view, queue = queued_view
    view.bind_call("api.answer", lambda: 42)
    view.bind_call("host.echo", lambda value: value)
    replacement = NativeCore()
    view._replay_api_bindings(replacement)
    view._replay_api_bindings(replacement)
    view._async_core = replacement
    assert len(replacement.handlers["api.answer"]) == 1
    assert replacement.methods == {"api": ["answer"], "host": ["echo"]}
    replacement.receive("api.answer", {"id": "replay"})
    queue.pop()()
    assert view.results[0]["result"] == 42


def test_custom_protocol_is_replayed_once_on_new_core(queued_view):
    view, _queue = queued_view

    def protocol(uri):
        return {"data": uri.encode("utf-8"), "mime_type": "text/plain", "status": 200}

    view.register_protocol("host", protocol)
    replacement = NativeCore()
    view._replay_api_bindings(replacement)
    view._replay_api_bindings(replacement)
    assert replacement.protocols == {"host": protocol}
    assert replacement.protocol_registrations == 1


def test_custom_protocol_cannot_register_on_foreign_active_core(queued_view):
    view, _queue = queued_view
    view._async_core = NativeCore()
    view._async_core.owner = -1
    with pytest.raises(RuntimeError, match="owner thread"):
        view.register_protocol("host", lambda uri: {})
    assert view._protocol_handlers == {}
    assert view._core.protocols == {}
    assert view._async_core.protocols == {}


def test_foreign_core_rebind_is_python_only_but_new_binding_fails(queued_view):
    view, _queue = queued_view
    view.bind_call("api.answer", lambda: 1)
    replacement = NativeCore()
    view._replay_api_bindings(replacement)
    view._async_core = replacement
    replacement.owner = -1

    view.bind_call("api.answer", lambda: 2)
    with pytest.raises(RuntimeError, match="owner thread"):
        view.bind_call("api.new", lambda: 3)
    assert view._bound_functions["api.answer"]() == 2
    assert "api.new" not in view.get_bound_methods()
    assert "api.new" not in replacement.handlers
    assert "api.new" not in view._core.handlers
    with pytest.raises(RuntimeError, match="owner thread"):
        view._replay_api_bindings(replacement)


def test_foreign_namespace_new_binding_fails_without_partial_rebind(queued_view):
    view, _queue = queued_view

    class API:
        def answer(self):
            return 2

        def new_method(self):
            return 3

    def original():
        return 1

    view.bind_call("api.answer", original)
    view._core.owner = -1
    with pytest.raises(RuntimeError, match="owner thread"):
        view.bind_api(API(), allow_rebind=True)
    assert view._bound_functions == {"api.answer": original}
    assert not view.is_namespace_bound("api")


def test_cancelled_callback_never_mutates_host(queued_view):
    view, queue = queued_view
    calls = []
    view.bind_call("mutate", lambda: calls.append(True))
    view._core.receive("mutate", {"id": "pending"})
    view._cancel_pending_calls("WebView closed")
    queue.pop()()
    assert calls == []
    assert view.results == [
        {
            "id": "pending",
            "ok": False,
            "error": {"name": "CancelledError", "message": "WebView closed"},
        }
    ]
    assert not view._pending_calls


def test_calls_after_cancellation_are_rejected_without_scheduling(queued_view):
    view, queue = queued_view
    calls = []
    view.bind_call("mutate", lambda: calls.append(True))
    view._cancel_pending_calls("WebView closed")
    view._core.receive("mutate", {"id": "late"})
    assert queue == []
    assert calls == []
    assert view.results[0]["error"]["name"] == "CancelledError"


def test_inflight_call_cannot_emit_late_success_after_close(queued_view):
    view, queue = queued_view
    running = threading.Event()
    finish = threading.Event()

    def target():
        running.set()
        assert finish.wait(timeout=2)
        return "late result"

    view.bind_call("slow", target)
    view._core.receive("slow", {"id": "inflight"})
    host_thread = threading.Thread(target=queue.pop())
    host_thread.start()
    try:
        assert running.wait(timeout=2)
        view._cancel_pending_calls("WebView closed")
    finally:
        finish.set()
        host_thread.join(timeout=2)
    assert not host_thread.is_alive()
    assert len(view.results) == 1
    assert view.results[0]["error"]["name"] == "CancelledError"


def test_callback_is_one_shot_even_if_scheduler_repeats_it(queued_view):
    view, queue = queued_view
    calls = []
    view.bind_call("mutate", lambda: calls.append(True))
    view._core.receive("mutate", {"id": "once"})
    callback = queue.pop()
    callback()
    callback()
    assert calls == [True]
    assert len(view.results) == 1


def test_fire_and_forget_calls_are_scheduled_without_result(queued_view):
    view, queue = queued_view
    calls = []
    view.bind_call("mutate", lambda: calls.append(True))
    view._core.receive("mutate", {})
    assert calls == []
    queue.pop()()
    assert calls == [True]
    assert view.results == []
    assert not view._pending_calls


def test_legacy_request_id_is_preserved(queued_view):
    view, queue = queued_view
    view.bind_call("answer", lambda: 42)
    view._core.receive("answer", {"__auroraview_call_id": "legacy"})
    queue.pop()()
    assert view.results == [{"id": "legacy", "ok": True, "result": 42}]


def test_telemetry_failure_does_not_swallow_result(queued_view):
    view, queue = queued_view

    def broken_telemetry(method, duration):
        raise RuntimeError("Telemetry unavailable")

    view._telemetry_on_ipc_call = broken_telemetry
    view.bind_call("answer", lambda: 42)
    view._core.receive("answer", {"id": "answer"})
    queue.pop()()
    assert view.results == [{"id": "answer", "ok": True, "result": 42}]
