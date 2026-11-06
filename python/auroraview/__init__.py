# -*- coding: utf-8 -*-
"""AuroraView - Rust-powered WebView for Python & DCC embedding.

This package provides a modern web-based UI solution for professional DCC applications
like Maya, 3ds Max, Houdini, Blender, Nuke, and Unreal Engine.

## Quick Start (Recommended)

Use ``create_webview()`` - it automatically selects the right implementation::

    from auroraview import create_webview

    # 1. Standalone window (no parent)
    webview = create_webview(url="http://localhost:3000")
    webview.show()

    # 2. Qt integration (pass QWidget parent)
    webview = create_webview(parent=maya_main_window(), url="http://localhost:3000")
    webview.show()

    # 3. HWND integration (pass int HWND)
    webview = create_webview(parent=unreal_hwnd, url="http://localhost:3000")
    webview.show()

## API Reference

| Use Case | API | Description |
|----------|-----|-------------|
| **Any** (recommended) | ``create_webview()`` | Auto-selects based on parent type |
| Maya/Houdini/Nuke | ``QtWebView`` | Qt widget with docking support |
| Unreal Engine | ``AuroraView`` | HWND-based for non-Qt apps |
| Desktop App | ``run_app()`` | Convenience for standalone apps |
| Advanced | ``auroraview.core.WebView`` | Low-level API |

## Unified Parameters

All WebView types share these common parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| parent | QWidget/int/None | None | Parent widget or HWND |
| title | str | "AuroraView" | Window title |
| width | int | 800 | Window width |
| height | int | 600 | Window height |
| url | str | None | URL to load |
| html | str | None | HTML content to load |
| debug | bool | True | Enable DevTools (F12) |
| context_menu | bool | True | Enable right-click menu |
| frame | bool | True | Show window frame |
| transparent | bool | False | Transparent background |
| mode | str | "auto" | Embedding mode |

## Bidirectional Communication

Python -> JavaScript::

    webview.emit("update_data", {"frame": 120})

JavaScript -> Python::

    @webview.on("export_scene")
    def handle_export(data):
        print(f"Exporting to: {data['path']}")

## Legacy APIs (still supported)

### Qt Mode (QtWebView)::

    from auroraview import QtWebView
    webview = QtWebView(parent=maya_main_window(), url="http://localhost:3000")
    webview.show()

### HWND Mode (AuroraView)::

    from auroraview import AuroraView
    webview = AuroraView(url="http://localhost:3000")
    webview.show()
    hwnd = webview.get_hwnd()  # For Unreal Engine embedding
"""

_CORE_IMPORT_ERROR = None

# Add DLL search paths for Windows (required for DCC applications like Substance Painter)
# This must be done BEFORE importing _core to ensure all required DLLs can be found.
#
# Background: Windows DLL search behavior changed in Python 3.8+
# - PATH environment variable is no longer sufficient for DLL discovery
# - Must explicitly call os.add_dll_directory() for each DLL search path
#
# Required DLLs:
# - python3.dll: Located in sys.prefix (e.g., DCC's pythonsdk directory)
# - WebView2Loader.dll: Located in auroraview package directory
import os as _os
import sys as _sys
from pathlib import Path as _Path

if _sys.platform == "win32" and hasattr(_os, "add_dll_directory"):
    # List of directories to add for DLL search
    _dll_dirs = [
        _Path(__file__).parent,  # auroraview package dir (for WebView2Loader.dll)
        _Path(_sys.prefix),  # Python install dir (for python3.dll in DCC apps)
    ]

    for _dll_dir in _dll_dirs:
        if _dll_dir.exists():
            try:
                _os.add_dll_directory(str(_dll_dir))
            except OSError:
                pass  # Directory may already be added or not a valid DLL directory

try:
    from ._core import (
        # High-performance DOM batch operations (Rust-powered)
        DomBatch,
        # Window utilities
        WindowInfo,
        __author__,
        __version__,
        close_window_by_hwnd,
        destroy_window_by_hwnd,
        find_window_by_exact_title,
        find_windows_by_title,
        get_all_windows,
        get_foreground_window,
        fix_webview2_child_windows,  # Qt6 compatibility
        # CLI utilities
        normalize_url,
        rewrite_html_for_custom_protocol,
        # Desktop runner (new name)
        run_desktop,
        # Standalone runner (legacy alias)
        run_standalone,
        # WebView2 warmup (Windows performance optimization)
        start_warmup,
        warmup_sync,
        is_warmup_complete,
        get_warmup_progress,
        get_warmup_stage,
        get_warmup_status,
        get_shared_user_data_folder,
        # WebView2 cleanup (stale directory cleanup)
        cleanup_webview_dirs,
        get_cleanup_stats,
        get_webview_data_dir,
        # Plugin system for native desktop operations
        PluginManager,
        # Thread-safe event emitter for cross-thread operations
        EventEmitter,
        # High-performance JSON functions (orjson-equivalent, no Python deps)
        json_loads,
        json_dumps,
        json_dumps_bytes,
    )
