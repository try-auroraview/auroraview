"""Shared dispatch helper for auroraview-webview skill scripts.

Every script in this skill is a thin wrapper: it validates its inputs and
forwards them to the live :class:`AuroraViewAdapter` registered with the
running DCC-MCP server. No script talks to the WebView directly -- the adapter
owns the host-thread dispatch and is the single execution path.

Runs on Python 3.7+.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

# Make the local scripts directory importable when executed as a script.
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read_params() -> Dict[str, Any]:
    """Read tool parameters from argv (JSON) or stdin (JSON).

    Returns:
        Parsed parameter dict; empty dict when nothing was supplied.
    """
    if len(sys.argv) > 1:
        return json.loads(sys.argv[1]) or {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw) or {}


def _find_adapter(view_id: Optional[str] = None, generation: Optional[str] = None) -> Any:
    """Resolve an explicit generation, or the sole registered legacy view.

    The environment factory is a fallback only when no view is registered and
    no routing identity was supplied. It must never override explicit targeting
    or hide a multiple-view ambiguity. A Registration checks liveness again at
    execute(), after any existing host dispatch queue has delayed the call.
    """
    from auroraview.dcc_mcp import adapter_registry

    registration = adapter_registry.resolve(view_id, generation)
    if registration is not None:
        return registration
    factory_path = os.environ.get("AURORAVIEW_ADAPTER")
    if factory_path:
        module_name, _, attr = factory_path.rpartition(".")
        if not module_name:
            raise RuntimeError(
                "AURORAVIEW_ADAPTER must be a dotted path like 'my.module.get_adapter'"
            )
        module = __import__(module_name, fromlist=[attr])
        adapter = getattr(module, attr)
        return adapter() if callable(adapter) else adapter
    raise RuntimeError(
        "No live AuroraView adapter found. Start an AuroraView window with "
        "auroraview.dcc_mcp.start_server(), or set AURORAVIEW_ADAPTER to a "
        "dotted path that returns the adapter."
    )


def run_tool(tool: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute ``tool`` against the live adapter and print the JSON result.

    Args:
        tool: Tool name understood by :class:`AuroraViewAdapter`.
        params: Tool parameters. Defaults to the parsed CLI/stdin payload.

    Returns:
        The adapter's result dict (also printed to stdout as JSON).
    """
    payload = params if params is not None else read_params()
    try:
        if not isinstance(payload, dict):
            raise TypeError("Tool parameters must be an object")
        payload = dict(payload)
        if tool == "list_views":
            from auroraview.dcc_mcp import adapter_registry

            if payload:
                raise ValueError("list_views does not accept parameters")
            result = {"ok": True, "views": adapter_registry.list_views()}
        else:
            if ("view_id" in payload or "generation" in payload) and (
                not isinstance(payload.get("view_id"), str)
                or not isinstance(payload.get("generation"), str)
            ):
                raise ValueError("view_id and generation must be supplied together as strings")
            view_id = payload.pop("view_id", None)
            generation = payload.pop("generation", None)
            adapter = _find_adapter(view_id, generation)
            result = adapter.execute(tool, payload)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent as JSON
        result = {"ok": False, "tool": tool, "error": str(exc)}
    print(json.dumps(result))
    return result
