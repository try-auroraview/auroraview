# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""Qt-inspired Signal-Slot System for AuroraView.

This module provides a type-safe signal-slot pattern similar to Qt's signals and slots,
with support for:
- Multiple handlers per signal (multi-receiver)
- Automatic cleanup via ConnectionGuard
- One-time connections (connect_once)
- Thread-safe operations
- Backward compatibility with @webview.on() decorator

Example:
    >>> from auroraview.core.signals import Signal, SignalRegistry
    >>>
    >>> # Create a signal
    >>> config_changed = Signal()
    >>>
    >>> # Connect handler
    >>> conn_id = config_changed.connect(lambda data: print(f"Config: {data}"))
    >>>
    >>> # Emit signal
    >>> config_changed.emit({"key": "value"})
    >>>
    >>> # Disconnect
    >>> config_changed.disconnect(conn_id)
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

# Type variable for signal payload
T = TypeVar("T")

# Handler type
Handler = Callable[[Any], Any]


@dataclass(frozen=True)
class ConnectionId:
    """Unique identifier for a signal connection.

    This ID can be used to disconnect a specific handler from a signal.
    """

    _id: str

    def __str__(self) -> str:
        return self._id

    def __hash__(self) -> int:
        return hash(self._id)


def _generate_connection_id() -> ConnectionId:
    """Generate a unique connection ID."""
    return ConnectionId(str(uuid.uuid4()))