except ImportError as e:
    # Capture the import error for diagnostics
    _CORE_IMPORT_ERROR = str(e)
    # Fallback for development without compiled extension
    __version__ = "0.1.0.dev"
    __author__ = "Hal Long <hal.long@outlook.com>"

    # Placeholder for window utilities
    WindowInfo = None  # type: ignore
    get_foreground_window = None  # type: ignore
    find_windows_by_title = None  # type: ignore
    find_window_by_exact_title = None  # type: ignore
    get_all_windows = None  # type: ignore
    close_window_by_hwnd = None  # type: ignore
    destroy_window_by_hwnd = None  # type: ignore
    fix_webview2_child_windows = None  # type: ignore

    # Placeholder for CLI utilities
    normalize_url = None  # type: ignore
    rewrite_html_for_custom_protocol = None  # type: ignore
    run_desktop = None  # type: ignore
    run_standalone = None  # type: ignore

    # Placeholder for DOM batch
    DomBatch = None  # type: ignore

    # Placeholder for warmup functions
    start_warmup = None  # type: ignore
    warmup_sync = None  # type: ignore
    is_warmup_complete = None  # type: ignore
    get_warmup_progress = None  # type: ignore
    get_warmup_stage = None  # type: ignore
    get_warmup_status = None  # type: ignore
    get_shared_user_data_folder = None  # type: ignore

    # Placeholder for cleanup functions
    cleanup_webview_dirs = None  # type: ignore
    get_cleanup_stats = None  # type: ignore
    get_webview_data_dir = None  # type: ignore

    # Placeholder for plugin system
    PluginManager = None  # type: ignore

    # Placeholder for JSON functions
    json_loads = None  # type: ignore
    json_dumps = None  # type: ignore
    json_dumps_bytes = None  # type: ignore

# Optional: Import runtime classes (if compiled with runtime features)
_RUNTIME_DESKTOP_AVAILABLE = False
_RUNTIME_DCC_AVAILABLE = False

try:
    from ._core import (
        # Desktop runtime (standalone applications)
        DesktopConfig,
        TrayConfig,
        DesktopIpcRouter,
        DesktopWindowManager,
        run_desktop_app,
    )

    _RUNTIME_DESKTOP_AVAILABLE = True
except ImportError:
    DesktopConfig = None  # type: ignore
    TrayConfig = None  # type: ignore
    DesktopIpcRouter = None  # type: ignore
    DesktopWindowManager = None  # type: ignore
    run_desktop_app = None  # type: ignore

try:
    from ._core import (
        # DCC runtime (Maya, Houdini, Nuke integration)
        DccType,
        DccConfig,
        DccIpcRouter,
        DccWindowManager,
    )

    _RUNTIME_DCC_AVAILABLE = True
except ImportError:
    DccType = None  # type: ignore
    DccConfig = None  # type: ignore
    DccIpcRouter = None  # type: ignore
    DccWindowManager = None  # type: ignore


def diagnose_core_library() -> dict:
    """Diagnose core library loading issues.

    Returns a dict with diagnostic information useful for troubleshooting
    when the Rust core library fails to load.

    Returns:
        dict: Diagnostic information including Python version, platform,
              import error details, and file locations.
    """
    result = {
        "python_version": _sys.version,
        "python_executable": _sys.executable,
        "platform": _sys.platform,
        "core_import_error": _CORE_IMPORT_ERROR,
        "core_loaded": _CORE_IMPORT_ERROR is None,
    }

    # Check for _core.pyd location
    try:
        import auroraview

        pkg_dir = _Path(auroraview.__file__).parent
        pyd_path = pkg_dir / "_core.pyd"
        so_path = pkg_dir / "_core.so"

        result["package_dir"] = str(pkg_dir)
        result["pyd_exists"] = pyd_path.exists()
        result["so_exists"] = so_path.exists()

        if pyd_path.exists():
            result["pyd_path"] = str(pyd_path)
            result["pyd_size"] = pyd_path.stat().st_size
        if so_path.exists():
            result["so_path"] = str(so_path)
            result["so_size"] = so_path.stat().st_size
    except Exception as e:
        result["path_check_error"] = str(e)

    # Check sys.path
    import sys

    result["sys_path"] = sys.path[:10]  # First 10 entries

    return result


