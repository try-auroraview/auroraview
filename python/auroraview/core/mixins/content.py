# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Content Loading Mixin.

This module provides content loading methods for the WebView class.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


class WebViewContentMixin:
    """Mixin providing content loading methods.

    Provides methods for loading content into the WebView:
    - load_url: Load a URL
    - get_current_url: Get the current URL
    - load_html: Load HTML content
    - load_file: Load a local HTML file via file:// URL
    - load_local_html: Load local HTML with path rewriting
    """

    # Type hints for attributes from main class
    _core: Any
    _async_core: Optional[Any]
    _async_core_lock: threading.Lock
    _stored_url: Optional[str]
    _stored_html: Optional[str]

    def load_url(self, url: str) -> None:
        """Load a URL in the WebView.

        Args:
            url: The URL to load

        Example:
            >>> webview.load_url("https://example.com")
        """
        logger.info(f"Loading URL: {url}")
        self._stored_url = url
        self._stored_html = None

        # Auto-telemetry: record navigation
        if hasattr(self, "_telemetry_on_navigate"):
            self._telemetry_on_navigate(url)

        # Use the async core if available (when running in background thread)
        self._command_target().load_url(url)

    def get_current_url(self) -> Optional[str]:
        """Get the current URL of the WebView.

        From a foreign thread, returns the last URL requested through this
        wrapper; the send-safe proxy does not expose native URL queries.

        Returns:
            The current URL, or None if not available

        Example:
            >>> url = webview.get_current_url()
            >>> print(f"Current URL: {url}")
        """
        # Use the async core if available
        core = self._get_active_core()
        if core is None or not self._is_core_owner(core):
            return self._stored_url

        # Try to get from Rust core first
        if hasattr(core, "get_current_url"):
            try:
                return core.get_current_url()
            except Exception as e:
                logger.debug(f"Failed to get URL from core: {e}")

        # Fallback to stored URL
        return self._stored_url

    def load_html(self, html: str) -> None:
        """Load HTML content in the WebView.

        Args:
            html: HTML content to load

        Example:
            >>> webview.load_html("<h1>Hello, World!</h1>")
        """
        logger.info(f"Loading HTML ({len(html)} bytes)")
        self._stored_html = html
        self._stored_url = None

        # Auto-telemetry: record navigation for inline HTML
        if hasattr(self, "_telemetry_on_navigate"):
            self._telemetry_on_navigate("about:blank (inline HTML)")

        # Use the async core if available (when running in background thread)
        self._command_target().load_html(html)

    def load_file(self, path: Union[str, Path]) -> None:
        """Load a local HTML file via a ``file://`` URL.

        This helper is intended for "static site" style frontends where
        an ``index.html`` and its assets (images/CSS/JS) live on disk.
        It resolves the given path and forwards to :meth:`load_url` with
        a ``file:///`` URL so that all relative asset paths are handled
        by the browser as usual.

        **IMPORTANT**: To load local files with their assets (CSS, JS, images),
        you must enable file protocol support when creating the WebView:

        - ``allow_file_protocol=True``: Allow loading via file:// protocol
        - ``asset_root``: Set to the directory containing your assets to use
          the more secure ``auroraview://`` protocol

        Args:
            path: Filesystem path to an HTML file.

        Example:
            >>> # Method 1: Using file:// protocol (simpler but less secure)
            >>> webview = WebView.create(title="My App", allow_file_protocol=True)
            >>> webview.load_file("dist/index.html")

            >>> # Method 2: Using auroraview:// protocol (recommended)
            >>> # In your HTML, use: <script src="auroraview://js/app.js"></script>
            >>> webview = WebView.create(title="My App", asset_root="dist")
            >>> webview.load_html(open("dist/index.html").read())
        """
        html_path = Path(path).expanduser().resolve()
        self.load_url(html_path.as_uri())

    def load_local_html(self, path: Union[str, Path], rewrite_paths: bool = True) -> None:
        """Load a local HTML file with automatic relative path resolution.

        This method reads an HTML file and automatically rewrites relative
        resource paths (CSS, JS, images) to use the ``auroraview://`` protocol.

        Args:
            path: Filesystem path to an HTML file.
            rewrite_paths: Whether to automatically rewrite relative paths to
                          use ``auroraview://`` protocol. Default: True.

        Example:
            >>> from pathlib import Path
            >>> html_path = Path("dist/index.html")
            >>> webview = WebView.create(
            ...     title="My App",
            ...     asset_root=str(html_path.parent),
            ... )
            >>> webview.load_local_html(html_path)
            >>> webview.show()
        """
        from auroraview import rewrite_html_for_custom_protocol

        html_path = Path(path).expanduser().resolve()
        if not html_path.exists():
            raise FileNotFoundError(f"HTML file not found: {html_path}")

        # Read HTML content
        html_content = html_path.read_text(encoding="utf-8")

        # Rewrite relative paths to use auroraview:// protocol
        if rewrite_paths:
            html_content = rewrite_html_for_custom_protocol(html_content)
            logger.info(
                f"Loaded local HTML file with path rewriting: {html_path} ({len(html_content)} bytes)"
            )
        else:
            logger.info(f"Loaded local HTML file: {html_path} ({len(html_content)} bytes)")

        self.load_html(html_content)
