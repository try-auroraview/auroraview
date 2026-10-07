# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Factory Methods.

This module provides factory methods for creating WebView instances.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

try:
    from typing import Literal  # py38+
except ImportError:  # pragma: no cover - only for py37
    from typing_extensions import Literal  # type: ignore

if TYPE_CHECKING:
    from auroraview.bridge import Bridge
    from auroraview.core.webview import WebView

logger = logging.getLogger(__name__)


class WebViewFactory:
    """Factory class for creating WebView instances.

    Provides static methods for creating WebView instances:
    - create: Main factory method with all options
    - run_embedded: Convenience method for embedded mode
    - create_embedded: Direct HWND embedding for host applications
    """

    # Singleton registry (shared with WebView class)
    _singleton_registry: dict = {}

    @classmethod
    def create(
        cls,
        webview_cls: type,
        title: str = "AuroraView",
        *,
        # Content
        url: Optional[str] = None,
        html: Optional[str] = None,
        # Window properties
        width: int = 800,
        height: int = 600,
        resizable: bool = True,
        frame: bool = True,
        always_on_top: bool = False,
        transparent: bool = False,
        background_color: Optional[str] = None,
        # DCC integration
        parent: Optional[int] = None,
        mode: Literal["auto", "owner", "child", "container"] = "auto",
        # Bridge integration
        bridge: Union["Bridge", bool, None] = None,
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
            webview_cls: The WebView class to instantiate
            title: Window title
            url: URL to load
            html: HTML content to load
            width: Window width in pixels
            height: Window height in pixels
            resizable: Make window resizable
            frame: Show window frame (title bar, borders)
            always_on_top: Keep window always on top
            parent: Parent window handle for DCC embedding
            mode: Embedding mode ("auto", "owner", "child", "container")
            bridge: Bridge for DCC/Web integration
            debug: Enable developer tools
            context_menu: Enable native context menu
            asset_root: Root directory for auroraview:// protocol
            data_directory: User data directory for WebView
            allow_file_protocol: Enable file:// protocol support
            auto_show: Automatically show after creation
            auto_timer: Auto-start event timer for embedded mode
            singleton: Singleton key for single instance control
            ipc_batch_size: Max messages per tick (0=unlimited)

        Returns:
            WebView instance
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
                logger.info(f"[AUTO-DETECT] parent={parent}, auto-selecting mode='owner'")
        else:
            actual_mode = mode if is_embedded else None
            if is_embedded:
                logger.info(f"[MANUAL] Using user-specified mode='{mode}'")

        logger.info(f"[MODE] Final mode: {actual_mode} (embedded={is_embedded})")

        # Create instance
        rust_auto_show = False if is_embedded else auto_show
        instance = webview_cls(
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
            auto_show=rust_auto_show,
            ipc_batch_size=ipc_batch_size,
            icon=icon,
            tool_window=tool_window,
            undecorated_shadow=undecorated_shadow,
            allow_new_window=allow_new_window,
            new_window_mode=new_window_mode,
            remote_debugging_port=remote_debugging_port,
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

        # Auto show (only for standalone mode)
        if auto_show and not is_embedded:
            instance.show()

        return instance

    @classmethod
    def run_embedded(
        cls,
        webview_cls: type,
        title: str = "AuroraView",
        *,
        url: Optional[str] = None,
        html: Optional[str] = None,
        width: int = 800,
        height: int = 600,
        resizable: bool = True,
        frame: bool = True,
        parent: Optional[int] = None,
        mode: Literal["auto", "owner", "child"] = "owner",
        bridge: Union["Bridge", bool, None] = None,
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
        return cls.create(
            webview_cls,
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

    @classmethod
    def create_embedded(
        cls,
        webview_cls: type,
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

        Args:
            webview_cls: The WebView class to instantiate
            parent_hwnd: The HWND of the parent window
            title: Window title (for debugging/identification)
            width: Width in pixels
            height: Height in pixels
            url: URL to load (optional)
            html: HTML content to load (optional)
            asset_root: Root directory for auroraview:// protocol (optional)
            debug: Enable developer tools (default: True)

        Returns:
            WebView: A configured WebView instance ready to use
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
        instance = webview_cls.__new__(webview_cls)
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
