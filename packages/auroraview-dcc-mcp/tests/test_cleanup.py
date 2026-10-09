import gc
import inspect
import weakref
from concurrent.futures import Future

import pytest
from auroraview_dcc_mcp import CleanupError, ContractError, Tool, ToolSet


def make_owner(subscribe):
    return ToolSet(
        "cleanup", [Tool("run", "Run", {"type": "object"}, lambda: True)], subscribe=subscribe
    )


class FutureLike:
    def __init__(self):
        self.cancel_calls = 0
        self.done_calls = 0

    def cancel(self):
        self.cancel_calls += 1
        return False

    def done(self):
        self.done_calls += 1
        return False


class Awaitable:
    def __await__(self):
        yield


@pytest.mark.parametrize(
    "result_kind",
    ["false", "future", "future-like", "coroutine", "suspended-coroutine", "awaitable"],
)
def test_incomplete_close_retains_cleanup_revokes_delivery_and_preserves_other_lease(result_kind):
    callbacks, attempts, results, received = {}, [], [], []

    async def deferred_cleanup():
        raise AssertionError("An unstarted cleanup coroutine must not run")

    async def suspended_cleanup():
        await Awaitable()
        raise AssertionError("Started host work must not be resumed")

    def suspend_cleanup():
        result = suspended_cleanup()
        result.send(None)
        return result

    def subscribe(event, callback):
        callbacks[event] = callback

        def unsubscribe():
            attempts.append(event)
            if event == "first" and attempts.count(event) == 1:
                result = {
                    "false": lambda: False,
                    "future": Future,
                    "future-like": FutureLike,
                    "coroutine": deferred_cleanup,
                    "suspended-coroutine": suspend_cleanup,
                    "awaitable": Awaitable,
                }[result_kind]()
                results.append(result)
                return result
            callbacks.pop(event)

        return unsubscribe

    owner = make_owner(subscribe)
    first, second = owner.borrow(), owner.borrow()
    first.subscribe("first", lambda value: received.append(("first", value)))
    second.subscribe("second", lambda value: received.append(("second", value)))
    stale = callbacks["first"]
    try:
        with pytest.raises(CleanupError, match="synchronously") as failure:
            first.close()
        assert len(failure.value.errors) == 1
        assert isinstance(failure.value.errors[0], ContractError)
        assert first.closed and not owner.closed
        stale(1)
        callbacks["second"](2)
        assert received == [("second", 2)]
        assert second.call("run") is True
        assert owner.call("run") is True
        result = results[0]
        if isinstance(result, Future):
            assert not result.done() and not result.cancelled()
        elif isinstance(result, FutureLike):
            assert result.cancel_calls == result.done_calls == 0
        elif inspect.iscoroutine(result):
            expected = (
                inspect.CORO_SUSPENDED
                if result_kind == "suspended-coroutine"
                else inspect.CORO_CLOSED
            )
            assert inspect.getcoroutinestate(result) == expected
        first.close()
        first.close()
        assert attempts == ["first", "first"]
        assert list(callbacks) == ["second"]
        owner.close()
        assert callbacks == {}
    finally:
        # Keep the red-test run free of leaked unstarted coroutines too.
        for result in results:
            if inspect.iscoroutine(result):
                result.close()
        owner.close()


def test_unsubscribe_handle_failure_is_inactive_but_retryable_without_closing_lease():
    callbacks, attempts, received = [], [], []

    def subscribe(event, callback):
        callbacks.append(callback)

        def unsubscribe():
            attempts.append(True)
            if len(attempts) == 1:
                return False
            callbacks.remove(callback)
            return True

        return unsubscribe

    with make_owner(subscribe) as owner:
        session = owner.borrow()
        unsubscribe = session.subscribe("changed", lambda: received.append(True))
        stale = callbacks[0]
        with pytest.raises(ContractError, match="synchronously"):
            unsubscribe()
        stale()
        assert received == []
        assert not session.closed and session.call("run") is True
        unsubscribe()
        unsubscribe()
        assert attempts == [True, True] and callbacks == []


