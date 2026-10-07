# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView JavaScript Interaction Mixin.

This module provides JavaScript interaction methods for the WebView class.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class WebViewJSMixin:
    """Mixin providing JavaScript interaction methods.

    Provides methods for JavaScript execution:
    - eval_js: Execute JavaScript synchronously
    - eval_js_async: Execute JavaScript with callback
    - eval_js_awaitable: Execute JavaScript with async/await
    - get_proxy: Get thread-safe proxy for cross-thread operations
    """

    # Type hints for attributes from main class
    _core: Any
    _async_core: Optional[Any]
    _async_core_lock: threading.Lock
    _post_eval_js_hook: Optional[Callable[[], None]]
    _in_blocking_event_loop: bool
    _event_processor: Optional[Any]

    def eval_js(self, script: str, auto_process: bool = True) -> None:
        """Execute JavaScript code in the WebView.

        Args:
            script: JavaScript code to execute
            auto_process: Automatically process message queue after execution (default: True).
                         Set to False if you want to batch multiple operations.

        Example:
            >>> webview.eval_js("console.log('Hello from Python')")

            >>> # Batch multiple operations
            >>> webview.eval_js("console.log('1')", auto_process=False)
            >>> webview.eval_js("console.log('2')", auto_process=False)
            >>> webview.process_events()  # Process all at once
        """
        logger.debug(f"Executing JavaScript: {script[:100]}...")

        t0 = time.monotonic()

        # Use the async core if available (when running in background thread)
        self._command_target().eval_js(script)

        # Auto-telemetry: record JS eval duration
        dt = (time.monotonic() - t0) * 1000.0
        if hasattr(self, "_telemetry_on_eval_js"):
            self._telemetry_on_eval_js(dt)

        # Call post eval_js hook if set (for Qt integration and testing)
        if self._post_eval_js_hook is not None:
            self._post_eval_js_hook()

        # Automatically process events to ensure immediate execution
        if auto_process:
            self._auto_process_events()

    def eval_js_async(
        self,
        script: str,
        callback: Optional[Callable[[Optional[str], Optional[Exception]], None]] = None,
        timeout_ms: int = 5000,
    ) -> None:
        """Execute JavaScript code asynchronously with result callback.

        Args:
            script: JavaScript code to execute. The last expression's value
                   will be returned as the result.
            callback: Optional callback function that receives (result, error).
            timeout_ms: Timeout in milliseconds (default: 5000)

        Example:
            >>> def on_result(result, error):
            ...     if error:
            ...         print(f"Error: {error}")
            ...     else:
            ...         print(f"Result: {result}")
            ...
            >>> webview.eval_js_async("document.title", on_result)
        """
        logger.debug(f"Executing JavaScript async: {script[:100]}...")

        # Wrap script to capture result
        # Note: callback is invoked synchronously after eval_js completes.
        # The callback_id pattern is reserved for future async bridge support.

        try:
            self._command_target().eval_js(script)

            if callback:
                callback(None, None)

        except Exception as e:
            logger.error(f"JavaScript execution failed: {e}")
            if callback:
                callback(None, e)

        self._auto_process_events()

    async def eval_js_awaitable(
        self,
        script: str,
        timeout_ms: int = 5000,
        poll_interval: float = 0.01,
    ) -> Optional[str]:
        """Execute JavaScript code and await the result.

        Args:
            script: JavaScript code to execute.
            timeout_ms: Timeout in milliseconds (default: 5000)
            poll_interval: Polling interval in seconds (default: 0.01)

        Returns:
            JSON string of the JavaScript return value, or None on error

        Raises:
            TimeoutError: If execution times out
            RuntimeError: If JavaScript execution fails

        Example:
            >>> import asyncio
            >>> async def get_title(webview):
            ...     title = await webview.eval_js_awaitable("document.title")
            ...     return title
        """
        logger.debug(f"Executing JavaScript awaitable: {script[:100]}...")

        # Result polling is not exposed by WebViewProxy. Reject cross-thread
        # use explicitly rather than entering an unsendable native object.
        core = self._require_owner_core("eval_js_awaitable")

        # Check if core supports eval_js_future
        if not hasattr(core, "eval_js_future"):
            logger.warning("Core does not support eval_js_future, using sync fallback")
            core.eval_js(script)
            self._auto_process_events()
            return None

        # Start async execution
        callback_id = core.eval_js_future(script, timeout_ms)
        self._auto_process_events()

        # Poll for result
        start_time = asyncio.get_event_loop().time()
        timeout_sec = timeout_ms / 1000.0

        while True:
            result = core.get_js_result(callback_id)
            status = result.get("status", "pending")

            if status == "complete":
                return result.get("result")
            elif status == "error":
                error_msg = result.get("error", "Unknown error")
                raise RuntimeError(f"JavaScript execution failed: {error_msg}")
            elif status == "timeout":
                raise TimeoutError(f"JavaScript execution timed out after {timeout_ms}ms")

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_sec:
                raise TimeoutError(f"JavaScript execution timed out after {timeout_ms}ms")

            self._auto_process_events()
            await asyncio.sleep(poll_interval)

    def get_proxy(self) -> Any:
        """Get a thread-safe proxy for cross-thread operations.

        Returns a WebViewProxy that can be safely shared across threads.
        Use this when you need to call `eval_js`, `emit`, etc. from a different
        thread than the one that created the WebView.

        This is essential for HWND mode where the WebView runs in a background
        thread but you need to call methods from the DCC main thread.

        Returns:
            WebViewProxy: A thread-safe proxy for WebView operations.
                The proxy supports:
                - eval_js(script): Execute JavaScript
                - eval_js_async(script, callback, timeout_ms): Async JavaScript
                - emit(event_name, data): Emit events to JavaScript
                - load_url(url): Load a URL
                - load_html(html): Load HTML content
                - reload(): Reload the current page

        Example:
            >>> # In HWND mode - WebView runs in background thread
            >>> def create_webview_thread():
            ...     webview = WebView(...)
            ...     proxy = webview.get_proxy()  # Get thread-safe proxy
            ...     self._proxy = proxy          # Store for cross-thread access
            ...     webview.show_blocking()
            ...
            >>> # From DCC main thread - safe!
            >>> self._proxy.eval_js("console.log('Hello from DCC!')")
            >>> self._proxy.emit("update", {"status": "ready"})

        Note:
            The proxy uses a message queue internally. Operations are queued
            and processed by the WebView's event loop on the correct thread.
        """
        # Use async core if available (when running in background thread)
        core = self._get_active_core()
        proxy = getattr(self, "_core_proxies", {}).get(id(core))
        if proxy is None:
            raise RuntimeError("WebView has no cached cross-thread command proxy")
        return proxy

    def _auto_process_events(self) -> None:
        """Automatically process events after emit() or eval_js().

        This method uses the strategy pattern:
        1. If in blocking event loop (HWND mode), skip - event loop handles it
        2. If an event processor is set, use it (UI framework integration)
        3. Otherwise, use default implementation (direct Rust call)
        """
        # Skip if we're in a blocking event loop
        if self._in_blocking_event_loop:
            logger.debug("Skipping _auto_process_events - in blocking event loop")
            return

        if getattr(self, "_show_thread", None) is not None:
            return
        core = self._get_active_core()
        if core is None or not self._is_core_owner(core):
            return

        try:
            if self._event_processor is not None:
                self._event_processor.process()
            else:
                core.process_events()
        except Exception as e:
            logger.debug(f"Auto process events failed (non-critical): {e}")
