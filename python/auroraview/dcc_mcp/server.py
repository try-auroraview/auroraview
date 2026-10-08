# -*- coding: utf-8 -*-
"""MCP/REST server + FileRegistry registration for AuroraView.

Starting a server through this module is what makes an AuroraView window
**discoverable** by the ``dcc-mcp-cli`` control plane: core's
``DccServerBase`` writes a registry row keyed by ``(dcc_type, instance_id)``
into the shared FileRegistry (``services.json``), holds an OS-level sentinel
lock for crash-resilient liveness, and heartbeats the row while the process
lives.

.. important::
   ``gateway_port`` must be non-zero. Setting it to ``0`` is core's explicit
   opt-out and disables FileRegistry self-registration entirely -- the server
   still runs but ``dcc-mcp-cli list`` will never see it.

Typical usage::

    from auroraview.dcc_mcp import AuroraViewAdapter, start_server

    adapter = AuroraViewAdapter(webview, host_dcc="maya")
    server = start_server(adapter)
    server.start()
    ...
    server.stop()
"""

from __future__ import annotations

import logging
import os
import tempfile
import weakref
from typing import Any, Dict, Optional

from . import adapter_registry
from ._compat import require_core as _require_core
from .adapter import DCC_NAME

logger = logging.getLogger(__name__)

#: Default gateway port used when none is supplied and none is configured.
DEFAULT_GATEWAY_PORT = 8790


def _builtin_skills_dir():
    """Return a stable directory for core's built-in skills.

    Returns:
        ``pathlib.Path`` to an existing (possibly empty) directory. Core
        exposes this value as ``_builtin_skills_dir`` and calls ``.is_dir()``
        on it, so it must be a ``Path`` rather than a ``str``.
    """
    from pathlib import Path

    base = Path(tempfile.gettempdir()) / "auroraview-dcc-mcp" / "builtin-skills"
    base.mkdir(parents=True, exist_ok=True)
    return base


def start_server(
    adapter: Any,
    *,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    dcc_version: Optional[str] = None,
    adapter_version: Optional[str] = None,
    display_name: Optional[str] = None,
    skill_paths: Optional[list] = None,
    enable_telemetry: bool = False,
    dispatcher: Optional[Any] = None,
) -> Any:
    """Build a ``DccServerBase`` for an AuroraView adapter.

    The returned server is **not** started; call ``.start()`` on it.

    Args:
        adapter: An :class:`~auroraview.dcc_mcp.adapter.AuroraViewAdapter`.
        gateway_port: Gateway/registry port. Non-zero is required for
            FileRegistry registration. Defaults to ``DCC_MCP_GATEWAY_PORT``,
            then :data:`DEFAULT_GATEWAY_PORT`.
        registry_dir: Registry directory. Defaults to ``DCC_MCP_REGISTRY_DIR``
            or core's default live registry.
        dcc_version: Reported AuroraView version.
        adapter_version: Reported adapter package version.
        display_name: Human-readable instance label shown when several
            instances are running. Defaults to the WebView window title.
        skill_paths: Extra directories to scan for skill packages.
        enable_telemetry: Forwarded to core; off by default.
        dispatcher: Existing host dispatcher for Core's execution bridge.
            Embedded hosts must supply their host-thread dispatcher. Omission
            retains the legacy inline path for standalone callers.

    Returns:
        A configured ``dcc_mcp_core.server_base.DccServerBase``.

    Raises:
        ImportError: If ``dcc-mcp-core`` is not installed.
        ValueError: If ``gateway_port`` resolves to ``0``, which would silently
            disable discovery.
    """
    _require_core()
    from dcc_mcp_core.server_base import DccServerBase, DccServerOptions

    if gateway_port is None:
        gateway_port = int(os.environ.get("DCC_MCP_GATEWAY_PORT") or DEFAULT_GATEWAY_PORT)
    if gateway_port == 0:
        raise ValueError(
            "gateway_port=0 disables FileRegistry registration, so the DCC-MCP "
            "CLI could never discover this instance. Pass a non-zero port."
        )

    context = adapter.get_context() if hasattr(adapter, "get_context") else {}
    if adapter_version is None:
        adapter_version = _adapter_version()
    if dcc_version is None:
        dcc_version = _auroraview_version()
    if display_name is None:
        display_name = context.get("window_title") or "AuroraView"

    options = DccServerOptions.from_env(
        DCC_NAME,
        builtin_skills_dir=_builtin_skills_dir(),
        gateway_port=gateway_port,
        registry_dir=registry_dir or os.environ.get("DCC_MCP_REGISTRY_DIR"),
        dcc_version=dcc_version,
        dcc_pid=os.getpid(),
        dcc_window_title=context.get("window_title"),
        adapter_version=adapter_version,
        enable_telemetry=enable_telemetry,
    )

    adapter_ref = weakref.ref(adapter)

    class AuroraViewServer(DccServerBase):
        def start(self, **kwargs):
            live = self._adapter or adapter_ref()
            if live is None:
                raise RuntimeError("AuroraView adapter was released before server startup")
            self._adapter = live
            adapter_registry.register(live)
            try:
                return super().start(**kwargs)
            except BaseException:
                try:
                    super().stop()
                except BaseException:
                    self._adapter = live
                    adapter_registry.register(live)
                    logger.exception(
                        "Server startup cleanup failed; adapter retained for stop retry"
                    )
                else:
                    adapter_registry.unregister(live)
                    self._adapter = None
                raise

        def stop(self):
            live = self._adapter or adapter_ref()
            try:
                result = super().stop()
            except BaseException:
                if live is not None:
                    self._adapter = live
                    adapter_registry.register(live)
                raise
            else:
                if live is not None:
                    adapter_registry.unregister(live)
                self._adapter = None
                return result

    server = AuroraViewServer(options)
    server._adapter = adapter
    server_ref = weakref.ref(server)

    def release_adapter():
        live = adapter_ref()
        if live is not None:
            adapter_registry.unregister(live)
        live_server = server_ref()
        if live_server is not None:
            live_server._adapter = None

    server.register_quit_hook(release_adapter)
    if dispatcher is not None:
        server.register_inprocess_executor(dispatcher)

    paths = [p for p in (skill_paths or []) if p]
    if paths:
        server.reload_skill_paths(extra_skill_paths=paths)
    return server


def _auroraview_version() -> str:
    """Return the installed AuroraView version, or ``"unknown"``."""
    try:
        import auroraview

        return str(getattr(auroraview, "__version__", "unknown"))
    except Exception:  # noqa: BLE001 - version reporting must never be fatal
        return "unknown"


def _adapter_version() -> str:
    """Return the AuroraView version as the adapter package version."""
    return _auroraview_version()


def registration_context(adapter: Any) -> Dict[str, Any]:
    """Return the WebView descriptor that describes this instance to the registry.

    This is the adapter's own context (``window_title``, ``url``, ``pid``,
    ``cdp_port``, ``host_dcc``), kept separate from the registry row core owns.

    Args:
        adapter: An :class:`~auroraview.dcc_mcp.adapter.AuroraViewAdapter`.

    Returns:
        Descriptor dict.
    """
    return dict(adapter.get_context())
