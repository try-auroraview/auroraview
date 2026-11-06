"""Explicit session lifetime for one native standalone AuroraView window."""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, ClassVar, Optional, Set

if TYPE_CHECKING:
    from auroraview.integration.framework import AuroraView

logger = logging.getLogger(__name__)

_pending_lock = threading.Lock()
_pending_windows = {}
_pending_queue = deque()
_pending_next = 0
_pending_worker_running = False
_pending_callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)


@_pending_callback_type
def _dispatch_pending(token):
    with _pending_lock:
        window = _pending_windows.pop(token, None)
        if window is not None:
            window._pending_scheduled = False
    if window is not None:
        try:
            window._poll()
        except Exception:
            logger.exception("Retained host completion dispatch failed")
    return 0


_add_pending_call = ctypes.pythonapi.Py_AddPendingCall
_add_pending_call.argtypes = (_pending_callback_type, ctypes.c_void_p)
_add_pending_call.restype = ctypes.c_int


def _submit_pending() -> None:
    global _pending_worker_running
    while True:
        with _pending_lock:
            if not _pending_queue:
                _pending_worker_running = False
                return
            token = _pending_queue.popleft()
        if _add_pending_call(_dispatch_pending, token) != 0:
            with _pending_lock:
                _pending_queue.append(token)
            time.sleep(0.02)


def _is_main_interpreter() -> bool:
    try:
        import _xxsubinterpreters as interpreters
    except ImportError:
        if sys.implementation.name != "cpython":
            raise RuntimeError(
                "RetainedWindow requires CPython interpreter-state support"
            ) from None
        api = ctypes.pythonapi  # PyDLL keeps the GIL held during each C API call.
        current = api.PyThreadState_Get
        current.argtypes = ()
        current.restype = ctypes.c_void_p
        main = api.PyInterpreterState_Main
        main.argtypes = ()
        main.restype = ctypes.c_void_p
        if sys.version_info < (3, 9):
            # CPython 3.7/3.8 expose this prefix of PyThreadState in pystate.h.
            # Read only our live current state; never traverse another thread's state.
            class ThreadState(ctypes.Structure):
                _fields_ = [
                    ("prev", ctypes.c_void_p),
                    ("next", ctypes.c_void_p),
                    ("interp", ctypes.c_void_p),
                ]

            interpreter = ctypes.cast(current(), ctypes.POINTER(ThreadState)).contents.interp
        else:
            get_interpreter = api.PyThreadState_GetInterpreter
            get_interpreter.argtypes = (ctypes.c_void_p,)
            get_interpreter.restype = ctypes.c_void_p
            interpreter = get_interpreter(current())
        return interpreter == main()
    return interpreters.get_current() == interpreters.get_main()


