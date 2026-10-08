# -*- coding: utf-8 -*-
"""Qt host lifecycle for the AuroraView DCC-MCP integration.

:class:`AuroraViewQtHost` wires a DCC-MCP dispatcher tick onto the Qt event
loop so tool invocations are executed on the thread that owns the WebView --
never on an HTTP or Tokio worker thread.

It implements the three hooks core's ``HostAdapter`` template requires:

* :meth:`AuroraViewQtHost.is_background` -- ``True`` when no Qt event loop runs.
* :meth:`AuroraViewQtHost.attach_tick` -- registers the tick with ``QTimer``.
* :meth:`AuroraViewQtHost.detach_tick` -- idempotent teardown.

AuroraView is a Qt host, so the DCC's own event loop drives dispatch; core
never takes over the message pump.
"""

from __future__ import annotations

import logging
import weakref
from typing import Any, Callable, Optional

from ._compat import require_core as _require_core

logger = logging.getLogger(__name__)

#: Default interval between dispatcher ticks while the host is idle (seconds).
DEFAULT_IDLE_INTERVAL = 0.05


def _host_adapter_base() -> Any:
    """Return core's ``HostAdapter`` base class, importing it on demand.

    Returns:
        The ``HostAdapter`` class.

    Raises:
        ImportError: If ``dcc-mcp-core`` is not installed.
    """
    _require_core()
    from dcc_mcp_core.host import HostAdapter

    return HostAdapter


class AuroraViewQtHost:
    """Drive a DCC-MCP dispatcher from the Qt event loop.

    Args:
        dispatcher: A DCC-MCP dispatcher exposing a tick entry point
            (``QueueDispatcher`` / ``BlockingDispatcher`` / any object
            satisfying the ``TickableDispatcher`` protocol).
        tick_interval_active: Seconds between ticks while work is pending.
        tick_interval_idle: Seconds between ticks while idle.
        name: Logical name used in log messages.

    Example::

        host = AuroraViewQtHost(dispatcher)
        host.start()   # ticks now run on the Qt event loop
        ...
        host.stop()
    """

    def __init__(
        self,
        dispatcher: Any,
        tick_interval_active: float = 0.0,
        tick_interval_idle: float = DEFAULT_IDLE_INTERVAL,
        name: str = "auroraview-host",
    ):
        owner = weakref.proxy(self)

        class QtHostAdapter(_host_adapter_base()):
            def is_background(self):
                return owner.is_background()

            def attach_tick(self, tick_fn):
                owner.attach_tick(tick_fn)

            def detach_tick(self):
                owner.detach_tick()

        self._base = QtHostAdapter(
            dispatcher,
            tick_interval_active=tick_interval_active,
            tick_interval_idle=tick_interval_idle,
            name=name,
        )
        self._timer = None
        self._tick_fn: Optional[Callable[[], Any]] = None

    @staticmethod
    def _require_qt_thread():
        """Refuse dispatch unless the caller owns the running Qt application."""
        from qtpy import QtCore

        app = QtCore.QCoreApplication.instance()
        if app is None:
            raise RuntimeError("AuroraViewQtHost requires a running Qt application")
        if QtCore.QThread.currentThread() != app.thread():
            raise RuntimeError("AuroraViewQtHost must run on the Qt application thread")
        return QtCore

    # ------------------------------------------------------------------
    # HostAdapter hooks
    # ------------------------------------------------------------------

    def is_background(self) -> bool:
        """Return ``True`` when no Qt event loop is running (headless mode).

        Returns:
            ``True`` when ``QCoreApplication`` is absent or no Qt binding is
            importable; ``False`` when a Qt event loop can host the tick.
        """
        try:
            from qtpy import QtCore  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - Qt is an optional dependency
            return True
        return QtCore.QCoreApplication.instance() is None

    def attach_tick(self, tick_fn: Callable[[], Any]) -> None:
        """Register ``tick_fn`` with a ``QTimer`` on the Qt event loop.

        Args:
            tick_fn: Zero-argument callable returning the next interval in
                seconds, or ``None`` to cancel.
        """
        QtCore = self._require_qt_thread()
        self.detach_tick()
        timer = QtCore.QTimer()

        def tick():
            interval = tick_fn()
            if interval is None:
                timer.stop()
            else:
                timer.start(max(1, int(interval * 1000)))

        timer.setTimerType(QtCore.Qt.PreciseTimer)
        timer.timeout.connect(tick)
        timer.start(max(1, int(DEFAULT_IDLE_INTERVAL * 1000)))
        self._timer = timer
        self._tick_fn = tick
        logger.debug("AuroraViewQtHost attached dispatcher tick to QTimer")

    def detach_tick(self) -> None:
        """Stop and drop the tick timer. Safe to call repeatedly."""
        timer = self._timer
        if timer is None:
            return
        self._require_qt_thread()
        timer.stop()
        timer.timeout.disconnect(self._tick_fn)
        timer.deleteLater()
        self._timer = None
        self._tick_fn = None

    # ------------------------------------------------------------------
    # Lifecycle delegation
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start dispatch on the Qt application thread; headless use is refused."""
        self._require_qt_thread()
        self._base.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the dispatcher and detach the timer.

        Args:
            timeout: Seconds to wait for the dispatcher to drain.
        """
        if self._timer is not None:
            self._require_qt_thread()
        try:
            self._base.stop(timeout=timeout)
        finally:
            self.detach_tick()

    def is_running(self) -> bool:
        """Return ``True`` while the dispatcher is running.

        ``is_running`` is a property on core's ``HostAdapter``, not a method.
        """
        return bool(self._base.is_running)

    def __enter__(self) -> "AuroraViewQtHost":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
