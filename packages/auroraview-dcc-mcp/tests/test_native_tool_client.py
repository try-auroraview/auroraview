"""Source composition checks with fake ports; these are not native host acceptance."""

import importlib.util
import inspect
import threading
from concurrent.futures import Future
from pathlib import Path

import pytest
from auroraview_dcc_mcp import CleanupError, ContractError, ThreadError

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "native_tool_client.py"
SPEC = importlib.util.spec_from_file_location("native_tool_client_example", str(EXAMPLE))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
tools_from_client = MODULE.tools_from_client

INPUT = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}
OUTPUT = {"type": "object", "required": ["native"], "properties": {"native": {"type": "string"}}}
DECLARATION = {
    "name": "authorized.operation",
    "description": "Caller-authorized native operation; a fake port for this test",
    "input_schema": INPUT,
    "output_schema": OUTPUT,
    "read_only": False,
    "destructive": False,
}


class Client:
    def __init__(self):
        self.identity = {"parent_id": 1234, "version": "test", "context": "editor"}
        self.calls = []
        self.callbacks = {}
        self.removals = []
        self.closed = False
        self.result = {"native": "receipt", "state": {"frame": 9}}
        self.failure = None
        self.after_call = None

    def call(self, method, params, *, timeout):
        self.calls.append((method, params, timeout))
        if self.failure:
            raise self.failure
        if self.after_call:
            self.after_call()
        return self.result

    def on(self, event, callback):
        self.callbacks[event] = callback

        def remove():
            self.removals.append(event)
            self.callbacks.pop(event, None)

        return remove

    def close(self):
        self.closed = True


def compose(client, dispatch=None, **kwargs):
    return tools_from_client(
        client,
        [DECLARATION],
        expected_identity={"parent_id": 1234, "version": "test"},
        dispatch=dispatch or (lambda callback: callback()),
        timeout=2.0,
        max_timeout=3.0,
        **kwargs,
    )


def in_worker(callback):
    errors = []

    def run():
        try:
            callback()
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    return errors


def test_only_explicit_native_methods_are_exposed_and_receipt_is_unchanged():
    client = Client()
    with compose(client) as tools:
        assert [tool["name"] for tool in tools.list_tools()] == ["authorized.operation"]
        with pytest.raises(ContractError, match="Unknown tool"):
            tools.call("tools.list")
        assert client.calls == []
        assert tools.call("authorized.operation", {"value": 1}) == client.result
        assert client.calls == [("authorized.operation", {"value": 1}, 2.0)]
    assert not client.closed
    assert client.call("caller.still.owns.client", {}, timeout=1) == client.result


def test_business_routing_keys_are_preserved_without_overriding_native_method():
    client = Client()
    declaration = dict(DECLARATION, input_schema={"type": "object"})
    params = {"method": "other", "params": {"value": 1}, "timeout": 999, "client": "other"}
    with tools_from_client(
        client,
        [declaration],
        expected_identity=client.identity,
        dispatch=lambda _: None,
        timeout=2.0,
    ) as tools:
        assert tools.call("authorized.operation", params) == client.result
    assert client.calls == [("authorized.operation", params, 2.0)]


@pytest.mark.parametrize("params", [{}, {"value": True}, {"value": 1, "extra": 2}])
def test_invalid_input_has_zero_native_calls(params):
    client = Client()
    with compose(client) as tools:
        with pytest.raises(ContractError):
            tools.call("authorized.operation", params)
    assert client.calls == []


@pytest.mark.parametrize("observed", [None, {}, {"parent_id": True}, {"parent_id": 9999}])
def test_identity_refusal_before_composition_has_zero_native_calls(observed):
    client = Client()
    client.identity = observed
    with pytest.raises(ContractError):
        compose(client)
    assert client.calls == []


def test_identity_snapshot_is_detached_and_type_preserving():
    client = Client()
    expected = {"parent_id": 1234, "version": "test"}
    with tools_from_client(
        client, [DECLARATION], expected_identity=expected, dispatch=lambda _: None
    ) as tools:
        expected["parent_id"] = 8
        assert tools.call("authorized.operation", {"value": 1}) == client.result
        client.identity["parent_id"] = 1234.0
        with pytest.raises(ContractError, match="differs"):
            tools.call("authorized.operation", {"value": 2})
    assert len(client.calls) == 1


