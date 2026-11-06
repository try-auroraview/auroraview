# -*- coding: utf-8 -*-
"""Window Management API for JavaScript bridge.

This module provides Python backend APIs that can be called from JavaScript
via window.auroraview.call() for window management operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .webview import WebView

logger = logging.getLogger(__name__)


class WindowAPI:
    """Window management API exposed to JavaScript.

    This class provides methods that can be bound to the WebView and called
    from JavaScript for window management operations.

    Example:
        >>> from auroraview import WebView
        >>> webview = WebView.create("My App")
        >>> # The WindowAPI is automatically bound when calling setup_window_api()
        >>> webview.setup_window_api()
    """

    def __init__(self, webview: "WebView"):
        """Initialize WindowAPI with a WebView instance.

        Args:
            webview: The WebView instance this API is bound to
        """
        self._webview = webview

    # ============================================
    # Window Lifecycle
    # ============================================

    def show(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Show a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            if getattr(window, "_retained_window", None) is not None:
                window.show(wait=False)
            else:
                window._core.show()
        return {"success": True}

    def hide(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Hide a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.hide()
        return {"success": True}

    def close(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Close a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.close()
        return {"success": True}

    def focus(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Focus a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.focus()
        return {"success": True}

    # ============================================
    # Window State
    # ============================================

    def minimize(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Minimize a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.minimize()
        return {"success": True}

    def maximize(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Maximize a window.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.maximize()
        return {"success": True}

    def restore(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Restore a window from minimized/maximized state.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.restore()
        return {"success": True}

    def toggle_fullscreen(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Toggle fullscreen mode.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.toggle_fullscreen()
        return {"success": True}

    # ============================================
    # Window Properties
    # ============================================

    def set_title(self, title: str, label: Optional[str] = None) -> Dict[str, Any]:
        """Set window title.

        Args:
            title: New window title
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            window.title = title
        elif window and hasattr(window._core, "set_title"):
            window._core.set_title(title)
            window._title = title
        return {"success": True}

    def set_position(self, x: int, y: int, label: Optional[str] = None) -> Dict[str, Any]:
        """Set window position.

        Args:
            x: X coordinate
            y: Y coordinate
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.move(x, y)
        return {"success": True}

    def set_size(self, width: int, height: int, label: Optional[str] = None) -> Dict[str, Any]:
        """Set window size.

        Args:
            width: Width in pixels
            height: Height in pixels
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.resize(width, height)
        return {"success": True}

    def set_min_size(self, width: int, height: int, label: Optional[str] = None) -> Dict[str, Any]:
        """Set minimum window size.

        Args:
            width: Minimum width
            height: Minimum height
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            window._window_command("set_min_size", width, height)
        elif window and hasattr(window._core, "set_min_size"):
            window._core.set_min_size(width, height)
        return {"success": True}

    def set_max_size(self, width: int, height: int, label: Optional[str] = None) -> Dict[str, Any]:
        """Set maximum window size.

        Args:
            width: Maximum width
            height: Maximum height
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            window._window_command("set_max_size", width, height)
        elif window and hasattr(window._core, "set_max_size"):
            window._core.set_max_size(width, height)
        return {"success": True}

    def center(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Center window on screen.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            window._window_command("center")
        elif window and hasattr(window._core, "center"):
            window._core.center()
        return {"success": True}

    def set_always_on_top(self, always_on_top: bool, label: Optional[str] = None) -> Dict[str, Any]:
        """Set always on top.

        Args:
            always_on_top: Whether to keep window on top
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.set_always_on_top(always_on_top)
        return {"success": True}

    def set_resizable(self, resizable: bool, label: Optional[str] = None) -> Dict[str, Any]:
        """Set whether window is resizable.

        Args:
            resizable: Whether window can be resized
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            window._window_command("set_resizable", resizable)
        elif window and hasattr(window._core, "set_resizable"):
            window._core.set_resizable(resizable)
        return {"success": True}

    def _apply_window(self, name: str, *args: Any, label: Optional[str] = None) -> Dict[str, Any]:
        window = self._get_window(label)
        if window is not None:
            getattr(window, name)(*args)
        return {"success": True}

    def set_visible(self, visible: bool, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("set_visible", visible, label=label)

    def set_focus(self, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("set_focus", label=label)

    def move(self, x: int, y: int, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("move", x, y, label=label)

    def move_to(self, x: int, y: int, label: Optional[str] = None) -> Dict[str, Any]:
        return self.move(x, y, label=label)

    def resize(self, width: int, height: int, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("resize", width, height, label=label)

    def sync_bounds(self, width: int, height: int, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("sync_bounds", width, height, label=label)

    def unmaximize(self, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("unmaximize", label=label)

    def toggle_maximize(self, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("toggle_maximize", label=label)

    def set_fullscreen(self, fullscreen: bool, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("set_fullscreen", fullscreen, label=label)

    def set_window_title(self, title: str, label: Optional[str] = None) -> Dict[str, Any]:
        return self.set_title(title, label=label)

    def set_decorations(self, decorations: bool, label: Optional[str] = None) -> Dict[str, Any]:
        return self._apply_window("set_decorations", decorations, label=label)

    def is_fullscreen(self, label: Optional[str] = None) -> Dict[str, bool]:
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            return {"fullscreen": window._retained_window._control.snapshot()["fullscreen"]}
        return {"fullscreen": False}

    def get_title(self, label: Optional[str] = None) -> Dict[str, str]:
        window = self._get_window(label)
        return {"title": window.title if window else ""}

    # ============================================
    # Window Queries
    # ============================================

    def get_position(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Get window position.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"x": int, "y": int}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            snapshot = window._retained_window._control.snapshot()
            return {"x": snapshot["x"], "y": snapshot["y"]}
        if window and hasattr(window._core, "get_position"):
            pos = window._core.get_position()
            return {"x": pos[0], "y": pos[1]}
        return {"x": window._x if window else 0, "y": window._y if window else 0}

    def get_size(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Get window size.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"width": int, "height": int}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            snapshot = window._retained_window._control.snapshot()
            return {"width": snapshot["width"], "height": snapshot["height"]}
        if window and hasattr(window._core, "get_size"):
            size = window._core.get_size()
            return {"width": size[0], "height": size[1]}
        return {
            "width": window._width if window else 0,
            "height": window._height if window else 0,
        }

    def get_bounds(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Get window bounds (position + size).

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"x": int, "y": int, "width": int, "height": int}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            snapshot = window._retained_window._control.snapshot()
            return {key: snapshot[key] for key in ("x", "y", "width", "height")}
        pos = self.get_position(label)
        size = self.get_size(label)
        return {**pos, **size}

    def get_state(self, label: Optional[str] = None) -> Dict[str, Any]:
        """Get complete window state.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"label": str, "visible": bool, "focused": bool, ...}
        """
        window = self._get_window(label)
        if not window:
            return {"error": "Window not found"}

        if getattr(window, "_retained_window", None) is not None:
            snapshot = window._retained_window._control.snapshot()
            return {
                "label": label or window._window_id or "main",
                "visible": snapshot["visible"],
                "focused": snapshot["focused"],
                "minimized": snapshot["minimized"],
                "maximized": snapshot["maximized"],
                "fullscreen": snapshot["fullscreen"],
                "bounds": {key: snapshot[key] for key in ("x", "y", "width", "height")},
            }

        bounds = self.get_bounds(label)
        actual_label = label or window._window_id or "main"

        return {
            "label": actual_label,
            "visible": True,  # If we got here, window exists
            "focused": self.is_focused(label).get("focused", False),
            "minimized": self.is_minimized(label).get("minimized", False),
            "maximized": self.is_maximized(label).get("maximized", False),
            "fullscreen": False,  # Would need core support
            "bounds": bounds,
        }

    def is_visible(self, label: Optional[str] = None) -> Dict[str, bool]:
        """Check if window is visible.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"visible": bool}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            return {"visible": window._retained_window._control.snapshot()["visible"]}
        if window and hasattr(window._core, "is_visible"):
            return {"visible": window._core.is_visible()}
        return {"visible": True}  # Assume visible if method not available

    def is_focused(self, label: Optional[str] = None) -> Dict[str, bool]:
        """Check if window is focused.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"focused": bool}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            return {"focused": window._retained_window._control.snapshot()["focused"]}
        if window and hasattr(window._core, "is_focused"):
            return {"focused": window._core.is_focused()}
        return {"focused": False}

    def is_minimized(self, label: Optional[str] = None) -> Dict[str, bool]:
        """Check if window is minimized.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"minimized": bool}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            return {"minimized": window._retained_window._control.snapshot()["minimized"]}
        if window and hasattr(window._core, "is_minimized"):
            return {"minimized": window._core.is_minimized()}
        return {"minimized": False}

    def is_maximized(self, label: Optional[str] = None) -> Dict[str, bool]:
        """Check if window is maximized.

        Args:
            label: Window label (uses current if not provided)

        Returns:
            {"maximized": bool}
        """
        window = self._get_window(label)
        if window and getattr(window, "_retained_window", None) is not None:
            return {"maximized": window._retained_window._control.snapshot()["maximized"]}
        if window and hasattr(window._core, "is_maximized"):
            return {"maximized": window._core.is_maximized()}
        return {"maximized": False}

    # ============================================
    # Window Manager Queries
    # ============================================

    def exists(self, label: str) -> Dict[str, bool]:
        """Check if a window exists.

        Args:
            label: Window label to check

        Returns:
            {"exists": bool}
        """
        from .window_manager import get_window_manager

        wm = get_window_manager()
        return {"exists": wm.has(label)}

    def list(self) -> Dict[str, List[str]]:
        """Get list of all window labels.

        Returns:
            {"labels": ["main", "settings", ...]}
        """
        from .window_manager import get_window_manager

        wm = get_window_manager()
        return {"labels": wm.get_all_ids()}

    def count(self) -> Dict[str, int]:
        """Get count of open windows.

        Returns:
            {"count": int}
        """
        from .window_manager import get_window_manager

        wm = get_window_manager()
        return {"count": wm.count()}

    # ============================================
    # Window Creation (Limited)
    # ============================================

    def create(
        self,
        url: Optional[str] = None,
        html: Optional[str] = None,
        title: str = "AuroraView",
        width: int = 800,
        height: int = 600,
        label: Optional[str] = None,
        center: bool = False,
        resizable: bool = True,
        frameless: bool = False,
        transparent: bool = False,
        always_on_top: bool = False,
        minimized: bool = False,
        maximized: bool = False,
        fullscreen: bool = False,
        devtools: bool = False,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new window.

        Note: This creates a new WebView instance. For DCC environments,
        additional setup may be required.

        Args:
            url: URL to load
            html: HTML content to load
            title: Window title
            width: Window width
            height: Window height
            label: Custom label for the window
            center: Center window on screen
            resizable: Make window resizable
            frameless: Create frameless window
            transparent: Make window transparent
            always_on_top: Keep window on top
            minimized: Start minimized
            maximized: Start maximized
            fullscreen: Start fullscreen
            devtools: Enable developer tools
            x: X position (ignored if center=True)
            y: Y position (ignored if center=True)

        Returns:
            {"label": str, "success": True}
        """
        from .webview import WebView
        from .window_manager import get_window_manager

        # Create new WebView
        new_webview = WebView.create(
            title=title,
            url=url,
            html=html,
            width=width,
            height=height,
            resizable=resizable,
            frame=not frameless,
            transparent=transparent,
            always_on_top=always_on_top,
            debug=devtools,
            auto_show=False,  # We'll control show manually
        )

        # Get label from WindowManager
        wm = get_window_manager()
        actual_label = label or new_webview._window_id or "new_window"

        # If custom label provided, re-register
        if label and label != new_webview._window_id:
            wm.unregister(new_webview._window_id)
            wm.register(new_webview, uid=label)
            new_webview._window_id = label

        # Apply position
        if center:
            if hasattr(new_webview._core, "center"):
                new_webview._core.center()
        elif x is not None and y is not None:
            new_webview.move(x, y)

        # Apply initial state
        if maximized:
            new_webview.maximize()
        elif minimized:
            new_webview.minimize()
        elif fullscreen:
            new_webview.toggle_fullscreen()

        # Show window
        new_webview.show()

        # Setup window API on new window too
        setup_window_api(new_webview)

        return {"label": actual_label, "success": True}

    # ============================================
    # Window Navigation
    # ============================================

    def navigate(self, url: str, label: Optional[str] = None) -> Dict[str, Any]:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.load_url(url)
        return {"success": True}

    def load_html(self, html: str, label: Optional[str] = None) -> Dict[str, Any]:
        """Load HTML content.

        Args:
            html: HTML content to load
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.load_html(html)
        return {"success": True}

    def eval(self, script: str, label: Optional[str] = None) -> Dict[str, Any]:
        """Execute JavaScript in a window.

        Args:
            script: JavaScript code to execute
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.eval_js(script)
        return {"success": True}

    def emit(self, event: str, data: Any = None, label: Optional[str] = None) -> Dict[str, Any]:
        """Emit an event to a window.

        Args:
            event: Event name
            data: Event data
            label: Window label (uses current if not provided)

        Returns:
            {"success": True}
        """
        window = self._get_window(label)
        if window:
            window.emit(event, data)
        return {"success": True}

    # ============================================
    # Helper Methods
    # ============================================

    def _get_window(self, label: Optional[str] = None) -> Optional["WebView"]:
        """Get a window by label or return the current window.

        Args:
            label: Window label (uses current window if not provided)

        Returns:
            WebView instance or None
        """
        if label is None:
            return self._webview

        from .window_manager import get_window_manager

        wm = get_window_manager()
        return wm.get(label)


def setup_window_api(webview: "WebView") -> WindowAPI:
    """Setup window API on a WebView instance.

    This function creates a WindowAPI instance and binds all its methods
    to the WebView so they can be called from JavaScript.

    Args:
        webview: The WebView instance to setup

    Returns:
        The WindowAPI instance

    Example:
        >>> webview = WebView.create("My App")
        >>> api = setup_window_api(webview)
        >>> # Now JavaScript can call: auroraview.call('window.show')
    """
    api = WindowAPI(webview)

    # List of methods to bind
    methods = [
        # Lifecycle
        "show",
        "hide",
        "close",
        "focus",
        "set_visible",
        "set_focus",
        # State
        "minimize",
        "maximize",
        "restore",
        "unmaximize",
        "toggle_maximize",
        "set_fullscreen",
        "toggle_fullscreen",
        # Properties
        "set_title",
        "set_window_title",
        "move",
        "move_to",
        "resize",
        "sync_bounds",
        "set_position",
        "set_size",
        "set_min_size",
        "set_max_size",
        "center",
        "set_always_on_top",
        "set_resizable",
        "set_decorations",
        # Queries
        "get_position",
        "get_size",
        "get_bounds",
        "get_state",
        "is_visible",
        "is_focused",
        "is_minimized",
        "is_maximized",
        "is_fullscreen",
        "get_title",
        # Window Manager
        "exists",
        "list",
        "count",
        "create",
        # Navigation
        "navigate",
        "load_html",
        "eval",
        "emit",
    ]

    for method_name in methods:
        method = getattr(api, method_name)
        full_name = f"window.{method_name}"
        # Use camelCase for JavaScript compatibility
        js_name = _to_camel_case(method_name)
        js_full_name = f"window.{js_name}"

        # Bind both snake_case and camelCase versions
        webview.bind_call(full_name, method, allow_rebind=False)
        if full_name != js_full_name:
            webview.bind_call(js_full_name, method, allow_rebind=False)

    logger.debug("Window API bound to WebView")
    return api


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase.

    Args:
        snake_str: String in snake_case format

    Returns:
        String in camelCase format
    """
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])
