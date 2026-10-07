# -*- coding: utf-8 -*-
"""Event timer for WebView event processing.

This module provides a timer-based event loop for processing WebView events
in embedded mode. It's designed to work with applications that have their
own event loops.

The timer periodically checks for:
- Window messages (WM_CLOSE, WM_DESTROY, etc.)
- Window validity (IsWindow check)
- User-defined callbacks

Supported Timer Backends (in priority order):
1. Qt QTimer - Most precise, works in Qt-based applications
2. Thread-based timer - Fallback for all platforms

Note: For DCC-specific timer implementations (Maya, Blender, Houdini, etc.),
use the integration modules in the `integrations/` package.

IMPORTANT: Qt backend runs in the main thread to avoid thread-safety issues.
The thread-based fallback uses a background daemon thread.

Example:
    >>> from auroraview import WebView
    >>> from auroraview.event_timer import EventTimer
    >>>
    >>> webview = WebView(parent=parent_hwnd, mode="owner")
    >>>
    >>> # Create timer with 16ms interval (60 FPS)
    >>> timer = EventTimer(webview, interval_ms=16)
    >>>
    >>> # Register close callback
    >>> @timer.on_close
    >>> def handle_close():
    ...     print("WebView closed")
    ...     timer.stop()
    >>>
    >>> # Start timer (auto-detects best backend)
    >>> timer.start()
"""

import logging
import threading
from typing import Any, Callable, ClassVar, Optional, Set

from auroraview.utils.timer_backends import (
    QtTimerBackend,
    ThreadTimerBackend,
    TimerBackend,
    get_available_backend,
)

logger = logging.getLogger(__name__)