def test_boolean_identity_does_not_equal_integer_identity():
    client = Client()
    client.identity["parent_id"] = True
    with pytest.raises(ContractError, match="differs"):
        tools_from_client(
            client, [DECLARATION], expected_identity={"parent_id": 1}, dispatch=lambda _: None
        )
    assert client.calls == []


@pytest.mark.parametrize(
    "expected",
    [
        {},
        {1: "not-a-field-name"},
        {"version": float("nan")},
        {"version": object()},
        {"nested": {1: "non-json-key"}},
    ],
)
def test_invalid_pinned_identity_has_zero_native_calls(expected):
    client = Client()
    with pytest.raises(ContractError):
        tools_from_client(
            client, [DECLARATION], expected_identity=expected, dispatch=lambda _: None
        )
    assert client.calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"output_schema": None},
        {"output_schema": {"type": "not-a-schema-type"}},
        {"input_schema": {"type": "not-a-schema-type"}},
        {"readback": lambda: {}},
        {"handler": lambda: {}},
    ],
)
def test_invalid_native_declaration_has_zero_native_calls(change):
    client = Client()
    declaration = dict(DECLARATION, **change)
    with pytest.raises(ContractError):
        tools_from_client(
            client, [declaration], expected_identity=client.identity, dispatch=lambda _: None
        )
    assert client.calls == []


def test_missing_native_output_schema_has_zero_native_calls():
    client = Client()
    declaration = dict(DECLARATION)
    declaration.pop("output_schema")
    with pytest.raises(ContractError, match="requires its output_schema"):
        tools_from_client(
            client, [declaration], expected_identity=client.identity, dispatch=lambda _: None
        )
    assert client.calls == []


def test_native_output_schema_refuses_bad_receipt_without_extra_rpc():
    client = Client()
    client.result = {"native": 9}
    with compose(client) as tools:
        with pytest.raises(ContractError, match="result"):
            tools.call("authorized.operation", {"value": 1})
    assert len(client.calls) == 1


def test_identity_drift_after_call_is_honestly_refused_without_second_rpc():
    client = Client()
    with compose(client) as tools:
        client.after_call = lambda: client.identity.update(parent_id=2)
        with pytest.raises(ContractError, match="differs"):
            tools.call("authorized.operation", {"value": 1})
    assert len(client.calls) == 1  # local checks cannot undo an already executed native operation


def test_native_timeout_error_is_unchanged_and_does_not_invent_cancel():
    client = Client()
    client.failure = TimeoutError("native deadline")
    with compose(client) as tools:
        with pytest.raises(TimeoutError) as caught:
            tools.call("authorized.operation", {"value": 1})
    assert caught.value is client.failure
    assert [method for method, _, _ in client.calls] == ["authorized.operation"]


@pytest.mark.parametrize(
    "timeout,bound",
    [(0, 2), (-1, 2), (True, 2), (float("inf"), 2), (1, float("nan")), (3, 2), (10**1000, 2)],
    ids=["zero", "negative", "boolean", "infinite", "nan-bound", "over-bound", "overflow"],
)
def test_invalid_timeout_is_refused_before_native_calls(timeout, bound):
    client = Client()
    with pytest.raises(ContractError):
        tools_from_client(
            client,
            [DECLARATION],
            expected_identity=client.identity,
            dispatch=lambda _: None,
            timeout=timeout,
            max_timeout=bound,
        )
    assert client.calls == []


def test_worker_events_use_injected_dispatcher_and_close_revokes_queued_callbacks():
    client, queued, received = Client(), [], []
    tools = compose(client, queued.append)
    session = tools.borrow()
    session.subscribe("native.changed", received.append)
    payload = {"native": "event", "state": {"frame": 10}}
    assert in_worker(lambda: client.callbacks["native.changed"](payload)) == []
    assert received == []
    queued.pop(0)()
    assert received == [payload]
    assert in_worker(lambda: client.callbacks["native.changed"](payload)) == []
    session.close()
    queued.pop(0)()
    assert received == [payload]
    assert client.removals == ["native.changed"]
    assert not tools.closed and not client.closed
    tools.close()
    assert not client.closed