class Signal(Generic[T]):
    """A Qt-inspired signal that can have multiple connected handlers.

    Signals emit values to all connected handlers when emit() is called.
    Handlers can be connected with connect() and disconnected with disconnect().

    Example:
        >>> signal = Signal()
        >>>
        >>> def handler(value):
        ...     print(f"Received: {value}")
        >>>
        >>> conn = signal.connect(handler)
        >>> signal.emit("Hello")
        Received: Hello
        >>>
        >>> signal.disconnect(conn)
    """

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialize a signal.

        Args:
            name: Optional name for debugging purposes
        """
        self._name = name or f"Signal-{id(self)}"
        self._handlers: Dict[ConnectionId, Handler] = {}
        self._once_handlers: Set[ConnectionId] = set()
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        """Get the signal name."""
        return self._name

    def connect(self, handler: Handler) -> ConnectionId:
        """Connect a handler to this signal.

        Args:
            handler: Callable that will be invoked when the signal is emitted

        Returns:
            ConnectionId that can be used to disconnect the handler
        """
        conn_id = _generate_connection_id()
        with self._lock:
            self._handlers[conn_id] = handler
        logger.debug(f"[Signal:{self._name}] Connected handler {conn_id}")
        return conn_id

    def connect_once(self, handler: Handler) -> ConnectionId:
        """Connect a handler that will only be called once.

        After the first emission, the handler is automatically disconnected.

        Args:
            handler: Callable that will be invoked once

        Returns:
            ConnectionId that can be used to disconnect before it fires
        """
        conn_id = _generate_connection_id()
        with self._lock:
            self._handlers[conn_id] = handler
            self._once_handlers.add(conn_id)
        logger.debug(f"[Signal:{self._name}] Connected once-handler {conn_id}")
        return conn_id

    def disconnect(self, conn_id: ConnectionId) -> bool:
        """Disconnect a handler by its ConnectionId.

        Args:
            conn_id: The ConnectionId returned by connect()

        Returns:
            True if a handler was removed, False if not found
        """
        with self._lock:
            if conn_id in self._handlers:
                del self._handlers[conn_id]
                self._once_handlers.discard(conn_id)
                logger.debug(f"[Signal:{self._name}] Disconnected {conn_id}")
                return True
        return False

    def disconnect_all(self) -> int:
        """Disconnect all handlers.

        Returns:
            Number of handlers that were disconnected
        """
        with self._lock:
            detached = self._handlers
            self._handlers = {}
            self._once_handlers.clear()
        count = len(detached)
        detached.clear()  # Callable finalizers may reconnect or inspect this signal.
        logger.debug(f"[Signal:{self._name}] Disconnected all ({count} handlers)")
        return count

    def emit(self, value: Any = None) -> int:
        """Emit this signal, calling all connected handlers.

        Args:
            value: Value to pass to handlers (optional)

        Returns:
            Number of handlers that were called
        """
        # Get snapshot of handlers
        with self._lock:
            handlers = list(self._handlers.items())
            once_ids = self._once_handlers.copy()

        if not handlers:
            return 0

        called = 0
        to_remove: List[ConnectionId] = []

        for conn_id, handler in handlers:
            try:
                if value is None:
                    handler()
                else:
                    handler(value)
                called += 1

                if conn_id in once_ids:
                    to_remove.append(conn_id)
            except Exception as e:
                logger.exception(f"[Signal:{self._name}] Handler error: {e}")

        # Remove once handlers after emission
        for conn_id in to_remove:
            self.disconnect(conn_id)

        return called

    @property
    def handler_count(self) -> int:
        """Get the number of connected handlers."""
        with self._lock:
            return len(self._handlers)

    @property
    def is_connected(self) -> bool:
        """Check if any handlers are connected."""
        with self._lock:
            return len(self._handlers) > 0

    def __call__(self, value: Any = None) -> int:
        """Allow calling the signal directly to emit.

        Example:
            >>> signal = Signal()
            >>> signal({"data": 123})  # Same as signal.emit({"data": 123})
        """
        return self.emit(value)


class ConnectionGuard:
    """RAII-style guard that automatically disconnects when destroyed.

    Use this when you want a handler to be automatically disconnected
    when the guard goes out of scope.

    Example:
        >>> signal = Signal()
        >>> guard = ConnectionGuard(signal, signal.connect(my_handler))
        >>> # Handler is connected
        >>> del guard
        >>> # Handler is now disconnected
    """

    def __init__(self, signal: Signal, conn_id: ConnectionId) -> None:
        """Create a connection guard.

        Args:
            signal: The signal the handler is connected to
            conn_id: The connection ID from signal.connect()
        """
        self._signal = signal
        self._conn_id = conn_id
        self._detached = False

    @property
    def id(self) -> ConnectionId:
        """Get the connection ID."""
        return self._conn_id

    def detach(self) -> None:
        """Detach the guard, preventing automatic disconnection.

        After calling this, the handler will remain connected even after
        the guard is destroyed.
        """
        self._detached = True

    def disconnect(self) -> bool:
        """Manually disconnect the handler.

        Returns:
            True if handler was disconnected
        """
        self._detached = True  # Prevent double disconnect
        return self._signal.disconnect(self._conn_id)

    def __del__(self) -> None:
        """Destructor - disconnects if not detached."""
        if not self._detached:
            self._signal.disconnect(self._conn_id)


class SignalRegistry:
    """A registry for dynamically named signals.

    This allows creating and accessing signals by name at runtime,
    useful when signal names are not known at compile time.

    Simple API:
        >>> registry = SignalRegistry()
        >>>
        >>> # Connect handler (creates signal if needed)
        >>> conn = registry.connect("my_event", handler)
        >>>
        >>> # Emit to signal
        >>> registry.emit("my_event", {"key": "value"})
        >>>
        >>> # Disconnect
        >>> registry.disconnect("my_event", conn)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._signals: Dict[str, Signal] = {}
        self._lock = threading.RLock()

    def get_or_create(self, name: str) -> Signal:
        """Get or create a signal by name.

        If the signal doesn't exist, a new one is created.

        Args:
            name: Signal name

        Returns:
            The Signal instance
        """
        with self._lock:
            if name not in self._signals:
                self._signals[name] = Signal(name=name)
            return self._signals[name]

    def get(self, name: str) -> Optional[Signal]:
        """Get a signal by name, returns None if not exists.

        Args:
            name: Signal name

        Returns:
            The Signal instance or None
        """
        with self._lock:
            return self._signals.get(name)

    def contains(self, name: str) -> bool:
        """Check if a signal exists.

        Args:
            name: Signal name

        Returns:
            True if signal exists
        """
        with self._lock:
            return name in self._signals

    def remove(self, name: str) -> bool:
        """Remove a signal by name.

        Args:
            name: Signal name

        Returns:
            True if signal was removed
        """
        with self._lock:
            if name in self._signals:
                del self._signals[name]
                return True
            return False

    def names(self) -> List[str]:
        """Get all signal names.

        Returns:
            List of signal names
        """
        with self._lock:
            return list(self._signals.keys())

    def connect(self, name: str, handler: Handler) -> ConnectionId:
        """Connect a handler to a named signal.

        Args:
            name: Signal name
            handler: Handler function

        Returns:
            ConnectionId for disconnection
        """
        return self.get_or_create(name).connect(handler)

    def connect_once(self, name: str, handler: Handler) -> ConnectionId:
        """Connect a one-time handler to a named signal.

        Args:
            name: Signal name
            handler: Handler function

        Returns:
            ConnectionId for disconnection
        """
        return self.get_or_create(name).connect_once(handler)

    def disconnect(self, name: str, conn_id: ConnectionId) -> bool:
        """Disconnect a handler from a named signal.

        Args:
            name: Signal name
            conn_id: Connection ID

        Returns:
            True if handler was disconnected
        """
        signal = self.get(name)
        if signal:
            return signal.disconnect(conn_id)
        return False

    def emit(self, name: str, value: Any = None) -> int:
        """Emit a value to a named signal.

        Does nothing if the signal doesn't exist.

        Args:
            name: Signal name
            value: Value to emit

        Returns:
            Number of handlers called
        """
        signal = self.get(name)
        if signal:
            return signal.emit(value)
        return 0

    def __getitem__(self, name: str) -> Signal:
        """Allow dictionary-style access: registry["signal_name"].

        Args:
            name: Signal name

        Returns:
            The Signal instance (created if not exists)
        """
        return self.get_or_create(name)

    def __contains__(self, name: str) -> bool:
        """Allow 'in' operator: "signal_name" in registry."""
        return self.contains(name)


