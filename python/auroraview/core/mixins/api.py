# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView API Binding Mixin.

This module provides API binding methods for the WebView class.
"""

from __future__ import annotations

import json
import logging
from threading import Lock, RLock
from typing import Any, Callable, Dict, Optional, Set

from ..packed import is_packed_mode

logger = logging.getLogger(__name__)


class WebViewApiMixin:
    """Mixin providing API binding methods.

    Provides methods for binding Python functions to JavaScript:
    - register_protocol: Register a custom protocol handler
    - bind_call: Bind a Python callable as an auroraview.call target
    - bind_api: Bind all public methods of an object
    - set_call_dispatcher: Schedule bound calls on the host's event loop

    Thread-Safety:
        All binding operations are protected by a lock to prevent race conditions
        when multiple threads attempt to bind APIs simultaneously.
    """

    # Type hints for attributes from main class
    _core: Any
    eval_js: Callable[[str], None]
    emit: Callable[..., None]

    # Registry of bound functions and lock for thread safety
    _bound_functions: Dict[str, Callable[..., Any]]
    _bound_namespaces: Set[str]  # Namespaces that have been bound (for idempotency)
    _bind_lock: Lock
    _is_loaded: bool  # Page loaded state

    def _init_api_registry(self) -> None:
        """Initialize the API binding registry.

        This should be called during WebView initialization to set up
        the internal registry for tracking bound functions and page state.
        """
        if not hasattr(self, "_bound_functions"):
            self._bound_functions = {}
        if not hasattr(self, "_bound_namespaces"):
            self._bound_namespaces = set()
        if not hasattr(self, "_bind_lock"):
            self._bind_lock = Lock()
        if not hasattr(self, "_is_loaded"):
            self._is_loaded = False
        if not hasattr(self, "_api_core_bindings"):
            self._api_core_bindings: Dict[int, Set[str]] = {}
            self._api_core_methods: Dict[int, Set[str]] = {}
            self._protocol_handlers: Dict[str, Callable] = {}
            self._protocol_core_bindings: Dict[int, Dict[str, Callable]] = {}
        if not hasattr(self, "_call_lock"):
            self._call_lock = RLock()
            self._call_dispatcher: Optional[Callable[[Callable[[], None]], None]] = None
            self._call_generation = 0
            self._pending_calls: Dict[object, Any] = {}
            self._calls_closed_reason: Optional[str] = None

    def _ensure_api_registry(self) -> None:
        """Ensure the API registry is initialized (lazy initialization)."""
        if (
            not hasattr(self, "_bound_functions")
            or not hasattr(self, "_bound_namespaces")
            or not hasattr(self, "_bind_lock")
            or not hasattr(self, "_call_lock")
        ):
            self._init_api_registry()

    def set_call_dispatcher(
        self, dispatcher: Optional[Callable[[Callable[[], None]], None]]
    ) -> None:
        """Set the scheduler used by ``bind_call`` and ``bind_api``.

        The scheduler receives a zero-argument callback. It must enqueue that
        callback on the host thread and return without waiting for its result.
        For example, a host timer can drain a queue filled by ``queue.put``.
        Bound functions remain synchronous; their result settles the existing
        JavaScript Promise after the scheduled callback has run.

        Pass ``None`` to restore the default: the existing asynchronous main-
        thread dispatcher in DCC mode, or direct invocation otherwise. Changing
        the scheduler affects future requests, not work already queued.
        DCC mode rejects calls if only the unsafe fallback dispatcher is
        available; supply a host scheduler explicitly in that case.
        """
        if dispatcher is not None and not callable(dispatcher):
            raise TypeError("Call dispatcher must be callable or None")
        self._ensure_api_registry()
        with self._call_lock:
            self._call_dispatcher = dispatcher

    def _api_registration_core(self) -> Any:
        """Select the native callback owner, or the packed Python registry."""
        getter = getattr(self, "_get_active_core", None)
        core = getter() if getter is not None else self._core
        if core is None and is_packed_mode():
            return None
        self._check_api_core_owner(core)
        return core

    def _check_api_core_owner(self, core: Any) -> None:
        if core is None:
            raise RuntimeError("WebView has no native core for API registration")
        check_owner = getattr(self, "_is_core_owner", None)
        if check_owner is not None and not check_owner(core):
            raise RuntimeError(
                "New API methods must be bound on the WebView owner thread; "
                "bind them before show_async(). Existing methods can be rebound."
            )

    def _register_api_bindings(self, core: Any, bindings: Dict[str, Callable]) -> None:
        """Register each native callback once. Caller holds ``_bind_lock``."""
        if core is None:
            return  # Packed stdio dispatch reads the Python registry directly.
        registered = self._api_core_bindings.setdefault(id(core), set())
        callbacks = [
            (name, self._create_ipc_handler(name, func))
            for name, func in bindings.items()
            if name not in registered
        ]
        if len(callbacks) > 1 and hasattr(core, "on_batch"):
            core.on_batch(callbacks)
            registered.update(name for name, _handler in callbacks)
        else:
            for name, handler in callbacks:
                core.on(name, handler)
                registered.add(name)

        # Track JavaScript publication separately so a failed registration can
        # be retried without appending native callbacks a second time.
        published = self._api_core_methods.setdefault(id(core), set())
        namespaces: Dict[str, list] = {}
        for name in bindings:
            if "." in name and name not in published:
                namespace, short_name = name.split(".", 1)
                namespaces.setdefault(namespace, []).append(short_name)
        for namespace, names in namespaces.items():
            core.register_api_methods(namespace, names)
            published.update(f"{namespace}.{name}" for name in names)

    def _replay_api_bindings(self, core: Any) -> None:
        """Replay bound APIs on a newly created native core's owner thread."""
        self._ensure_api_registry()
        self._check_api_core_owner(core)
        with self._bind_lock:
            self._register_api_bindings(core, self._bound_functions)
            protocols = self._protocol_core_bindings.setdefault(id(core), {})
            for scheme, handler in self._protocol_handlers.items():
                if protocols.get(scheme) is not handler:
                    core.register_protocol(scheme, handler)
                    protocols[scheme] = handler

    def _cancel_pending_calls(self, reason: str) -> None:
        """Invalidate queued calls before closing the native result channel.

        Already-running Python functions cannot be interrupted, but their late
        results are discarded. Callbacks that have not started become no-ops.
        A closed WebView cannot accept more calls; create a new instance instead.
        """
        self._ensure_api_registry()
        with self._call_lock:
            self._call_generation += 1
            self._calls_closed_reason = reason
            calls = list(self._pending_calls.values())
            self._pending_calls.clear()
            for call_id in calls:
                if call_id:
                    self._dispatch_call_result(
                        {
                            "id": call_id,
                            "ok": False,
                            "error": {"name": "CancelledError", "message": reason},
                        }
                    )

    def _set_loaded(self, loaded: bool = True) -> None:
        """Set the page loaded state.

        This should be called when the page finishes loading.

        Args:
            loaded: Whether the page is loaded (default True)
        """
        self._ensure_api_registry()
        self._is_loaded = loaded
        logger.debug("Page loaded state set to %s", loaded)

    def is_loaded(self) -> bool:
        """Check if the page has finished loading.

        Returns:
            True if page is loaded, False otherwise.
        """
        self._ensure_api_registry()
        return self._is_loaded

    def is_method_bound(self, method: str) -> bool:
        """Check if a method is already bound.

        Args:
            method: Method name to check (e.g., "api.echo")

        Returns:
            True if the method is already bound, False otherwise.
        """
        self._ensure_api_registry()
        return method in self._bound_functions

    def get_bound_methods(self) -> list:
        """Get list of all bound method names.

        Returns:
            List of bound method names.
        """
        self._ensure_api_registry()
        return list(self._bound_functions.keys())

    def register_protocol(self, scheme: str, handler: Callable[[str], Dict[str, Any]]) -> None:
        """Register a custom protocol handler.

        Args:
            scheme: Protocol scheme (e.g., "maya", "fbx")
            handler: Python function that takes URI string and returns dict with:
                - data (bytes): Response data
                - mime_type (str): MIME type (e.g., "image/png")
                - status (int): HTTP status code (e.g., 200, 404)

        Example:
            >>> def handle_fbx(uri: str) -> dict:
            ...     path = uri.replace("fbx://", "")
            ...     try:
            ...         with open(f"C:/models/{path}", "rb") as f:
            ...             return {
            ...                 "data": f.read(),
            ...                 "mime_type": "application/octet-stream",
            ...                 "status": 200
            ...             }
            ...     except FileNotFoundError:
            ...         return {
            ...             "data": b"Not Found",
            ...             "mime_type": "text/plain",
            ...             "status": 404
            ...         }
            ...
            >>> webview.register_protocol("fbx", handle_fbx)
        """
        self._ensure_api_registry()
        with self._bind_lock:
            core = self._api_registration_core()
            self._check_api_core_owner(core)
            core.register_protocol(scheme, handler)
            self._protocol_handlers[scheme] = handler
            self._protocol_core_bindings.setdefault(id(core), {})[scheme] = handler
        logger.debug(f"Registered custom protocol: {scheme}")

    def _emit_call_result_js(self, payload: Dict[str, Any]) -> None:
        """Internal helper to emit __auroraview_call_result via eval_js.

        This is a compatibility path for environments where the core
        event bridge does not reliably dispatch DOM CustomEvents.
        Uses window.auroraview.trigger() for consistent event handling.
        """
        try:
            json_str = json.dumps(payload)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to JSON-encode __auroraview_call_result payload: %s", exc)
            return

        # Use auroraview.trigger() for consistent event handling
        script = (
            "(function() {"
            "  if (window.auroraview && window.auroraview.trigger) {"
            f"    window.auroraview.trigger('__auroraview_call_result', JSON.parse({json_str!r}));"
            "  } else {"
            "    console.error('[AuroraView] Event bridge not ready, cannot emit call_result');"
            "  }"
            "})();"
        )
        logger.debug("Dispatching call result to JS: id=%s", payload.get("id"))
        try:
            self.eval_js(script)
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to dispatch __auroraview_call_result via eval_js: %s", exc)

    def _dispatch_call_result(self, payload: Dict[str, Any]) -> None:
        """Dispatch call result to JS with emit-first, eval_js fallback."""
        try:
            self.emit("__auroraview_call_result", payload)
            return
        except Exception:
            logger.debug(
                "WebView.emit for __auroraview_call_result raised; falling back to eval_js"
            )
        self._emit_call_result_js(payload)

    def bind_call(
        self,
        method: str,
        func: Optional[Callable[..., Any]] = None,
        *,
        allow_rebind: bool = True,
    ):
        """Bind a Python callable as an ``auroraview.call`` target.

        The JavaScript side sends messages of the form::

            {"id": "<request-id>", "params": ...}

        This helper unwraps the ``params`` payload, calls ``func`` and then
        emits a ``__auroraview_call_result`` event back to JavaScript so that
        the Promise returned by ``auroraview.call`` can resolve or reject.

        Usage::

            def echo(params):
                return params

            webview.bind_call("api.echo", echo)

        Or as a decorator::

            @webview.bind_call("api.echo")
            def echo(params):
                return params

        Args:
            method: Method name (e.g., "api.echo")
            func: Python callable to bind
            allow_rebind: If True (default), allows rebinding an already bound method.
                         If False, skips binding if method is already bound.

        Returns:
            The original function (for decorator usage)

        NOTE: Currently only synchronous callables are supported.
        """
        self._ensure_api_registry()

        # Decorator usage: @webview.bind_call("api.echo")
        if func is None:

            def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.bind_call(method, fn, allow_rebind=allow_rebind)
                return fn

            return decorator

        if not callable(func):
            raise TypeError("Bound call target must be callable")

        # A native callback resolves the latest Python function at invocation.
        # Rebinding must not append another callback to the native event list.
        with self._bind_lock:
            if method in self._bound_functions:
                if not allow_rebind:
                    logger.debug("Method '%s' already bound, skipping (allow_rebind=False)", method)
                    return func
                self._bound_functions[method] = func
                return func

            core = self._api_registration_core()
            self._register_api_bindings(core, {method: func})
            self._bound_functions[method] = func

        logger.info("Bound auroraview.call handler: %s", method)

        # For decorator-style usage, return the original function
        return func

    def bind_api(
        self,
        api: Any,
        namespace: str = "api",
        *,
        allow_rebind: bool = False,
    ) -> None:
        """Bind all public methods of an object under a namespace.

        This is a convenience helper so that you can expose a Python "API" object
        to JavaScript without writing many ``bind_call`` lines by hand.

        Idempotency:
            This method is idempotent at the namespace level. If a namespace has
            already been bound, subsequent calls will be silently skipped unless
            ``allow_rebind=True`` is explicitly specified. This prevents accidental
            duplicate bindings and eliminates the need for callers to track binding
            state.

        Example::

            class API:
                def echo(self, message: str) -> str:
                    return message

            api = API()
            webview.bind_api(api)  # JS: await auroraview.api.echo({"message": "hi"})
            webview.bind_api(api)  # Safe: silently skipped (idempotent)

        Args:
            api: Object whose public callables should be exposed.
            namespace: Logical namespace prefix used on the JS side (default: "api").
            allow_rebind: If True, allows rebinding an already bound namespace.
                         If False (default), skips binding if namespace is already
                         bound (idempotent behavior).

        Thread-Safety:
            This method is thread-safe and uses locking internally.

        Performance:
            Optimized to minimize Python-Rust boundary crossings and redundant operations:
            - Namespace-level idempotency check (O(1) set lookup)
            - Single pass collection of methods with callable references
            - Batch IPC handler registration
            - Single Rust call for JS method registration
        """
        self._ensure_api_registry()

        # Check before inspecting the object: skipped namespaces must not even
        # evaluate its properties. Recheck under the lock after collection.
        with self._bind_lock:
            if namespace in self._bound_namespaces and not allow_rebind:
                return

        methods: Dict[str, Callable] = {}
        for name in dir(api):
            if not name.startswith("_"):
                attr = getattr(api, name)
                if callable(attr):
                    methods[f"{namespace}.{name}"] = attr

        with self._bind_lock:
            if namespace in self._bound_namespaces and not allow_rebind:
                return
            methods = {
                name: func
                for name, func in methods.items()
                if allow_rebind or name not in self._bound_functions
            }
            if not methods:
                return
            new_methods = {
                name: func for name, func in methods.items() if name not in self._bound_functions
            }
            if new_methods:
                core = self._api_registration_core()
                self._register_api_bindings(core, new_methods)
            self._bound_functions.update(methods)
            self._bound_namespaces.add(namespace)

        logger.info("Bound %d API methods for namespace '%s'", len(methods), namespace)

    def is_namespace_bound(self, namespace: str) -> bool:
        """Check if a namespace has been bound.

        Args:
            namespace: The namespace to check (e.g., "api").

        Returns:
            True if the namespace has been bound, False otherwise.
        """
        self._ensure_api_registry()
        return namespace in self._bound_namespaces

    def _create_ipc_handler(self, method: str, func: Callable[..., Any]) -> Callable:
        """Create an IPC handler for a bound method (internal).

        This creates a handler function without registering it, allowing for
        batch registration of multiple handlers.

        Args:
            method: Full method name (e.g., "api.echo")
            func: Python callable to invoke

        Returns:
            Handler function to be registered with the IPC system.
        """

        def _handler(raw: Dict[str, Any]) -> None:
            import time as _time

            call_id = raw.get("id") or raw.get("__auroraview_call_id")
            has_params_key = "params" in raw
            params = raw.get("params")
            token = object()
            started = False
            host_backend = None

            with self._call_lock:
                if self._calls_closed_reason is not None:
                    if call_id:
                        self._dispatch_call_result(
                            {
                                "id": call_id,
                                "ok": False,
                                "error": {
                                    "name": "CancelledError",
                                    "message": self._calls_closed_reason,
                                },
                            }
                        )
                    return
                generation = self._call_generation
                self._pending_calls[token] = call_id
                dispatcher = self._call_dispatcher

            def _finish(payload: Dict[str, Any]) -> None:
                with self._call_lock:
                    if generation != self._call_generation or token not in self._pending_calls:
                        return
                    del self._pending_calls[token]
                    if call_id:
                        self._dispatch_call_result(payload)

            def _error(exc: Exception) -> Dict[str, Any]:
                return {
                    "id": call_id,
                    "ok": False,
                    "error": {"name": exc.__class__.__name__, "message": str(exc)},
                }

            def _invoke() -> None:
                nonlocal started
                with self._call_lock:
                    if (
                        started
                        or generation != self._call_generation
                        or token not in self._pending_calls
                    ):
                        return
                    started = True

                _t0 = _time.monotonic()
                # Resolve on execution, so hot-reloads also affect queued work.
                current_func = self._bound_functions.get(method, func)
                try:
                    if host_backend is not None and not host_backend.is_main_thread():
                        raise RuntimeError("Host dispatcher did not execute on the main thread")
                    if not has_params_key:
                        result = current_func()
                    elif isinstance(params, dict):
                        result = current_func(**params)
                    elif isinstance(params, list):
                        result = current_func(*params)
                    else:
                        result = current_func(params)
                    payload = {"id": call_id, "ok": True, "result": result}
                    if call_id:
                        # Validate before emit: a non-JSON result must reject
                        # the Promise rather than disappearing in the bridge.
                        # Normalize tuples and JSON object keys as well: the
                        # native converter only accepts lists and string keys.
                        payload = json.loads(json.dumps(payload, allow_nan=False))
                except Exception as exc:
                    payload = _error(exc)
                    logger.exception("Error in bound call '%s'", method)

                # Telemetry must not prevent a Promise from settling.
                try:
                    if not payload["ok"] and hasattr(self, "_telemetry_on_error"):
                        self._telemetry_on_error(f"ipc:{method}")
                    if hasattr(self, "_telemetry_on_ipc_call"):
                        self._telemetry_on_ipc_call(method, (_time.monotonic() - _t0) * 1000.0)
                except Exception:
                    logger.debug("Failed to record IPC telemetry", exc_info=True)
                _finish(payload)

            try:
                if dispatcher is not None:
                    dispatcher(_invoke)
                elif getattr(self, "_dcc_mode", False):
                    from auroraview.utils.thread_dispatcher import (
                        get_dispatcher_backend,
                        run_on_main_thread,
                    )
                    from auroraview.utils.thread_dispatcher.backends.fallback import (
                        FallbackDispatcherBackend,
                    )

                    host_backend = get_dispatcher_backend()
                    if isinstance(host_backend, FallbackDispatcherBackend):
                        raise RuntimeError(
                            "No host main-thread dispatcher is available; "
                            "configure set_call_dispatcher() before making DCC calls"
                        )
                    run_on_main_thread(_invoke)
                else:
                    _invoke()
            except Exception as exc:
                # A scheduler may enqueue and then fail. Removing the token
                # also prevents that queued callback from executing later.
                logger.exception("Failed to dispatch bound call '%s'", method)
                _finish(_error(exc))

        return _handler

    def _register_ipc_handler(self, method: str, func: Callable[..., Any]) -> None:
        """Register a bound method through the same idempotent binding path.

        Args:
            method: Full method name (e.g., "api.echo")
            func: Python callable to invoke
        """
        self.bind_call(method, func)