class EventTimer:
    """Timer-based event processor for WebView.

    This class provides a timer that periodically processes WebView events
    and checks window validity. It's designed for embedded mode where the
    WebView is integrated into a DCC application's event loop.

    The timer uses a pluggable backend system. You can either:
    1. Let it auto-select the best available backend (default)
    2. Provide a specific backend instance
    3. Register custom backends globally using register_timer_backend()

    Args:
        webview: WebView instance to monitor
        interval_ms: Timer interval in milliseconds (default: 16ms = ~60 FPS)
        check_window_validity: Whether to check if window is still valid (default: True)
        backend: Optional TimerBackend instance. If None, auto-selects best available.

    Example - Auto-select backend:
        >>> timer = EventTimer(webview, interval_ms=16)
        >>> timer.start()

    Example - Use specific backend:
        >>> from auroraview.timer_backends import QtTimerBackend
        >>> backend = QtTimerBackend()
        >>> timer = EventTimer(webview, backend=backend)
        >>> timer.start()

    Example - Register custom backend globally:
        >>> from auroraview.timer_backends import register_timer_backend
        >>> register_timer_backend(MayaTimerBackend, priority=200)
        >>> timer = EventTimer(webview)  # Will use Maya backend if available
        >>> timer.start()
    """

    # Class-level dedup set of webview types that already emitted the
    # "missing `is_ready`" debug message. Keyed on ``type(webview)`` so the
    # warning is suppressed once per stub class for the lifetime of the
    # process — even if the same partial mock is wrapped by many
    # short-lived ``EventTimer`` instances (a common pattern in test
    # fixtures). Class-level set keeps this independent of per-instance
    # state and avoids the weakref bookkeeping that a per-instance flag
    # would otherwise need.
    _warned_missing_is_ready_types: ClassVar[Set[type]] = set()

    def __init__(
        self,
        webview,
        interval_ms: int = 16,
        check_window_validity: bool = True,
        backend: Optional[TimerBackend] = None,
    ):
        """Initialize event timer.

        Args:
            webview: WebView instance to monitor
            interval_ms: Timer interval in milliseconds (default: 16ms = ~60 FPS)
            check_window_validity: Whether to check if window is still valid
            backend: Optional TimerBackend instance. If None, auto-selects best available.
        """
        self._webview = webview
        self._interval_ms = interval_ms
        self._check_validity = check_window_validity
        self._backend = backend  # Can be None, will be set in start()
        self._running = False
        self._starting = False
        self._processing_events = False
        self._close_notified = False
        self._close_notifying = False
        self._cleanup_active = False
        self._cleanup_lock = threading.Lock()
        self._close_observed = False
        self._timer_handle: Optional[Any] = None  # Handle returned by backend.start()
        self._owner_thread_id: Optional[int] = None
        self._notification_thread_id = threading.get_ident()
        self._close_callbacks: "list[Callable[[], None]]" = []
        self._tick_callbacks: "list[Callable[[], None]]" = []
        self._last_valid = True
        self._tick_count = 0

        logger.debug(
            f"EventTimer created: interval={interval_ms}ms, check_validity={check_window_validity}, "
            f"backend={backend.get_name() if backend else 'auto'}"
        )

    def start(self) -> None:
        """Start the timer.

        If no backend was provided in __init__, this will auto-select the best
        available backend based on registered backends and their priorities.

        Raises:
            RuntimeError: If timer is already running or no timer backend available
        """
        if self._running or self._starting:
            raise RuntimeError("Timer is already running")

        # Auto-select backend if not provided
        if self._backend is None:
            self._backend = get_available_backend()
            if self._backend is None:
                raise RuntimeError(
                    "No timer backend available. Please register a timer backend or provide one explicitly."
                )

        # Start the timer using the backend
        self._starting = True
        try:
            self._timer_handle = self._backend.start(self._interval_ms, self._tick)
            self._owner_thread_id = threading.get_ident()
            self._notification_thread_id = self._owner_thread_id
            self._running = True
            self._close_notified = False
            self._close_observed = False
            logger.info(
                f"EventTimer started with {self._backend.get_name()} backend (interval={self._interval_ms}ms)"
            )
        except Exception as e:
            logger.error(f"Failed to start timer with {self._backend.get_name()} backend: {e}")
            raise RuntimeError(f"Failed to start timer: {e}") from e
        finally:
            self._starting = False

    def stop(self) -> None:
        """Stop the timer and cleanup resources.

        This stops the timer backend and clears the webview reference
        to prevent circular references.
        """
        if self._starting:
            raise RuntimeError("EventTimer startup is still in progress")
        if not self._running:
            return

        if not self.can_cleanup_from_current_thread():
            raise RuntimeError("EventTimer must be stopped on its owning thread")

        # Stop the timer using the backend
        if self._backend and self._timer_handle is not None:
            try:
                self._backend.stop(self._timer_handle)
                logger.info(f"{self._backend.get_name()} timer stopped")
            except Exception as e:
                logger.error(f"Failed to stop {self._backend.get_name()} timer: {e}")
                raise RuntimeError(f"Failed to stop timer: {e}") from e

        self._running = False
        self._timer_handle = None
        self._owner_thread_id = None

        # Clear webview reference to prevent circular references
        # This is important for proper cleanup in DCC environments
        self._webview = None

        logger.info("EventTimer stopped and cleaned up")

    def cleanup(self) -> bool:
        """Cleanup all resources and references.

        This method should be called when the EventTimer is no longer needed.
        It stops the timer and clears all references to prevent memory leaks.
        Returns False immediately if an outer cleanup/notification is still
        active, including reentry from a close observer. No lock is held while
        invoking backend operations or user callbacks. Returns True only after
        stop, all close observers, and reference cleanup have finished. Observer
        return values are ignored; they are not close vetoes or completion flags.
        """
        with self._cleanup_lock:
            if self._cleanup_active or self._close_notifying:
                return False
            self._cleanup_active = True
        try:
            if getattr(self._webview, "_native_close_observed", False) is True:
                self._observe_close()
            self.stop()
            if self._close_observed and not self._notify_close():
                return False
            self._webview = None
            self._close_callbacks.clear()
            self._tick_callbacks.clear()
            logger.info("EventTimer cleanup complete")
            return True
        finally:
            with self._cleanup_lock:
                self._cleanup_active = False

    @property
    def owner_thread_id(self) -> Optional[int]:
        """Thread that successfully started the native timer, if any."""
        return self._owner_thread_id

    @property
    def processing_events(self) -> bool:
        """True while wrapper event processing can request deferred cleanup."""
        return self._processing_events

    def _notify_close(self) -> bool:
        with self._cleanup_lock:
            if self._close_notified:
                return True
            if self._close_notifying:
                return False
            if not self.can_cleanup_from_current_thread():
                raise RuntimeError("Close notification must run on the timer's owning thread")
            self._close_notifying = True
            callbacks = list(self._close_callbacks)
        completed = False
        try:
            for callback in callbacks:
                try:
                    callback()
                except Exception as exc:
                    logger.error("Error in close callback: %s", exc, exc_info=True)
            completed = True
            return True
        finally:
            with self._cleanup_lock:
                # The once-only reentry guard does not imply completion.
                self._close_notified = completed
                self._close_notifying = False

    def _observe_close(self) -> None:
        """Retain the close event until owner-side cleanup can notify it once."""
        self._close_observed = True

    def can_cleanup_from_current_thread(self) -> bool:
        """Whether cleanup can safely touch this timer's backend now."""
        if self._starting or self._close_notifying:
            return False
        # stop() releases the native handle, but an observed close callback
        # still belongs to that host thread until notification has completed.
        if (
            self._close_observed
            and not self._close_notified
            and type(self._backend) is not ThreadTimerBackend
            and self._notification_thread_id != threading.get_ident()
        ):
            return False
        if not self._running and self._timer_handle is None:
            return True
        # ThreadTimerBackend.stop only sets threading.Event and never joins.
        if type(self._backend) is ThreadTimerBackend:
            return True
        return self._owner_thread_id == threading.get_ident()

    def on_close(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register callback for window close event.

        The callback will be called when the window is closed or becomes invalid.

        Args:
            callback: Function to call when window closes

        Returns:
            The callback function (for decorator usage)

        Example:
            >>> @timer.on_close
            >>> def handle_close():
            ...     print("Window closed")
        """
        self._close_callbacks.append(callback)
        logger.debug(f"Close callback registered: {callback.__name__}")
        return callback

    def on_tick(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register callback for timer tick.

        The callback will be called on every timer tick, before processing events.

        Args:
            callback: Function to call on each tick

        Returns:
            The callback function (for decorator usage)

        Example:
            >>> @timer.on_tick
            >>> def handle_tick():
            ...     print("Tick")
        """
        self._tick_callbacks.append(callback)
        logger.debug(f"Tick callback registered: {callback.__name__}")
        return callback

    def off_close(self, callback: Callable[[], None]) -> bool:
        """Unregister a previously registered close callback.

        Returns:
            True if the callback was removed, False if it was not found.
        """
        try:
            self._close_callbacks.remove(callback)
            logger.debug(
                f"Close callback unregistered: {getattr(callback, '__name__', repr(callback))}"
            )
            return True
        except ValueError:
            logger.debug("Close callback not found during unregistration")
            return False

    def off_tick(self, callback: Callable[[], None]) -> bool:
        """Unregister a previously registered tick callback.

        Returns:
            True if the callback was removed, False if it was not found.
        """
        try:
            self._tick_callbacks.remove(callback)
            logger.debug(
                f"Tick callback unregistered: {getattr(callback, '__name__', repr(callback))}"
            )
            return True
        except ValueError:
            logger.debug("Tick callback not found during unregistration")
            return False

    def _is_core_ready(self) -> bool:
        """Return True when the WebView core is initialized.

        Single source of truth: :attr:`WebView.is_ready`. The timer never
        inspects ``_core`` / ``_async_core`` directly — stub compatibility,
        lock acquisition and dual-core (sync + async) semantics are all
        owned by ``WebView.is_ready`` so we don't drift from the canonical
        probe.

        Stubs that don't expose ``is_ready`` (or expose a non-bool value)
        are treated as not-ready; they should add an ``is_ready`` property
        to integrate with the timer.
        """
        webview = self._webview
        if webview is None:
            return False
        # Lightweight one-shot warning for legacy stubs / partial mocks that
        # don't expose `is_ready`. We log at DEBUG (not WARNING) because some
        # test fixtures intentionally fake a webview without going through
        # the full `WebView` constructor — and we don't want noisy output in
        # the steady state. Dedup is keyed on the stub's *type* (class-level
        # set) so we emit at most one message per webview class for the
        # lifetime of the process, even across many short-lived timers.
        if not hasattr(webview, "is_ready"):
            wv_type = type(webview)
            if wv_type not in EventTimer._warned_missing_is_ready_types:
                EventTimer._warned_missing_is_ready_types.add(wv_type)
                logger.debug(
                    "EventTimer: webview %r exposes no `is_ready` property; "
                    "treating as not-ready. Add an `is_ready` property to the "
                    "stub if it should drive the timer.",
                    wv_type.__name__,
                )
            return False
        return bool(webview.is_ready)

    def _tick(self) -> None:
        """Timer tick callback (runs in main thread for Qt, background thread for thread backend)."""
        if not self._running:
            return

        webview = self._webview
        if webview is not None and getattr(webview, "_close_requested", False) is True:
            # Do not invoke user tick callbacks after close/unload. A Qt timer
            # reaches this path on its actual owner thread, finishing cleanup
            # that a foreign close deliberately left pending.
            cleanup = getattr(webview, "_cleanup_auto_timer", None)
            if cleanup is not None:
                cleanup()
            elif self.can_cleanup_from_current_thread():
                self.cleanup()
            return

        self._tick_count += 1

        try:
            # Call tick callbacks
            for callback in self._tick_callbacks:
                if (
                    self._webview is None
                    or getattr(self._webview, "_close_requested", False) is True
                ):
                    return
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in tick callback: {e}", exc_info=True)

            # Process WebView events (only if WebView is initialized)
            should_close = False
            try:
                if not self._is_core_ready():
                    # WebView not yet initialized, skip this tick
                    return

                # Choose event-processing strategy based on timer backend.
                # Qt backend uses IPC-only mode if available, others use full process_events
                is_qt_backend = isinstance(self._backend, QtTimerBackend)
                self._processing_events = True
                if is_qt_backend and hasattr(self._webview, "process_events_ipc_only"):
                    # Qt hosts own the native event loop.
                    # In this mode we only drain AuroraView's internal IPC queue
                    # and rely on Qt to drive the Win32/WebView2 message pump.
                    should_close = self._webview.process_events_ipc_only()
                else:
                    # Thread backend uses the full process_events() path,
                    # which drives the native message pump directly.
                    should_close = self._webview.process_events()
            except RuntimeError as e:
                if "not initialized" in str(e) and not self._close_observed:
                    # WebView not yet initialized, skip this tick silently
                    return
                logger.error(f"Error processing events: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing events: {e}", exc_info=True)
            finally:
                self._processing_events = False
                # The wrapper may observe should_close, then raise while
                # sending a close request. Preserve the observed event rather
                # than relying on the interrupted method's return value.
                if getattr(webview, "_native_close_observed", False) is True:
                    self._observe_close()
                should_close = should_close or self._close_observed

            # Check window validity (Windows only, gated by `_is_core_ready`).
            #
            # We previously also tested `hasattr(self._webview, "_core")` here,
            # but that became a hidden second source of truth: stubs without
            # `_core` would silently bypass validity checks even when their
            # `is_ready` reported True. Delegating entirely to
            # `_is_core_ready()` keeps :class:`WebView` as the single owner
            # of "what does ready mean".
            if self._check_validity and not should_close:
                try:
                    if not self._is_core_ready():
                        # WebView not yet initialized, skip validity check
                        return

                    is_valid = self._check_window_valid()
                    if self._last_valid and not is_valid:
                        logger.info("Window became invalid")
                        should_close = True
                    self._last_valid = is_valid
                except RuntimeError as e:
                    if "not initialized" in str(e):
                        # WebView not yet initialized, skip validity check silently
                        return
                    logger.error(f"Error checking window validity: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Error checking window validity: {e}", exc_info=True)

            # Handle close event
            if should_close:
                logger.info("Close event detected")
                # Cleanup orders stop -> once-only notification -> release.
                # If stop fails, the observation and callbacks survive retry.
                self._observe_close()
                self.cleanup()
                cleanup = getattr(webview, "_cleanup_auto_timer", None)
                if cleanup is not None:
                    cleanup()

        except Exception as e:
            logger.error(f"Unexpected error in timer tick: {e}", exc_info=True)

    def _check_window_valid(self) -> bool:
        """Check if window is still valid.

        Delegates entirely to :meth:`WebView.is_window_valid` — the timer
        does **not** look at ``_core`` / ``_async_core`` directly. This
        keeps :class:`WebView` as the single owner of "what does ready /
        valid mean" and removes the previous duplicated fallback path
        that silently bypassed checks for stubs without a ``_core``
        attribute.

        Stubs that don't expose ``is_window_valid`` are treated as valid
        (legacy behavior preserved); they should add the method if they
        want to drive the timer's close-on-destroy logic.

        Returns:
            True if window is valid or its validity cannot be determined,
            False only when the native probe explicitly reports the
            window has been destroyed.
        """
        webview = self._webview
        if webview is None:
            return False
        # ``_is_core_ready`` already gated the call site, but keep the
        # guard here too so direct callers (tests) get the same answer.
        if not self._is_core_ready():
            return True

        probe = getattr(webview, "is_window_valid", None)
        if probe is None:
            # Stub without the public probe — treat as valid so the
            # timer doesn't synthesize a spurious close event.
            return True
        try:
            return bool(probe())
        except Exception as e:
            logger.error(f"Error checking window validity: {e}")
            return False

    @property
    def is_running(self) -> bool:
        """Check if timer is running."""
        return self._running

    @property
    def interval_ms(self) -> int:
        """Get timer interval in milliseconds."""
        return self._interval_ms

    @interval_ms.setter
    def interval_ms(self, value: int) -> None:
        """Set timer interval in milliseconds.

        Note: This only takes effect after restarting the timer.
        """
        if value <= 0:
            raise ValueError("Interval must be positive")
        self._interval_ms = value
        logger.debug(f"Timer interval set to {value}ms")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False

    def __repr__(self) -> str:
        """String representation."""
        status = "running" if self._running else "stopped"
        backend_name = self._backend.get_name() if self._backend else "none"
        return (
            f"EventTimer(interval={self._interval_ms}ms, backend={backend_name}, status={status})"
        )


__all__ = ["EventTimer"]
