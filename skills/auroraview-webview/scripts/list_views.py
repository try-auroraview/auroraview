"""auroraview-webview: run the `list_views` tool against a live AuroraView panel.

Runs on Python 3.7+.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from _dispatch import read_params, run_tool  # type: ignore[import-not-found]

TOOL = "list_views"


def main(params: Dict[str, Any]) -> int:
    """Dispatch the tool and return a process exit code.

    Args:
        params: Tool parameters.

    Returns:
        0 on success, 1 on failure.
    """
    result = run_tool(TOOL, params)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(read_params()))
