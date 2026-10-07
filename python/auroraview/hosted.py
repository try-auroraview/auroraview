"""Private opt-in Linux host pump. Native Blender acceptance is outstanding.

The host supplies exactly one main-thread timer and a bounded call dispatcher.
There is no background GTK route and this module does not change capabilities.
"""

import sys
import threading
from typing import Any, Dict


def _require_main_thread() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Hosted GTK operations must run on the main thread")


class HostRuntime:
    """Own all experimental floating Linux views in one host process.

    Hosts must call shutdown before unregistering their pump. A False return
    indicates deferred native teardown, so the current dispatch must unwind.
    """

    def __init__(self, *, experimental: bool = False) -> None:
        _require_main_thread()
        if not experimental or sys.platform != "linux":
            raise RuntimeError("Hosted GTK requires Linux and experimental=True")
        from auroraview import _core

        native_factory = getattr(_core, "HostRuntime", None)
        if native_factory is None:
            raise RuntimeError("Core was not built with experimental-hosted-gtk")
        self._native = native_factory()
        self._views = {}  # type: Dict[int, Any]
        self._closed = False

    def show(self, view: Any) -> None:
        """Create a view with existing Core configuration, bridge, and IPC."""
        _require_main_thread()
        if self._closed:
            raise RuntimeError("HostRuntime is shut down")
        view._check_open()
        view._ensure_api_registry()
        if view._call_dispatcher is None:
            raise RuntimeError("Configure set_call_dispatcher before hosted creation")
        if getattr(view, "_is_running", False) or getattr(view, "_host_runtime", None):
            raise RuntimeError("Use a fresh WebView for hosted creation")
        core = view._require_owner_core("show_hosted")
        if getattr(view, "_auto_timer", None) is not None:
            raise RuntimeError("Hosted GTK requires one host-owned timer")
        # Capture a send-safe, read-only queue gate before native construction.
        # Reentrant finalizers must never reacquire or borrow unsendable Core.
        proxy = getattr(view, "_core_proxies", {}).get(id(core))
        gate = getattr(proxy, "callbacks_allowed", None)
        if not callable(gate):
            raise RuntimeError("Hosted GTK requires the Core proxy callback-admission gate")
        view._host_callback_gate = gate
        view._host_runtime = self
        view._is_running = True
        view._closed_event.clear()
        self._views[id(view)] = view
        try:
            self._native.show(core)
        except BaseException:
            view.request_close()
            view._observe_native_close()
            self._views.pop(id(view), None)
            raise

    def _reap(self) -> None:
        for key, view in list(self._views.items()):
            if view._core.lifecycle_state == "destroyed":
                view.request_close()
                view._observe_native_close()
                self._views.pop(key, None)

    def poll(
        self, *, max_iterations: int = 64, max_messages: int = 64, budget_ms: float = 2.0
    ) -> Dict[str, Any]:
        """Perform one shared nonblocking slice, then observe completed closes."""
        _require_main_thread()
        if self._closed:
            self._reap()
            return {"live_views": len(self._views), "shutdown_pending": bool(self._views)}
        try:
            return self._native.poll(max_iterations, max_messages, budget_ms)
        finally:
            self._reap()

    def shutdown(self) -> bool:
        """Cancel application work and release native state before stopping timers."""
        _require_main_thread()
        self._closed = True
        errors = []
        for view in list(self._views.values()):
            try:
                view.request_close()
            except Exception as error:
                errors.append(error)
        complete = self._native.shutdown()
        self._reap()
        if errors:
            raise RuntimeError("Hosted view cancellation failed") from errors[0]
        return complete and not self._views
