# -*- coding: utf-8 -*-
"""High-level Python API for WebView."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

# Import Mixin classes
from auroraview.core.mixins import (
    WebViewApiMixin,
    WebViewBridgeMixin,
    WebViewChannelsMixin,
    WebViewCommandsMixin,
    WebViewContentMixin,
    WebViewDOMMixin,
    WebViewEventMixin,
    WebViewFactoryMixin,
    WebViewJSMixin,
    WebViewLifecycleMixin,
    WebViewStateMixin,
    WebViewTelemetryMixin,
    WebViewWindowMixin,
)

if TYPE_CHECKING:
    from .bridge import Bridge
    from .channel import ChannelManager
    from .commands import CommandRegistry
    from .config import WebViewConfig
    from .ready_events import ReadyEvents
    from .state import State

_CORE_IMPORT_ERROR = None
_IS_PACKED_MODE = False
try:
    from auroraview._core import WebView as _CoreWebView
except ImportError as e:
    _CoreWebView = None
    _CORE_IMPORT_ERROR = str(e)
    # Check if running in packed mode where _core.pyd is not needed
    import os

    _IS_PACKED_MODE = os.environ.get("AURORAVIEW_PACKED", "0") == "1"

logger = logging.getLogger(__name__)


class WebView(
    WebViewLifecycleMixin,
    WebViewWindowMixin,
    WebViewContentMixin,
    WebViewJSMixin,
    WebViewEventMixin,
    WebViewApiMixin,
    WebViewDOMMixin,
    WebViewTelemetryMixin,
    WebViewStateMixin,
    WebViewCommandsMixin,
    WebViewChannelsMixin,
    WebViewFactoryMixin,
    WebViewBridgeMixin,
):
    """High-level WebView class with enhanced Python API.

    This class wraps the Rust core WebView implementation and provides
    a more Pythonic interface with additional features.

    Args:
        title: Window title (default: "AuroraView")
        width: Window width in pixels (default: 800)
        height: Window height in pixels (default: 600)
        url: URL to load (optional)
        html: HTML content to load (optional)
        debug: Enable developer tools (default: True)
        context_menu: Enable native context menu (default: True)
        resizable: Make window resizable (default: True)
        frame: Show window frame (title bar, borders) (default: True)
        parent: Parent window handle for embedding (optional)
        mode: Embedding mode - "child" or "owner" (optional, Windows only)
              "owner" is safer for cross-thread usage
              "child" requires same-thread parenting

    Example:
        >>> # Standalone window
        >>> webview = WebView(title="My Tool", width=1024, height=768)
        >>> webview.load_url("http://localhost:3000")
        >>> webview.show()

        >>> # DCC integration (e.g., Maya)
        >>> import maya.OpenMayaUI as omui
        >>> maya_hwnd = int(omui.MQtUtil.mainWindow())
        >>> webview = WebView(title="My Tool", parent=maya_hwnd, mode="owner")
        >>> webview.show()

        >>> # Disable native context menu for custom menu
        >>> webview = WebView(title="My Tool", context_menu=False)
        >>> webview.show()
    """

    # Class-level singleton registry using weak references
    _singleton_registry: Dict[str, "WebView"] = {}

    def __init__(
        self,
        title: str = "AuroraView",
        width: int = 800,
        height: int = 600,
        url: Optional[str] = None,
        html: Optional[str] = None,
        debug: Optional[bool] = None,
        context_menu: bool = True,
        resizable: bool = True,
        frame: Optional[bool] = None,
        parent: Optional[int] = None,
        mode: Optional[str] = None,
        bridge: Union["Bridge", bool, None] = None,  # type: ignore
        dev_tools: Optional[bool] = None,
        decorations: Optional[bool] = None,
        asset_root: Optional[str] = None,
        data_directory: Optional[str] = None,
        allow_file_protocol: bool = False,
        capture_file_drop: Optional[bool] = None,
        always_on_top: bool = False,
        transparent: bool = False,
        background_color: Optional[str] = None,
        auto_show: bool = True,
        ipc_batch_size: int = 0,
        icon: Optional[str] = None,
        tool_window: bool = False,
        undecorated_shadow: bool = False,
        allow_new_window: bool = False,
        new_window_mode: Optional[str] = None,
        remote_debugging_port: Optional[int] = None,
        splash_overlay: bool = False,
        allow_downloads: bool = True,
        download_prompt: bool = False,
        download_directory: Optional[str] = None,
        proxy_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        # Aliases for more intuitive API
        parent_hwnd: Optional[int] = None,
        embed_mode: Optional[str] = None,
        # DCC thread safety
        dcc_mode: Union[bool, str] = "auto",
        # New structured config (takes precedence if provided)
        config: Optional["WebViewConfig"] = None,
        _native_core: Any = None,
    ) -> None:
        r"""Initialize the WebView.

               Args:
                   title: Window title
                   width: Window width in pixels
                   height: Window height in pixels
                   url: URL to load (optional)
                   html: HTML content to load (optional)
                   debug: Enable developer tools (default: True). Press F12 or right-click
                       > Inspect to open DevTools.
                   context_menu: Enable native context menu (default: True)
                   resizable: Make window resizable (default: True)
                   frame: Show window frame (title bar, borders). If None, uses sensible defaults.
        (default: True)
                   parent: Parent window handle for embedding (optional)
                   mode: Embedding mode - "child" or "owner" (optional)
                   bridge: Bridge instance for DCC integration
                          - Bridge instance: Use provided bridge
                          - True: Auto-create bridge with default settings
                          - None: No bridge (default)
                   asset_root: Root directory for auroraview:// protocol.
                       When set, enables the auroraview:// custom protocol for secure
                       local resource loading. Files under this directory can be accessed
                       using URLs like ``auroraview://path/to/file``.

                       **Platform-specific URL format**:

                       - Windows: ``https://auroraview.localhost/path``
                       - macOS/Linux: ``auroraview://path``

                       **Security**: Uses ``.localhost`` TLD (IANA reserved, RFC 6761)
                       which cannot be registered and is treated as a local address.
                       Requests are intercepted before DNS resolution.

                       **Recommended** over ``allow_file_protocol=True`` because access
                       is restricted to the specified directory only.

                   data_directory: User data directory for WebView (cookies, cache, localStorage).
                       If None, uses system default (usually %LOCALAPPDATA%\...\EBWebView on Windows).
                       Set this to isolate WebView data per application or user profile.

                   allow_file_protocol: Enable file:// protocol support (default: False).
                       **WARNING**: Enabling this allows access to ANY file on the system
                       that the process can read. Only use with trusted content.
                       Prefer using ``asset_root`` for secure local resource loading.

                   always_on_top: Keep window always on top of other windows (default: False).
                       Useful for floating tool panels or overlay windows.

                   tool_window: Apply tool window style (default: False, Windows only).
                       When enabled, the window:
                       - Does NOT appear in the taskbar
                       - Does NOT appear in Alt+Tab window switcher
                       - Has a smaller title bar (if decorations are enabled)

                       This is commonly used with ``embed_mode="owner"`` for floating tool windows.

                       See: https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles

                   undecorated_shadow: Show shadow for frameless windows (default: False, Windows only).
                       When ``frame=False``, Windows can still show a subtle shadow around the window.
                       Set this to ``True`` to explicitly enable the shadow.

                       truly transparent frameless windows (e.g., floating logo buttons).

                       Example::

                           # Transparent logo button with no shadow
                           webview = WebView(
                               html=LOGO_HTML,
                               width=64,
                               height=64,
                               frame=False,
                               transparent=True,
                               undecorated_shadow=False,
                               tool_window=True,
                           )

                   remote_debugging_port: Enable Chrome DevTools Protocol (CDP) remote debugging.
                       When set, the WebView will listen on the specified port for CDP connections.
                       This allows tools like MCP servers, Playwright, or Chrome DevTools to connect
                       and control the WebView remotely.

                       Example::

                           # Enable CDP on port 9222
                           webview = WebView(
                               title="Debug Me",
                               remote_debugging_port=9222,
                           )
                           # Connect with: chrome://inspect or ws://localhost:9222

                   splash_overlay: Show splash overlay while loading URL (default: False).
                       When enabled, displays an animated Aurora-themed loading overlay
                       that automatically fades out when the page is fully loaded.
                       Useful for slow network loads or branded loading experience.

                       Example::

                           # Show splash while loading external URL
                           webview = WebView(
                               url="https://example.com",
                               splash_overlay=True,
                           )

                  allow_downloads: Enable file downloads (default: True).
                      AuroraView enables downloads by default for better user experience.
                      When enabled, allows file downloads from the WebView.

                  download_prompt: Show "Save As" dialog for downloads (default: False).
                      When True, prompts user to choose save location like a browser.
                      When False, downloads go directly to download_directory.

                  download_directory: Default download directory (optional).
                      When set, downloaded files are saved to this directory.
                      Uses system default Downloads folder (e.g., ~/Downloads) if not set.
                      Ignored when download_prompt is True.

                   proxy_url: Proxy server URL (optional).
                       Format: "http://host:port" or "socks5://host:port"
                       When set, all WebView network requests go through this proxy.

                       Example::

                           # Use HTTP proxy
                           webview = WebView(
                               url="https://example.com",
                               proxy_url="http://127.0.0.1:8080",
                           )

                           # Use SOCKS5 proxy
                           webview = WebView(
                               url="https://example.com",
                               proxy_url="socks5://127.0.0.1:1080",
                           )

                   user_agent: Custom User-Agent string (optional).
                       When set, overrides the default browser User-Agent.

                   parent_hwnd: Alias for ``parent`` parameter (for backward compatibility).
                   embed_mode: Alias for ``mode`` parameter. Values: "child", "owner".

                       - **child**: Embed WebView inside a Qt widget (WS_CHILD).
                         Window is clipped to parent bounds, cannot be moved independently.

                       - **owner**: Create floating tool window (GWLP_HWNDPARENT).
                         Window stays above owner in Z-order, hidden when owner minimizes.

                       See: https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features

                   dcc_mode: DCC thread safety mode (default: "auto").
                       Controls whether event handlers are automatically wrapped to run
                       on the DCC main thread. This is essential for Maya, Blender, etc.

                       Values:
                           - ``"auto"``: Automatically detect DCC environment (default).
                             Thread safety is enabled only when running inside a DCC
                             application (Maya, Blender, Houdini, 3ds Max, Nuke, Unreal).
                           - ``True``: Always enable thread safety.
                           - ``False``: Never enable thread safety (for standalone apps).

                       With ``"auto"`` (default), you don't need to specify anything:

                           # In Maya - automatically thread-safe
                           webview = WebView(parent=maya_hwnd)

                           @webview.on("create_object")
                           def handle_create(data):
                               # Automatically runs on Maya main thread!
                               import maya.cmds as cmds
                               return cmds.polyCube()[0]
        """
        if _CoreWebView is None and _native_core is None:
            # In packed mode, _core.pyd is not needed - Python runs as API server
            if _IS_PACKED_MODE:
                logger.info("Packed mode: _core.pyd not available, WebView will run as API server")
            else:
                import sys

                error_details = [
                    "AuroraView core library not found.",
                    f"Import error: {_CORE_IMPORT_ERROR}",
                    f"Python version: {sys.version}",
                    f"Platform: {sys.platform}",
                ]
                # Check if _core.pyd exists in expected locations
                try:
                    import auroraview

                    pkg_dir = Path(auroraview.__file__).parent
                    pyd_path = pkg_dir / "_core.pyd"
                    so_path = pkg_dir / "_core.so"
                    if pyd_path.exists():
                        error_details.append(f"Found: {pyd_path}")
                    elif so_path.exists():
                        error_details.append(f"Found: {so_path}")
                    else:
                        error_details.append(f"_core.pyd not found in: {pkg_dir}")
                except Exception:
                    pass
                raise RuntimeError("\n".join(error_details))

        # Support new WebViewConfig if provided
        if config is not None:
            # Config takes precedence - extract values
            title = config.window.title
            width = config.window.width
            height = config.window.height
            icon = config.window.icon
            frame = config.window.frame
            resizable = config.window.resizable
            always_on_top = config.window.always_on_top
            transparent = config.window.transparent
            background_color = config.window.background_color
            tool_window = config.window.tool_window
            undecorated_shadow = config.window.undecorated_shadow
            url = config.content.url
            html = config.content.html
            asset_root = config.content.asset_root
            allow_file_protocol = config.content.allow_file_protocol
            capture_file_drop = config.content.capture_file_drop
            parent = config.embedding.parent
            mode = config.embedding.mode if config.embedding.parent else None
            dcc_mode = config.embedding.dcc_mode
            auto_show = config.embedding.auto_show
            allow_downloads = config.download.allow_downloads
            download_prompt = config.download.download_prompt
            download_directory = config.download.download_directory
            proxy_url = config.network.proxy_url
            user_agent = config.network.user_agent
            debug = config.debug.debug
            context_menu = config.debug.context_menu
            remote_debugging_port = config.debug.remote_debugging_port
            splash_overlay = config.debug.splash_overlay
            allow_new_window = config.new_window.allow_new_window
            new_window_mode = config.new_window.new_window_mode
            bridge = config.bridge
            data_directory = config.data_directory
            ipc_batch_size = config.ipc_batch_size

        # Backward-compat parameter aliases
        if dev_tools is not None and debug is None:
            debug = dev_tools
        if decorations is not None and frame is None:
            frame = decorations
        if debug is None:
            debug = True

        # Default decorations strategy
        #
        # - Keep explicit overrides: `frame=` / `decorations=` take precedence.
        # - For typical app windows, keep decorations on.
        # - For tool/overlay style windows (tool_window/transparent), default to frameless.
        if frame is None:
            if tool_window or transparent:
                frame = False
            else:
                frame = True

        # Handle parameter aliases for more intuitive API
        # parent_hwnd is alias for parent
        if parent_hwnd is not None and parent is None:
            parent = parent_hwnd
        # embed_mode is alias for mode
        if embed_mode is not None and mode is None:
            mode = embed_mode

        # Map new parameter names to Rust core (which still uses old names)
        # In packed mode, _CoreWebView is not available - Python runs as API server
        self._core_factory = type(_native_core) if _native_core is not None else _CoreWebView
        self._core_kwargs = {
            "title": title,
            "width": width,
            "height": height,
            "url": url,
            "html": html,
            "dev_tools": debug,
            "context_menu": context_menu,
            "resizable": resizable,
            "decorations": frame,
            "parent_hwnd": parent,
            "parent_mode": mode,
            "asset_root": asset_root,
            "data_directory": data_directory,
            "allow_file_protocol": allow_file_protocol,
            # RFC 0017: pass tri-state Optional[bool] through unchanged.
            # Rust binding applies unwrap_or(false); do not collapse here.
            "capture_file_drop": capture_file_drop,
            "always_on_top": always_on_top,
            "transparent": transparent,
            "background_color": background_color,
            "auto_show": auto_show,
            "ipc_batch_size": ipc_batch_size,
            "icon": icon,
            "tool_window": tool_window,
            "undecorated_shadow": undecorated_shadow,
            "allow_new_window": allow_new_window,
            "new_window_mode": new_window_mode,
            "remote_debugging_port": remote_debugging_port,
            "splash_overlay": splash_overlay,
            "allow_downloads": allow_downloads,
            "download_prompt": download_prompt,
            "download_directory": download_directory,
            "proxy_url": proxy_url,
            "user_agent": user_agent,
        }
        if _native_core is not None:
            self._core = _native_core
        elif _CoreWebView is not None:
            self._core = self._core_factory(**self._core_kwargs)
        else:
            self._core = None  # Packed mode: no Rust core needed
        # Preserve native smart-show detection without querying a foreign core.
        self._is_embedded = _native_core is not None or bool(
            getattr(self._core, "_is_embedded", False)
        )

        # Record which thread owns each Rust core so a later close() raised on
        # another thread can be routed through the close channel instead of
        # touching the unsendable object directly.
        self._core_threads: Dict[int, int] = {}
        self._core_proxies: Dict[int, Any] = {}
        self._track_core_thread(self._core)

        self._event_handlers: Dict[str, List[Callable]] = {}
        self._event_handlers_lock = threading.Lock()
        self._title = title
        self._width = width
        self._height = height
        self._x = 0
        self._y = 0
        self._debug = debug
        self._resizable = resizable
        self._frame = frame
        self._parent = parent
        self._mode = mode
        self._always_on_top = always_on_top
        self._transparent = transparent
        self._background_color = background_color
        self._tool_window = tool_window
        self._undecorated_shadow = undecorated_shadow
        self._allow_new_window = allow_new_window
        self._new_window_mode = new_window_mode
        self._remote_debugging_port = remote_debugging_port
        self._splash_overlay = splash_overlay

        # Resolve dcc_mode: "auto" → detect DCC environment
        if dcc_mode == "auto":
            from auroraview.utils.thread_dispatcher import is_dcc_environment

            self._dcc_mode = is_dcc_environment()
            if self._dcc_mode:
                from auroraview.utils.thread_dispatcher import get_current_dcc_name

                dcc_name = get_current_dcc_name()
                logger.info(f"DCC mode auto-enabled: {dcc_name} detected")
        else:
            self._dcc_mode = bool(dcc_mode)
        self._show_thread: Optional[threading.Thread] = None
        self._is_running = _native_core is not None
        self._auto_timer = None  # Will be set by create() factory method
        self._auto_show = auto_show  # Store auto_show setting
        # Store content for async mode (use passed-in values)
        self._stored_url: Optional[str] = url
        self._stored_html: Optional[str] = html
        # Store the background thread's core instance
        self._async_core: Optional[Any] = None
        self._async_core_lock = threading.Lock()
        # Track if running in blocking event loop (for HWND mode)
        self._in_blocking_event_loop = False
        # Thread-safe HWND cache (for cross-thread access in non-blocking mode)
        self._cached_hwnd: Optional[int] = None
        self._cached_hwnd_lock = threading.Lock()

        # Close requested flag (used to coordinate background-thread WebView lifecycle)
        self._close_requested = False
        self._native_close_observed = False
        self._lifecycle_lock = threading.RLock()
        self._closed_event = threading.Event()
        if not self._is_running:
            self._closed_event.set()  # There is no running event loop yet.
        self._close_sent = set()
        self._close_pending = {}
        self._close_send_done = threading.Event()
        self._close_send_done.set()
        self._host_cleanup_done = threading.Event()
        self._host_cleanup_done.set()
        self._timer_cleanup_pending = False
        self._startup_error: Optional[Exception] = None

        # Event processor (strategy pattern for UI framework integration)
        self._event_processor: Optional[Any] = None

        # Post eval_js hook (for Qt integration and testing)
        self._post_eval_js_hook: Optional[Callable[[], None]] = None

        # Bridge integration
        self._bridge: Optional["Bridge"] = None  # type: ignore
        if bridge is not None:
            if bridge is True:
                # Auto-create bridge with default settings
                from .bridge import Bridge

                self._bridge = Bridge(port=9001)
                logger.info("Auto-created Bridge on port 9001")
            else:
                # Use provided bridge instance
                self._bridge = bridge
                logger.info(f"Using provided Bridge: {bridge}")

            # Setup bidirectional communication
            if self._bridge:
                self._setup_bridge_integration()

        # Shared state system (lazy initialization)
        self._state: Optional["State"] = None

        # Command registry (lazy initialization)
        self._commands: Optional["CommandRegistry"] = None

        # Channel manager (lazy initialization)
        self._channels: Optional["ChannelManager"] = None

        # Plugin manager for handling plugin:* invoke commands
        self._plugin_manager: Optional[Any] = None

        # WindowManager integration - register this window globally
        from .ready_events import ReadyEvents
        from .window_manager import get_window_manager

        self._window_id: Optional[str] = None
        self._ready_events = ReadyEvents(self)

        # Register with WindowManager
        wm = get_window_manager()
        self._window_id = wm.register(self)
        logger.debug(f"WebView registered with WindowManager: {self._window_id}")

        # Mark as created
        self._ready_events.set_created()

        # Setup lifecycle event handlers
        self._setup_lifecycle_events()

        # Initialize auto-telemetry (after WindowManager registration)
        self._init_telemetry()

    def _init_embedded_core(
        self,
        core: Any,
        *,
        parent_hwnd: int,
        title: str,
        width: int,
        height: int,
        url: Optional[str],
        html: Optional[str],
        asset_root: Optional[str],
        debug: bool,
    ) -> None:
        """Initialize both legacy __new__ factories through the normal bootstrap.

        The supplied native core is already live on this thread. It must not be
        constructed again, but needs every normal Python registry and lifecycle
        field, including future additions to the standard constructor.
        """
        WebView.__init__(
            self,
            title=title,
            width=width,
            height=height,
            parent=parent_hwnd,
            mode="child",
            url=url,
            html=html,
            asset_root=asset_root,
            debug=debug,
            auto_show=False,
            _native_core=core,
        )
        self._config = {
            "title": title,
            "width": width,
            "height": height,
            "url": url,
            "html": html,
            "asset_root": asset_root,
            "debug": debug,
        }

    def set_event_processor(self, processor: Any) -> None:
        """Set event processor (strategy pattern for UI framework integration).

        Args:
            processor: Event processor object with a `process()` method.
                      This allows UI frameworks (Qt, Tk, etc.) to inject their
                      event processing logic.

        Example:
            >>> class QtEventProcessor:
            ...     def process(self):
            ...         QCoreApplication.processEvents()
            ...         webview._core.process_events()
            >>>
            >>> processor = QtEventProcessor()
            >>> webview.set_event_processor(processor)
        """
        self._event_processor = processor
        logger.debug(f"Event processor set: {type(processor).__name__}")

    def set_plugin_manager(self, plugin_manager: Any) -> None:
        """Set plugin manager for handling plugin:* invoke commands.

        This enables JavaScript to call Rust plugins via `window.auroraview.invoke()`.

        Args:
            plugin_manager: PluginManager instance from auroraview.PluginManager

        Example:
            >>> from auroraview import WebView, PluginManager
            >>>
            >>> view = WebView(title="Plugin Demo")
            >>> plugins = PluginManager.permissive()
            >>> view.set_plugin_manager(plugins)
            >>>
            >>> # Now JavaScript can call plugins:
            >>> # await auroraview.invoke("plugin:fs|read_file", {path: "/tmp/test.txt"})
        """
        self._plugin_manager = plugin_manager
        # Register handler for __plugin_invoke__ events from Rust IPC
        self.register_callback("__plugin_invoke__", self._handle_plugin_invoke)
        logger.info("Plugin manager set and __plugin_invoke__ handler registered")

    def _handle_plugin_invoke(self, data: dict) -> None:
        """Handle plugin invoke commands from JavaScript.

        This is called when Rust IPC receives a `type: 'invoke'` message
        and forwards it as `__plugin_invoke__` event.

        Args:
            data: Dict with 'cmd', 'args', and optional 'id' fields
        """
        if self._plugin_manager is None:
            logger.warning("Plugin invoke received but no plugin manager set")
            return

        cmd = data.get("cmd", "")
        args = data.get("args", {})
        call_id = data.get("id")

        logger.info(f"[Plugin] Invoke: {cmd}, args: {args}, id: {call_id}")

        try:
            # Convert args to JSON string for PluginManager.handle_command()
            args_json = json.dumps(args) if isinstance(args, dict) else "{}"
            result_json = self._plugin_manager.handle_command(cmd, args_json)
            result = json.loads(result_json)

            # Send result back to JavaScript
            payload = {
                "id": call_id,
                "ok": result.get("success", False),
            }
            if result.get("success"):
                payload["result"] = result.get("data")
            else:
                payload["error"] = {
                    "message": result.get("error", "Unknown error"),
                    "code": result.get("code", "PLUGIN_ERROR"),
                }

            # Emit result via __invoke_result__ event
            self.emit("__invoke_result__", payload)
            logger.info(f"[Plugin] Result sent: {payload}")

        except Exception as e:
            logger.error(f"[Plugin] Error handling invoke: {e}")
            error_payload = {
                "id": call_id,
                "ok": False,
                "error": {
                    "message": str(e),
                    "code": "INTERNAL_ERROR",
                },
            }
            self.emit("__invoke_result__", error_payload)

    def _auto_process_events(self) -> None:
        """Automatically process events after emit() or eval_js().

        This method uses the strategy pattern:
        1. If in blocking event loop (HWND mode), skip - event loop handles it
        2. If an event processor is set, use it (UI framework integration)
        3. Otherwise, use default implementation (direct Rust call)

        Subclasses can still override this method for custom behavior.
        """
        # Skip if we're in a blocking event loop (e.g., HWND mode background thread)
        # The event loop automatically processes the message queue
        if self._in_blocking_event_loop:
            logger.debug("Skipping _auto_process_events - in blocking event loop")
            return

        if self._show_thread is not None:
            return
        core = self._get_active_core()
        if core is None or not self._is_core_owner(core):
            return

        try:
            if self._event_processor is not None:
                # Use strategy pattern: delegate to event processor
                self._event_processor.process()
            else:
                # Default implementation: direct Rust call
                core.process_events()
        except Exception as e:
            logger.debug(f"Auto process events failed (non-critical): {e}")

    def process_events(self) -> bool:
        """Process pending window events.

        This method should be called periodically in embedded mode to handle
        window messages and user interactions. Returns True if the window
        should be closed.

        Returns:
            True if the window should close, False otherwise. Also returns
            False when no backing core is currently available (packed mode,
            pre-init, post-dispose) — in those cases there is nothing to
            drain and synthesizing a close request would be wrong.

        Example:
            >>> # In Maya, use a scriptJob to process events
            >>> def process_webview_events():
            ...     if webview.process_events():
            ...         # Window should close
            ...         cmds.scriptJob(kill=job_id)
            ...
            >>> job_id = cmds.scriptJob(event=["idle", process_webview_events])
        """
        # Prefer ``_async_core`` when wired up by the show-thread, then
        # fall back to ``_core``. Without this, packed mode
        # (``_core is None`` but ``_async_core`` wired up by the
        # show-thread) would have ``is_ready`` report True while
        # ``self._core.process_events()`` raises ``AttributeError`` on
        # every 16 ms timer tick.
        with self._async_core_lock:
            core = self._async_core if self._async_core is not None else self._core
        if core is None:
            return False
        if not self._is_core_owner(core):
            return False  # The owner loop drains its own queue.
        should_close = core.process_events()
        if should_close:
            self._observe_native_close()
            self.request_close()
        return should_close

    def process_events_ipc_only(self) -> bool:
        """Process only internal AuroraView IPC without touching host event loop.

        This variant is intended for host-driven embedding scenarios (Qt/DCC)
        where the native window message pump is owned by the host application.
        It only drains the internal WebView message queue and respects
        lifecycle close requests.

        Returns:
            True if the window should close, False otherwise. Also returns
            False when no backing core is currently available — see
            :meth:`process_events` for the full enumeration.
        """
        # Same active-core probe as :meth:`process_events`; see that method
        # for the rationale on aligning with :attr:`is_ready` semantics.
        with self._async_core_lock:
            core = self._async_core if self._async_core is not None else self._core
        if core is None:
            return False
        if not self._is_core_owner(core):
            return False
        should_close = core.process_ipc_only()
        if should_close:
            self._observe_native_close()
            self.request_close()
        return should_close

    def is_alive(self) -> bool:
        """Check if WebView is still running.

        Returns:
            True if WebView is running, False otherwise

        Example:
            >>> webview.show(wait=False)
            >>> while webview.is_alive():
            ...     time.sleep(0.1)
        """
        if getattr(self, "_host_runtime", None) is not None:
            core = self._require_owner_core("is_alive") if not self._close_requested else self._core
            if not self._is_core_owner(core):
                raise RuntimeError("Hosted is_alive must run on the owner thread")
            return core is not None and core.is_alive()
        if self._show_thread is None:
            return False
        return self._show_thread.is_alive()

    def get_hwnd(self) -> Optional[int]:
        """Get the native window handle (HWND on Windows).

        This is useful for integrating with external applications that need
        the native window handle, such as:
        - Unreal Engine: `unreal.parent_external_window_to_slate(hwnd)`
        - Windows API: Direct window manipulation
        - Other DCC tools with HWND-based integration

        Returns:
            int: The native window handle (HWND), or None if not available.

        Raises:
            RuntimeError: If WebView is not initialized (call show() first).

        Example:
            >>> webview = WebView.create(...)
            >>> webview.show()
            >>> hwnd = webview.get_hwnd()
            >>> if hwnd:
            ...     print(f"Window HWND: 0x{hwnd:x}")
            ...     # Use with Unreal Engine
            ...     # unreal.parent_external_window_to_slate(hwnd)
        """
        # First check Python-side cached HWND (thread-safe, works in non-blocking mode)
        with self._cached_hwnd_lock:
            if self._cached_hwnd is not None:
                return self._cached_hwnd

        # In non-blocking mode (show_thread exists), avoid calling Rust core
        # as it may cause GIL contention and blocking
        if self._show_thread is not None:
            # Background thread mode - only use Python-side cache
            # The cache is set by the on_hwnd_created callback in the background thread
            return None

        # Fall back to Rust core (only works if called from the same thread)
        # This is for blocking mode or when called from the background thread
        try:
            core = self._get_active_core()
            if core is not None and self._is_core_owner(core):
                return core.get_hwnd()
            return None
        except Exception:
            # In non-blocking mode, _core.get_hwnd() may fail due to thread safety
            return None

    def get_proxy(self) -> Any:
        """Get a thread-safe proxy for cross-thread operations.

        Returns a WebViewProxy that can be safely shared across threads.
        Use this when you need to call `eval_js`, `emit`, etc. from a different
        thread than the one that created the WebView.

        This is essential for HWND mode where the WebView runs in a background
        thread but you need to call methods from the DCC main thread.

        Returns:
            WebViewProxy: A thread-safe proxy for WebView operations.
                The proxy supports:
                - eval_js(script): Execute JavaScript
                - eval_js_async(script, callback, timeout_ms): Async JavaScript
                - emit(event_name, data): Emit events to JavaScript
                - load_url(url): Load a URL
                - load_html(html): Load HTML content
                - reload(): Reload the current page

        Example:
            >>> # In HWND mode - WebView runs in background thread
            >>> def create_webview_thread():
            ...     webview = WebView(...)
            ...     proxy = webview.get_proxy()  # Get thread-safe proxy
            ...     self._proxy = proxy          # Store for cross-thread access
            ...     webview.show_blocking()
            ...
            >>> # From DCC main thread - safe!
            >>> self._proxy.eval_js("console.log('Hello from DCC!')")
            >>> self._proxy.emit("update", {"status": "ready"})

        Note:
            The proxy uses a message queue internally. Operations are queued
            and processed by the WebView's event loop on the correct thread.
        """
        return WebViewJSMixin.get_proxy(self)

    def create_emitter(self) -> Any:
        """Create a thread-safe event emitter.

        Returns an EventEmitter that can be safely used from any thread to emit
        events to the JavaScript frontend. This is useful for plugin callbacks
        that run on background threads (e.g., ProcessPlugin).

        Unlike `emit()` which must be called from the main thread, the emitter
        returned by this method can be called from any thread safely.

        Returns:
            EventEmitter: A thread-safe emitter with an `emit(event_name, data)` method.

        Example:
            >>> # Create emitter for cross-thread event emission
            >>> emitter = webview.create_emitter()
            >>>
            >>> # Use with PluginManager (ProcessPlugin runs on background threads)
            >>> plugins = PluginManager.permissive()
            >>> plugins.set_emit_callback(emitter.emit)
            >>>
            >>> # ProcessPlugin will emit events like:
            >>> # - process:stdout - { pid, data }
            >>> # - process:stderr - { pid, data }
            >>> # - process:exit - { pid, code }
        """
        core = self._get_active_core()
        emitter = getattr(self, "_core_emitters", {}).get(id(core))
        if emitter is None:
            raise RuntimeError("WebView has no cached thread-safe EventEmitter")
        return emitter

    def thread_safe(self) -> Any:
        """Get a thread-safe wrapper for cross-thread operations.

        Returns a DCCThreadSafeWrapper that provides thread-safe methods
        for common WebView operations. Use this when you need to call
        WebView methods from a different thread than the one that created it.

        This is particularly useful in DCC environments where:
        - WebView runs in a background thread (HWND mode)
        - You need to call methods from the DCC main thread
        - You want simpler API than using get_proxy() directly

        Returns:
            DCCThreadSafeWrapper: A wrapper with thread-safe methods including:
                - eval_js(script): Execute JavaScript (fire-and-forget)
                - eval_js_sync(script, timeout): Execute JavaScript (blocking)
                - emit(event_name, data): Emit events to JavaScript
                - load_url(url): Load a URL
                - load_html(html): Load HTML content
                - reload(): Reload the current page
                - close(): Close the WebView

        Example:
            >>> webview = WebView(parent=dcc_hwnd)
            >>> webview.show()  # Runs in background thread
            >>>
            >>> # From any thread:
            >>> safe = webview.thread_safe()
            >>> safe.eval_js("updateStatus('ready')")
            >>> safe.emit("data_loaded", {"count": 100})
            >>>
            >>> # Synchronous JavaScript execution
            >>> title = safe.eval_js_sync("document.title")

        Note:
            The wrapper uses the internal message queue to deliver operations
            to the WebView thread. Most operations are non-blocking.
        """
        from auroraview.utils.thread_dispatcher import DCCThreadSafeWrapper

        return DCCThreadSafeWrapper(self)

    @property
    def dcc_mode(self) -> bool:
        """Check if DCC thread safety mode is enabled.

        Returns:
            bool: True if dcc_mode is enabled, False otherwise.
        """
        return self._dcc_mode

    def _setup_lifecycle_events(self) -> None:
        """Setup internal event handlers for lifecycle tracking."""

        # Track page load completion
        @self.on("page:load_finish")
        def _on_load_finish(data: Any) -> None:
            if hasattr(self, "_ready_events") and self._ready_events:
                self._ready_events.set_loaded()
            # Auto-telemetry: record page load time
            self._telemetry_on_page_loaded()

        # Track bridge ready
        @self.on("auroraviewready")
        def _on_bridge_ready(data: Any) -> None:
            if hasattr(self, "_ready_events") and self._ready_events:
                self._ready_events.set_bridge_ready()

    @property
    def window_id(self) -> Optional[str]:
        """Get the unique window ID in WindowManager.

        Returns:
            The window's unique ID, or None if not registered
        """
        return self._window_id

    @property
    def ready_events(self) -> "ReadyEvents":
        """Get the ReadyEvents container for lifecycle waiting.

        Returns:
            ReadyEvents instance for this WebView

        Example:
            >>> webview.ready_events.wait_loaded(timeout=10)
            >>> webview.ready_events.wait_bridge_ready()
        """
        return self._ready_events

    @property
    def title(self) -> str:
        """Get the window title."""
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        """Set the window title."""
        self._window_command("set_title", value)
        self._title = value

    def __repr__(self) -> str:
        """String representation of the WebView."""
        return f"WebView(title='{self._title}', width={self._width}, height={self._height})"

    def __enter__(self) -> "WebView":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ARG002
        """Context manager exit."""
        self.close()
