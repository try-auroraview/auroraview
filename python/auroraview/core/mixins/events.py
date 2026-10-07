# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Event System Mixin.

This module provides event handling methods for the WebView class.
It integrates with the signal-slot system for Qt-inspired event handling
while maintaining backward compatibility with the @webview.on() decorator pattern.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Union

from auroraview.core.signals import ConnectionId, WebViewSignals

logger = logging.getLogger(__name__)


class WebViewEventMixin:
    """Mixin providing event system methods with signal-slot support.

    Provides methods for event handling:
    - emit: Emit an event to JavaScript
    - on: Decorator to register event callback (backward compatible)
    - register_callback: Register a callback for an event
    - signals: WebViewSignals instance for Qt-style signal connections
    - on_loaded, on_shown, on_hidden, on_closing, on_closed: Lifecycle event decorators
    - on_resized, on_moved, on_focused, on_blurred: Window event decorators
    - on_minimized, on_maximized, on_restored: State event decorators

    Signal-Slot Pattern:
        The mixin supports both the traditional decorator pattern and the
        new Qt-inspired signal-slot pattern:

        # Traditional pattern (still supported)
        @webview.on("my_event")
        def handle_event(data):
            print(data)

        # New signal-slot pattern
        conn_id = webview.signals.custom["my_event"].connect(handle_event)
        webview.signals.custom["my_event"].disconnect(conn_id)
    """

    # Type hints for attributes from main class
    _core: Any
    _async_core: Optional[Any]
    _async_core_lock: threading.Lock
    _event_handlers: Dict[str, List[Callable]]
    _event_handlers_lock: threading.Lock
    _post_eval_js_hook: Optional[Callable[[], None]]
    _auto_process_events: Callable[[], None]
    _signals: Optional[WebViewSignals]
    _dcc_mode: bool  # DCC thread safety mode flag

    def _init_signals(self) -> None:
        """Initialize the signal system. Called during WebView initialization."""
        self._signals = WebViewSignals()

    def set_event_dispatcher(
        self, dispatcher: Optional[Callable[[Callable[[], None]], None]]
    ) -> None:
        """Route non-veto events through the host's asynchronous owner queue.

        Configure this on the wrapper's creating thread. The dispatcher must
        enqueue a zero-argument callback on that thread and return without
        waiting. Callback return values are ignored. ``closing`` callbacks
        require a synchronous veto result and cannot use this route: remove
        them before configuring a dispatcher, or registration is refused.

        Existing event registrations, including internal ready callbacks, use
        the new route. Replacing or disabling it invalidates already queued
        deliveries. Passing ``None`` restores the legacy DCC dispatch behavior.
        Closing or disconnecting still invalidates pending callbacks; this
        queue is not a guaranteed teardown-notification channel.
        """
        if dispatcher is not None and not callable(dispatcher):
            raise TypeError("Event dispatcher must be callable or None")
        with self._event_handlers_lock:
            self._check_open()
            if getattr(self, "_events_closed", False):
                raise RuntimeError("WebView event callbacks are closed")
            owner = getattr(self, "_event_dispatch_owner", None)
            if owner is None:
                core = getattr(self, "_core", None)
                owner = getattr(self, "_core_threads", {}).get(id(core), threading.get_ident())
            if owner != threading.get_ident():
                raise RuntimeError("Configure event dispatch on the wrapper's creating thread")
            if dispatcher is not None and any(
                name == "closing" and active[0]
                for name, _callback, active in getattr(self, "_event_connections", {}).values()
            ):
                raise RuntimeError(
                    "Remove synchronous closing callbacks before host event dispatch"
                )
            self._event_dispatcher = dispatcher
            self._event_dispatch_owner = owner
            self._event_dispatch_generation = getattr(self, "_event_dispatch_generation", 0) + 1

    @property
    def signals(self) -> WebViewSignals:
        """Get the WebView signals for Qt-style event handling.

        Returns:
            WebViewSignals instance with pre-defined and custom signals

        Example:
            >>> # Connect to lifecycle signal
            >>> webview.signals.page_loaded.connect(lambda: print("Loaded!"))
            >>>
            >>> # Connect to custom event
            >>> conn = webview.signals.custom["my_event"].connect(handler)
            >>> webview.signals.custom["my_event"].disconnect(conn)
        """
        if not hasattr(self, "_signals") or self._signals is None:
            self._init_signals()
        return self._signals  # type: ignore

    def emit(
        self, event_name: str, data: Union[Dict[str, Any], Any] = None, auto_process: bool = True
    ) -> None:
        """Emit an event to JavaScript.

        Args:
            event_name: Name of the event
            data: Data to send with the event (will be JSON serialized)
            auto_process: Automatically process message queue after emission (default: True).

        Example:
            >>> webview.emit("update_scene", {"objects": ["cube", "sphere"]})

            >>> # Batch multiple events
            >>> webview.emit("event1", {"data": 1}, auto_process=False)
            >>> webview.emit("event2", {"data": 2}, auto_process=False)
            >>> webview.process_events()  # Process all at once
        """
        if data is None:
            data = {}

        logger.debug(f"[SEND] [WebView.emit] START - Event: {event_name}")
        logger.debug(f"[SEND] [WebView.emit] Data type: {type(data)}")
        logger.debug(f"[SEND] [WebView.emit] Data: {data}")

        # Convert data to dict if needed
        if not isinstance(data, dict):
            logger.debug("[SEND] [WebView.emit] Converting non-dict data to dict")
            data = {"value": data}

        # In packed mode, send events through stdout to Rust CLI
        from auroraview.core.packed import is_packed_mode, send_event

        if is_packed_mode():
            logger.debug("[SEND] [WebView.emit] Packed mode: sending event via stdout")
            send_event(event_name, data)
            logger.debug(f"[OK] [WebView.emit] Event sent to Rust CLI: {event_name}")
            return

        # Do not wait on a host UI thread for startup or call any methods on a
        # foreign unsendable core. The owner cached this proxy before publication.
        self._command_target().emit(event_name, data)

        # Auto-telemetry: record event emission
        if hasattr(self, "_telemetry_on_emit"):
            self._telemetry_on_emit(event_name)

        # Call post eval_js hook if set (for Qt integration and testing)
        if self._post_eval_js_hook is not None:
            self._post_eval_js_hook()

        # Automatically process events to ensure immediate delivery
        if auto_process:
            self._auto_process_events()

    def emit_batch(
        self,
        events: list,
        auto_process: bool = True,
    ) -> int:
        """Emit multiple events to JavaScript in a single batch.

        This is more efficient than calling emit() multiple times because
        all events are queued together and processed in one go.

        Args:
            events: List of tuples (event_name, data_dict)
            auto_process: Automatically process message queue after emission (default: True).

        Returns:
            Number of events emitted

        Example:
            >>> webview.emit_batch([
            ...     ("update", {"field": "name", "value": "John"}),
            ...     ("update", {"field": "email", "value": "john@example.com"}),
            ...     ("batch_complete", {"count": 2}),
            ... ])
        """
        if not events:
            return 0

        # Use the async core if available (when running in background thread)
        target = self._command_target()

        # Convert events to proper format for Rust
        rust_events = []
        for event_name, data in events:
            if data is None:
                data = {}
            elif not isinstance(data, dict):
                data = {"value": data}
            rust_events.append((event_name, data))

        if hasattr(target, "emit_batch"):
            count = target.emit_batch(rust_events)
        else:
            # The send-safe proxy supports individual events, not native batch.
            for event_name, data in rust_events:
                target.emit(event_name, data)
            count = len(rust_events)
        logger.debug(f"[OK] [WebView.emit_batch] Emitted {count} events via Rust")

        if auto_process:
            self._auto_process_events()
        return count

    def on(
        self,
        event_name: str,
        handler: Optional[Callable] = None,
    ) -> Union[Callable, ConnectionId]:
        """Register a Python callback for JavaScript events.

        Can be used as a decorator or as a method call:

            # As decorator (returns the function)
            @webview.on("export_scene")
            def handle_export(data):
                print(f"Exporting to: {data['path']}")

            # As method call (returns ConnectionId for disconnect)
            conn_id = webview.on("export_scene", handle_export)
            webview.disconnect(conn_id)

        Args:
            event_name: Name of the event to listen for
            handler: Optional callback function

        Returns:
            If handler is None (decorator mode): returns a decorator
            If handler is provided: returns ConnectionId for disconnection
        """
        if handler is None:
            # Decorator usage
            def decorator(func: Callable) -> Callable:
                self.register_callback(event_name, func)
                return func

            return decorator

        # Direct call - use signal system
        return self.register_callback(event_name, handler)

    def register_callback(self, event_name: str, callback: Callable) -> ConnectionId:
        """Register a callback for an event.

        If dcc_mode is enabled on the WebView, the callback is automatically
        wrapped to run on the DCC main thread for thread safety.

        Args:
            event_name: Name of the event (can be a string or WindowEvent enum)
            callback: Function to call when event occurs

        Returns:
            ConnectionId that can be used to disconnect the callback
        """
        # Convert WindowEvent enum to string if needed
        event_str = str(event_name)

        core = self._get_active_core()
        registered = getattr(self, "_registered_events", {}).get(id(core), set())
        if core is not None and event_str not in registered and not self._is_core_owner(core):
            raise RuntimeError("Register new events before show() or on the WebView owner thread")

        # Guard the actual user invocation, inside the DCC scheduling wrapper.
        # Checking only at native dispatch would let already-queued host work
        # run after close, disconnect, or add-on unload.
        generation = getattr(self, "_event_generation", 0)
        active = [True]
        user_callback = callback

        def invoke(*args: Any, **kwargs: Any) -> Any:
            with self._event_handlers_lock:
                if (
                    not active[0]
                    or getattr(self, "_events_closed", False)
                    or getattr(self, "_close_requested", False)
                    or generation != getattr(self, "_event_generation", 0)
                ):
                    return None
            return user_callback(*args, **kwargs)

        def route(*args: Any, **kwargs: Any) -> Any:
            with self._event_handlers_lock:
                if not active[0] or getattr(self, "_events_closed", False):
                    return None
                dispatcher = getattr(self, "_event_dispatcher", None)
                dispatch_generation = getattr(self, "_event_dispatch_generation", 0)
                owner = getattr(self, "_event_dispatch_owner", None)
            started = False
            cancelled = False

            def deliver() -> Any:
                nonlocal started, cancelled
                with self._event_handlers_lock:
                    if (
                        started
                        or cancelled
                        or dispatch_generation != getattr(self, "_event_dispatch_generation", 0)
                    ):
                        return None
                    if dispatcher is not None and threading.get_ident() != owner:
                        cancelled = True
                        raise RuntimeError("Host event dispatcher must execute on its owner thread")
                    started = True
                return invoke(*args, **kwargs)

            if dispatcher is not None:
                try:
                    dispatcher(deliver)
                except Exception:
                    # An enqueue-then-fail scheduler must not mutate the host
                    # later through a callback it reported as rejected.
                    cancelled = True
                    raise
                return None
            if getattr(self, "_dcc_mode", False):
                from auroraview.utils.thread_dispatcher import wrap_callback_for_dcc

                return wrap_callback_for_dcc(deliver)()
            return deliver()

        callback = route

        # Register with legacy event handlers dict (for backward compatibility)
        # Use lock to protect concurrent access from background threads.
        with self._event_handlers_lock:
            self._check_open()
            if getattr(self, "_events_closed", False):
                raise RuntimeError("WebView event callbacks are closed")
            if event_str == "closing" and getattr(self, "_event_dispatcher", None) is not None:
                raise RuntimeError(
                    "Synchronous closing veto callbacks cannot use host event dispatch"
                )
            if event_str not in self._event_handlers:
                self._event_handlers[event_str] = []
            self._event_handlers[event_str].append(callback)
            # Keep one connection identity across native and signal dispatch.
            conn_id = self.signals.custom.connect(event_str, callback)
            if not hasattr(self, "_event_connections"):
                self._event_connections = {}
            self._event_connections[conn_id] = (event_str, callback, active)
        logger.debug(f"Registered callback for event: {event_str} (conn_id: {conn_id})")

        # Register with core (if available - packed mode may not have core)
        if core is not None:
            self._register_native_event(core, event_str)
        else:
            logger.debug(
                f"Skipped core registration for event {event_str} (packed mode or core not available)"
            )

        return conn_id

    def _register_native_event(self, core: Any, event_name: str) -> None:
        """Install one dispatcher; later handlers stay in the Python registry."""
        if not hasattr(self, "_registered_events"):
            self._registered_events = {}
        registered = self._registered_events.setdefault(id(core), set())
        if event_name in registered:
            return
        if not self._is_core_owner(core):
            raise RuntimeError("Native event registration requires the WebView owner thread")

        def dispatch(data: Any) -> Any:
            with self._event_handlers_lock:
                handlers = list(self._event_handlers.get(event_name, []))
            result = None
            for handler in handlers:
                value = handler(data)
                # Preserve the closing-event veto convention.
                if value is False:
                    result = False
                elif result is not False:
                    result = value
            return result

        core.on(event_name, dispatch)
        registered.add(event_name)

    def _replay_event_bindings(self, core: Any) -> None:
        """Replay all registered event names before the new owner starts show()."""
        with self._event_handlers_lock:
            names = list(self._event_handlers)
        for event_name in names:
            self._register_native_event(core, event_name)

    def disconnect(self, event_name: str, conn_id: ConnectionId) -> bool:
        """Disconnect a callback by its ConnectionId.

        Args:
            event_name: Name of the event
            conn_id: ConnectionId returned by on() or register_callback()

        Returns:
            True if callback was disconnected
        """
        event_str = str(event_name)
        removed = False
        with self._event_handlers_lock:
            connections = getattr(self, "_event_connections", {})
            connection = connections.get(conn_id)
            if connection is not None and connection[0] == event_str:
                _name, callback, active = connections.pop(conn_id)
                active[0] = False
                handlers = self._event_handlers.get(event_str, [])
                if callback in handlers:
                    handlers.remove(callback)
                if not handlers:
                    self._event_handlers.pop(event_str, None)
                removed = True
        return self.signals.custom.disconnect(event_str, conn_id) or removed

    def _cancel_event_callbacks(self) -> None:
        """Invalidate queued host callbacks and release both Python registries."""
        lock = getattr(self, "_event_handlers_lock", None)
        if lock is None:
            return
        with lock:
            self._events_closed = True
            self._event_generation = getattr(self, "_event_generation", 0) + 1
            for _name, _callback, active in getattr(self, "_event_connections", {}).values():
                active[0] = False
            self._event_connections = {}
            self._event_handlers.clear()
        signals = getattr(self, "_signals", None)
        if signals is not None:
            signals.disconnect_all()

    def _connect_lifecycle_signal(
        self, signal: Any, conn_id: ConnectionId, payload: Callable
    ) -> None:
        """Reuse the guarded callback for the lifecycle-signal compatibility path."""
        with self._event_handlers_lock:
            connection = self._event_connections.get(conn_id)
            if connection is not None and not getattr(self, "_events_closed", False):
                callback = connection[1]
                signal.connect(lambda *args: callback(payload(*args)))

    # =========================================================================
    # Window Event Convenience Methods
    # These methods connect to both the core and the signal system
    # =========================================================================

    def on_loaded(self, callback: Callable) -> Callable:
        """Register a callback for when the page finishes loading.

        Args:
            callback: Function to call when page loads

        Returns:
            The callback function (for decorator use)

        Example:
            >>> @webview.on_loaded
            >>> def handle_loaded(data):
            ...     print("Page loaded!")
        """
        conn_id = self.register_callback("loaded", callback)
        # Also connect to lifecycle signal (wraps to handle None arg)
        self._connect_lifecycle_signal(self.signals.page_loaded, conn_id, lambda: {})
        return callback

    def on_shown(self, callback: Callable) -> Callable:
        """Register a callback for when the window becomes visible."""
        self.register_callback("shown", callback)
        return callback

    def on_hidden(self, callback: Callable) -> Callable:
        """Register a callback for when the window becomes hidden."""
        self.register_callback("hidden", callback)
        return callback

    def on_closing(self, callback: Callable) -> Callable:
        """Register a callback for before the window closes.

        The callback can return False to prevent the window from closing.

        Example:
            >>> @webview.on_closing
            >>> def handle_closing(data):
            ...     if has_unsaved_changes():
            ...         return False  # Prevent closing
            ...     return True
        """
        conn_id = self.register_callback("closing", callback)
        self._connect_lifecycle_signal(self.signals.closing, conn_id, lambda: {})
        return callback

    def on_closed(self, callback: Callable) -> Callable:
        """Register a callback for after the window has closed."""
        conn_id = self.register_callback("closed", callback)
        self._connect_lifecycle_signal(self.signals.closed, conn_id, lambda: {})
        return callback

    def on_resized(self, callback: Callable) -> Callable:
        """Register a callback for when the window is resized.

        Args:
            callback: Function to call when window is resized.
                     Data includes {width, height}.

        Example:
            >>> @webview.on_resized
            >>> def handle_resize(data):
            ...     print(f"New size: {data['width']}x{data['height']}")
        """
        conn_id = self.register_callback("resized", callback)
        self._connect_lifecycle_signal(
            self.signals.resized, conn_id, lambda size: {"width": size[0], "height": size[1]}
        )
        return callback

    def on_moved(self, callback: Callable) -> Callable:
        """Register a callback for when the window is moved.

        Args:
            callback: Function to call when window is moved.
                     Data includes {x, y}.
        """
        conn_id = self.register_callback("moved", callback)
        self._connect_lifecycle_signal(
            self.signals.moved, conn_id, lambda pos: {"x": pos[0], "y": pos[1]}
        )
        return callback

    def on_focused(self, callback: Callable) -> Callable:
        """Register a callback for when the window gains focus."""
        conn_id = self.register_callback("focused", callback)
        self._connect_lifecycle_signal(self.signals.focused, conn_id, lambda: {})
        return callback

    def on_blurred(self, callback: Callable) -> Callable:
        """Register a callback for when the window loses focus."""
        conn_id = self.register_callback("blurred", callback)
        self._connect_lifecycle_signal(self.signals.blurred, conn_id, lambda: {})
        return callback

    def on_minimized(self, callback: Callable) -> Callable:
        """Register a callback for when the window is minimized."""
        conn_id = self.register_callback("minimized", callback)
        self._connect_lifecycle_signal(self.signals.minimized, conn_id, lambda: {})
        return callback

    def on_maximized(self, callback: Callable) -> Callable:
        """Register a callback for when the window is maximized."""
        conn_id = self.register_callback("maximized", callback)
        self._connect_lifecycle_signal(self.signals.maximized, conn_id, lambda: {})
        return callback

    def on_restored(self, callback: Callable) -> Callable:
        """Register a callback for when the window is restored from minimized/maximized state."""
        conn_id = self.register_callback("restored", callback)
        self._connect_lifecycle_signal(self.signals.restored, conn_id, lambda: {})
        return callback
