# Copyright (c) 2026 Long Hao
# Licensed under the MIT License
"""Explicit ownership of an existing backend's public tools and subscriptions.

Construct and use a session on its backend owner thread. This module creates no
server, listener, thread, event loop, dispatcher or event bus. An adapter must
deliver notifications on that same thread using its existing host dispatcher.

``invoke_tool(name, params)`` and ``list_tools()`` preserve their public results
and exceptions, including structured MCP errors and awaitables. A returned
Future must belong to that individual request: the session may cancel it.
Bare coroutine scheduling belongs to the caller's existing event loop; this
module neither schedules nor cancels unscheduled coroutines.

``subscribe(event, handler)`` must synchronously return a removable subscription's
dispose callable. ``stop`` must synchronously stop only an explicitly owned
runtime. Asynchronous lifecycle APIs need a public synchronous host adapter.

DccServerBase 0.20.41 lacks public tool invocation and removable subscriptions.
It cannot directly supply this contract. Use a public host adapter or MCP client;
do not reach into its private server or duplicate its event bus.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, List, Optional, Tuple

__all__ = ["BackendSession", "Connection", "BackendCleanupError"]


class BackendCleanupError(RuntimeError):
    """Cleanup failures whose resources remain owned for a later close retry."""

    def __init__(self, errors: List[Tuple[str, Exception]]) -> None:
        self.errors = tuple(errors)
        super().__init__("Backend cleanup failed: " + ", ".join(name for name, _ in errors))


def _callable(value: Any, name: str) -> None:
    if not callable(value):
        raise TypeError("{} must be a public callable".format(name))


def _cleanup(callback: Callable[[], Any], name: str) -> None:
    result = callback()
    if inspect.isawaitable(result) or (
        callable(getattr(result, "cancel", None)) and callable(getattr(result, "done", None))
    ):
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError("{} must complete synchronously through its public adapter".format(name))


class Connection:
    """One subscription, deactivated before its retryable public unsubscribe.

    A disposed connection is never reactivated. Already queued notifications
    therefore cannot cross its lifetime or retain the consumer's handler.
    """

    def __init__(self, session: BackendSession, handler: Callable[..., Any]) -> None:
        self._session = session  # type: Optional[BackendSession]
        self._thread = session._thread
        self._handler = handler  # type: Optional[Callable[..., Any]]
        self._remove = None  # type: Optional[Callable[[], Any]]
        self._active = True
        self._subscribing = True
        self._disposing = False

    def _require_owner(self) -> None:
        if threading.current_thread() is not self._thread:
            raise RuntimeError("Backend connections require their constructor owner thread")

    @property
    def active(self) -> bool:
        return self._active and self._session is not None and not self._session._closing

    @property
    def disposed(self) -> bool:
        return not self._active and not self._subscribing and self._remove is None

    def _deliver(self, *args: Any, **kwargs: Any) -> Any:
        if not self.active:
            return None
        self._require_owner()
        return self._handler(*args, **kwargs)

    def _deactivate(self) -> None:
        self._active = False
        self._handler = None

    def dispose(self) -> bool:
        """Disconnect once; a failed unsubscribe remains inactive and retryable."""
        self._require_owner()
        self._deactivate()
        if self._subscribing or self._disposing:
            return False
        if self._remove is not None:
            self._disposing = True
            try:
                _cleanup(self._remove, "Subscription disposal")
            finally:
                self._disposing = False
            self._remove = None
        if self._session is not None:
            self._session._connections.remove(self)
            self._session = None
        return True

    def __enter__(self) -> Connection:
        self._require_owner()
        if not self.active:
            raise RuntimeError("Backend connection is inactive")
        return self

    def __exit__(self, *_args: Any) -> None:
        self.dispose()


class BackendSession:
    """Borrow public backend operations or explicitly own their runtime stop.

    Closing invalidates notifications immediately and attempts every owned
    cleanup. Failures raise BackendCleanupError and remain retryable. False
    means a cancellation or reentrant subscription is still completing; call
    close again on the owner thread after the existing loop has advanced.
    """

    def __init__(
        self,
        *,
        invoke_tool: Callable[[str, Any], Any],
        list_tools: Callable[[], Any],
        subscribe: Optional[Callable[[str, Callable[..., Any]], Callable[[], Any]]] = None,
        stop: Optional[Callable[[], Any]] = None,
    ) -> None:
        _callable(invoke_tool, "invoke_tool")
        _callable(list_tools, "list_tools")
        if subscribe is not None:
            _callable(subscribe, "subscribe")
            if inspect.iscoroutinefunction(subscribe):
                raise TypeError("subscribe must synchronously return a dispose callable")
        if stop is not None:
            _callable(stop, "stop")
            if inspect.iscoroutinefunction(stop):
                raise TypeError("stop requires a synchronous public lifecycle adapter")
        self._thread = threading.current_thread()
        self._invoke_tool = invoke_tool
        self._list_tools = list_tools
        self._subscribe = subscribe
        self._stop = stop
        self._owns_runtime = stop is not None
        self._connections = []  # type: List[Connection]
        self._pending = []  # type: List[Any]
        self._closing = False
        self._cleaning = False

    @classmethod
    def borrow(
        cls,
        *,
        invoke_tool: Callable[[str, Any], Any],
        list_tools: Callable[[], Any],
        subscribe: Optional[Callable[[str, Callable[..., Any]], Callable[[], Any]]] = None,
    ) -> BackendSession:
        """Borrow an existing public client/adapter without stopping its runtime."""
        return cls(invoke_tool=invoke_tool, list_tools=list_tools, subscribe=subscribe)

    @classmethod
    def own(
        cls,
        *,
        invoke_tool: Callable[[str, Any], Any],
        list_tools: Callable[[], Any],
        stop: Callable[[], Any],
        subscribe: Optional[Callable[[str, Callable[..., Any]], Callable[[], Any]]] = None,
    ) -> BackendSession:
        """Own only the runtime identified by the explicitly supplied stop callable."""
        _callable(stop, "stop")
        return cls(invoke_tool=invoke_tool, list_tools=list_tools, subscribe=subscribe, stop=stop)

    def _require_owner(self) -> None:
        if threading.current_thread() is not self._thread:
            raise RuntimeError("Backend sessions require their constructor owner thread")

    def _require_active(self) -> None:
        self._require_owner()
        if self._closing:
            raise RuntimeError("Backend session is closing or closed")

    @property
    def owns_runtime(self) -> bool:
        return self._owns_runtime

    @property
    def closed(self) -> bool:
        return self._closing and not self._connections and not self._pending and self._stop is None

    def _track(self, result: Any) -> Any:
        if callable(getattr(result, "cancel", None)) and callable(getattr(result, "done", None)):
            remaining = []
            for pending in self._pending:
                try:
                    if pending.done():
                        continue
                except Exception:
                    pass  # Keep uncertain ownership until explicit cleanup can report it.
                remaining.append(pending)
            self._pending = remaining
            if not any(pending is result for pending in self._pending):
                self._pending.append(result)
            if self._closing:
                self.close()
        return result

    def call(self, name: str, params: Any = None) -> Any:
        """Invoke the unchanged tool namespace and preserve its result/exception."""
        self._require_active()
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name must be a nonempty string")
        return self._track(self._invoke_tool(name, params))

    def tools(self) -> Any:
        """Return the public backend's real descriptors, without projection."""
        self._require_active()
        return self._track(self._list_tools())

    def on(self, event: str, handler: Callable[..., Any]) -> Connection:
        """Subscribe through the existing backend; removable subscriptions are required."""
        self._require_active()
        if not isinstance(event, str) or not event:
            raise ValueError("Event name must be a nonempty string")
        _callable(handler, "handler")
        if self._subscribe is None:
            raise RuntimeError("Backend has no public removable subscribe interface")
        connection = Connection(self, handler)
        self._connections.append(connection)
        try:
            remove = self._subscribe(event, connection._deliver)
            if not callable(remove) or inspect.iscoroutinefunction(remove):
                if inspect.iscoroutine(remove):
                    remove.close()
                raise TypeError("subscribe must return a synchronous dispose callable")
        except BaseException:
            connection._subscribing = False
            connection.dispose()
            raise
        connection._remove = remove
        connection._subscribing = False
        if not connection.active:
            connection.dispose()
            if self._closing:
                self.close()
        return connection

    def close(self) -> bool:
        """Try all owned cleanup, preserving failures for a later retry."""
        self._require_owner()
        self._closing = True
        if self._cleaning:
            return False
        self._cleaning = True
        errors = []  # type: List[Tuple[str, Exception]]
        try:
            for connection in tuple(self._connections):
                try:
                    connection.dispose()
                except Exception as exc:
                    errors.append(("disconnect", exc))
            remaining = []
            for pending in self._pending:
                try:
                    if not pending.done():
                        accepted = pending.cancel()
                        if not accepted and not pending.done():
                            raise RuntimeError("Pending backend call refused cancellation")
                    if not pending.done():
                        remaining.append(pending)
                except Exception as exc:
                    remaining.append(pending)
                    errors.append(("cancel", exc))
            self._pending = remaining
            busy = any(item._subscribing or item._disposing for item in self._connections)
            if self._stop is not None and not busy:
                try:
                    _cleanup(self._stop, "Runtime stop")
                except Exception as exc:
                    errors.append(("stop", exc))
                else:
                    self._stop = None
        finally:
            self._cleaning = False
        if errors:
            raise BackendCleanupError(errors)
        return self.closed

    dispose = close

    def __enter__(self) -> BackendSession:
        self._require_active()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
