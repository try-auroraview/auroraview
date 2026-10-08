"""Existing backend ownership without a native renderer, host or transport."""

import ast
import asyncio
import importlib.util
import inspect
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "python/auroraview/integration/backend.py"
SPEC = importlib.util.spec_from_file_location("backend_session_contract", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BackendSession = MODULE.BackendSession
BackendCleanupError = MODULE.BackendCleanupError


class Backend:
    def __init__(self):
        self.descriptors = [{"name": "unreal.scene.describe", "inputSchema": {"type": "object"}}]
        self.result = {"content": [{"type": "text", "text": "scene"}], "isError": False}
        self.call_tool = Mock(side_effect=lambda *_args: self.result)
        self.list_tools = Mock(side_effect=lambda: self.descriptors)
        self.stop = Mock(return_value=None)
        self.listeners = []
        self.removers = []

    def subscribe(self, event, handler):
        item = (event, handler)
        self.listeners.append(item)
        remove = Mock(return_value=None, side_effect=lambda: self.listeners.remove(item))
        self.removers.append(remove)
        return remove

    def publish(self, event, value):
        for name, handler in tuple(self.listeners):
            if name == event:
                handler(value)

    def session(self, own=False):
        kwargs = {
            "invoke_tool": self.call_tool,
            "list_tools": self.list_tools,
            "subscribe": self.subscribe,
        }
        return (
            BackendSession.own(stop=self.stop, **kwargs) if own else BackendSession.borrow(**kwargs)
        )


def worker_error(callback):
    errors = []

    def run():
        try:
            callback()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    return errors


def test_public_tool_namespace_results_and_descriptors_are_preserved():
    backend = Backend()
    session = backend.session()
    params = {"selection": ["Cube"], "limit": 3}
    assert session.call("unreal.scene.describe", params) is backend.result
    backend.call_tool.assert_called_once_with("unreal.scene.describe", params)
    assert backend.call_tool.call_args[0][1] is params
    assert session.tools() is backend.descriptors
    assert not session.owns_runtime
    assert session.close()
    backend.stop.assert_not_called()


def test_structured_errors_and_raised_transport_errors_are_not_rewritten():
    backend = Backend()
    session = backend.session()
    backend.result = {"isError": True, "content": [{"type": "text", "text": "not found"}]}
    assert session.call("unreal.scene.describe") is backend.result
    error = ValueError("transport refused")
    backend.call_tool.side_effect = error
    with pytest.raises(ValueError) as raised:
        session.call("unreal.scene.describe")
    assert raised.value is error
    session.close()


def test_two_views_borrow_one_backend_and_close_only_their_subscriptions():
    backend = Backend()
    first, second = backend.session(), backend.session()
    first_events, second_events = [], []
    first.on("scene.changed", first_events.append)
    second.on("scene.changed", second_events.append)
    assert first.close()
    backend.publish("scene.changed", {"selection": ["Sphere"]})
    assert first_events == []
    assert second_events == [{"selection": ["Sphere"]}]
    assert second.call("unreal.scene.describe") is backend.result
    assert second.close()
    assert not backend.listeners
    backend.stop.assert_not_called()


def test_connection_context_manager_disposes_once_and_keeps_other_connection_live():
    backend = Backend()
    session = backend.session()
    first, second = Mock(), Mock()
    other = session.on("scene.changed", second)
    with session.on("scene.changed", first) as connection:
        backend.publish("scene.changed", "before")
    assert connection.disposed
    assert not connection.active
    assert connection.dispose()
    backend.removers[1].assert_called_once()
    backend.publish("scene.changed", "after")
    assert first.call_count == 1
    assert second.call_count == 2
    assert other.active
    session.dispose()


def test_queued_notifications_are_invalid_after_dispose_even_when_unsubscribe_fails():
    backend = Backend()
    session = backend.session()
    handler = Mock()
    connection = session.on("scene.changed", handler)
    queued = backend.listeners[0][1]
    remove = backend.removers[0]
    remove.side_effect = [RuntimeError("unsubscribe failed"), None]
    with pytest.raises(RuntimeError, match="unsubscribe failed"):
        connection.dispose()
    assert not connection.active and not connection.disposed
    assert connection._handler is None
    assert queued("late") is None
    handler.assert_not_called()
    assert connection.dispose()
    assert connection.disposed
    assert remove.call_count == 2
    assert session.close()


def test_close_invalidates_all_callbacks_before_attempting_any_cleanup():
    backend = Backend()
    session = backend.session()
    first, second = Mock(), Mock()
    session.on("scene.changed", first)
    session.on("scene.changed", second)
    backend.removers[0].side_effect = lambda: backend.publish("scene.changed", "during cleanup")
    assert session.close()
    first.assert_not_called()
    second.assert_not_called()


def test_owned_close_tries_all_resources_retains_failures_and_retries_only_failures():
    backend = Backend()
    session = backend.session(own=True)
    first = session.on("scene.changed", Mock())
    second = session.on("scene.changed", Mock())
    backend.removers[0].side_effect = [ValueError("disconnect failed"), None]
    pending = Mock()
    pending.done.return_value = False
    pending.cancel.side_effect = [ValueError("cancel failed"), True]
    backend.result = pending
    assert session.call("unreal.scene.describe") is pending
    backend.stop.side_effect = [ValueError("stop failed"), None]
    with pytest.raises(BackendCleanupError) as raised:
        session.close()
    assert [name for name, _ in raised.value.errors] == ["disconnect", "cancel"]
    assert not first.active and not first.disposed
    assert second.disposed
    assert not session.closed
    backend.stop.assert_not_called()
    pending.done.return_value = True
    with pytest.raises(BackendCleanupError) as raised:
        session.close()
    assert [name for name, _ in raised.value.errors] == ["stop"]
    assert first.disposed and not session.closed
    assert session.close()
    assert session.closed and session.owns_runtime
    assert first.disposed
    assert backend.removers[0].call_count == 2
    backend.removers[1].assert_called_once()
    assert backend.stop.call_count == 2
    assert session.close()
    assert backend.stop.call_count == 2


def test_only_requests_started_by_this_session_are_cancelled():
    backend = Backend()
    first, second = backend.session(), backend.session()
    foreign, own, shared_backend_work = Future(), Future(), Future()
    backend.result = foreign
    second.call("unreal.scene.describe")
    backend.result = own
    first.call("unreal.scene.describe")
    assert first.close()
    assert own.cancelled()
    assert not foreign.cancelled()
    assert not shared_backend_work.cancelled()
    assert second.close()
    assert foreign.cancelled()
    backend.stop.assert_not_called()


def test_pending_cancellation_keeps_handle_until_existing_loop_completes():
    backend = Backend()
    session = backend.session()
    pending = Mock()
    pending.done.return_value = False
    pending.cancel.return_value = True
    backend.result = pending
    session.call("unreal.scene.describe")
    assert not session.close()
    assert not session.closed
    pending.done.return_value = True
    assert session.close()
    pending.cancel.assert_called_once()


def test_asyncio_task_cancellation_completes_on_existing_owner_loop():
    async def scenario():
        async def wait():
            await asyncio.Future()

        backend = Backend()
        session = backend.session()
        task = asyncio.create_task(wait())
        backend.result = task
        assert session.call("unreal.scene.describe") is task
        await asyncio.sleep(0)
        assert not session.close()
        await asyncio.sleep(0)
        assert task.cancelled()
        assert session.close()
        backend.stop.assert_not_called()

    asyncio.run(scenario())


def test_owned_runtime_stop_waits_for_cancellation_on_its_existing_loop():
    async def scenario():
        async def wait():
            await asyncio.Future()

        backend = Backend()
        session = backend.session(own=True)
        task = asyncio.create_task(wait())
        backend.result = task
        session.call("unreal.scene.describe")
        await asyncio.sleep(0)
        assert not session.close()
        backend.stop.assert_not_called()
        await asyncio.sleep(0)
        assert task.cancelled()
        assert session.close()
        backend.stop.assert_called_once()

    asyncio.run(scenario())


def test_refused_cancellation_remains_retryable():
    backend = Backend()
    session = backend.session()
    pending = Mock()
    pending.done.return_value = False
    pending.cancel.return_value = False
    backend.result = pending
    session.call("unreal.scene.describe")
    with pytest.raises(BackendCleanupError) as raised:
        session.close()
    assert raised.value.errors[0][0] == "cancel"
    pending.done.return_value = True
    assert session.close()


def test_completed_futures_are_pruned_without_touching_their_result():
    backend = Backend()
    session = backend.session()
    previous, current = Future(), Future()
    previous.set_exception(ValueError("public result remains caller-owned"))
    backend.result = previous
    assert session.call("unreal.scene.describe") is previous
    backend.result = current
    session.call("unreal.scene.describe")
    assert session._pending == [current]
    assert session.close()
    assert previous.exception().args == ("public result remains caller-owned",)


def test_async_transport_result_is_unchanged_and_uses_callers_existing_loop():
    async def invoke(name, params):
        return {"name": name, "params": params}

    session = BackendSession.borrow(invoke_tool=invoke, list_tools=lambda: [])
    before = tuple(threading.enumerate())
    result = session.call("scene.describe", {"limit": 1})
    assert tuple(threading.enumerate()) == before
    assert asyncio.run(result) == {"name": "scene.describe", "params": {"limit": 1}}
    assert session.close()


def test_reentrant_event_close_prevents_late_and_new_calls():
    backend = Backend()
    session = backend.session(own=True)
    connection = session.on("scene.changed", lambda _value: session.close())
    queued = backend.listeners[0][1]
    backend.publish("scene.changed", "close")
    assert session.closed and connection.disposed
    assert queued("late") is None
    with pytest.raises(RuntimeError, match="closing or closed"):
        session.call("scene.describe")
    with pytest.raises(RuntimeError, match="closing or closed"):
        session.on("scene.changed", Mock())
    backend.stop.assert_called_once()


def test_reentrant_unsubscribe_and_stop_do_not_repeat_cleanup():
    backend = Backend()
    session = backend.session(own=True)
    connection = session.on("scene.changed", Mock())
    backend.removers[0].side_effect = lambda: (connection.dispose(), session.close())
    backend.stop.side_effect = session.close
    assert session.close()
    backend.removers[0].assert_called_once()
    backend.stop.assert_called_once()


def test_immediate_subscription_callback_can_close_before_registration_returns():
    remove, stop = Mock(return_value=None), Mock(return_value=None)
    session = None

    def subscribe(_event, handler):
        handler("initial")
        return remove

    session = BackendSession.own(
        invoke_tool=Mock(), list_tools=lambda: [], subscribe=subscribe, stop=stop
    )
    connection = session.on("scene.changed", lambda _value: session.close())
    assert connection.disposed and session.closed
    remove.assert_called_once()
    stop.assert_called_once()


def test_future_returned_after_reentrant_close_is_still_cancelled():
    future = Future()
    session = None

    def invoke(_name, _params):
        session.close()
        return future

    session = BackendSession.borrow(invoke_tool=invoke, list_tools=lambda: [])
    assert session.call("scene.describe") is future
    assert future.cancelled() and session.closed


@pytest.mark.parametrize("operation", ["call", "tools"])
def test_owned_stop_waits_for_reentrant_operation_to_return_its_future(operation):
    future = Future()
    trace = []
    session = None

    def invoke(*_args):
        trace.append("invoke")
        assert not session.close()
        assert not session.closed
        assert trace == ["invoke"]
        trace.append("return future")
        return future

    def stop():
        assert future.cancelled()
        trace.append("stop")

    session = BackendSession.own(invoke_tool=invoke, list_tools=invoke, stop=stop)
    result = session.call("scene.describe") if operation == "call" else session.tools()
    assert result is future and future.cancelled() and session.closed
    assert trace == ["invoke", "return future", "stop"]


def test_reentrant_close_during_failed_operation_preserves_error_and_retry_ownership():
    error = ValueError("existing backend error")
    stop = Mock(return_value=None)
    session = None

    def invoke(*_args):
        assert not session.close()
        raise error

    session = BackendSession.own(invoke_tool=invoke, list_tools=lambda: [], stop=stop)
    with pytest.raises(ValueError) as raised:
        session.call("scene.describe")
    assert raised.value is error
    stop.assert_not_called()
    assert not session.closed
    assert session.close()
    stop.assert_called_once()


def test_worker_calls_and_notifications_fail_before_touching_backend_or_consumer():
    backend = Backend()
    session = backend.session()
    handler = Mock()
    connection = session.on("scene.changed", handler)
    queued = backend.listeners[0][1]
    for callback in (
        lambda: session.call("scene.describe"),
        session.tools,
        lambda: session.on("scene.changed", Mock()),
        session.close,
        connection.dispose,
        lambda: queued("worker"),
    ):
        errors = worker_error(callback)
        assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
    backend.call_tool.assert_not_called()
    backend.list_tools.assert_not_called()
    backend.removers[0].assert_not_called()
    handler.assert_not_called()
    session.close()
    assert not worker_error(lambda: queued("expired worker"))


def test_missing_or_nonremovable_subscription_fails_without_live_consumer_callback():
    session = BackendSession.borrow(invoke_tool=Mock(), list_tools=lambda: [])
    with pytest.raises(RuntimeError, match="removable subscribe"):
        session.on("scene.changed", Mock())
    captured = []
    handler = Mock()
    session = BackendSession.borrow(
        invoke_tool=Mock(),
        list_tools=lambda: [],
        subscribe=lambda _name, callback: captured.append(callback),
    )
    with pytest.raises(TypeError, match="dispose callable"):
        session.on("scene.changed", handler)
    assert captured[0]("late") is None
    handler.assert_not_called()
    assert session.close()


def test_invalid_public_callables_and_async_lifecycle_are_rejected():
    with pytest.raises(TypeError, match="invoke_tool"):
        BackendSession.borrow(invoke_tool=object(), list_tools=lambda: [])
    with pytest.raises(TypeError, match="stop"):
        BackendSession.own(invoke_tool=Mock(), list_tools=lambda: [], stop=None)

    async def async_stop():
        pass

    with pytest.raises(TypeError, match="synchronous"):
        BackendSession.own(invoke_tool=Mock(), list_tools=lambda: [], stop=async_stop)


def test_coroutine_returned_by_sync_subscribe_is_closed_and_notification_invalidated():
    async def register():
        raise AssertionError("Registration must not be scheduled")

    registration = register()
    captured = []
    handler = Mock()

    def subscribe(_event, callback):
        captured.append(callback)
        return registration

    session = BackendSession.borrow(invoke_tool=Mock(), list_tools=lambda: [], subscribe=subscribe)
    with pytest.raises(TypeError, match="dispose callable"):
        session.on("scene.changed", handler)
    assert inspect.getcoroutinestate(registration) == inspect.CORO_CLOSED
    assert captured[0]("late") is None
    handler.assert_not_called()
    assert session.close()


def test_async_cleanup_returned_by_sync_callable_is_rejected_and_retained_for_retry():
    async def cleanup():
        pass

    backend = Backend()
    session = backend.session(own=True)
    connection = session.on("scene.changed", Mock())
    backend.removers[0].side_effect = cleanup
    backend.stop.side_effect = cleanup
    with pytest.raises(BackendCleanupError) as raised:
        session.close()
    assert [name for name, _ in raised.value.errors] == ["disconnect"]
    assert all(isinstance(error, TypeError) for _, error in raised.value.errors)
    assert not connection.active and not connection.disposed and not session.closed
    backend.stop.assert_not_called()
    backend.removers[0].side_effect = None
    with pytest.raises(BackendCleanupError) as raised:
        session.close()
    assert [name for name, _ in raised.value.errors] == ["stop"]
    backend.stop.side_effect = None
    assert session.close()


def test_python37_syntax_and_no_runtime_dcc_dependencies():
    source = SOURCE.read_text(encoding="utf-8")
    tree = (
        ast.parse(source, feature_version=(3, 7))
        if sys.version_info >= (3, 8)
        else ast.parse(source)
    )
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    assert set(imports) == {"__future__", "inspect", "threading", "typing"}
