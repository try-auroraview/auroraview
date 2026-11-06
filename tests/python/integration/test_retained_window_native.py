"""Real WebView2 retained lifecycle checks on a Windows desktop."""

import ctypes
import sys
import threading
import time

import pytest

from auroraview import AuroraView, RetainedWindow
from auroraview.core.window_api import WindowAPI

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows WebView2 only")


def wait_state(window, expected, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if window.state == expected:
            return
        if window.state == "failed":
            raise AssertionError(f"Retained startup failed: {window.startup_error}")
        time.sleep(0.02)
    raise AssertionError(
        f"Expected {expected}, got {window.state}; native_events={window._control.native_events()}"
    )


def wait_snapshot(window, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = window._control.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"Native snapshot did not match: {window._control.snapshot()}")


def close_window(window):
    window.close()
    deadline = time.monotonic() + 10.0
    while not window.wait(0) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert window.wait(0)


def test_hidden_prepare_reuses_native_window_without_showing_it():
    tool = AuroraView(html="<html><body>Retained native test</body></html>")
    window = RetainedWindow(tool)
    user32 = ctypes.windll.user32
    try:
        window.prepare()
        wait_state(window, "hidden")
        hwnd = window.get_hwnd()
        assert hwnd and user32.IsWindow(hwnd)
        assert not user32.IsWindowVisible(hwnd)

        window.show()
        wait_state(window, "visible")
        assert user32.IsWindowVisible(hwnd)

        window.hide()
        wait_state(window, "hidden")
        assert not user32.IsWindowVisible(hwnd)

        window.show()
        wait_state(window, "visible")
        assert window.get_hwnd() == hwnd
    finally:
        close_window(window)
    assert window.wait(0)
    assert window.get_hwnd() is None


def test_window_operations_share_owner_snapshot_and_preserve_hidden_state():
    tool = AuroraView(html="<html><body>Window commands</body></html>")
    window = RetainedWindow(tool)
    api = WindowAPI(tool.view)
    try:
        window.prepare()
        wait_state(window, "hidden")
        proxy = tool.view.get_proxy()
        hwnd = window.get_hwnd()

        tool.set_title("facade title")
        wait_snapshot(window, lambda s: s["title"] == "facade title")
        tool.view.set_window_title("view title")
        wait_snapshot(window, lambda s: s["title"] == "view title")
        proxy.set_title("proxy title")
        wait_snapshot(window, lambda s: s["title"] == "proxy title")
        api.set_title("api title")
        wait_snapshot(window, lambda s: s["title"] == "api title")

        tool.move_to(130, 140)
        wait_snapshot(window, lambda s: (s["x"], s["y"]) == (130, 140))
        tool.view.set_position(150, 160)
        wait_snapshot(window, lambda s: (s["x"], s["y"]) == (150, 160))
        proxy.move_to(170, 180)
        wait_snapshot(window, lambda s: (s["x"], s["y"]) == (170, 180))
        api.set_position(190, 200)
        wait_snapshot(window, lambda s: (s["x"], s["y"]) == (190, 200))

        tool.set_size(500, 400)
        wait_snapshot(window, lambda s: (s["width"], s["height"]) == (500, 400))
        tool.view.sync_bounds(520, 420)
        wait_snapshot(window, lambda s: (s["width"], s["height"]) == (520, 420))
        proxy.set_size(540, 440)
        wait_snapshot(window, lambda s: (s["width"], s["height"]) == (540, 440))
        api.set_size(560, 460)
        snapshot = wait_snapshot(window, lambda s: (s["width"], s["height"]) == (560, 460))
        assert snapshot["visible"] is False
        assert api.get_bounds() == {key: snapshot[key] for key in ("x", "y", "width", "height")}
        assert proxy.position() == (snapshot["x"], snapshot["y"])
        assert proxy.inner_size() == (560, 460)
        assert proxy.window_title() == "api title"
        assert proxy.get_hwnd() == hwnd

        for name, args in (
            ("set_min_size", (200, 150)),
            ("set_max_size", (900, 800)),
            ("set_always_on_top", (True,)),
            ("set_resizable", (True,)),
            ("set_decorations", (True,)),
            ("minimize", ()),
            ("maximize", ()),
            ("unmaximize", ()),
            ("toggle_maximize", ()),
            ("restore", ()),
            ("set_fullscreen", (True,)),
            ("toggle_fullscreen", ()),
            ("center", ()),
        ):
            before = window._control.snapshot()["version"]
            getattr(proxy, name)(*args)
            wait_snapshot(window, lambda s, before=before: s["version"] > before)
            assert window._control.snapshot()["visible"] is False, name

        window.show()
        wait_state(window, "visible")
        assert window.get_hwnd() == hwnd
        assert api.get_state()["visible"] is True
        assert api.is_visible() == {"visible": True}
    finally:
        close_window(window)
    with pytest.raises(RuntimeError, match="closing"):
        proxy.set_title("late")


def test_confirmed_hooks_are_once_and_reentrant():
    class HookTool(AuroraView):
        def __init__(self):
            self.events = []
            super().__init__(html="<html><body>Hook test</body></html>")

        def on_show(self):
            self.events.append("show")
            self.view.get_proxy().window_title()

        def on_hide(self):
            self.events.append("hide")
            self.view.get_proxy().window_title()

        def on_close(self):
            self.events.append("close")
            self.view.close()

    tool = HookTool()
    window = RetainedWindow(tool)
    try:
        window.prepare()
        wait_state(window, "hidden")
        assert tool.events == []
        window.show()
        wait_state(window, "visible")
        window.show()
        time.sleep(0.05)
        assert tool.events == ["show"]
        window.hide()
        wait_state(window, "hidden")
        assert tool.events == ["show", "hide"]
    finally:
        close_window(window)
    assert tool.events == ["show", "hide", "close"]


def test_real_titlebar_x_hides_and_drag_cancel_does_not():
    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32 = ctypes.windll.user32
    tool = AuroraView(html="<html><body>X input</body></html>")
    window = RetainedWindow(tool)
    cursor = Point()
    user32.GetCursorPos(ctypes.byref(cursor))
    try:
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        rect = Rect()
        assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.SendMessageW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )
        user32.SendMessageW.restype = ctypes.c_ssize_t
        targets = []
        for y0 in range(rect.top + 5, min(rect.top + 70, rect.bottom), 5):
            for x0 in range(rect.right - 100, rect.right - 5, 5):
                point = (y0 << 16) | (x0 & 0xFFFF)
                if user32.SendMessageW(hwnd, 0x0084, 0, point) == 20:
                    targets.append((x0, y0))
        assert targets, f"No HTCLOSE hit region in {rect.left, rect.top, rect.right, rect.bottom}"
        x, y = targets[len(targets) // 2]
        user32.WindowFromPoint.argtypes = [Point]
        user32.WindowFromPoint.restype = ctypes.c_void_p

        def aim_at_x():
            for _ in range(5):
                user32.SetForegroundWindow(hwnd)
                user32.SetCursorPos(x, y)
                time.sleep(0.05)
                if user32.WindowFromPoint(Point(x, y)) == hwnd:
                    return
            raise AssertionError("Native X input target is occluded")

        aim_at_x()
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        wait_state(window, "hidden")
        assert "x_activated" in window._control.native_events()
        assert window.get_hwnd() == hwnd
        assert user32.IsWindow(hwnd)
        assert not user32.IsWindowVisible(hwnd)

        window.show()
        wait_state(window, "visible")
        aim_at_x()
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.SetCursorPos(rect.left + 80, rect.bottom - 80)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.1)
        assert window.state == "visible", window._control.native_events()
        assert window._control.native_events().count("x_activated") == 1
        assert user32.IsWindow(hwnd)

        # A cancelled press must not poison the next genuine X activation.
        time.sleep(0.3)
        assert not (user32.GetAsyncKeyState(0x01) & 0x8000)
        aim_at_x()
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        wait_state(window, "hidden")
        assert window._control.native_events().count("x_activated") == 2
        assert window.get_hwnd() == hwnd
    finally:
        user32.SetCursorPos(cursor.x, cursor.y)
        close_window(window)


