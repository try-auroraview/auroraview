"""Explicit host event queues, without Blender or a native WebView."""

from __future__ import annotations

import threading

import pytest

from auroraview.core.events import WindowEvent
from auroraview.core.mixins.events import WebViewEventMixin


class NativeCore:
    def __init__(self):
        self.owner = threading.get_ident()
        self.handlers = {}

    def on(self, name, callback):
        assert threading.get_ident() == self.owner
        self.handlers[name] = callback


class HostView(WebViewEventMixin):
    def __init__(self, *, dcc_mode=True):
        self._core = NativeCore()
        self._core_threads = {id(self._core): self._core.owner}
        self._dcc_mode = dcc_mode
        self._event_handlers = {}
        self._event_handlers_lock = threading.Lock()
        self._close_requested = False

    def _get_active_core(self):
        return self._core

    def _is_core_owner(self, core):
        return core.owner == threading.get_ident()

    def _check_open(self):
        if self._close_requested:
            raise RuntimeError("WebView is closed")

    def close(self):
        self._cancel_event_callbacks()
        self._close_requested = True


def in_worker(callback):
    errors = []

    def run():
        try:
            callback()
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive(), "Host event delivery must not block the native owner"
    return errors


@pytest.fixture
def queued_view(monkeypatch):
    def forbidden_legacy(*_args, **_kwargs):
        raise AssertionError("Explicit host events must never use the legacy dispatcher")

    monkeypatch.setattr(
        "auroraview.utils.thread_dispatcher.wrap_callback_for_dcc", forbidden_legacy
    )
    view = HostView()
    queue = []
    view.set_event_dispatcher(queue.append)
    return view, queue


def test_worker_event_queues_and_executes_once_on_host_thread(queued_view):
    view, queue = queued_view
    called = []
    view.on("selection", lambda data: called.append((data, threading.get_ident())))
    assert in_worker(lambda: view._core.handlers["selection"]({"value": 1})) == []
    assert called == []
    assert len(queue) == 1
    queue[0]()
    queue[0]()
    assert called == [({"value": 1}, threading.get_ident())]


def test_existing_native_and_lifecycle_signal_callbacks_switch_to_host_queue(queued_view):
    view, queue = queued_view
    view.set_event_dispatcher(None)
    called = []
    view.on_loaded(lambda data: called.append(data))
    view.set_event_dispatcher(queue.append)
    assert in_worker(lambda: view._core.handlers["loaded"]({"native": True})) == []
    assert in_worker(view.signals.page_loaded.emit) == []
    assert called == []
    for callback in queue:
        callback()
    assert called == [{"native": True}, {}]


@pytest.mark.parametrize("cancel", ["close", "disconnect", "replace", "disable"])
def test_pending_host_delivery_is_invalidated(queued_view, cancel):
    view, queue = queued_view
    called = []
    connection = view.on("selection", called.append)
    assert in_worker(lambda: view._core.handlers["selection"]({"old": True})) == []
    if cancel == "close":
        view.close()
    elif cancel == "disconnect":
        assert view.disconnect("selection", connection)
    elif cancel == "replace":
        view.set_event_dispatcher(lambda callback: None)
    else:
        view.set_event_dispatcher(None)
    queue[0]()
    assert called == []


@pytest.mark.parametrize("enqueue_first", [False, True])
def test_rejected_or_expired_host_queue_never_delivers(queued_view, enqueue_first):
    view, queue = queued_view
    called = []

    def expired(callback):
        if enqueue_first:
            queue.append(callback)
        raise RuntimeError("Host dispatcher belongs to an expired session")

    view.set_event_dispatcher(expired)
    view.on("selection", called.append)
    errors = in_worker(lambda: view._core.handlers["selection"]({"stale": True}))
    assert len(errors) == 1
    assert "expired session" in str(errors[0])
    for callback in queue:
        callback()
    assert called == []


def test_wrong_thread_queue_execution_refuses_host_mutation(queued_view):
    view, queue = queued_view
    called = []
    view.on("selection", called.append)
    view._core.handlers["selection"]({"value": 1})
    errors = in_worker(queue[0])
    assert len(errors) == 1
    assert "owner thread" in str(errors[0])
    queue[0]()  # A refused delivery cannot later mutate the host either.
    assert called == []


def test_dispatcher_configuration_requires_original_owner_thread(queued_view):
    view, queue = queued_view
    errors = in_worker(lambda: view.set_event_dispatcher(None))
    assert len(errors) == 1
    assert "creating thread" in str(errors[0])
    called = []
    view.on("selection", called.append)
    view._core.handlers["selection"]({"value": 1})
    queue[0]()
    assert called == [{"value": 1}]
    fresh = HostView()
    errors = in_worker(lambda: fresh.set_event_dispatcher(queue.append))
    assert len(errors) == 1
    assert "creating thread" in str(errors[0])


@pytest.mark.parametrize("event_name", ["closing", WindowEvent.CLOSING])
def test_host_dispatch_refuses_veto_registration_transactionally(queued_view, event_name):
    view, _queue = queued_view
    with pytest.raises(RuntimeError, match="closing veto"):
        view.on(event_name, lambda _data: False)
    assert "closing" not in view._event_handlers
    assert "closing" not in view._core.handlers
    assert getattr(view, "_event_connections", {}) == {}
    with pytest.raises(RuntimeError, match="closing veto"):
        view.on_closing(lambda _data: False)


def test_existing_veto_refuses_dispatcher_then_disconnect_allows_it():
    view = HostView(dcc_mode=False)
    connection = view.on("closing", lambda _data: False)
    with pytest.raises(RuntimeError, match="Remove synchronous closing"):
        view.set_event_dispatcher(lambda callback: None)
    assert getattr(view, "_event_dispatcher", None) is None
    assert view._core.handlers["closing"]({}) is False
    assert view.disconnect("closing", connection)
    view.set_event_dispatcher(lambda callback: None)


def test_absent_host_dispatcher_retains_legacy_route_and_disable_invalidates_queue(monkeypatch):
    legacy_queue = []
    monkeypatch.setattr(
        "auroraview.utils.thread_dispatcher.wrap_callback_for_dcc",
        lambda callback: lambda: legacy_queue.append(callback),
    )
    view = HostView()
    called = []
    view.on("selection", called.append)
    assert in_worker(lambda: view._core.handlers["selection"]({"legacy": True})) == []
    host_queue = []
    view.set_event_dispatcher(host_queue.append)
    legacy_queue[0]()
    assert called == []
    view.set_event_dispatcher(None)
    assert in_worker(lambda: view._core.handlers["selection"]({"restored": True})) == []
    legacy_queue[1]()
    assert called == [{"restored": True}]


def test_invalid_dispatcher_does_not_replace_configured_queue(queued_view):
    view, queue = queued_view
    with pytest.raises(TypeError, match="callable"):
        view.set_event_dispatcher(object())
    called = []
    view.on("selection", called.append)
    view._core.handlers["selection"]({"value": 1})
    queue[0]()
    assert called == [{"value": 1}]
