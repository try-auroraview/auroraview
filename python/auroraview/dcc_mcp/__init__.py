# -*- coding: utf-8 -*-
"""DCC-MCP ecosystem integration for AuroraView.

This subpackage exposes a running AuroraView WebView as a first-class
`dcc-mcp-core` WebView host, so the `dcc-mcp-cli` control plane can discover
and drive AuroraView tools through the standard DCC-MCP contracts:

* :class:`~auroraview.dcc_mcp.adapter.AuroraViewAdapter` -- capability and
  dispatch contract (structurally compatible with ``dcc_mcp_core.WebViewAdapter``).
* :class:`~auroraview.dcc_mcp.host.AuroraViewQtHost` -- host-thread dispatch
  lifecycle wired to the Qt event loop (wraps ``dcc_mcp_core.host.HostAdapter``).
* :func:`~auroraview.dcc_mcp.server.start_server` -- MCP/REST server plus
  FileRegistry registration.

`dcc-mcp-core` is an **optional** dependency; AuroraView keeps its
"no mandatory third-party Python dependency" guarantee. When the package is
absent, importing this module still succeeds and every constructor raises a
clear :class:`ImportError` at use time.

Example::

    from auroraview.dcc_mcp import AuroraViewAdapter, start_server

    adapter = AuroraViewAdapter(webview)
    server = start_server(adapter)
    server.start()

Requires: ``pip install auroraview[dcc-mcp]``
"""

from __future__ import annotations

from ._compat import DCC_MCP_CORE_IMPORT_ERROR, HAS_DCC_MCP_CORE, require_core

from . import adapter as adapter  # noqa: E402
from . import host as host  # noqa: E402
from . import host_detect as host_detect  # noqa: E402
from . import server as server  # noqa: E402
from .adapter import AuroraViewAdapter, WebViewToolSpec  # noqa: E402
from .host import AuroraViewQtHost  # noqa: E402
from .adapter_registry import current_adapter  # noqa: E402
from .host_detect import detect_host_dcc  # noqa: E402
from .server import start_server  # noqa: E402

__all__ = [
    "DCC_MCP_CORE_IMPORT_ERROR",
    "AuroraViewAdapter",
    "current_adapter",
    "detect_host_dcc",
    "AuroraViewQtHost",
    "WebViewToolSpec",
    "start_server",
    "is_available",
]


def is_available() -> bool:
    """Return ``True`` when the optional ``dcc-mcp-core`` dependency is importable."""
    return HAS_DCC_MCP_CORE