@pytest.mark.parametrize("message,wparam", [(0x0112, 0xF060), (0x0010, 0)])
def test_other_native_close_sources_destroy(message, wparam):
    tool = AuroraView(html="<html><body>Close source</body></html>")
    window = RetainedWindow(tool)
    user32 = ctypes.windll.user32
    try:
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        if message == 0x0112:
            user32.SendMessageW.argtypes = (
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_size_t,
                ctypes.c_ssize_t,
            )
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.SendMessageW(hwnd, message, wparam, 0)
        else:
            assert user32.PostMessageW(hwnd, message, wparam, 0)
        deadline = time.monotonic() + 10.0
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert window.wait(0), (
            f"state={window.state} error={window.startup_error} "
            f"flags={window._control.completion_status()} hwnd_alive={user32.IsWindow(hwnd)} "
            f"native_events={window._control.native_events()}"
        )
        assert window.state == "closed"
        assert not user32.IsWindow(hwnd)
    finally:
        if not window.wait(0):
            close_window(window)


@pytest.mark.parametrize("source", ["alt_f4", "system_menu"])
def test_real_keyboard_close_sources_destroy(source):
    tool = AuroraView(html="<html><body>Keyboard close</body></html>")
    window = RetainedWindow(tool)
    user32 = ctypes.windll.user32

    def key(vk, up=False):
        user32.keybd_event(vk, 0, 0x0002 if up else 0, 0)
        time.sleep(0.03)

    try:
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        assert user32.SetForegroundWindow(hwnd)
        foreground_deadline = time.monotonic() + 2
        while user32.GetForegroundWindow() != hwnd and time.monotonic() < foreground_deadline:
            time.sleep(0.02)
        assert user32.GetForegroundWindow() == hwnd
        time.sleep(0.1)
        key(0x12)
        if source == "alt_f4":
            key(0x73)
            key(0x73, up=True)
            key(0x12, up=True)
        else:
            key(0x20)
            key(0x20, up=True)
            key(0x12, up=True)
            key(0x43)
            key(0x43, up=True)
        deadline = time.monotonic() + 5.0
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert window.wait(0), (
            f"source={source} state={window.state} events={window._control.native_events()}"
        )
        assert not user32.IsWindow(hwnd)
    finally:
        if not window.wait(0):
            close_window(window)


