"""Disposable Blender add-on for measuring a minimal AuroraView page.

Run with ``vx just blender-loading-probe <blender.exe>`` after building Core.
No scene changes, external resources, Qt, or front-end framework are involved.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import queue
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import bpy

bl_info = {
    "name": "AuroraView Loading Probe",
    "blender": (4, 2, 0),
    "category": "Development",
}

ROOT = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
_probe = None


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint32),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("planes", ctypes.c_uint16),
        ("bit_count", ctypes.c_uint16),
        ("compression", ctypes.c_uint32),
        ("image_size", ctypes.c_uint32),
        ("x_pixels_per_meter", ctypes.c_int32),
        ("y_pixels_per_meter", ctypes.c_int32),
        ("colors_used", ctypes.c_uint32),
        ("colors_important", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("header", _BitmapInfoHeader), ("colors", ctypes.c_uint32 * 3)]


def desktop_page_pixel(hwnd):
    """Return a matching screen pixel, rather than a WebView DOM paint mark."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Point)]
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.GetPixel.restype = ctypes.c_int
    rect = _Rect()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    point = _Point(max(0, rect.right - 80), min(300, max(0, rect.bottom - 80)))
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return None
    dc = user32.GetDC(None)
    if not dc:
        return None
    try:
        color = gdi32.GetPixel(dc, point.x, point.y)
    finally:
        user32.ReleaseDC(None, dc)
    if color == -1:
        return None
    rgb = (color & 255, (color >> 8) & 255, (color >> 16) & 255)
    expected = (0x17, 0x3C, 0x2C)
    return (
        {"x": point.x, "y": point.y, "rgb": rgb}
        if all(abs(actual - target) <= 8 for actual, target in zip(rgb, expected))
        else None
    )


