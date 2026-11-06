# -*- coding: utf-8 -*-
"""High-level AuroraView base class.

This module provides the :class:`AuroraView` Python base class that wraps a
``WebView``/``QtWebView`` instance and offers:

* A stable facade for ``bind_call`` / ``bind_api`` / ``emit``.
* An internal keep-alive registry so DCC hosts (Maya, Nuke, etc.) do not need
  to store global references like ``__main__.my_dialog = dlg``.
* HWND integration mode for non-Qt applications (e.g., Unreal Engine).

## Integration Modes

AuroraView supports two main integration modes:

1. **HWND Mode** (AuroraView class):
   - For Unreal Engine, custom applications, or any HWND-based integration
   - Creates a standalone WebView window and exposes HWND for external embedding
   - Use ``get_hwnd()`` to retrieve the native window handle

2. **Qt Mode** (QtWebView class):
   - For Qt-based DCC applications (Maya, Houdini, Nuke, 3ds Max)
   - Integrates directly with Qt widget hierarchy
   - Supports QDockWidget docking

## Examples

HWND Mode (Unreal Engine)::

    from auroraview import AuroraView

    webview = AuroraView(url="http://localhost:3000")
    webview.show()

    # Get HWND for Unreal integration
    hwnd = webview.get_hwnd()
    if hwnd:
        import unreal
        unreal.parent_external_window_to_slate(hwnd)

Qt Mode (Maya/Houdini/Nuke)::

    from auroraview import QtWebView

    webview = QtWebView(parent=my_dialog, url="http://localhost:3000")
    webview.show()  # Automatically embedded in parent
"""

from __future__ import annotations

import logging
from typing import Any, Callable, ClassVar, Optional, Set

from auroraview.core.webview import WebView

logger = logging.getLogger(__name__)