def test_mouse_opened_system_menu_close_destroys():
    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    user32 = ctypes.windll.user32
    tool = AuroraView(html="<p>Mouse system menu</p>")
    window = RetainedWindow(tool)
    try:
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        rect = Rect()
        assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.SendMessageW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )
        user32.SendMessageW.restype = ctypes.c_ssize_t
        points = [
            (x, y)
            for x in range(rect.left + 5, rect.left + 60, 5)
            for y in range(rect.top + 5, rect.top + 50, 5)
            if user32.SendMessageW(hwnd, 0x0084, 0, (y << 16) | (x & 0xFFFF)) == 3
        ]
        assert points, "No HTSYSMENU hit region"
        x, y = points[len(points) // 2]
        assert user32.SetForegroundWindow(hwnd)
        user32.SetCursorPos(x, y)
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.1)
        user32.keybd_event(0x43, 0, 0, 0)
        user32.keybd_event(0x43, 0, 0x0002, 0)
        deadline = time.monotonic() + 5
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert window.wait(0), window._control.native_events()
        assert "system_close" in window._control.native_events()
        assert not user32.IsWindow(hwnd)
    finally:
        if not window.wait(0):
            close_window(window)


def test_host_exit_closes_ready_window_without_blender_timer(monkeypatch):
    monkeypatch.setattr(RetainedWindow, "_exiting", False)
    tool = AuroraView(html="<html><body>Host exit</body></html>")
    window = RetainedWindow(tool)
    try:
        window.prepare()
        wait_state(window, "hidden")
        hwnd = window.get_hwnd()
        window._stop_poll_timer()
        RetainedWindow.close_all_for_exit(timeout=2.0)
        assert window.wait(0)
        assert window.state == "closed"
        assert not ctypes.windll.user32.IsWindow(hwnd)
    finally:
        if not window.wait(0):
            close_window(window)