class WebViewSignals:
    """Pre-defined signals for WebView lifecycle and events.

    These signals are emitted automatically by the WebView during its lifecycle.
    Applications can connect handlers to respond to these events.

    Example:
        >>> view = WebView()
        >>> view.signals.page_loaded.connect(lambda: print("Page loaded!"))
        >>> view.signals.custom["my_event"].connect(handle_my_event)
    """

    def __init__(self) -> None:
        """Initialize WebView signals."""
        # Lifecycle signals
        self.page_loaded: Signal[None] = Signal(name="page_loaded")
        self.closing: Signal[None] = Signal(name="closing")
        self.closed: Signal[None] = Signal(name="closed")

        # Focus signals
        self.focused: Signal[None] = Signal(name="focused")
        self.blurred: Signal[None] = Signal(name="blurred")

        # Window state signals
        self.resized: Signal[tuple] = Signal(name="resized")  # (width, height)
        self.moved: Signal[tuple] = Signal(name="moved")  # (x, y)
        self.minimized: Signal[None] = Signal(name="minimized")
        self.maximized: Signal[None] = Signal(name="maximized")
        self.restored: Signal[None] = Signal(name="restored")

        # Custom signals registry
        self.custom: SignalRegistry = SignalRegistry()

    def get_custom(self, name: str) -> Signal:
        """Get or create a custom signal by name.

        Args:
            name: Custom signal name

        Returns:
            The Signal instance
        """
        return self.custom.get_or_create(name)

    def on(self, event_name: str, handler: Handler) -> ConnectionId:
        """Connect a handler to a custom signal (decorator compatible).

        This provides backward compatibility with @webview.on("event") pattern.

        Args:
            event_name: Event name
            handler: Handler function

        Returns:
            ConnectionId for disconnection
        """
        return self.custom.connect(event_name, handler)

    def emit_custom(self, event_name: str, data: Any = None) -> int:
        """Emit a custom event.

        Args:
            event_name: Event name
            data: Event data

        Returns:
            Number of handlers called
        """
        return self.custom.emit(event_name, data)

    def disconnect_all(self) -> None:
        """Disconnect all handlers from all signals."""
        self.page_loaded.disconnect_all()
        self.closing.disconnect_all()
        self.closed.disconnect_all()
        self.focused.disconnect_all()
        self.blurred.disconnect_all()
        self.resized.disconnect_all()
        self.moved.disconnect_all()
        self.minimized.disconnect_all()
        self.maximized.disconnect_all()
        self.restored.disconnect_all()
        for name in self.custom.names():
            signal = self.custom.get(name)
            if signal:
                signal.disconnect_all()
