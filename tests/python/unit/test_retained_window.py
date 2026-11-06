"""Public retained-window contract without opening a native window."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from auroraview import AuroraView, RetainedWindow
from auroraview._core import RetainedControl
from auroraview.core.window_api import WindowAPI

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows standalone only")


class Tool(AuroraView):
    def __init__(self):
        self.closed = 0
        super().__init__(html="<h1>Retained</h1>")

    def on_close(self):
        self.closed += 1


def test_standalone_main_interpreter_without_private_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "bpy", None)
    monkeypatch.setitem(sys.modules, "_xxsubinterpreters", None)
    tool = Tool()
    window = RetainedWindow(tool)
    window.close()
    assert window.wait(0)
    assert tool.closed == 1


def test_private_module_fallback_rejects_a_real_subinterpreter():
    interpreters = pytest.importorskip("_xxsubinterpreters")
    source = Path(__file__).resolve().parents[3] / "python/auroraview/core/retained_window.py"
    # Python 3.12 isolates extension modules by default; ctypes needs the shared GIL.
    child = (
        interpreters.create(isolated=False)
        if sys.version_info >= (3, 12)
        else interpreters.create()
    )
    try:
        interpreters.run_string(
            child,
            "import runpy, sys\n"
            "sys.modules['_xxsubinterpreters'] = None\n"
            f"module = runpy.run_path({str(source)!r})\n"
            "assert not module['_is_main_interpreter']()\n",
        )
    finally:
        interpreters.destroy(child)


def test_close_before_prepare_releases_registration_once():
    tool = Tool()
    window = RetainedWindow(tool)
    assert window.state == "new"
    assert window.get_hwnd() is None

    window.close()
    window.close()

    assert window.wait(0)
    assert window.state == "closed"
    assert tool.closed == 1
    assert tool not in AuroraView._instances


def test_blocking_legacy_entry_rejected_before_native_start():
    tool = Tool()
    window = RetainedWindow(tool)
    with pytest.raises(RuntimeError, match="non-blocking"):
        tool.view.show_blocking()
    with pytest.raises(RuntimeError, match="non-blocking"):
        tool.show(wait=True)
    assert window.state == "new"
    window.close()


def test_same_instance_cannot_be_retained_twice():
    tool = Tool()
    window = RetainedWindow(tool)
    with pytest.raises(ValueError, match="already retained"):
        RetainedWindow(tool)
    window.close()


def test_retention_releases_initial_core_on_host_thread():
    tool = Tool()
    initial_id = id(tool.view._core)
    window = RetainedWindow(tool)
    try:
        assert tool.view._core is None
        assert initial_id not in tool.view._core_threads
        assert initial_id not in tool.view._core_proxies
    finally:
        window.close()


def test_rejects_core_created_on_another_thread_without_taking_ownership():
    ready = threading.Event()
    release = threading.Event()
    holder = {}

    def create():
        tool = Tool()
        holder["tool"] = tool
        holder["core"] = tool.view._core
        holder["owner"] = threading.get_ident()
        ready.set()
        release.wait(2)
        tool.view.close()
        tool.view._core = None
        holder.pop("core", None)

    worker = threading.Thread(target=create)
    worker.start()
    assert ready.wait(2)
    tool = holder["tool"]
    try:
        with pytest.raises(RuntimeError, match="created on the host thread"):
            RetainedWindow(tool)
        assert tool.view._core is holder["core"]
        assert tool.view._core_threads[id(holder["core"])] == holder["owner"]
        assert getattr(tool, "_retained_window", None) is None
    finally:
        release.set()
        worker.join(3)


def test_retention_replays_bindings_even_if_python_reuses_initial_core_id():
    tool = Tool()
    tool.view.on("retained_ping", lambda _data: None)
    tool.view.bind_call("probe.ping", lambda _data: None)
    initial_id = id(tool.view._core)
    assert "retained_ping" in tool.view._registered_events[initial_id]
    assert "probe.ping" in tool.view._api_core_bindings[initial_id]
    window = RetainedWindow(tool)
    try:
        assert initial_id not in tool.view._registered_events
        assert initial_id not in tool.view._api_core_bindings
        tool.view.bind_call("probe.late", lambda _data: None)
        tool.view.on("retained_late", lambda _data: None)
    finally:
        window.close()


@pytest.mark.parametrize(
    "name,args",
    [
        ("focus", ()),
        ("set_focus", ()),
        ("move", (1, 2)),
        ("move_to", (1, 2)),
        ("set_position", (1, 2)),
        ("center", ()),
        ("resize", (320, 240)),
        ("set_size", (320, 240)),
        ("sync_bounds", (320, 240)),
        ("set_min_size", (100, 100)),
        ("set_max_size", (1000, 1000)),
        ("minimize", ()),
        ("maximize", ()),
        ("unmaximize", ()),
        ("toggle_maximize", ()),
        ("restore", ()),
        ("set_fullscreen", (True,)),
        ("toggle_fullscreen", ()),
        ("set_title", ("new",)),
        ("set_window_title", ("new",)),
        ("set_always_on_top", (True,)),
        ("set_resizable", (True,)),
        ("set_decorations", (True,)),
    ],
)
def test_window_operation_requires_native_ready(name, args):
    tool = Tool()
    window = RetainedWindow(tool)
    try:
        with pytest.raises(RuntimeError, match="not ready|proxy is not ready"):
            getattr(tool, name)(*args)
        with pytest.raises(RuntimeError, match="not ready|proxy is not ready"):
            getattr(tool.view, name)(*args)
        assert window.state == "new"
    finally:
        window.close()


@pytest.mark.parametrize(
    "name,args",
    [
        ("move", (1, 2)),
        ("move_to", (1, 2)),
        ("resize", (320, 240)),
        ("sync_bounds", (320, 240)),
        ("set_focus", ()),
        ("unmaximize", ()),
        ("toggle_maximize", ()),
        ("set_fullscreen", (True,)),
        ("set_window_title", ("new",)),
        ("set_decorations", (True,)),
    ],
)
def test_builtin_window_api_operation_requires_native_ready(name, args):
    tool = Tool()
    window = RetainedWindow(tool)
    api = WindowAPI(tool.view)
    try:
        with pytest.raises(RuntimeError, match="not ready|proxy is not ready"):
            getattr(api, name)(*args)
        assert window.state == "new"
    finally:
        window.close()


def test_native_condition_wait_releases_gil():
    control = RetainedControl()
    done = threading.Event()
    started = threading.Event()
    result = []

    def observe():
        started.set()
        result.append(control.native_done(0.2))
        done.set()

    worker = threading.Thread(target=observe)
    worker.start()
    assert started.wait(1)
    progress = 0
    while not done.is_set():
        progress += 1
    worker.join(1)
    assert result == [False]
    assert progress > 1000


def test_host_event_callback_uses_retained_inflight_guard():
    tool = Tool()
    window = RetainedWindow(tool)
    observed = []

    def callback(_data):
        observed.append(window._control.active_callbacks())
        window.close()

    tool.view.register_callback("business", callback)
    handler = tool.view._event_handlers["business"][0]
    handler({})
    assert observed == [1]
    assert window._control.active_callbacks() == 0
    handler({})
    assert observed == [1]


def test_bound_call_uses_retained_inflight_guard():
    tool = Tool()
    window = RetainedWindow(tool)
    observed = []

    def callback():
        observed.append(window._control.active_callbacks())
        window.close()

    handler = tool.view._create_ipc_handler("business", callback)
    handler({"id": "one"})
    assert observed == [1]
    assert window._control.active_callbacks() == 0
    handler({"id": "two"})
    assert observed == [1]


def test_confirmed_show_hide_hooks_are_drained_before_close_hook():
    class Hooks(Tool):
        def __init__(self):
            self.events = []
            super().__init__()

        def on_show(self):
            self.events.append("show")

        def on_hide(self):
            self.events.append("hide")

        def on_close(self):
            self.events.append("close")

    tool = Hooks()
    window = RetainedWindow(tool)
    original = window._control
    window._control = SimpleNamespace(
        state="closing",
        take_cancelled=lambda: [],
        take_visibility_transitions=lambda: [True, False],
        native_done=lambda _timeout: False,
    )
    try:
        window._poll()
        assert tool.events == ["show", "hide"]
    finally:
        window._control = original
        window.close()
    assert tool.events == ["show", "hide", "close"]


def test_accepted_command_cancellation_emits_once_before_cleanup():
    tool = Tool()
    received = []
    tool.view.on("window_command_failed", received.append)
    window = RetainedWindow(tool)
    original = window._control
    cancelled = [[(7, "set_title")], []]
    window._control = SimpleNamespace(
        state="closing",
        take_cancelled=lambda: cancelled.pop(0),
        take_visibility_transitions=lambda: [],
        native_done=lambda _timeout: False,
    )
    try:
        window._poll()
        window._poll()
        assert received == [
            {
                "window_id": tool.view._window_id,
                "request_seq": 7,
                "operation": "set_title",
                "message": "retained window closed before command application",
            }
        ]
    finally:
        window._control = original
        window.close()


def test_blender_exit_handler_belongs_to_live_managers(monkeypatch):
    from auroraview.core import retained_window as module

    handlers = []
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(handlers=SimpleNamespace(exit_pre=handlers, persistent=lambda fn: fn))
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    monkeypatch.setattr(RetainedWindow, "_exit_handler_registered", False)
    monkeypatch.setattr(RetainedWindow, "_instances", set())
    first, second = RetainedWindow(Tool()), RetainedWindow(Tool())
    assert handlers == [module._blender_exit_pre]
    first.close()
    assert handlers == [module._blender_exit_pre]
    second.close()
    assert handlers == []
    assert RetainedWindow._exit_handler_registered is False

    third = RetainedWindow(Tool())
    assert handlers == [module._blender_exit_pre]
    handlers.clear()  # A file switch or add-on reload removed this registration.
    fourth = RetainedWindow(Tool())
    assert handlers == [module._blender_exit_pre]
    third.close()
    fourth.close()
    assert handlers == []


def test_host_exit_uses_one_shared_deadline_and_attempts_every_close(monkeypatch):
    from auroraview.core.retained_window import RetainedWindow as Manager

    calls = []

    class Control:
        state = "closing"
        startup_error = None

        def __init__(self, name):
            self.name = name

        def native_done(self, timeout):
            calls.append((self.name, "wait", timeout))
            time.sleep(timeout)
            return False

        def get_hwnd(self):
            return None

        def completion_status(self):
            return (False, False, False)

        def active_callbacks(self):
            return 0

    class Instance:
        def __init__(self, name):
            self._webview = SimpleNamespace(_window_id=name)
            self._control = Control(name)

        def _stop_poll_timer(self):
            calls.append((self._webview._window_id, "timer"))

        def _stop_admission(self):
            calls.append((self._webview._window_id, "admission"))

        def close(self):
            calls.append((self._webview._window_id, "close"))

    first, second = Instance("first"), Instance("second")
    monkeypatch.setattr(Manager, "_instances", {first, second})
    monkeypatch.setattr(Manager, "_exiting", False)
    started = time.monotonic()
    Manager.close_all_for_exit(timeout=0.08)
    elapsed = time.monotonic() - started
    assert Manager._exiting
    assert sum(call[1] == "close" for call in calls) == 2
    waits = [call[2] for call in calls if call[1] == "wait"]
    assert len(waits) == 2
    assert max(waits) <= 0.081
    assert elapsed < 0.15