def test_host_exit_during_preparation_never_reports_false_completion(monkeypatch):
    monkeypatch.setattr(RetainedWindow, "_exiting", False)

    class Tool(AuroraView):
        def __init__(self):
            self.closed = 0
            super().__init__(html="<html><body>Preparing exit</body></html>")

        def on_close(self):
            self.closed += 1

    tool = Tool()
    window = RetainedWindow(tool)
    window.prepare()
    RetainedWindow.close_all_for_exit(timeout=0.01)
    if not window.wait(0):
        assert window.state == "closing"
        assert tool.closed == 0
    assert window._control.native_done(15.0)
    assert window.wait(0)
    assert tool.closed == 1


def test_adapter_install_failure_releases_created_hwnd_before_terminal_state():
    tool = AuroraView(html="<html><body>Adapter failure</body></html>")
    window = RetainedWindow(tool)
    if not hasattr(window._control, "fail_adapter_install_once"):
        window.close()
        pytest.skip("Native fault injection is available in debug builds")
    window._control.fail_adapter_install_once()
    window.prepare()
    wait_state(window, "failed")
    hwnd = window._control.last_created_hwnd()
    assert hwnd is not None
    assert not ctypes.windll.user32.IsWindow(hwnd)
    assert window.get_hwnd() is None
    assert window._control.completion_status() == (True, True, True)
    assert "injected retained adapter" in str(window.startup_error)


def test_standalone_close_completes_on_creator_without_manager_polling():
    main_thread = threading.get_ident()
    closed = threading.Event()

    class Tool(AuroraView):
        def on_close(self):
            assert threading.get_ident() == main_thread
            closed.set()

    window = RetainedWindow(Tool(html="<html><body>Standalone close</body></html>"))
    try:
        window.prepare()
        wait_state(window, "hidden")
        window._stop_poll_timer()
        worker = threading.Thread(target=window.close)
        worker.start()
        worker.join(2)
        assert not worker.is_alive()
        deadline = time.monotonic() + 3
        while not closed.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert closed.is_set(), "on_close needs creator-thread dispatch without a manager poll"
        assert window._control.completion_status() == (True, True, True)
    finally:
        if not window.wait(0):
            window.close()
            window._poll()


def test_owner_thread_external_destroy_reports_real_release():
    user32 = ctypes.windll.user32
    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.DestroyWindow.restype = ctypes.c_int
    invoked = threading.Event()
    holder = {}

    def destroy(_data):
        hwnd = holder["hwnd"]
        assert user32.DestroyWindow(hwnd)
        invoked.set()

    tool = AuroraView(html="<html><body>External destroy</body></html>", dcc_mode=False)
    tool.view.on("external_destroy", destroy)
    window = RetainedWindow(tool)
    try:
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        holder["hwnd"] = hwnd
        tool.view.get_proxy().eval_js("window.auroraview.send_event('external_destroy', {})")
        deadline = time.monotonic() + 5
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert invoked.is_set()
        assert window.wait(0)
        assert not user32.IsWindow(hwnd)
        assert window._control.completion_status() == (True, True, True)
    finally:
        if not window.wait(0):
            close_window(window)


def test_host_exit_closes_multiple_windows_with_one_deadline(monkeypatch, tmp_path):
    monkeypatch.setattr(RetainedWindow, "_exiting", False)
    windows = [
        RetainedWindow(
            AuroraView(
                html=f"<p>Exit {number}</p>",
                data_directory=str(tmp_path / f"window-{number}"),
            )
        )
        for number in range(2)
    ]
    try:
        windows[0].show()
        windows[1].prepare()
        wait_state(windows[0], "visible")
        wait_state(windows[1], "hidden")
        hwnds = [window.get_hwnd() for window in windows]
        RetainedWindow.close_all_for_exit(timeout=2.0)
        assert all(window.wait(0) for window in windows)
        assert all(window._control.completion_status() == (True, True, True) for window in windows)
        assert all(not ctypes.windll.user32.IsWindow(hwnd) for hwnd in hwnds)
    finally:
        for window in windows:
            if not window.wait(0):
                close_window(window)