def desktop_screenshot(hwnd, path):
    """Write an uncompressed BMP of the actual desktop client rectangle."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    rect = _Rect()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetClientRect failed")
    point = _Point(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise OSError("ClientToScreen failed")
    width, height = rect.right, rect.bottom
    if width <= 0 or height <= 0:
        raise OSError("Empty client rectangle")
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.BitBlt.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint32,
    ]
    gdi32.GetDIBits.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfo),
        ctypes.c_uint32,
    ]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    if not screen or not memory or not bitmap:
        raise OSError("Desktop bitmap allocation failed")
    old = gdi32.SelectObject(memory, bitmap)
    try:
        if not gdi32.BitBlt(memory, 0, 0, width, height, screen, point.x, point.y, 0xCC0020):
            raise OSError("BitBlt failed")
        info = _BitmapInfo()
        info.header.size = ctypes.sizeof(_BitmapInfoHeader)
        info.header.width = width
        info.header.height = height
        info.header.planes = 1
        info.header.bit_count = 32
        data = ctypes.create_string_buffer(width * height * 4)
        if gdi32.GetDIBits(memory, bitmap, 0, height, data, ctypes.byref(info), 0) != height:
            raise OSError("GetDIBits failed")
        header = struct.pack("<2sIHHI", b"BM", 54 + len(data), 0, 0, 54)
        path.write_bytes(header + bytes(info.header) + data.raw)
    finally:
        gdi32.SelectObject(memory, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
    return width, height


@bpy.app.handlers.persistent
def _probe_exit_pre(user_exit):
    if _probe is None:
        return
    _probe.exit_locked = True
    retained = _probe.retained
    _probe.log(
        "exit_pre_observed",
        user_exit=bool(user_exit),
        state=retained.state if retained else None,
        completion=retained._control.completion_status() if retained else None,
        active_callbacks=retained._control.active_callbacks() if retained else None,
        since_request_ms=round((time.monotonic() - _probe.exit_request_time) * 1000, 2)
        if _probe.exit_request_time
        else None,
    )


class Probe:
    def __init__(self, args):
        self.args = args
        self.run = 0
        self.started = 0.0
        self.view = None
        self.retained = None
        self.pending_show = False
        self.retained_marker = None
        self.retained_reused = False
        self.dom_check_sent = False
        self.ping_sent = False
        self.binding_count = 0
        self.retained_open_count = 0
        self.exit_locked = False
        self.exit_request_time = None
        self.block_entered = threading.Event()
        self.deadline = 0.0
        self.closing = False
        self.next_open = None
        self.warmup = None
        self.finishing = False
        self.hold_hidden_until = None
        self.pixel_started = None
        self.pixel_logged = False
        self.first_ready_at = None
        self.file_switch_done = False
        self.unload_done = False
        self.last_tick = None
        self.max_tick_gap_ms = 0
        self.host_events = queue.Queue()
        self.last_eval = 0
        self.events = set()
        self.lock = threading.Lock()
        self.output = Path(args.output).resolve()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.profile = (
            Path(args.profile).resolve()
            if args.profile
            else self.output.parent / (self.output.stem + "-profile")
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.server.daemon_threads = True
        self.endpoint = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def log(self, event, **data):
        row = {
            "run": self.run,
            "event": event,
            "elapsed_ms": round((time.time() - self.started) * 1000, 2),
            **data,
        }
        with self.lock:
            self.events.add(event)
            with self.output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row) + "\n")
        print("LOADING_PROBE " + json.dumps(row), flush=True)

    def handler(self):
        probe = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                page = probe.page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if payload.pop("run") == probe.run:
                    event = payload.pop("event")
                    probe.log(event, **payload)
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

            def log_message(self, *_args):
                pass

        return Handler

    def page(self):
        config = {"run": self.run, "start": self.started * 1000, "endpoint": self.endpoint}
        page = PAGE.replace("__PROBE_CONFIG__", json.dumps(config))
        if self.args.retained:
            page = page.replace(
                "</html>",
                '<input id="retained-input" aria-label="Unsaved draft">'
                '<div style="height:1400px"></div></html>',
            )
        return page

    def open(self):
        # Only this main-thread method touches bpy; HTTP callbacks only log data.
        if self.exit_locked:
            self.log("open_rejected_host_exit")
            return
        if self.args.retained and self.retained is not None:
            state = self.retained.state
            if state == "closing":
                self.log("reopen_pending_close", state=state)
                return
            if state in ("closed", "failed"):
                self.retained = None
                self.view = None
            else:
                self.retained_reused = True
                self.retained_open_count += 1
                self.run += 1
                self.started = time.time()
                self.events.clear()
                self.last_tick = time.monotonic()
                self.log("open_requested", retained=True, reused=True, state=state)
                self.pixel_started = time.monotonic()
                self.pixel_logged = False
                self.retained.show()
                self.log("show_returned", retained=True, reused=True, hwnd=self.retained.get_hwnd())
                self.deadline = time.monotonic() + self.args.timeout
                self.dom_check_sent = False
                self.ping_sent = False
                return
        self.run += 1
        self.retained_reused = False
        self.retained_marker = None
        self.binding_count = 0
        self.retained_open_count = 1 if self.args.retained else 0
        self.ping_sent = False
        self.started = time.time()
        self.events.clear()
        self.closing = False
        self.pixel_started = None
        self.pixel_logged = False
        self.last_tick = time.monotonic()
        self.max_tick_gap_ms = 0
        self.log(
            "open_requested",
            blender=bpy.app.version_string,
            python=sys.version,
            source=self.args.source,
            profile=str(self.profile),
            started_epoch_ms=self.started * 1000,
            endpoint=self.endpoint,
            url=self.args.url,
            prewarm=self.args.prewarm,
            reopen_delay=self.args.reopen_delay,
        )
        import auroraview
        from auroraview import AuroraView

        self.log(
            "imported",
            core_version=auroraview.__version__,
            core_path=str(auroraview.__file__),
            binary_path=str(auroraview._core.__file__),
        )
        if self.args.source == "inline":
            content = {"html": self.page()}
        elif self.args.source == "file":
            page_path = self.output.parent / (self.output.stem + "-%d.html" % self.run)
            page_path.write_text(self.page(), encoding="utf-8")
            content = {"url": page_path.as_uri(), "allow_file_protocol": True}
        else:
            content = {"url": self.args.url or self.endpoint + "/"}
        self.view = AuroraView(
            title="AuroraView Loading Probe",
            width=640,
            height=420,
            debug=False,
            data_directory=str(self.profile),
            remote_debugging_port=self.args.cdp_port,
            dcc_mode=False if self.args.exit_at == "callback" else "auto",
            **content,
        )
        self.log("constructed")
        if self.args.ipc_probe or (self.args.retained and self.args.exit_at != "callback"):
            self.view.view.set_event_dispatcher(self.host_events.put)
        if self.args.retained:
            self.view.view.on("retained_probe_ping", self.receive_ping)
            if self.args.exit_at == "callback":
                self.view.view.on("retained_probe_block", self.block_callback)
        if self.args.ipc_probe:
            self.view.view.on("loading_probe_metrics", self.receive_metrics)
        if self.args.retained:
            from auroraview import RetainedWindow

            self.retained = RetainedWindow(self.view)
            if _probe_exit_pre not in bpy.app.handlers.exit_pre:
                bpy.app.handlers.exit_pre.append(_probe_exit_pre)
            # Preparation responsiveness starts with the actual prepare call.
            # Import and construction have separate timings above.
            self.log("prepare_started", retained=True)
            self.last_tick = time.monotonic()
            self.retained.prepare()
            self.log("prepare_requested", retained=True)
            self.pending_show = True
        else:
            self.view.show(wait=False)
            self.log("show_returned")
        self.deadline = time.monotonic() + self.args.timeout

    def tick(self):
        if self.exit_locked:
            return None
        now = time.monotonic()
        if self.last_tick is not None:
            self.max_tick_gap_ms = max(self.max_tick_gap_ms, (now - self.last_tick) * 1000)
        self.last_tick = now
        while not self.host_events.empty():
            self.host_events.get_nowait()()
        if self.args.retained and self.pending_show:
            state = self.retained.state
            if self.args.exit_at == "preparing":
                self.request_host_exit()
                return None
            if state == "failed":
                self.log("prepare_failed", error=str(self.retained.startup_error))
                return None
            if state == "hidden":
                if self.args.file_switch_at_hidden and not self.file_switch_done:
                    self.file_switch_done = True
                    bpy.ops.wm.read_factory_settings(use_empty=True)
                    self.log("file_switch_completed", retained_state=self.retained.state)
                    return 0.01
                if self.args.unload_at_hidden and not self.unload_done:
                    self.unload_done = True
                    retained = self.retained
                    self.log("unload_requested", retained_state=retained.state)
                    unregister()

                    def check_unload():
                        if not retained.wait(0):
                            return 0.02
                        from auroraview.core.retained_window import _blender_exit_pre

                        self.log(
                            "unload_completed",
                            completion=retained._control.completion_status(),
                            manager_handler_count=bpy.app.handlers.exit_pre.count(
                                _blender_exit_pre
                            ),
                        )
                        register()
                        self.log(
                            "reload_completed",
                            manager_handler_count=bpy.app.handlers.exit_pre.count(
                                _blender_exit_pre
                            ),
                        )
                        unregister()
                        bpy.ops.wm.quit_blender()
                        return None

                    bpy.app.timers.register(check_unload, first_interval=0.02, persistent=True)
                    return None
                # This is test-page readiness for the first display metric.
                # RetainedWindow's hidden/prepare contract remains native-only.
                if not {"dom_ready", "bridge_ready", "first-contentful-paint"} <= self.events:
                    return 0.01
                if self.first_ready_at is None:
                    self.first_ready_at = now
                if now - self.first_ready_at < self.args.ready_to_show_delay:
                    return 0.01
                self.pending_show = False
                self.log("prepared", hwnd=self.retained.get_hwnd())
                if self.args.exit_at == "hidden":
                    self.request_host_exit()
                    return None
                self.pixel_started = time.monotonic()
                self.retained.show()
                self.log("show_returned", retained=True, reused=False)
            return 0.01
        if self.args.retained and self.next_open is not None and self.view is not None:
            if self.retained.state != "hidden" or now < self.next_open:
                return 0.01
            self.next_open = None
            self.open()
            return 0.01
        if self.hold_hidden_until is not None:
            if self.retained.state != "hidden":
                return 0.01
            if "hidden_stable" not in self.events:
                self.log("hidden_stable", hwnd=self.retained.get_hwnd())
                self.hold_hidden_until = now + self.args.hold_hidden_seconds
            if now < self.hold_hidden_until:
                return 0.05
            self.hold_hidden_until = None
            self.retained.close()
            self.closing = True
            self.deadline = time.monotonic() + 10
            return 0.01
        if self.finishing:
            if not self.warmup.view.wait(0):
                return 0.01
            self.warmup = None
            bpy.ops.wm.quit_blender()
            return None
        if self.view is None:
            if self.next_open is not None:
                if now < self.next_open:
                    return 0.05
                self.next_open = None
                self.open()
                return 0.01
            return None
        if not self.closing and self.view.view.wait(0):
            self.log("closed_by_user")
            self.view = None
            return None
        if self.closing:
            if not self.view.view.wait(0):
                if time.monotonic() > self.deadline:
                    self.log("close_timeout")
                    return None
                return 0.01
            self.log("closed")
            if self.args.retained:
                self.retained = None
            if self.run < self.args.runs:
                self.view = None
                self.next_open = time.monotonic() + self.args.reopen_delay
                return 0.01
            self.view = None
            if self.args.quit:
                if self.warmup:
                    self.warmup.close()
                    self.finishing = True
                    return 0.01
                bpy.ops.wm.quit_blender()
            return None

        hwnd = self.view.get_hwnd()
        if hwnd and "window_visible" not in self.events:
            user32 = ctypes.windll.user32
            user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
            if user32.IsWindowVisible(hwnd):
                self.log("window_visible", hwnd=hwnd)
        if (
            self.args.retained
            and self.args.source != "url"
            and self.pixel_started is not None
            and not self.pixel_logged
            and "window_visible" in self.events
        ):
            pixel = desktop_page_pixel(hwnd)
            if pixel is not None:
                self.pixel_logged = True
                self.log(
                    "desktop_pixel_visible",
                    since_show_ms=round((time.monotonic() - self.pixel_started) * 1000, 2),
                    **pixel,
                )
                shot = self.output.with_name(f"{self.output.stem}-run{self.run}-desktop.bmp")
                try:
                    width, height = desktop_screenshot(hwnd, shot)
                    self.log(
                        "desktop_screenshot",
                        path=str(shot),
                        width=width,
                        height=height,
                    )
                except OSError as exc:
                    self.log("screenshot_error", error=str(exc))
        if (
            self.args.retained
            and self.args.exit_at == "visible"
            and "window_visible" in self.events
            and self.retained.state == "visible"
        ):
            self.request_host_exit()
            return None
        if self.args.retained and self.args.exit_at == "callback":
            if not self.block_entered.is_set() and "bridge_ready" in self.events:
                if "callback_requested" not in self.events:
                    self.log("callback_requested")
                    self.view.view.get_proxy().eval_js(
                        "window.auroraview.send_event('retained_probe_block', {})"
                    )
            if self.block_entered.is_set():
                self.request_host_exit()
                return None
        if self.args.retained and self.retained_reused and hwnd and not self.dom_check_sent:
            self.dom_check_sent = True
            check = {"run": self.run, "marker": self.retained_marker, "endpoint": self.endpoint}
            script = """(() => {
              const check = __CHECK__;
              const marker = document.body.dataset.retainedMarker;
              const input = document.getElementById('retained-input')?.value;
              const scrollY = window.scrollY;
              const preserved = marker === check.marker && input === 'unsaved-draft' && scrollY >= 200;
              fetch(check.endpoint + '/metrics', {
                method: 'POST', mode: 'cors',
                headers: {'Content-Type': 'text/plain'},
                body: JSON.stringify({
                  run: check.run, event: preserved ? 'dom_retained' : 'dom_lost',
                  marker, expected: check.marker, input, scroll_y: scrollY
                })
              });
            })();""".replace("__CHECK__", json.dumps(check))
            self.view.view.get_proxy().eval_js(script)
        if (
            self.args.retained
            and self.retained_reused
            and hwnd
            and "window_visible" in self.events
            and not self.ping_sent
        ):
            self.ping_sent = True
            self.view.view.get_proxy().eval_js(
                "window.auroraview.send_event('retained_probe_ping', {run: %d})" % self.run
            )
        if self.args.ipc_probe and hwnd and now - self.last_eval > 0.1:
            self.last_eval = now
            config = json.dumps(
                {"run": self.run, "start": self.started * 1000, "url": self.args.url}
            )
            script = """(() => {
              const config = __CONFIG__;
              const url = location.origin + location.pathname;
              if (url !== config.url || !window.auroraview?.isReady?.()) return;
              const paint = performance.getEntriesByName('first-contentful-paint')[0];
              if (!paint || window.__probeSent === config.run) return;
              window.__probeSent = config.run;
              window.auroraview.send_event('loading_probe_metrics', {
                run: config.run, url, title: document.title,
                heading: document.querySelector('h1')?.textContent?.trim(),
                navigation: performance.getEntriesByType('navigation')[0]?.toJSON(),
                page_ms: paint.startTime,
                since_open_ms: performance.timeOrigin + paint.startTime - config.start
              });
            })();""".replace("__CONFIG__", config)
            self.view.view.eval_js(script, auto_process=False)

        required = (
            {
                "window_visible",
                "desktop_pixel_visible",
                "desktop_screenshot",
                "dom_retained",
                "binding_once",
            }
            if self.args.retained and self.retained_reused and self.args.source != "url"
            else {"window_visible", "dom_retained", "binding_once"}
            if self.args.retained and self.retained_reused
            else {
                "window_visible",
                "desktop_pixel_visible",
                "desktop_screenshot",
                "first-contentful-paint",
                "bridge_ready",
            }
            if self.args.retained and self.args.source != "url"
            else {"window_visible", "first-contentful-paint", "bridge_ready"}
            if self.args.retained
            else {"window_visible", "snapshot"}
            if self.args.cdp_port
            else {"window_visible", "first-contentful-paint", "bridge_ready"}
        )
        aborted = bool(
            {
                "observer_timeout",
                "observer_error",
                "dom_lost",
                "binding_duplicate",
                "screenshot_error",
            }
            & self.events
        )
        complete = required <= self.events and not aborted
        if aborted:
            self.args.runs = self.run
        if complete and not self.args.quit and self.run >= self.args.runs:
            if "complete" not in self.events:
                self.log("complete", max_tick_gap_ms=round(self.max_tick_gap_ms, 2))
            return 0.05
        if complete or aborted or time.monotonic() > self.deadline:
            self.log(
                "complete" if complete else "page_timeout",
                max_tick_gap_ms=round(self.max_tick_gap_ms, 2),
            )
            if self.args.retained and complete and self.run < self.args.runs:
                if self.retained_marker is None:
                    self.retained_marker = "retained-%d" % self.run
                    self.view.view.get_proxy().eval_js(
                        "document.body.dataset.retainedMarker = %s; "
                        "document.getElementById('retained-input').value = 'unsaved-draft'; "
                        "window.scrollTo(0, 260)" % json.dumps(self.retained_marker)
                    )
                self.retained.hide()
                self.log("hide_requested", retained=True, hwnd=self.retained.get_hwnd())
                self.next_open = time.monotonic() + self.args.reopen_delay
            elif self.args.retained and complete and self.args.hold_hidden_seconds > 0:
                self.retained.hide()
                self.log("hide_requested", retained=True, hwnd=self.retained.get_hwnd())
                self.hold_hidden_until = float("inf")
            else:
                self.retained.close() if self.args.retained else self.view.close()
                self.closing = True
                self.deadline = time.monotonic() + 10
        return 0.01

    def receive_metrics(self, data):
        if data.get("run") != self.run:
            return
        data = {**data, "navigation": {**data.get("navigation", {}), "name": data["url"]}}
        self.log(
            "first-contentful-paint", **{key: value for key, value in data.items() if key != "run"}
        )
        self.log("bridge_ready")

    def receive_ping(self, data):
        self.binding_count += 1
        expected = data.get("run")
        self.log(
            "binding_once"
            if expected == self.run and self.binding_count == self.retained_open_count - 1
            else "binding_duplicate",
            count=self.binding_count,
            expected=expected,
        )

    def block_callback(self, _data):
        self.block_entered.set()
        self.log("callback_entered")
        time.sleep(3)
        self.log("callback_returned")

    def request_host_exit(self):
        self.exit_request_time = time.monotonic()
        self.log(
            "exit_requested",
            state=self.retained.state,
            completion=self.retained._control.completion_status(),
            active_callbacks=self.retained._control.active_callbacks(),
            hwnd=self.retained.get_hwnd(),
        )
        bpy.ops.wm.quit_blender()

    def stop(self):
        if self.retained:
            self.retained.close()
        elif self.view:
            self.view.close()
        if self.warmup:
            self.warmup.close()
        self.server.shutdown()
        self.server.server_close()


class AURORAVIEW_OT_loading_probe(bpy.types.Operator):
    bl_idname = "auroraview.loading_probe"
    bl_label = "Open Loading Probe"

    def execute(self, _context):
        if _probe.exit_locked:
            self.report({"INFO"}, "Blender is exiting")
            return {"CANCELLED"}
        if _probe.retained is not None and _probe.retained.state == "closing":
            self.report({"INFO"}, "The loading probe is still closing")
            return {"CANCELLED"}
        if _probe.view is not None and (
            _probe.retained is None or _probe.retained.state not in ("hidden", "closed", "failed")
        ):
            self.report({"INFO"}, "The loading probe is already open")
            return {"CANCELLED"}
        _probe.open()
        bpy.app.timers.register(
            _probe.tick,
            first_interval=0.01,
            persistent=_probe.args.file_switch_at_hidden,
        )
        return {"FINISHED"}


class AURORAVIEW_PT_loading_probe(bpy.types.Panel):
    bl_label = "AuroraView Loading Probe"
    bl_idname = "AURORAVIEW_PT_loading_probe"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Loading Probe"

    def draw(self, _context):
        self.layout.operator("auroraview.loading_probe")


def register():
    global _probe
    if _probe is None:
        _probe = Probe(options([]))
    bpy.utils.register_class(AURORAVIEW_OT_loading_probe)
    bpy.utils.register_class(AURORAVIEW_PT_loading_probe)


def unregister():
    global _probe
    if _probe:
        if _probe_exit_pre in bpy.app.handlers.exit_pre:
            bpy.app.handlers.exit_pre.remove(_probe_exit_pre)
        if bpy.app.timers.is_registered(_probe.tick):
            bpy.app.timers.unregister(_probe.tick)
        _probe.stop()
        _probe = None
    bpy.utils.unregister_class(AURORAVIEW_PT_loading_probe)
    bpy.utils.unregister_class(AURORAVIEW_OT_loading_probe)


def options(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=str(ROOT / "python"))
    parser.add_argument("--source", choices=("inline", "http", "file", "url"), default="inline")
    parser.add_argument("--url", help="Remote URL (requires the CDP measurement runner)")
    parser.add_argument("--cdp-port", type=int)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--profile", help="WebView2 data directory; defaults beside the log")
    parser.add_argument("--output", default=str(ROOT / "target/loading-probe/events.jsonl"))
    parser.add_argument("--quit", action="store_true")
    parser.add_argument(
        "--retained",
        action="store_true",
        help="Exercise one retained native window across hide/show cycles",
    )
    parser.add_argument(
        "--exit-at",
        choices=("none", "preparing", "hidden", "visible", "callback"),
        default="none",
        help="Request a real Blender exit at a retained lifecycle point",
    )
    parser.add_argument(
        "--prewarm", choices=("none", "import", "library", "hidden"), default="none"
    )
    parser.add_argument("--reopen-delay", type=float, default=0)
    parser.add_argument("--preprepare-delay", type=float, default=0)
    parser.add_argument("--hold-hidden-seconds", type=float, default=0)
    parser.add_argument("--ready-to-show-delay", type=float, default=0)
    parser.add_argument("--file-switch-at-hidden", action="store_true")
    parser.add_argument("--unload-at-hidden", action="store_true")
    parser.add_argument(
        "--ipc-probe",
        action="store_true",
        help="Measure URL paint using the bridge without enabling CDP",
    )
    args = parser.parse_args(argv)
    if args.runs < 1 or args.timeout <= 0:
        parser.error("runs and timeout must be positive")
    if args.source == "url" and (not args.url or not (args.cdp_port or args.ipc_probe)):
        parser.error("URL mode requires --url and either --cdp-port or --ipc-probe")
    if args.exit_at != "none" and not args.retained:
        parser.error("--exit-at requires --retained")
    if (args.file_switch_at_hidden or args.unload_at_hidden) and not args.retained:
        parser.error("lifecycle checks require --retained")
    return args


if __name__ == "__main__":
    args = options(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    sys.path.insert(0, str(Path(args.site).resolve()))
    _probe = Probe(args)
    register()

    def start():
        bpy.ops.auroraview.loading_probe()
        return None

    def prepare():
        import auroraview
        from auroraview import AuroraView

        _probe.started = time.time()
        _probe.log("prewarm_started", mode=args.prewarm)
        if args.prewarm == "hidden":
            _probe.warmup = AuroraView(
                title="Probe Warmup",
                html="<title>Probe Warmup</title><p>Warmup</p>",
                auto_show=False,
                debug=False,
                data_directory=str(_probe.profile),
                remote_debugging_port=args.cdp_port,
            )
            _probe.warmup.show(wait=False)
        elif args.prewarm == "library":
            auroraview.start_warmup(str(_probe.profile))

        def wait_ready():
            if args.prewarm == "hidden" and not _probe.warmup.get_hwnd():
                return 0.01
            if args.prewarm == "library" and not auroraview.is_warmup_complete():
                return 0.01
            _probe.log(
                "prewarm_ready",
                mode=args.prewarm,
                library_status=auroraview.get_warmup_status()
                if args.prewarm == "library"
                else None,
            )
            bpy.app.timers.register(start, first_interval=0.5 + args.preprepare_delay)
            return None

        bpy.app.timers.register(wait_ready, first_interval=0.01)
        return None

    bpy.app.timers.register(start if args.prewarm == "none" else prepare, first_interval=2.0)