# Import from submodules
from .core import (
    DEFAULT_SETTINGS,
    BackendType,
    ConnectionGuard,
    ConnectionId,
    Cookie,
    EventEmitter,
    EventHandler,
    LoadEvent,
    NavigationEvent,
    ReadyEvents,
    Signal,
    SignalRegistry,
    WebView,  # Kept for backward compatibility, prefer QtWebView/AuroraView
    WebViewSettings,
    WebViewSignals,
    WindowAPI,
    WindowEvent,
    WindowEventData,
    WindowManager,
    broadcast_event,
    get_active_window,
    get_available_backends,
    get_backend_type,
    get_default_backend,
    get_window_manager,
    get_windows,
    is_backend_available,
    require_bridge_ready,
    require_created,
    require_loaded,
    require_ready,
    require_shown,
    set_backend_type,
    setup_window_api,
)

# Unified API (recommended for new code)
# - create_webview() auto-selects the right implementation based on parent type
# - run_app() is a convenience function for standalone apps
from .api import create_webview, run_app

# Note: WebView is exported for backward compatibility, but for new code:
# - Use create_webview() for automatic mode selection (recommended)
# - Use QtWebView for Qt-based DCC apps (Maya, Houdini, Nuke)
# - Use AuroraView for HWND-based apps (Unreal Engine)
# - Use run_desktop() for standalone desktop applications
from .integration import AuroraView, Bridge, QtWebView
from .core.retained_window import RetainedWindow
from .ui import Element, ElementCollection, Menu, MenuBar, MenuItem, MenuItemType
from .utils import (
    Automation,
    BrowserBackend,
    EventTimer,
    LocalWebViewBackend,
    QtTimerBackend,
    SteelBrowserBackend,
    ThreadTimerBackend,
    TimerBackend,
    get_available_backend,
    list_registered_backends,
    path_to_file_url,
    prepare_html_with_local_assets,
    register_timer_backend,
)

# Runtime diagnostics (host, dispatcher, thread, Qt)
from .diagnostics import diagnostics, format_diagnostics

# Browser module for multi-tab support
from .browser import Browser, TabContainer, TabState

# Feature modules (browser-like capabilities)
from .features import (
    BookmarkManager,
    Bookmark,
    BookmarkFolder,
    HistoryManager,
    HistoryEntry,
    DownloadManager,
    DownloadItem,
    DownloadState,
    SettingsManager,
    Setting,
    NotificationManager,
    Notification,
    NotificationType,
)

# Child window support
from .child import (
    ChildContext,
    ChildInfo,
    get_child_id,
    get_parent_id,
    is_child_mode,
    run_example,
)

# Service Discovery (optional - requires Rust core)
_SERVICE_DISCOVERY_IMPORT_ERROR = None
try:
    from ._core import ServiceDiscovery, ServiceInfo
except ImportError as e:
    _SERVICE_DISCOVERY_IMPORT_ERROR = str(e)

    class ServiceDiscovery:  # type: ignore
        """ServiceDiscovery placeholder - Rust core not available."""

        def __init__(self, *_args, **_kwargs):
            raise ImportError(
                "ServiceDiscovery requires Rust core module. "
                "Rebuild the package with: pip install -e .\n"
                f"Original error: {_SERVICE_DISCOVERY_IMPORT_ERROR}"
            )

    class ServiceInfo:  # type: ignore
        """ServiceInfo placeholder - Rust core not available."""

        pass


# Qt availability flag for tests
_QT_IMPORT_ERROR = None
try:
    from qtpy import QtCore as _QtCore

    _HAS_QT = True
except ImportError as e:
    _HAS_QT = False
    _QT_IMPORT_ERROR = str(e)

# Backward-compatibility aliases for old import paths
# These allow: from auroraview.webview import WebView
# and: from auroraview.event_timer import EventTimer
from . import core

webview = core.webview  # auroraview.webview -> auroraview.core.webview
from . import utils

event_timer = utils.event_timer  # auroraview.event_timer -> auroraview.utils.event_timer
file_protocol = utils.file_protocol  # auroraview.file_protocol -> auroraview.utils.file_protocol
timer_backends = (
    utils.timer_backends
)  # auroraview.timer_backends -> auroraview.utils.timer_backends
from . import ui

dom = ui.dom  # auroraview.dom -> auroraview.ui.dom
from . import integration