def test_failed_close_keeps_lease_owned_until_owner_retries_cleanup():
    callbacks, attempts = [], []

    def subscribe(event, callback):
        callbacks.append(callback)

        def unsubscribe():
            attempts.append(True)
            if len(attempts) == 1:
                return False
            callbacks.remove(callback)

        return unsubscribe

    owner = make_owner(subscribe)
    session = owner.borrow()
    session.subscribe("changed", lambda: None)
    reference = weakref.ref(session)
    with pytest.raises(CleanupError):
        session.close()
    del session
    gc.collect()
    assert reference() is not None
    owner.close()
    gc.collect()
    assert reference() is None
    assert attempts == [True, True] and callbacks == []


@pytest.mark.parametrize("callable_object", [False, True])
def test_async_host_subscribe_function_is_rejected_before_acquisition(callable_object):
    calls = []

    async def subscribe(event, callback):
        calls.append(True)
        return lambda: None

    class AsyncSource:
        __call__ = staticmethod(subscribe)

    with pytest.raises(ContractError, match="synchronous"):
        make_owner(AsyncSource() if callable_object else subscribe)
    assert calls == []


def test_host_subscribe_coroutine_result_is_closed_without_delivery_or_owner_shutdown():
    coroutines, received = [], []

    async def deferred_subscribe():
        raise AssertionError("An unstarted subscription coroutine must not run")

    def subscribe(event, callback):
        result = deferred_subscribe()
        coroutines.append(result)
        return result

    with make_owner(subscribe) as owner:
        session = owner.borrow()
        try:
            with pytest.raises(ContractError, match="synchronous"):
                session.subscribe("changed", lambda: received.append(True))
            assert inspect.getcoroutinestate(coroutines[0]) == inspect.CORO_CLOSED
            assert received == []
            assert owner.borrow().call("run") is True
            session.close()
            assert not owner.closed
        finally:
            for result in coroutines:
                result.close()


@pytest.mark.parametrize("close_owner", [False, True])
def test_close_during_acquisition_keeps_false_cleanup_for_retry(close_owner):
    callbacks, attempts, received = [], [], []

    def subscribe(event, callback):
        callbacks.append(callback)
        (owner if close_owner else session).close()

        def unsubscribe():
            attempts.append(True)
            if len(attempts) == 1:
                return False
            callbacks.remove(callback)

        return unsubscribe

    owner = make_owner(subscribe)
    session = owner.borrow()
    with pytest.raises(CleanupError, match="synchronously"):
        session.subscribe("changed", lambda: received.append(True))
    assert session.closed and len(callbacks) == 1
    callbacks[0]()
    assert received == []
    owner.close()
    assert attempts == [True, True] and callbacks == []


@pytest.mark.parametrize("close_owner", [False, True])
@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize("failure", [None, "false", "raise"])
def test_unsubscribe_reentrant_close_runs_once_and_releases_only_after_cleanup(
    close_owner, direct, failure
):
    callbacks, attempts, received = [], [], []
    removing = [False]

    def subscribe(event, callback):
        callbacks.append(callback)

        def unsubscribe():
            assert not removing[0], "Reentrant close attempted duplicate native removal"
            removing[0] = True
            try:
                attempts.append(True)
                target_ref().close()
                stale()
                assert received == []
                if len(attempts) == 1:
                    if failure == "false":
                        return False
                    if failure == "raise":
                        raise RuntimeError("Native removal failed")
                callbacks.remove(callback)
            finally:
                removing[0] = False

        return unsubscribe

    owner = make_owner(subscribe)
    session = owner.borrow()
    target_ref = weakref.ref(owner if close_owner else session)
    unsubscribe = session.subscribe("changed", lambda: received.append(True))
    stale = callbacks[0]
    reference = weakref.ref(session)
    action = unsubscribe if direct else session.close
    if failure is None:
        action()
    else:
        error_type = (
            (ContractError if failure == "false" else RuntimeError) if direct else CleanupError
        )
        message = "synchronously" if failure == "false" else "Native removal failed"
        with pytest.raises(error_type, match=message):
            action()
    assert session.closed and owner.closed == close_owner
    assert attempts == [True]
    assert len(callbacks) == (0 if failure is None else 1)
    if not close_owner:
        assert owner.call("run") is True
    del action, unsubscribe, session
    gc.collect()
    if failure is None:
        # Successful direct unsubscribe must release a lease closed reentrantly.
        assert reference() is None
    else:
        assert reference() is not None
    owner.close()
    gc.collect()
    assert reference() is None
    assert attempts == [True] * (1 if failure is None else 2)
    assert callbacks == []