class RetainedWindow:
    """Prepare one business WebView off the host thread and retain its DOM."""

    _instances: ClassVar[Set["RetainedWindow"]] = set()
    _exiting: ClassVar[bool] = False
    _exit_handler_registered: ClassVar[bool] = False

    def __init__(self, view: "AuroraView") -> None:
        from auroraview._core import RetainedControl
        from auroraview.integration.framework import AuroraView

        if not isinstance(view, AuroraView):
            raise TypeError("RetainedWindow requires an AuroraView instance")
        webview = view.view
        if getattr(view, "_retained_window", None) is not None:
            raise ValueError("AuroraView is already retained")
        if (
            getattr(webview, "_show_thread", None) is not None
            or getattr(webview, "_is_running", False)
            or getattr(webview, "_close_requested", False)
        ):
            raise ValueError("AuroraView has already started or closed")
        if sys.platform != "win32" or self._exiting:
            raise RuntimeError("RetainedWindow requires a running Windows host")
        if (
            getattr(view, "_parent", None) is not None
            or getattr(webview, "_parent", None) is not None
            or getattr(webview, "_is_embedded", False)
            or getattr(webview, "_core_factory", None) is None
            or getattr(webview, "_core_kwargs", {}).get("headless", False)
        ):
            raise RuntimeError("RetainedWindow requires a native standalone window")
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("RetainedWindow must be constructed on the host thread")
        initial = webview._core
        if initial is not None and webview._core_threads.get(id(initial)) != threading.get_ident():
            raise RuntimeError(
                "RetainedWindow requires the initial Core to be created on the host thread"
            )
        blender_host = False
        try:
            import bpy  # noqa: F401

            blender_host = True
        except ImportError:
            if not _is_main_interpreter():
                raise RuntimeError(
                    "RetainedWindow standalone host must use the main interpreter"
                ) from None

        self.view = view
        self._webview = webview
        self._host_thread = threading.get_ident()
        self._control = RetainedControl()
        self._control.set_window_id(webview._window_id or "")
        self._lock = threading.RLock()
        self._owner: Optional[threading.Thread] = None
        self._last_visible = False
        self._close_hook_sent = False
        self._cleaned = False
        self._timer = None
        self._blender_host = blender_host
        self._pending_scheduled = False
        self._phase_events = []
        self._ensure_blender_exit_handler()
        # The constructor core was created on this host thread. It must be
        # destroyed here; only the owner-created core may reach run_retained.
        webview._core = None
        if initial is not None:
            webview._core_threads.pop(id(initial), None)
            webview._core_proxies.pop(id(initial), None)
            webview._core_emitters.pop(id(initial), None)
            for registry_name in (
                "_registered_events",
                "_api_core_bindings",
                "_api_core_methods",
                "_protocol_core_bindings",
            ):
                getattr(webview, registry_name, {}).pop(id(initial), None)
            del initial
        view._retained_window = self
        webview._retained_window = self
        self._instances.add(self)

    @property
    def state(self) -> str:
        self._poll()
        return self._control.state

    @property
    def startup_error(self) -> Optional[Exception]:
        message = self._control.startup_error
        return RuntimeError(message) if message else None

    def get_hwnd(self) -> Optional[int]:
        return self._control.get_hwnd()

    def prepare(self) -> None:
        with self._lock:
            if self._control.state == "new":
                self._control.prepare()
                self._start()
            else:
                self._control.prepare()

    def show(self) -> None:
        with self._lock:
            was_new = self._control.state == "new"
            self._control.show(True)
            if was_new:
                self._start()
        self._poll()

    def set_visible(self, visible: bool) -> None:
        with self._lock:
            if visible:
                was_new = self._control.state == "new"
                self._control.show(False)
                if was_new:
                    self._start()
            else:
                self._control.hide()
        self._poll()

    def hide(self) -> None:
        self.set_visible(False)

    def close(self) -> None:
        with self._lock:
            was_new = self._control.state == "new"
            try:
                self._control.close()
            finally:
                if was_new:
                    self._control.native_skipped()
                    self._control.owner_returned()
                self._stop_admission()
        self._poll()
        self._schedule_host_poll()

    def wait(self, timeout: float = 0) -> bool:
        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        if timeout > 0 and threading.get_ident() == self._host_thread:
            raise ValueError("Host thread cannot block in RetainedWindow.wait")
        self._poll()
        return self._control.wait(float(timeout))

    def _start(self) -> None:
        if self._owner is not None:
            return
        if self._exiting:
            raise RuntimeError("Host is exiting")
        self._owner = threading.Thread(
            target=self._run,
            name="AuroraViewRetainedOwner",
            daemon=True,
        )
        self._webview._show_thread = self._owner
        self._webview._is_running = True
        try:
            self._owner.start()
        except Exception as exc:
            self._control.fail(str(exc))
            self._control.native_skipped()
            self._control.owner_returned()
            self._schedule_host_poll()
            self._webview._is_running = False
            raise
        self._start_poll_timer()

    def _run(self) -> None:
        core = None
        entered_native = False
        try:
            webview = self._webview
            self._mark_phase("owner_config")
            config = dict(webview._core_kwargs)
            config.update(
                url=webview._stored_url,
                html=webview._stored_html,
                title=webview._title,
                width=webview._width,
                height=webview._height,
                always_on_top=webview._always_on_top,
                auto_show=False,
            )
            self._mark_phase("owner_core_create")
            core = webview._core_factory(**config)
            self._mark_phase("owner_core_created")
            core.attach_retained(self._control)
            webview._track_core_thread(core)
            if webview._core_proxies.get(id(core)) is None:
                raise RuntimeError("Retained owner has no send-safe proxy")
            webview._replay_event_bindings(core)
            webview._replay_api_bindings(core)
            self._mark_phase("owner_bindings_ready")
            with webview._async_core_lock:
                webview._async_core = core
            entered_native = True
            self._mark_phase("native_enter")
            core.run_retained()
            self._mark_phase("native_return")
        except Exception as exc:
            self._mark_phase("owner_error")
            logger.exception("Retained owner failed")
            self._control.fail(str(exc))
            if not entered_native:
                self._control.native_skipped()
        finally:
            self._mark_phase("owner_cleanup")
            with self._webview._async_core_lock:
                self._webview._async_core = None
            self._webview._is_running = False
            self._webview._closed_event.set()
            core = None
            self._control.owner_returned()
            self._schedule_host_poll()

    def _mark_phase(self, phase: str) -> None:
        self._phase_events.append((time.monotonic(), phase))

    def _schedule_host_poll(self) -> None:
        if threading.get_ident() == self._host_thread:
            self._poll()
            return
        if self._blender_host:
            return
        with _pending_lock:
            if self._pending_scheduled:
                return
            self._pending_scheduled = True
            global _pending_next, _pending_worker_running
            _pending_next += 1
            token = _pending_next
            _pending_windows[token] = self
            _pending_queue.append(token)
            if _pending_worker_running:
                return
            _pending_worker_running = True
        # One worker retries queue-full submissions across all windows. The
        # callback itself performs host cleanup only on the creator thread.
        threading.Thread(target=_submit_pending, name="AuroraViewHostDispatch", daemon=True).start()

    def _stop_admission(self) -> None:
        webview = self._webview
        if not webview._close_requested:
            webview._close_requested = True
            webview._cancel_event_callbacks()
            webview._cancel_pending_calls("WebView closed")
            webview._teardown_telemetry()

    def _poll(self) -> None:
        if threading.get_ident() != self._host_thread:
            return
        state = self._control.state
        for request_seq, operation in self._control.take_cancelled():
            payload = {
                "window_id": self._webview._window_id or "",
                "request_seq": request_seq,
                "operation": operation,
                "message": "retained window closed before command application",
            }
            if self._exiting:
                logger.info("Retained window command cancelled during exit: %s", payload)
                continue
            handlers = tuple(getattr(self._webview, "_retained_failure_handlers", {}).values())
            for callback in handlers:
                try:
                    callback(payload)
                except Exception:
                    logger.exception("Retained command failure callback failed")
        transitions = self._control.take_visibility_transitions()
        for visible in transitions:
            self._last_visible = visible
            self._hook("on_show" if visible else "on_hide")
        if state == "closing":
            self._stop_admission()
        if (
            not self._cleaned
            and self._control.native_done(0)
            and self._control.active_callbacks() == 0
        ):
            self._finish()

    def _finish(self) -> None:
        if self._cleaned:
            return
        webview = self._webview
        self._stop_admission()
        if not webview._cleanup_auto_timer():
            logger.warning("Retained window host timer cleanup is pending")
            return
        self._stop_poll_timer()
        webview._core = None
        webview._core_proxies.clear()
        webview._core_emitters.clear()
        webview._core_threads.clear()
        with webview._cached_hwnd_lock:
            webview._cached_hwnd = None
        for key, value in list(webview._singleton_registry.items()):
            if value is webview:
                del webview._singleton_registry[key]
        from auroraview.core.window_manager import get_window_manager

        if webview._window_id:
            get_window_manager().unregister(webview._window_id)
        type(self.view)._instances.discard(self.view)
        self._instances.discard(self)
        getattr(webview, "_retained_failure_handlers", {}).clear()
        self._release_blender_exit_handler()
        self._cleaned = True
        self._control.host_cleaned()
        if not self._close_hook_sent:
            self._close_hook_sent = True
            self._hook("on_close")

    def _hook(self, name: str) -> None:
        started = time.monotonic()
        try:
            getattr(self.view, name)()
        except Exception:
            logger.exception("Retained window hook %s failed", name)
        finally:
            logger.debug("Retained hook %s took %.3f s", name, time.monotonic() - started)

    def _start_poll_timer(self) -> None:
        try:
            import bpy
        except ImportError:
            return

        def poll():
            self._poll()
            return None if self._cleaned else 0.02

        self._timer = poll
        bpy.app.timers.register(poll, first_interval=0.02, persistent=True)

    def _stop_poll_timer(self) -> None:
        timer = self._timer
        self._timer = None
        if timer is None:
            return
        try:
            import bpy

            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
        except (ImportError, ValueError):
            logger.debug("Retained poll timer already stopped", exc_info=True)

    @classmethod
    def _ensure_blender_exit_handler(cls) -> None:
        try:
            import bpy
        except ImportError:
            return
        if not hasattr(bpy.app.handlers, "exit_pre"):
            raise RuntimeError("Blender exit_pre is required for retained windows")
        handler = _blender_exit_pre
        bpy.app.handlers.persistent(handler)
        if handler not in bpy.app.handlers.exit_pre:
            bpy.app.handlers.exit_pre.append(handler)
        cls._exit_handler_registered = True

    @classmethod
    def _release_blender_exit_handler(cls) -> None:
        if cls._instances:
            return
        try:
            import bpy

            handlers = bpy.app.handlers.exit_pre
            if _blender_exit_pre in handlers:
                handlers.remove(_blender_exit_pre)
        except (ImportError, AttributeError, ValueError):
            logger.debug("Retained Blender exit handler already unavailable", exc_info=True)
        cls._exit_handler_registered = False

    @classmethod
    def close_all_for_exit(cls, timeout: float = 2.0) -> None:
        cls._exiting = True
        instances = tuple(cls._instances)
        for instance in instances:
            instance._stop_poll_timer()
            instance._stop_admission()
        for instance in instances:
            try:
                instance.close()
            except Exception:
                logger.exception("Retained window close request failed during host exit")
        deadline = time.monotonic() + timeout
        for instance in instances:
            remaining = max(0.0, deadline - time.monotonic())
            if instance._control.native_done(remaining):
                instance._poll()
                if instance._control.state in ("closed", "failed"):
                    logger.info(
                        "Retained window exit completed: window_id=%s native_released=%s "
                        "owner_returned=%s host_cleaned=%s active_callbacks=%s",
                        instance._webview._window_id,
                        *instance._control.completion_status(),
                        instance._control.active_callbacks(),
                    )
                    continue
            if instance._control.state not in ("closed", "failed"):
                logger.error(
                    "Retained window exit timed out: window_id=%s state=%s hwnd=%s "
                    "native_released=%s owner_returned=%s host_cleaned=%s "
                    "active_callbacks=%s error=%s",
                    instance._webview._window_id,
                    instance._control.state,
                    instance._control.get_hwnd(),
                    *instance._control.completion_status(),
                    instance._control.active_callbacks(),
                    instance._control.startup_error,
                )


def _blender_exit_pre(_user_exit: bool) -> None:
    RetainedWindow.close_all_for_exit()
