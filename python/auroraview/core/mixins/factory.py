# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Factory Mixin - creation and embedding helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

try:
    from typing import Literal  # py38+
except ImportError:  # pragma: no cover - py37 compatibility
    from typing_extensions import Literal

if TYPE_CHECKING:
    from ..bridge import Bridge
    from ..webview import WebView

logger = logging.getLogger(__name__)


class WebViewFactoryMixin:
    """Mixin for WebView factory methods (create, run_embedded, create_embedded)."""

    # Class-level singleton registry (should be overridden by WebView)
    _singleton_registry: dict

    # Instance variables
    _auto_timer: Optional[object]
    _title: str
    _width: int
    _height: int

    @classmethod
    def create(
        cls,
        title: str = "AuroraView",
        *,
        # Content
        url: Optional[str] = None,
        html: Optional[str] = None,
        # Window properties
        width: int = 800,
        height: int = 600,
        resizable: bool = True,
        frame: Optional[bool] = None,
        always_on_top: bool = False,
        transparent: bool = False,
        background_color: Optional[str] = None,
        # DCC integration
        parent: Optional[int] = None,
        mode: Literal["auto", "owner", "child", "container"] = "auto",
        # Bridge integration
        bridge: Union["Bridge", bool, None] = None,  # type: ignore
        # Development options
        debug: bool = True,
        context_menu: bool = True,
        # Custom protocol
        asset_root: Optional[str] = None,
        data_directory: Optional[str] = None,
        allow_file_protocol: bool = False,
        capture_file_drop: Optional[bool] = None,
        # Automation
        auto_show: bool = False,
        auto_timer: bool = True,
        # Singleton control
        singleton: Optional[str] = None,
        # IPC performance tuning
        ipc_batch_size: int = 0,
        # Custom icon
        icon: Optional[str] = None,
        # Window style
        tool_window: bool = False,
        undecorated_shadow: bool = False,
        # New window handling
        allow_new_window: bool = False,
        new_window_mode: Optional[str] = None,
        # Remote debugging
        remote_debugging_port: Optional[int] = None,
    ) -> "WebView":
        """Create WebView instance (recommended way).

        Args:
            title: Window title
            url: URL to load
            html: HTML content to load
            width: Window width in pixels
            height: Window height in pixels
            resizable: Make window resizable
            frame: Show window frame (title bar, borders). If None, uses sensible defaults.

            always_on_top: Keep window always on top of other windows (default: False)
            parent: Parent window handle for DCC embedding
            mode: Embedding mode
                - "auto": Auto-select (recommended)
                - "owner": Owner mode (cross-thread safe)
                - "child": Child window mode (same-thread)
            bridge: Bridge for DCC/Web integration
                - Bridge instance: Use provided bridge
                - True: Auto-create bridge (port 9001)
                - None: No bridge (default)
            debug: Enable developer tools
            context_menu: Enable native context menu (default: True)
            asset_root: Root directory for auroraview:// protocol
            data_directory: User data directory for WebView (cookies, cache, localStorage).
                If None, uses system default. Set to isolate data per app/user profile.
            allow_file_protocol: Enable file:// protocol support (default: False)
                WARNING: Enabling this bypasses WebView's default security restrictions
            auto_show: Automatically show after creation
            auto_timer: Auto-start event timer for embedded mode (recommended)
            singleton: Singleton key. If provided, only one instance with this key
                      can exist at a time. Calling create() again with the same key
                      returns the existing instance.

        Returns:
            WebView instance

        Examples:
            >>> # Standalone window
            >>> webview = WebView.create("My App", url="http://localhost:3000")
            >>> webview.show()

            >>> # DCC embedding (Maya)
            >>> webview = WebView.create("Maya Tool", parent=maya_hwnd)
            >>> webview.show()

            >>> # With Bridge integration
            >>> webview = WebView.create("Photoshop Tool", bridge=True)
            >>> @webview.bridge.on('layer_created')
            >>> async def handle_layer(data, client):
            ...     return {"status": "ok"}
            >>> webview.show()

            >>> # Auto-show
            >>> webview = WebView.create("App", auto_show=True)

            >>> # Singleton mode - only one instance allowed

        Note:
            For Qt-based DCC applications (Maya, Houdini, Nuke), consider using
            QtWebView instead for automatic event processing and better integration:

            >>> from auroraview import QtWebView
            >>> webview = QtWebView(parent=maya_main_window(), title="My Tool")
            >>> webview.load_url("http://localhost:3000")
            >>> webview.show()  # Automatic event processing!
            >>> webview1 = WebView.create("Tool", singleton="my_tool")
            >>> webview2 = WebView.create("Tool", singleton="my_tool")  # Returns webview1
            >>> assert webview1 is webview2
        """
        # Check singleton registry
        if singleton is not None:
            if singleton in cls._singleton_registry:
                existing = cls._singleton_registry[singleton]
                logger.info(f"Returning existing singleton instance: '{singleton}'")
                return existing
            logger.info(f"Creating new singleton instance: '{singleton}'")
        # Detect mode
        is_embedded = parent is not None

        # Auto-select mode
        if mode == "auto":
            actual_mode = "owner" if is_embedded else None
            if is_embedded:
                logger.info(f"[AUTO-DETECT] parent={parent} detected, auto-selecting mode='owner'")
        else:
            actual_mode = mode if is_embedded else None
            if is_embedded:
                logger.info(f"[MANUAL] Using user-specified mode='{mode}'")

        logger.info(f"[MODE] Final mode: {actual_mode} (embedded={is_embedded})")

        # Create instance
        # For embedded mode, always set auto_show=False to let Qt control visibility
        # For standalone mode, use the user-provided auto_show value
        rust_auto_show = False if is_embedded else auto_show
        instance = cls(
            title=title,
            width=width,
            height=height,
            url=url,
            html=html,
            resizable=resizable,
            frame=frame,
            always_on_top=always_on_top,
            transparent=transparent,
            background_color=background_color,
            parent=parent,
            mode=actual_mode,
            debug=debug,
            context_menu=context_menu,
            bridge=bridge,
            asset_root=asset_root,
            data_directory=data_directory,
            allow_file_protocol=allow_file_protocol,
            # RFC 0017: pass tri-state Optional[bool] through unchanged.
            capture_file_drop=capture_file_drop,
            auto_show=rust_auto_show,  # Pass to Rust layer
            ipc_batch_size=ipc_batch_size,  # Max messages per tick (0=unlimited)
            icon=icon,  # Custom window icon path
            tool_window=tool_window,  # Tool window style
            undecorated_shadow=undecorated_shadow,  # Shadow for frameless windows
            allow_new_window=allow_new_window,  # Allow window.open()
            new_window_mode=new_window_mode,  # New window behavior
            remote_debugging_port=remote_debugging_port,  # CDP debugging port
        )

        # Auto timer (embedded mode)
        if is_embedded and auto_timer:
            try:
                from auroraview.utils.event_timer import EventTimer

                instance._auto_timer = EventTimer(instance, interval_ms=16)
                instance._auto_timer.on_close(lambda: instance._auto_timer.stop())
                logger.info("Auto timer created for embedded mode")
            except ImportError as e:
                logger.warning("EventTimer not available: %s, auto_timer disabled", e)
                instance._auto_timer = None
        else:
            instance._auto_timer = None

        # Register singleton
        if singleton is not None:
            cls._singleton_registry[singleton] = instance
            logger.info(f"Registered singleton instance: '{singleton}'")

        # Auto show (only for standalone mode, embedded mode is controlled by Qt)
        if auto_show and not is_embedded:
            instance.show()

        return instance

    @classmethod
    def run_embedded(
        cls,
        title: str = "AuroraView",
        *,
        url: Optional[str] = None,
        html: Optional[str] = None,
        width: int = 800,
        height: int = 600,
        resizable: bool = True,
        frame: Optional[bool] = None,
        parent: Optional[int] = None,
        mode: Literal["auto", "owner", "child"] = "owner",
        bridge: Union["Bridge", bool, None] = None,  # type: ignore
        debug: bool = True,
        context_menu: bool = True,
        capture_file_drop: Optional[bool] = None,
        auto_timer: bool = True,
    ) -> "WebView":
        """Create and show an embedded WebView with auto timer (non-blocking).

        This is a convenience helper equivalent to:
            WebView.create(..., parent=..., mode=..., auto_timer=True, auto_show=True)

        Returns:
            WebView: The created instance (kept alive by your reference)
        """
        instance = cls.create(
            title=title,
            url=url,
            html=html,
            width=width,
            height=height,
            resizable=resizable,
            frame=frame,
            parent=parent,
            mode=mode,
            bridge=bridge,
            debug=debug,
            context_menu=context_menu,
            # RFC 0017: pass tri-state Optional[bool] through unchanged.
            capture_file_drop=capture_file_drop,
            auto_show=True,
            auto_timer=auto_timer,
        )
        return instance

    @classmethod
    def create_embedded(
        cls,
        parent_hwnd: int,
        *,
        title: str = "Embedded WebView",
        width: int = 800,
        height: int = 600,
        url: Optional[str] = None,
        html: Optional[str] = None,
        asset_root: Optional[str] = None,
        debug: bool = True,
    ) -> "WebView":
        """Create a WebView directly embedded into a parent window's HWND.

        This is the fastest way to embed a WebView into a host application because:
        1. No Qt Widget intermediate layer
        2. WebView2 is created synchronously on the calling thread
        3. Uses host's native message loop directly

        This method is ideal when you have the host window's HWND and want
        maximum performance with minimal overhead. Works with DCC applications
        (Maya, 3ds Max, Houdini, etc.) or any Windows application with a HWND.

        Args:
            parent_hwnd: The HWND of the parent window (e.g., from Qt winId())
            title: Window title (for debugging/identification)
            width: Width in pixels
            height: Height in pixels
            url: URL to load (optional)
            html: HTML content to load (optional)
            asset_root: Root directory for auroraview:// protocol (optional)
            debug: Enable developer tools (default: True)

        Returns:
            WebView: A configured WebView instance ready to use

        Example (Houdini):
            >>> import hou
            >>> from auroraview import WebView
            >>> from PySide2.QtCore import QTimer
            >>>
            >>> # Get Houdini main window HWND
            >>> main_window = hou.qt.mainWindow()
            >>> hwnd = int(main_window.winId())
            >>>
            >>> # Create WebView directly embedded
            >>> webview = WebView.create_embedded(
            ...     parent_hwnd=hwnd,
            ...     title="My Tool",
            ...     width=650,
            ...     height=500,
            ...     url="https://example.com"
            ... )
            >>>
            >>> # Set up timer to process messages
            >>> timer = QTimer()
            >>> timer.timeout.connect(webview.process_events_ipc_only)
            >>> timer.start(16)  # 60 FPS
        """
        from auroraview._core import WebView as _CoreWebView

        logger.info(f"[create_embedded] Creating WebView for parent HWND: {parent_hwnd}")

        # Create core WebView using create_embedded static method
        core = _CoreWebView.create_embedded(
            parent_hwnd=parent_hwnd,
            title=title,
            width=width,
            height=height,
        )

        # Create Python wrapper
        instance = cls.__new__(cls)
        instance._init_embedded_core(
            core,
            parent_hwnd=parent_hwnd,
            title=title,
            width=width,
            height=height,
            url=url,
            html=html,
            asset_root=asset_root,
            debug=debug,
        )

        # Configure asset root
        if asset_root:
            core.set_asset_root(asset_root)

        # Load content
        if url:
            core.load_url(url)
        elif html:
            core.load_html(html)

        logger.info("[create_embedded] WebView created successfully")
        logger.info("[create_embedded] Remember to call process_events_ipc_only() periodically!")

        return instance
