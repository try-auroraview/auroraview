# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Lifecycle Mixin.

This module provides lifecycle methods for the WebView class.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _is_panic_exception(exc: BaseException) -> bool:
    """Return True when ``exc`` is PyO3's ``PanicException``.

    ``PanicException`` derives from ``BaseException``, so ``except Exception``
    never sees it. PyO3 raises it whenever an ``unsendable`` ``#[pyclass]`` is
    touched from a thread other than the one that created it, which is exactly
    the failure ``close()`` has to route around. The type lives in ``builtins``
    and is owned by PyO3 rather than by this package, so it is matched by type
    name instead of by import.

    Args:
        exc: The exception to classify.

    Returns:
        bool: True when the exception is a PyO3 panic.
    """
    return type(exc).__name__ == "PanicException"


def _request_close_via_channel(proxy: Any) -> bool:
    """Request close using a proxy previously captured on the core's owner thread."""
    if proxy is None:
        return False

    try:
        proxy.close()
    except Exception as e:
        logger.warning(f"Error requesting core close through the channel: {e}")
        return False

    logger.info("Core WebView close requested through the close channel")
    return True


class WebViewLifecycleMixin:
    """Mixin providing lifecycle methods.

    Provides methods for controlling the WebView lifecycle:
    - show: Show the WebView window (smart mode)
    - show_async: Show window in non-blocking mode
    - show_blocking: Show window and block until closed
    - wait: Wait for window to close
    - close: Close the WebView
    """

    def _track_core_thread(self, core: Any) -> None:
        """Record the thread that owns a Rust core instance.

        The Rust ``WebView`` is ``unsendable`` and the underlying window may
        only be torn down on the thread that created it, so ``close()`` needs to
        know the owning thread to decide whether a direct call is safe or the
        request has to travel through the close channel.

        Args:
            core: The Rust core WebView instance, or None.
        """
        if core is None:
            return

        threads = getattr(self, "_core_threads", None)
        if threads is None:
            threads = {}
            self._core_threads = threads
        threads[id(core)] = threading.get_ident()
        proxies = getattr(self, "_core_proxies", None)
        if proxies is None:
            proxies = {}
            self._core_proxies = proxies
        # This must run on the creating thread. Even get_proxy() is a method
        # on the unsendable PyO3 object; it cannot be called after handoff.
        get_proxy = getattr(core, "get_proxy", None)
        if get_proxy is not None:
            try:
                proxies[id(core)] = get_proxy()
            except Exception:
                logger.debug("Core does not provide a usable proxy", exc_info=True)
        emitters = getattr(self, "_core_emitters", None)
        if emitters is None:
            emitters = self._core_emitters = {}
        create_emitter = getattr(core, "create_emitter", None)
        if create_emitter is not None:
            try:
                emitters[id(core)] = create_emitter()
            except Exception:
                logger.debug("Core does not provide a usable EventEmitter", exc_info=True)

    def _is_core_owner(self, core: Any) -> bool:
        if core is None:
            return True  # Packed mode has no native object to access.
        owner = getattr(self, "_core_threads", {}).get(id(core))
        # Unknown ownership must never authorize native method access. Tests or
        # integrations injecting a core must track it on its creating thread.
        return owner is not None and owner == threading.get_ident()

    def _get_active_core(self) -> Any:
        """Select a core without accessing any of its native methods."""
        with self._async_core_lock:
            self._check_open()
            if self._async_core is not None:
                return self._async_core
            if getattr(self, "_is_running", False) and self._show_thread is not None:
                raise RuntimeError("WebView is starting; its command proxy is not ready")
            return self._core

    def _command_target(self) -> Any:
        """Return the active owner core or its cached, send-safe command proxy."""
        core = self._get_active_core()
        if core is None:
            raise RuntimeError("WebView has no native core")
        if self._is_core_owner(core):
            return core
        proxy = getattr(self, "_core_proxies", {}).get(id(core))
        if proxy is None:
            raise RuntimeError("WebView has no cached cross-thread command proxy")
        return proxy

    def _require_owner_core(self, operation: str) -> Any:
        core = self._get_active_core()
        if core is None or not self._is_core_owner(core):
            raise RuntimeError(f"{operation} must run on the WebView owner thread")
        return core

    def _check_open(self) -> None:
        if getattr(self, "_close_requested", False):
            raise RuntimeError("WebView is closed; create a fresh WebView to reopen")

    @property
    def startup_error(self) -> Optional[Exception]:
        """Background owner failure, or None; inspect after ``wait(0)`` completes."""
        return getattr(self, "_startup_error", None)

    @property
    def cleanup_pending(self) -> bool:
        """True while timer cleanup still needs its owning host thread."""
        return getattr(self, "_timer_cleanup_pending", False)

    @property
    def close_pending(self) -> bool:
        """True when at least one native close request still needs a retry."""
        return bool(getattr(self, "_close_pending", {}))

    def _send_core_close(self, core: Any) -> None:
        """Send once per core, retaining unsuccessful targets for later retries."""
        core_id = id(core)
        if core_id in self._close_sent:
            return
        proxy = getattr(self, "_core_proxies", {}).get(core_id)
        try:
            if not self._is_core_owner(core):
                if not _request_close_via_channel(proxy):
                    raise RuntimeError("Could not send WebView close through its cached proxy")
            else:
                try:
                    core.close()
                except BaseException as exc:  # noqa: BLE001 - PyO3 panic is a BaseException
                    if not _is_panic_exception(exc):
                        raise
                    if not _request_close_via_channel(proxy):
                        raise RuntimeError(
                            "Could not send WebView close after native panic"
                        ) from exc
        except Exception as exc:
            # Keep the owner-created send-safe target independently of the
            # native core reference, which the owner may release on exit.
            self._close_pending[core_id] = (proxy, str(exc))
            self._close_send_done.clear()
            raise
        self._mark_close_sent(core_id)

    def _mark_close_sent(self, core_id: int) -> None:
        self._close_sent.add(core_id)
        self._close_pending.pop(core_id, None)
        if not self._close_pending:
            self._close_send_done.set()

    def _retry_pending_close(self, core_id: int, proxy: Any) -> None:
        """Retry a detached target using only its retained send-safe proxy."""
        if not _request_close_via_channel(proxy):
            message = "Could not retry WebView close through its retained send-safe proxy"
            self._close_pending[core_id] = (proxy, message)
            self._close_send_done.clear()
            raise RuntimeError(message)
        self._mark_close_sent(core_id)

    def _observe_native_close(self) -> None:
        """Record the pump's close indication separately from send/cleanup errors.

        This records an observed lifecycle event, not proof of native resource
        destruction or collection of Rust-held Python callbacks.
        """
        with self._lifecycle_lock:
            self._native_close_observed = True
            self._is_running = False
            timer = getattr(self, "_auto_timer", None)
            if timer is not None:
                # Publish pending host work before publishing native-close
                # observation, including the interval before observers start.
                self._timer_cleanup_pending = True
                self._host_cleanup_done.clear()
            self._closed_event.set()
        observe = getattr(timer, "_observe_close", None)
        if observe is not None:
            observe()

    def _cleanup_auto_timer(self) -> bool:
        """Claim cleanup briefly, then invoke observers without holding our lock."""
        with self._lifecycle_lock:
            timer = getattr(self, "_auto_timer", None)
            completed = getattr(self, "_host_cleanup_done", None)
            if timer is None:
                self._timer_cleanup_pending = False
                if completed is not None:
                    completed.set()
                return True
            if completed is None:
                completed = self._host_cleanup_done = threading.Event()
            completed.clear()
            self._timer_cleanup_pending = True
            if getattr(self, "_timer_cleanup_active", False):
                return False
            self._timer_cleanup_active = True

        try:
            can_cleanup = getattr(timer, "can_cleanup_from_current_thread", None)
            if can_cleanup is None or not can_cleanup():
                return False

            # A synchronous embedded loop still needs its final owner-thread
            # drain. Never stop the only host pump before its close is handled.
            if getattr(self, "_is_running", False) and self._show_thread is None:
                core = self._core
                if core is None or not self._is_core_owner(core):
                    return False
                try:
                    should_close = core.process_ipc_only()
                except Exception:
                    logger.warning("Owner event drain remains pending", exc_info=True)
                    return False
                if not should_close:
                    return False
                self._observe_native_close()
            try:
                if getattr(timer, "processing_events", False) is True:
                    # The timer must deliver its once-only close notification
                    # before callbacks and wrapper references are released.
                    timer.stop()
                    return False
                if timer.cleanup() is False:
                    return False
            except Exception:
                logger.warning("Host timer cleanup remains pending", exc_info=True)
                return False
            with self._lifecycle_lock:
                if self._auto_timer is timer:
                    self._auto_timer = None
                if self._auto_timer is not None:
                    return False
                self._timer_cleanup_pending = False
                completed.set()
                return True
        finally:
            with self._lifecycle_lock:
                self._timer_cleanup_active = False

    # Type hints for attributes from main class
    _core: Any
    _ready_events: Any
    _show_thread: Optional[threading.Thread]
    _is_running: bool
    _title: str
    _stored_url: Optional[str]
    _stored_html: Optional[str]
    _auto_timer: Any
    _bridge: Any
    _async_core: Any
    _async_core_lock: threading.Lock
    _cached_hwnd: Optional[int]
    _cached_hwnd_lock: threading.Lock
    _close_requested: bool
    _event_handlers: Any
    _event_handlers_lock: threading.Lock
    _in_blocking_event_loop: bool
    _singleton_registry: Any
    _window_id: Optional[str]

    def show(self, *, wait: Optional[bool] = None) -> None:
        """Show the WebView window (smart mode).

        Automatically detects standalone/embedded/packed mode and chooses the best behavior:
        - Packed mode: Runs as headless API server (no window, JSON-RPC via stdin/stdout)
        - Standalone window: Blocks until closed (unless wait=False)
        - Embedded window: Non-blocking, auto-starts timer if available

        Args:
            wait: Whether to wait for window to close
                - None: Auto-detect (standalone=True, embedded=False)
                - True: Block until window closes
                - False: Return immediately (background thread)

        Examples:
            >>> # Standalone window - auto-blocking
            >>> webview = WebView(title="My App")
            >>> webview.show()  # Blocks until closed

            >>> # Standalone window - force non-blocking
            >>> webview = WebView(title="My App")
            >>> webview.show(wait=False)  # Returns immediately
            >>> input("Press Enter to exit...")

            >>> # Embedded window - auto non-blocking
            >>> webview = WebView(title="Tool", parent=maya_hwnd)
            >>> webview.show()  # Returns immediately, timer auto-runs

            >>> # Packed mode - automatic API server (no code changes needed)
            >>> # When running in a packed .exe, show() automatically switches
            >>> # to API server mode. All bind_call() handlers work seamlessly.
        """
        # Check for packed mode first - transparent to developers
        from ..packed import (
            dump_cli_metadata,
            invoke_cli_command,
            is_cli_dump_mode,
            is_cli_invoke_mode,
            is_packed_mode,
            run_api_server,
        )

        # RFC 0018 (section 13.3): pack-time metadata dump short-circuits
        # before any window/server work. The packer runs the entry point with
        # AURORAVIEW_CLI_DUMP=1 purely to harvest CLI command metadata.
        if is_cli_dump_mode():
            logger.info("CLI dump mode detected: emitting command metadata and exiting")
            dump_cli_metadata(self)
            return

        # RFC 0018 (section 7): headless CLI invoke short-circuits before any
        # window/server work. The Rust launcher sets AURORAVIEW_CLI_INVOKE to
        # run one command and exit, without opening a window.
        if is_cli_invoke_mode():
            logger.info("CLI invoke mode detected: running command headlessly")
            invoke_cli_command(self)
            return

        if is_packed_mode():
            logger.info("Packed mode detected: running as API server")
            run_api_server(self)
            return

        # Detect mode
        is_embedded = getattr(self, "_is_embedded", False)

        if wait is None:
            wait = not is_embedded  # Standalone=blocking, Embedded=non-blocking

        if wait:
            self.show_blocking()
        else:
            self.show_async()

    def show_async(self) -> None:
        """Show the WebView window in non-blocking mode (compatibility helper).

        Equivalent to calling show(wait=False). Currently supported on Windows
        only. If already running, the call is ignored. After close, construct a
        fresh WebView instead of reusing native state from an earlier window.
        """
        self._show_non_blocking()

    def _show_non_blocking(self) -> None:
        """Start a Windows owner thread; other platforms require a host loop.

        Native Linux/macOS background-thread window creation has not been
        validated. Reject it before creating a thread or touching GUI state.
        Closed instances are single-use: create a new WebView to reopen.
        """
        with self._lifecycle_lock:
            self._check_open()
            if self._is_running:
                return
            if sys.platform != "win32":
                raise RuntimeError(
                    "Background-thread WebView windows are only supported on Windows; "
                    "Linux/macOS require a supported main-thread host integration"
                )
            self._is_running = True
            self._closed_event.clear()
            self._startup_error = None

        def _run_webview():
            """Create, register, show and release native state on its owner."""
            core = None
            try:
                if self._close_requested:
                    return
                # Share one normalized constructor snapshot with synchronous
                # creation, including content/security/network/download options.
                config = dict(self._core_kwargs)
                config.update(
                    url=self._stored_url,
                    html=self._stored_html,
                    title=self._title,
                    width=self._width,
                    height=self._height,
                    always_on_top=self._always_on_top,
                )
                core = self._core_factory(**config)
                self._track_core_thread(core)
                if self._core_proxies.get(id(core)) is None:
                    raise RuntimeError("Background WebView requires a send-safe native proxy")

                # Set up HWND callback to cache HWND for cross-thread access
                def on_hwnd_created(hwnd: int) -> None:
                    with self._cached_hwnd_lock:
                        self._cached_hwnd = hwnd
                    logger.info(f"Background thread: Cached HWND 0x{hwnd:X}")

                if hasattr(core, "set_on_hwnd_created"):
                    core.set_on_hwnd_created(on_hwnd_created)

                with self._lifecycle_lock:
                    if self._close_requested:
                        return
                    self._replay_event_bindings(core)
                    self._replay_api_bindings(core)
                    # Publish only after proxy and every binding are installed.
                    with self._async_core_lock:
                        self._async_core = core
                core.show()
            except Exception as e:
                self._startup_error = e
                logger.error(f"Error in background WebView: {e}", exc_info=True)
            finally:
                # Close-before-ready and construction failures must use this
                # same owner cleanup path, without joining the host UI thread.
                try:
                    try:
                        self.request_close()
                    except Exception:
                        logger.warning("Some native close requests remain pending", exc_info=True)
                    if core is not None:
                        with self._lifecycle_lock:
                            try:
                                self._send_core_close(core)
                            except Exception:
                                logger.warning("Owner close request remains pending", exc_info=True)
                finally:
                    with self._async_core_lock:
                        self._async_core = None
                    # Retain owner metadata for in-flight callers that already
                    # selected this core. Erasing it would make a stale foreign
                    # reference look like an untracked same-thread core.
                    with self._cached_hwnd_lock:
                        self._cached_hwnd = None
                    self._is_running = False
                    self._closed_event.set()

        # Create and start the background thread as daemon
        # CRITICAL: daemon=True allows Maya to exit cleanly when user closes Maya
        # The event loop now uses run_return() instead of run(), which prevents
        # the WebView from calling std::process::exit() and terminating Maya
        with self._lifecycle_lock:
            self._show_thread = threading.Thread(target=_run_webview, daemon=True)
            try:
                self._show_thread.start()
            except Exception:
                self._is_running = False
                self._closed_event.set()
                raise
        logger.info("WebView background thread started (daemon=True)")

    def show_blocking(self) -> None:
        """Show the WebView window (blocking - for standalone scripts).

        This method blocks until the window is closed. Use this in standalone scripts
        where you want the script to wait for the user to close the window.

        NOT recommended for DCC integration (Maya, Houdini, etc.) as it will freeze
        the main application.

        Example:
            >>> webview = WebView(title="My App", width=800, height=600)
            >>> webview.load_html("<h1>Hello</h1>")
            >>> webview.show_blocking()  # Blocks until window closes
            >>> print("Window was closed")
        """
        logger.info(f"Showing WebView (blocking): {self._title}")
        logger.info("Calling _core.show()...")
        self._check_open()
        core = self._require_owner_core("show_blocking")

        # Check if we're in embedded mode
        is_embedded = self._parent is not None  # Use new parameter name

        # Mark that we're entering blocking event loop
        # This tells eval_js to skip _auto_process_events since the event loop
        # will handle message queue processing automatically
        self._in_blocking_event_loop = True
        self._is_running = True
        self._closed_event.clear()

        try:
            core.show()
            logger.info("_core.show() returned successfully")
        except Exception as e:
            logger.error(f"Error in _core.show(): {e}", exc_info=True)
            raise
        finally:
            # Clear the flag when event loop exits
            self._in_blocking_event_loop = False
            if not is_embedded:
                self._is_running = False
                self.request_close()
                self._closed_event.set()

        # IMPORTANT: Only cleanup in standalone mode
        # In embedded mode, the window should stay open until explicitly closed
        if not is_embedded:
            logger.info("Standalone mode: WebView show_blocking() completed, cleaning up...")
            try:
                self.close()
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup: {cleanup_error}")
        else:
            logger.info("Embedded mode: WebView window is now open (non-blocking)")
            logger.info("IMPORTANT: Keep this Python object alive to prevent window from closing")
            logger.info("Example: __main__.webview = webview")

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for the WebView to close.

        Completion requires an observed native close or owner-loop return,
        accepted close sends and host cleanup. Host UI callbacks must use
        ``wait(timeout=0)`` to poll;
        never block a host thread needed for dispatch or native event pumping.
        ``close()`` itself never waits or joins a thread.
        If ``cleanup_pending`` is true, the timer's host thread must pump once
        or call ``close()`` again to finish cleanup; a stopped host stays pending.
        Neither an observed close flag nor a successful proxy send proves
        native resource destruction or GC.

        Args:
            timeout: Maximum time to wait in seconds (None = indefinitely)

        Returns:
            True if the WebView closed, False if timeout expired

        Example:
            >>> webview.show_async()
            >>> if webview.wait(timeout=60):
            ...     print("WebView closed by user")
            ... else:
            ...     print("Timeout waiting for WebView")
        """
        event = getattr(self, "_closed_event", None)
        if event is None:
            return not getattr(self, "_is_running", False) and not self.close_pending
        if threading.current_thread() is self._show_thread and not event.is_set():
            if timeout != 0:
                raise RuntimeError("The WebView owner thread cannot wait for itself")
        started = time.monotonic()
        if not event.wait(timeout):
            return False
        for name in ("_close_send_done", "_host_cleanup_done"):
            completed = getattr(self, name, None)
            if completed is not None:
                remaining = (
                    None if timeout is None else max(0.0, timeout - (time.monotonic() - started))
                )
                if not completed.wait(remaining):
                    return False
        return not self.cleanup_pending and not self.close_pending

    def close(self) -> None:
        """Request close without blocking; use ``wait(0)`` to observe completion.

        Closed instances cannot be shown again. Construct a fresh WebView when
        reopening a host tool, so stale proxies and callbacks cannot be reused.
        """
        self.request_close()

    def request_close(self) -> None:
        """Cancel admission once, and retry any native close sends that failed.

        Successful targets are not sent again. Failures do not skip other
        targets or registry cleanup; the first failure is raised afterwards.
        ``close_pending`` and ``wait(0)`` expose incomplete delivery.
        """
        lock = getattr(self, "_lifecycle_lock", None)
        if lock is None:
            lock = self._lifecycle_lock = threading.RLock()
        errors = []
        with lock:
            if not hasattr(self, "_close_sent"):
                self._close_sent = set()
                self._close_pending = {}
                self._close_send_done = threading.Event()
                self._close_send_done.set()
            if not getattr(self, "_close_requested", False):
                self._cancel_event_callbacks()
                self._cancel_pending_calls("WebView closed")
                self._close_requested = True
                self._teardown_telemetry()
            with self._async_core_lock:
                cores = [self._async_core, self._core]
            seen = set()
            for core in cores:
                if core is None or id(core) in seen:
                    continue
                seen.add(id(core))
                try:
                    self._send_core_close(core)
                except Exception as exc:
                    errors.append(exc)

            # An async owner can exit and clear _async_core after a failed
            # close send. Its pending proxy remains independently retryable;
            # never reacquire or invoke a foreign unsendable native core.
            for core_id, (proxy, _error) in list(self._close_pending.items()):
                if core_id in seen:
                    continue
                try:
                    self._retry_pending_close(core_id, proxy)
                except Exception as exc:
                    errors.append(exc)

            # Mark pending before publishing any native-close completion. The
            # actual timer cleanup can invoke user observers and must happen
            # after releasing this lock, including in reentrant close calls.
            if getattr(self, "_auto_timer", None) is not None:
                completed = getattr(self, "_host_cleanup_done", None)
                if completed is None:
                    completed = self._host_cleanup_done = threading.Event()
                completed.clear()
                self._timer_cleanup_pending = True

            if not getattr(self, "_is_running", False):
                event = getattr(self, "_closed_event", None)
                if event is not None:
                    event.set()

        if not self._cleanup_auto_timer():
            logger.warning("WebView timer cleanup is pending on its owning host thread")

        # Python registry cleanup does not wait for native teardown.
        for key, instance in list(self._singleton_registry.items()):
            if instance is self:
                del self._singleton_registry[key]
                logger.info(f"Removed from singleton registry: '{key}'")
                break

        # Remove from WindowManager
        if getattr(self, "_window_id", None):
            from ..window_manager import get_window_manager

            wm = get_window_manager()
            wm.unregister(self._window_id)
            logger.debug(f"WebView unregistered from WindowManager: {self._window_id}")

        logger.info("WebView close requested")
        if errors:
            raise errors[0]