@pytest.mark.parametrize("explicit", [False, True])
def test_concurrent_retained_prepare_can_share_one_profile(tmp_path, explicit):
    profile = str(tmp_path / "shared-profile") if explicit else None
    windows = [
        RetainedWindow(AuroraView(html=f"<p>Shared {number}</p>", data_directory=profile))
        for number in range(2)
    ]
    try:
        for window in windows:
            window.prepare()
        for window in windows:
            wait_state(window, "hidden")
        assert all(window.get_hwnd() for window in windows)
    finally:
        for window in windows:
            close_window(window)


def test_host_exit_during_injected_native_create_delay_stays_pending(monkeypatch):
    monkeypatch.setattr(RetainedWindow, "_exiting", False)
    window = RetainedWindow(AuroraView(html="<p>Delayed create</p>"))
    if not hasattr(window._control, "delay_native_create_once"):
        window.close()
        pytest.skip("Native delay injection is available in debug builds")
    window._control.delay_native_create_once(300)
    window.prepare()
    RetainedWindow.close_all_for_exit(timeout=0.01)
    assert window.state == "closing"
    assert not window.wait(0)
    assert window._control.completion_status() != (True, True, True)
    deadline = time.monotonic() + 3
    while not window.wait(0) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert window.wait(0)
    assert window._control.completion_status() == (True, True, True)


@pytest.mark.parametrize("decorations", [True, False])
def test_retained_destroy_clears_hwnd_in_both_decoration_modes(decorations):
    window = RetainedWindow(AuroraView(html="<p>Decorations</p>", decorations=decorations))
    window.show()
    wait_state(window, "visible")
    hwnd = window.get_hwnd()
    close_window(window)
    assert not ctypes.windll.user32.IsWindow(hwnd)
    assert window.get_hwnd() is None


def test_reused_hwnd_cannot_reopen_closed_manager():
    user32 = ctypes.windll.user32
    previous = []
    for number in range(3):
        window = RetainedWindow(AuroraView(html=f"<p>Generation {number}</p>"))
        window.show()
        wait_state(window, "visible")
        hwnd = window.get_hwnd()
        assert user32.IsWindow(hwnd)
        assert window.state == "visible"
        close_window(window)
        assert not user32.IsWindow(hwnd)
        previous.append(window)
        for closed in previous:
            assert closed.get_hwnd() is None
            assert closed.wait(0)


def test_close_preempts_queued_business_messages():
    window = RetainedWindow(AuroraView(html="<p>Queue pressure</p>"))
    try:
        window.show()
        wait_state(window, "visible")
        proxy = window.view.view.get_proxy()
        for _ in range(2000):
            proxy.eval_js("void 0")
        started = time.monotonic()
        window.close()
        deadline = started + 2
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert window.wait(0)
        assert time.monotonic() - started < 2
    finally:
        if not window.wait(0):
            close_window(window)


def test_close_preempts_continuous_business_producer():
    window = RetainedWindow(AuroraView(html="<p>Continuous producer</p>"))
    stopped = threading.Event()
    produced = [0]
    producer = None
    try:
        window.show()
        wait_state(window, "visible")
        proxy = window.view.view.get_proxy()

        def send():
            while not stopped.is_set():
                try:
                    proxy.eval_js("void 0")
                    produced[0] += 1
                except RuntimeError:
                    return

        producer = threading.Thread(target=send)
        producer.start()
        ready_deadline = time.monotonic() + 2
        while produced[0] < 100 and time.monotonic() < ready_deadline:
            time.sleep(0.001)
        assert produced[0] >= 100
        started = time.monotonic()
        window.close()
        stopped.set()
        producer.join(2)
        assert not producer.is_alive()
        deadline = started + 2
        while not window.wait(0) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert window.wait(0)
    finally:
        stopped.set()
        if producer is not None:
            producer.join(2)
        if not window.wait(0):
            close_window(window)


def test_latest_hide_wins_after_full_command_batch():
    tool = AuroraView(html="<p>Visibility race</p>")
    window = RetainedWindow(tool)
    try:
        window.prepare()
        wait_state(window, "hidden")
        for number in range(128):
            tool.set_title(f"Queued {number}")
        window.show()
        window.hide()
        wait_snapshot(window, lambda snapshot: snapshot["title"] == "Queued 127")
        wait_state(window, "hidden")
        assert not ctypes.windll.user32.IsWindowVisible(window.get_hwnd())
    finally:
        close_window(window)
