# -*- coding: utf-8 -*-
"""Smoke tests for the Qt host adapter.

``AuroraViewQtHost`` attaches the dispatcher tick to a QTimer so tool calls
run on the thread that owns the WebView. It is the one piece that only
misbehaves inside a real DCC, so it gets a smoke test here: a stub Qt module
is injected via ``sys.modules``, which lets us construct and drive the host
without a display or a real Qt binding.

Requires the optional ``dcc-mcp-core`` dependency; skipped when absent.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "python"))

from auroraview.dcc_mcp import DCC_MCP_CORE_IMPORT_ERROR  # noqa: E402

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        DCC_MCP_CORE_IMPORT_ERROR is not None,
        reason="dcc-mcp-core not installed (pip install auroraview[dcc-mcp])",
    ),
]

if DCC_MCP_CORE_IMPORT_ERROR is None:
    from auroraview.dcc_mcp.host import AuroraViewQtHost


class _FakeDispatcher:
    """Stand-in for a DCC-MCP dispatcher."""

    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)

    def tick(self, *args, **kwargs):
        self.jobs.append("tick")
        return types.SimpleNamespace(more_pending=False)

    def has_pending_jobs(self):
        return False

    def is_shutdown(self):
        return False


@pytest.fixture()
def fake_qt(monkeypatch):
    """Install a stub ``qtpy`` module exposing just what the host uses."""
    qtcore = types.ModuleType("qtpy.QtCore")

    class _Timer:
        started = []
        stopped = []

        def __init__(self):
            self._active = False
            self._cb = None

        def setTimerType(self, _kind):
            pass

        def timeout_connect(self, cb):
            self._cb = cb

        # Qt uses .connect on the signal; emulate the attribute shape used.
        @property
        def timeout(self):
            return _Signal(self)

        def start(self, interval_ms):
            self._active = True
            _Timer.started.append(interval_ms)

        def stop(self):
            self._active = False
            _Timer.stopped.append(True)

        def isActive(self):
            return self._active

    class _Signal:
        def __init__(self, owner):
            self._owner = owner

        def connect(self, cb):
            self._owner.timeout_connect(cb)

        def disconnect(self, cb):
            assert self._owner._cb is cb
            self._owner._cb = None

    class _App:
        _instance = None

        def thread(self):
            return "qt-thread"

        @classmethod
        def instance(cls):
            return cls._instance

    qtcore.QTimer = _Timer
    _Timer.deleteLater = lambda self: None
    qtcore.Qt = types.SimpleNamespace(PreciseTimer=0)
    qtcore.QThread = types.SimpleNamespace(currentThread=lambda: "qt-thread")
    qtcore.QCoreApplication = _App
    monkeypatch.setitem(sys.modules, "qtpy", types.ModuleType("qtpy"))
    monkeypatch.setitem(sys.modules, "qtpy.QtCore", qtcore)
    return qtcore


def test_host_attaches_and_detaches_a_timer(fake_qt):
    """attach_tick starts a QTimer; detach_tick stops it and is idempotent."""
    fake_qt.QCoreApplication._instance = fake_qt.QCoreApplication()
    host = AuroraViewQtHost(_FakeDispatcher())
    host.attach_tick(lambda: None)
    assert host._timer is not None
    assert host._timer.isActive() is True

    host.detach_tick()
    assert host._timer is None
    # Second detach must not raise.
    host.detach_tick()


def test_host_reports_background_without_qt_application(fake_qt):
    """With no QCoreApplication instance the host is in background mode."""
    fake_qt.QCoreApplication._instance = None
    host = AuroraViewQtHost(_FakeDispatcher())
    assert host.is_background() is True


def test_host_reports_foreground_with_qt_application(fake_qt):
    """A live QCoreApplication means the Qt loop can host the tick."""
    fake_qt.QCoreApplication._instance = object()
    host = AuroraViewQtHost(_FakeDispatcher())
    assert host.is_background() is False


def test_host_lifecycle_without_starting(fake_qt):
    """Construction alone must not start any timer."""
    host = AuroraViewQtHost(_FakeDispatcher())
    assert host.is_running() is False
    assert host._timer is None


def test_start_uses_core_lifecycle_on_the_qt_thread(fake_qt):
    fake_qt.QCoreApplication._instance = fake_qt.QCoreApplication()
    dispatcher = _FakeDispatcher()
    host = AuroraViewQtHost(dispatcher, tick_interval_idle=0.125)
    host.start()
    assert host.is_running()
    timer = host._timer
    timer._cb()
    assert dispatcher.jobs == ["tick"]
    assert timer.started[-1] == 125
    host.stop()
    assert not host.is_running()
    assert not timer.isActive()
    assert timer._cb is None


def test_start_requires_a_qt_application(fake_qt):
    host = AuroraViewQtHost(_FakeDispatcher())
    with pytest.raises(RuntimeError, match="running Qt application"):
        host.start()
    assert host._timer is None
    assert not host.is_running()


def test_start_and_stop_refuse_a_worker_thread(fake_qt):
    fake_qt.QCoreApplication._instance = fake_qt.QCoreApplication()
    host = AuroraViewQtHost(_FakeDispatcher())
    fake_qt.QThread.currentThread = lambda: "worker-thread"
    with pytest.raises(RuntimeError, match="application thread"):
        host.start()
    fake_qt.QThread.currentThread = lambda: "qt-thread"
    host.start()
    fake_qt.QThread.currentThread = lambda: "worker-thread"
    with pytest.raises(RuntimeError, match="application thread"):
        host.stop()
    assert host.is_running()
    fake_qt.QThread.currentThread = lambda: "qt-thread"
    host.stop()