def test_event_identity_is_checked_on_owner_thread_after_dispatch():
    client, queued, received = Client(), [], []
    with compose(client, queued.append) as tools:
        session = tools.borrow()
        session.subscribe("native.changed", received.append)
        assert in_worker(lambda: client.callbacks["native.changed"]({"native": "event"})) == []
        client.identity["parent_id"] = 9999
        with pytest.raises(ContractError, match="differs"):
            queued.pop(0)()
    assert received == []


def test_wrong_thread_dispatcher_and_refused_dispatch_are_honest_errors():
    client, received = Client(), []
    with compose(client) as tools:
        tools.borrow().subscribe("native.changed", received.append)
        errors = in_worker(lambda: client.callbacks["native.changed"]({}))
        assert len(errors) == 1 and isinstance(errors[0], ThreadError)
    with compose(client, lambda _: False) as tools:
        tools.borrow().subscribe("native.changed", received.append)
        with pytest.raises(ContractError, match="did not accept"):
            client.callbacks["native.changed"]({})
    assert received == []


@pytest.mark.parametrize("started", [False, True])
def test_coroutine_dispatcher_is_refused_without_closing_started_work(started):
    client, pending, received = Client(), [], []

    class Awaitable:
        def __await__(self):
            yield

    async def deferred():
        await Awaitable()

    def dispatch(_):
        pending.append(deferred())
        if started:
            pending[-1].send(None)
        return pending[-1]

    try:
        with compose(client, dispatch) as tools:
            tools.borrow().subscribe("native.changed", received.append)
            with pytest.raises(ContractError, match="did not accept"):
                client.callbacks["native.changed"]({})
        expected = inspect.CORO_SUSPENDED if started else inspect.CORO_CLOSED
        assert inspect.getcoroutinestate(pending[0]) == expected
        assert received == []
    finally:
        for coroutine in pending:
            coroutine.close()  # the test owns started dispatcher work


@pytest.mark.parametrize("method", ["call", "on"])
@pytest.mark.parametrize("callable_object", [False, True])
def test_async_client_port_is_rejected_before_native_work(method, callable_object):
    client, calls = Client(), []

    async def asynchronous(*args, **kwargs):
        calls.append(True)

    class AsyncPort:
        __call__ = staticmethod(asynchronous)

    setattr(client, method, AsyncPort() if callable_object else asynchronous)
    with pytest.raises(ContractError, match="synchronous"):
        compose(client)
    assert calls == client.calls == []


def test_client_on_is_required_before_composition():
    client = Client()
    client.on = None
    with pytest.raises(ContractError, match="Client.on"):
        compose(client)
    assert client.calls == []


@pytest.mark.parametrize("future_result", [False, True])
def test_invalid_subscription_result_does_not_leak_created_coroutine_or_cancel_future(
    future_result,
):
    client, results = Client(), []

    async def deferred():
        raise AssertionError("Invalid subscription coroutine must not execute")

    def on(event, callback):
        results.append(Future() if future_result else deferred())
        return results[-1]

    client.on = on
    with compose(client) as tools:
        session = tools.borrow()
        with pytest.raises(ContractError, match="synchronously"):
            session.subscribe("native.changed", lambda _: None)
        assert session.call("authorized.operation", {"value": 1}) == client.result
    if future_result:
        assert not results[0].done() and not results[0].cancelled()
    else:
        assert inspect.getcoroutinestate(results[0]) == inspect.CORO_CLOSED


def test_unsubscribe_result_reaches_sdk_and_failed_removal_keeps_event_inactive():
    client, queued, received = Client(), [], []
    attempts = []

    def source(event, callback):
        client.callbacks[event] = callback

        def remove():
            attempts.append(event)
            return False if len(attempts) == 1 else None

        return remove

    client.on = source
    with compose(client, queued.append) as tools:
        session = tools.borrow()
        session.subscribe("native.changed", received.append)
        client.callbacks["native.changed"]({})
        with pytest.raises(CleanupError):
            session.close()
        queued.pop(0)()
        assert received == [] and session.closed
        session.close()
    assert attempts == ["native.changed", "native.changed"]