class AuroraView:
    """HWND-based WebView for non-Qt applications.

    This class provides a standalone WebView window with HWND access for
    integration with non-Qt applications like Unreal Engine.

    For Qt-based DCC applications (Maya, Houdini, Nuke), use ``QtWebView``
    instead for proper Qt widget integration and docking support.

    Key Features:
        * Standalone WebView window
        * HWND access via ``get_hwnd()`` for external embedding
        * Keep-alive registry to prevent GC
        * Event binding (``bind_call``, ``bind_api``, ``emit``)

    Example (Unreal Engine)::

        from auroraview import AuroraView

        # Create standalone WebView
        webview = AuroraView(url="http://localhost:3000")
        webview.show()

        # Get HWND for Unreal Engine embedding
        hwnd = webview.get_hwnd()
        if hwnd:
            import unreal
            unreal.parent_external_window_to_slate(hwnd)

    Example (Standalone)::

        from auroraview import AuroraView

        webview = AuroraView(
            url="http://localhost:3000",
            title="My Tool",
            width=1024,
            height=768
        )
        webview.show()  # Blocks until window is closed

    Args:
        parent: Parent window HWND (optional, for owner mode positioning)
        parent_hwnd: Alias for parent (more explicit naming)
        url: URL to load in the WebView
        html: HTML content to load (alternative to url)
        title: Window title
        width: Window width in pixels
        height: Window height in pixels
        fullscreen: Start in fullscreen mode
        debug: Enable developer tools
        api: Object to expose to JavaScript (methods become callable)
        embed_mode: Embedding mode ("none" for standalone, "owner" for positioned)
        _view: Existing WebView instance to wrap (advanced)
        _keep_alive_root: Root object to keep alive (advanced)
        _auto_show: Automatically show on creation
        **kwargs: Additional arguments passed to WebView
    """

    _instances: ClassVar[Set["AuroraView"]] = set()

    def __init__(
        self,
        *,
        parent: Optional[Any] = None,
        parent_hwnd: Optional[int] = None,  # Explicit HWND parameter
        url: Optional[str] = None,
        html: Optional[str] = None,
        title: str = "AuroraView",
        width: int = 800,
        height: int = 600,
        fullscreen: bool = False,
        debug: bool = False,
        api: Optional[Any] = None,
        embed_mode: str = "none",  # Default to standalone
        _view: Optional[Any] = None,
        _keep_alive_root: Optional[Any] = None,
        _auto_show: bool = False,
        **kwargs: Any,
    ) -> None:
        # Handle parent_hwnd alias
        if parent_hwnd is not None and parent is None:
            parent = parent_hwnd

        self._parent = parent
        self._title = title
        self._width = width
        self._height = height
        self._fullscreen = fullscreen
        self._debug = debug
        self._url = url
        self._html = html
        self._api = api if api is not None else self
        self._embed_mode = embed_mode

        if _view is not None:
            # Reuse an existing backend view (typically a QtWebView widget).
            self._view = _view
        else:
            # Create native WebView with specified embed mode
            # Note: WebView uses 'mode' parameter (maps to Rust's parent_mode)
            self._view = WebView(
                title=title,
                width=width,
                height=height,
                url=url,
                html=html,
                debug=debug,
                parent=parent,
                mode=embed_mode,  # embed_mode -> mode (WebView parameter name)
                **kwargs,
            )

        # Bind API object if provided and the backend supports bind_api.
        bind_api = getattr(self._view, "bind_api", None)
        if self._api is not None and callable(bind_api):
            bind_api(self._api)

        # The root that should be kept alive (typically the top-level window).
        self._keep_alive_root = _keep_alive_root or self._view

        # Register for automatic keep-alive to prevent premature GC.
        AuroraView._instances.add(self)
        logger.debug("AuroraView instance registered for keep-alive: %r", self)

        if _auto_show:
            self.show()

    # ------------------------------------------------------------------
    # Lifecycle hooks (subclasses may override)
    # ------------------------------------------------------------------
    def on_show(self) -> None:  # pragma: no cover - default hook
        """Called after :meth:`show` is invoked."""

    def on_hide(self) -> None:  # pragma: no cover - default hook
        """Placeholder for future hide support."""

    def on_close(self) -> None:  # pragma: no cover - default hook
        """Called when :meth:`close` is executed."""

    def on_ready(self) -> None:  # pragma: no cover - default hook
        """Placeholder for JS bridge ready hook."""

    # ------------------------------------------------------------------
    # Delegation helpers
    # ------------------------------------------------------------------
    @property
    def view(self) -> Any:
        """Return the underlying WebView/QtWebView instance."""

        return self._view

    def emit(self, event_name: str, payload: Any) -> None:
        """Emit an event to JavaScript via the underlying view."""

        emit = getattr(self._view, "emit", None)
        if callable(emit):
            emit(event_name, payload)

    def bind_call(
        self,
        method: str,
        func: Optional[Callable[..., Any]] = None,
    ):
        """Bind a Python callable as an ``auroraview.call`` target."""

        bind_call = getattr(self._view, "bind_call", None)
        if not callable(bind_call):
            raise RuntimeError("Underlying view does not support bind_call")
        return bind_call(method, func)

    def bind_api(self, api: Any, namespace: str = "api") -> None:
        """Bind all public methods of an object under a namespace."""

        bind_api = getattr(self._view, "bind_api", None)
        if not callable(bind_api):
            raise RuntimeError("Underlying view does not support bind_api")
        bind_api(api, namespace=namespace)

    def show(self, *args: Any, **kwargs: Any) -> None:
        """Show the underlying view/window."""

        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            if args or (kwargs.get("wait") is True):
                raise RuntimeError("Retained windows require non-blocking show()")
            retained.show()
            return

        show = getattr(self._view, "show", None)
        if callable(show):
            show(*args, **kwargs)
        self.on_show()

    def close(self) -> None:
        """Close the tool and unregister it from the keep-alive registry."""

        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            retained.close()
            return

        if self in AuroraView._instances:
            AuroraView._instances.remove(self)
            logger.debug("AuroraView instance unregistered: %r", self)

        # Close keep-alive root if it has a close() method
        root = self._keep_alive_root
        try:
            close_root = getattr(root, "close", None)
            if callable(close_root):
                close_root()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Error while closing keep_alive_root")

        # If root differs from the underlying view, attempt to close view as well
        if root is not self._view:
            try:
                close_view = getattr(self._view, "close", None)
                if callable(close_view):
                    close_view()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error while closing underlying view")

        self.on_close()

    # ------------------------------------------------------------------
    # HWND Integration (for Unreal Engine and other non-Qt apps)
    # ------------------------------------------------------------------
    def get_hwnd(self) -> Optional[int]:
        """Get the native window handle (HWND) of the WebView.

        This is the primary method for integrating AuroraView with non-Qt
        applications like Unreal Engine.

        Returns:
            int: The native window handle (HWND on Windows), or None if
                not available (e.g., before show() is called).

        Example (Unreal Engine)::

            from auroraview import AuroraView

            webview = AuroraView(url="http://localhost:3000")
            webview.show()

            hwnd = webview.get_hwnd()
            if hwnd:
                import unreal
                unreal.parent_external_window_to_slate(hwnd)

        Example (Windows API)::

            import ctypes

            hwnd = webview.get_hwnd()
            if hwnd:
                # Move window to specific position
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 100, 100, 800, 600, 0
                )
        """
        get_hwnd = getattr(self._view, "get_hwnd", None)
        if callable(get_hwnd):
            return get_hwnd()
        return None

    def set_visible(self, visible: bool) -> None:
        """Set the visibility of the WebView window.

        Args:
            visible: True to show, False to hide.
        """
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            retained.set_visible(visible)
            return
        set_visible = getattr(self._view, "set_visible", None)
        if callable(set_visible):
            set_visible(visible)

    def _window_call(self, name: str, *args: Any) -> Any:
        method = getattr(self._view, name, None)
        if method is None:
            raise RuntimeError(f"Window operation {name} is unavailable")
        return method(*args)

    def hide(self) -> None:
        self._window_call("hide")

    def focus(self) -> None:
        self._window_call("focus")

    def set_focus(self) -> None:
        self.focus()

    def move(self, x: int, y: int) -> None:
        self._window_call("move", x, y)

    def move_to(self, x: int, y: int) -> None:
        self.move(x, y)

    def resize(self, width: int, height: int) -> None:
        self._window_call("resize", width, height)

    def center(self) -> None:
        self._window_call("center")

    def set_min_size(self, width: int, height: int) -> None:
        self._window_call("set_min_size", width, height)

    def set_max_size(self, width: int, height: int) -> None:
        self._window_call("set_max_size", width, height)

    def minimize(self) -> None:
        self._window_call("minimize")

    def maximize(self) -> None:
        self._window_call("maximize")

    def unmaximize(self) -> None:
        self._window_call("unmaximize")

    def toggle_maximize(self) -> None:
        self._window_call("toggle_maximize")

    def restore(self) -> None:
        self._window_call("restore")

    def set_fullscreen(self, fullscreen: bool) -> None:
        self._window_call("set_fullscreen", fullscreen)

    def toggle_fullscreen(self) -> None:
        self._window_call("toggle_fullscreen")

    def set_always_on_top(self, value: bool = True) -> None:
        self._window_call("set_always_on_top", value)

    def set_resizable(self, value: bool) -> None:
        self._window_call("set_resizable", value)

    def set_decorations(self, value: bool) -> None:
        self._window_call("set_decorations", value)

    def set_title(self, title: str) -> None:
        self._window_call("set_window_title", title)

    def set_window_title(self, title: str) -> None:
        self.set_title(title)

    def sync_bounds(self, width: int, height: int) -> None:
        self._window_call("sync_bounds", width, height)

    def set_position(self, x: int, y: int) -> None:
        """Set the position of the WebView window.

        Args:
            x: X coordinate (screen coordinates).
            y: Y coordinate (screen coordinates).
        """
        set_position = getattr(self._view, "set_position", None)
        if callable(set_position):
            set_position(x, y)

    def set_size(self, width: int, height: int) -> None:
        """Set the size of the WebView window.

        Args:
            width: Width in pixels.
            height: Height in pixels.
        """
        set_size = getattr(self._view, "set_size", None)
        if callable(set_size):
            set_size(width, height)

    def register_protocol(self, scheme: str, handler: Callable[[str], Any]) -> None:
        """Register a custom protocol handler.

        Args:
            scheme: Protocol scheme (e.g., "maya", "fbx")
            handler: Python function that takes URI string and returns dict with:
                - data (bytes): Response data
                - mime_type (str): MIME type (e.g., "image/png")
                - status (int): HTTP status code (e.g., 200, 404)

        Example:
            >>> def handle_fbx(uri: str) -> dict:
            ...     path = uri.replace("fbx://", "")
            ...     try:
            ...         with open(f"C:/models/{path}", "rb") as f:
            ...             return {
            ...                 "data": f.read(),
            ...                 "mime_type": "application/octet-stream",
            ...                 "status": 200
            ...             }
            ...     except FileNotFoundError:
            ...         return {
            ...             "data": b"Not Found",
            ...             "mime_type": "text/plain",
            ...             "status": 404
            ...         }
            ...
            >>> webview.register_protocol("fbx", handle_fbx)
        """
        register_protocol = getattr(self._view, "register_protocol", None)
        if not callable(register_protocol):
            logger.warning(
                "Underlying view does not support register_protocol: %s", type(self._view)
            )
            return
        register_protocol(scheme, handler)

    @property
    def state(self) -> Any:
        """Get the shared state container for Python ↔ JavaScript sync.

        Returns:
            State container with dict-like interface

        Example:
            >>> webview.state["user"] = {"name": "Alice"}
            >>> webview.state["theme"] = "dark"
            >>>
            >>> @webview.state.on_change
            >>> def handle_change(key, value, source):
            ...     print(f"{key} = {value} from {source}")
        """
        state = getattr(self._view, "state", None)
        if state is None:
            raise RuntimeError("Underlying view does not support state")
        return state

    def on(self, event_name: str) -> Callable:
        """Decorator to register a Python callback for JavaScript events.

        Args:
            event_name: Name of the event to listen for

        Returns:
            Decorator function

        Example:
            >>> @webview.on("export_scene")
            >>> def handle_export(data):
            >>>     print(f"Exporting to: {data['path']}")
        """
        on_method = getattr(self._view, "on", None)
        if not callable(on_method):
            raise RuntimeError("Underlying view does not support on()")
        return on_method(event_name)

    def command(self, name: Optional[str] = None) -> Callable:
        """Decorator to register a Python function as a callable command from JavaScript.

        Args:
            name: Optional command name (defaults to function name)

        Returns:
            Decorator function

        Example:
            >>> @webview.command
            >>> def export_scene(path: str) -> dict:
            ...     return {"success": True, "path": path}
            >>>
            >>> @webview.command("set_theme")
            >>> def set_theme_cmd(theme: str) -> dict:
            ...     return {"theme": theme}
        """
        command_method = getattr(self._view, "command", None)
        if not callable(command_method):
            raise RuntimeError("Underlying view does not support command()")
        return command_method(name) if name else command_method()