qt_integration = integration.qt  # auroraview.qt_integration -> auroraview.integration.qt

# Simple top-level event decorator (for tests/backward-compat)
_EVENT_HANDLERS = {}


def on_event(event_name: str):
    """Top-level event decorator used in basic examples/tests.

    Note: This is a lightweight registry; core event routing is per-WebView via
    webview.on(). This helper exists for compatibility with older code/tests.
    """

    def decorator(func):
        _EVENT_HANDLERS.setdefault(event_name, []).append(func)
        return func

    return decorator


# Submodule imports for organized access
from . import core  # auroraview.core - WebView, Backend, Settings, Cookies
from . import integration  # auroraview.integration - AuroraView, Bridge, Qt
from . import ui  # auroraview.ui - DOM, Menu
from . import utils  # auroraview.utils - EventTimer, FileProtocol, Automation
from . import browser  # auroraview.browser - Browser, TabContainer
from . import (
    features,
)  # auroraview.features - Bookmarks, History, Downloads, Settings, Notifications
# Note: AI module has been moved to separate package: auroraview-ai

__all__ = [
    # ============================================================
    # Submodules (organized access)
    # ============================================================
    "core",  # auroraview.core - WebView, Backend, Settings, Cookies
    "ui",  # auroraview.ui - DOM, Menu
    "integration",  # auroraview.integration - AuroraView, Bridge, Qt
    "utils",  # auroraview.utils - EventTimer, FileProtocol, Automation
    "browser",  # auroraview.browser - Browser, TabContainer
    "features",  # auroraview.features - Bookmarks, History, Downloads, Settings, Notifications
    # ============================================================
    # Unified API (recommended for new code)
    # ============================================================
    # Auto-selects WebView/QtWebView based on parent type
    "create_webview",
    "diagnostics",
    "format_diagnostics",
    # Convenience function for standalone apps
    "run_app",
    # ============================================================
    # Browser API (multi-tab support)
    # ============================================================
    "Browser",
    "TabContainer",
    "TabState",
    # ============================================================
    # Feature modules (browser-like capabilities)
    # ============================================================
    # Bookmarks
    "BookmarkManager",
    "Bookmark",
    "BookmarkFolder",
    # History
    "HistoryManager",
    "HistoryEntry",
    # Downloads
    "DownloadManager",
    "DownloadItem",
    "DownloadState",
    # Settings
    "SettingsManager",
    "Setting",
    # Notifications
    "NotificationManager",
    "Notification",
    "NotificationType",
    # ============================================================
    # Window Management
    # ============================================================
    "WindowManager",
    "get_window_manager",
    "get_windows",
    "get_active_window",
    "broadcast_event",
    # ============================================================
    # Ready Events (lifecycle waiting)
    # ============================================================
    "ReadyEvents",
    "require_created",
    "require_shown",
    "require_loaded",
    "require_bridge_ready",
    "require_ready",
    # ============================================================
    # Primary APIs (legacy - still supported)
    # ============================================================
    # Qt-based DCC integration (Maya, Houdini, Nuke, 3ds Max)
    "QtWebView",
    # HWND-based integration (Unreal Engine, non-Qt apps)
    "AuroraView",
    "RetainedWindow",
    # Desktop standalone apps
    "run_desktop",
    "run_standalone",  # Legacy alias for run_desktop
    # Bridge for DCC integration
    "Bridge",
    # ============================================================
    # Core WebView (backward compatibility)
    # ============================================================
    # Note: Prefer create_webview() for new code
    "WebView",
    # ============================================================
    # Core utilities (auroraview.core)
    # ============================================================
    # Backend abstraction
    "BackendType",
    "get_backend_type",
    "set_backend_type",
    "get_default_backend",
    "get_available_backends",
    "is_backend_available",
    # Settings
    "WebViewSettings",
    "DEFAULT_SETTINGS",
    # Cookie management
    "Cookie",
    # Events
    "WindowEvent",
    "WindowEventData",
    "EventHandler",
    # EventEmitter pattern
    "EventEmitter",
    "NavigationEvent",
    "LoadEvent",
    # Signals (Qt-inspired)
    "Signal",
    "SignalRegistry",
    "ConnectionId",
    "ConnectionGuard",
    "WebViewSignals",
    # ============================================================
    # UI (auroraview.ui)
    # ============================================================
    # DOM manipulation
    "Element",
    "ElementCollection",
    # High-performance DOM batch (Rust-powered)
    "DomBatch",
    # Menu support
    "Menu",
    "MenuBar",
    "MenuItem",
    "MenuItemType",
    # ============================================================
    # Service Discovery
    # ============================================================
    "ServiceDiscovery",
    "ServiceInfo",
    # ============================================================
    # Utils (auroraview.utils)
    # ============================================================
    # Event Timer
    "EventTimer",
    # Timer Backends
    "TimerBackend",
    "QtTimerBackend",
    "ThreadTimerBackend",
    "register_timer_backend",
    "get_available_backend",
    "list_registered_backends",
    # File protocol utilities
    "path_to_file_url",
    "prepare_html_with_local_assets",
    # Automation (Steel Browser compatible)
    "Automation",
    "BrowserBackend",
    "LocalWebViewBackend",
    "SteelBrowserBackend",
    # ============================================================
    # Window utilities (Rust-powered)
    # ============================================================
    "WindowInfo",
    "get_foreground_window",
    "find_windows_by_title",
    "find_window_by_exact_title",
    "get_all_windows",
    "close_window_by_hwnd",
    "destroy_window_by_hwnd",
    "fix_webview2_child_windows",  # Qt6 compatibility
    # ============================================================
    # Window API (JS Bridge)
    # ============================================================
    "WindowAPI",
    "setup_window_api",
    # ============================================================
    # CLI utilities (Rust-powered)
    # ============================================================
    "normalize_url",
    "rewrite_html_for_custom_protocol",
    # ============================================================
    # WebView2 warmup (Windows performance optimization)
    # ============================================================
    "start_warmup",
    "warmup_sync",
    "is_warmup_complete",
    "get_warmup_progress",
    "get_warmup_stage",
    "get_warmup_status",
    "get_shared_user_data_folder",
    # ============================================================
    # WebView2 cleanup (stale directory cleanup)
    # ============================================================
    "cleanup_webview_dirs",
    "get_cleanup_stats",
    "get_webview_data_dir",
    # ============================================================
    # High-performance JSON (Rust-powered, orjson-equivalent)
    # ============================================================
    "json_loads",
    "json_dumps",
    "json_dumps_bytes",
    # ============================================================
    # Plugin system
    # ============================================================
    "PluginManager",
    # ============================================================
    # Runtime classes (optional - require feature flags)
    # ============================================================
    # Desktop runtime
    "DesktopConfig",
    "TrayConfig",
    "DesktopIpcRouter",
    "DesktopWindowManager",
    "run_desktop_app",
    "_RUNTIME_DESKTOP_AVAILABLE",
    # DCC runtime
    "DccType",
    "DccConfig",
    "DccIpcRouter",
    "DccWindowManager",
    "_RUNTIME_DCC_AVAILABLE",
    # ============================================================
    # Child window support
    # ============================================================
    "is_child_mode",
    "get_parent_id",
    "get_child_id",
    "ChildContext",
    "ChildInfo",
    "run_example",
    # ============================================================
    # Helpers
    # ============================================================
    "on_event",
    # ============================================================
    # Backward-compatibility aliases
    # ============================================================
    "_HAS_QT",  # Qt availability flag
    "_QT_IMPORT_ERROR",  # Qt import error message (for tests)
    "webview",  # auroraview.webview -> auroraview.core.webview
    "event_timer",  # auroraview.event_timer -> auroraview.utils.event_timer
    "file_protocol",  # auroraview.file_protocol -> auroraview.utils.file_protocol
    "timer_backends",  # auroraview.timer_backends -> auroraview.utils.timer_backends
    "dom",  # auroraview.dom -> auroraview.ui.dom
    "qt_integration",  # auroraview.qt_integration -> auroraview.integration.qt
    # ============================================================
    # Metadata
    # ============================================================
    "__version__",
    "__author__",
]


# ============================================================
# Auto-start WebView2 warmup on Windows (performance optimization)
# ============================================================
# Multiple WebView instances share a single pre-warmed WebView2 environment.
# By starting warmup during module import, subsequent WebView creation is fast.
# This is especially beneficial in DCC applications where startup time matters.
#
# Note: The warmup runs in a background thread and does not block imports.
# Users can still call start_warmup() manually for custom user_data_folder.
#
# Environment variables:
#   AURORAVIEW_DISABLE_WARMUP=1 - Disable auto-warmup (useful for CI/testing)
_disable_warmup = _os.environ.get("AURORAVIEW_DISABLE_WARMUP", "").lower() in ("1", "true", "yes")
if _sys.platform == "win32" and start_warmup is not None and not _disable_warmup:
    try:
        start_warmup()
    except Exception:
        # Silently ignore warmup errors - they don't affect core functionality
        pass
