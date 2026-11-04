# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""WebView Window Control Mixin.

This module provides window control methods for the WebView class.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


class WebViewWindowMixin:
    """Mixin providing window control methods.

    Provides methods for controlling the WebView window:
    - move: Move window to a new position
    - resize: Resize the window
    - minimize: Minimize the window
    - maximize: Maximize the window
    - restore: Restore window from minimized/maximized
    - toggle_fullscreen: Toggle fullscreen mode
    - set_always_on_top: Set window always on top
    - hide: Hide the window
    - focus: Focus the window
    """

    # Type hints for attributes from main class
    _core: Any
    _x: int
    _y: int
    _width: int
    _height: int

    def _window_command(self, name: str, *args: Any) -> None:
        """Window controls require native owner support or a proxy operation."""
        target = self._command_target()
        method = getattr(target, name, None)
        if method is None:
            if getattr(self, "_retained_window", None) is not None:
                raise RuntimeError(f"{name} is unavailable on this retained window")
            if self._is_core_owner(self._get_active_core()):
                logger.warning("%s not supported by current backend", name)
                return
            raise RuntimeError(f"{name} is unavailable on this WebView thread/backend")
        method(*args)

    def move(self, x: int, y: int) -> None:
        """Move the window to a new position.

        Args:
            x: New x position (pixels from left)
            y: New y position (pixels from top)

        Example:
            >>> webview.move(100, 50)
        """
        self._window_command("move_to", x, y)
        self._x = x
        self._y = y

    def resize(self, width: int, height: int) -> None:
        """Resize the window.

        Args:
            width: New width in pixels
            height: New height in pixels

        Example:
            >>> webview.resize(1024, 768)
        """
        self._window_command("resize", width, height)
        self._width = width
        self._height = height

    def minimize(self) -> None:
        """Minimize the window."""
        self._window_command("minimize")

    def maximize(self) -> None:
        """Maximize the window."""
        self._window_command("maximize")

    def restore(self) -> None:
        """Restore the window from minimized/maximized state."""
        self._window_command("restore")

    def unmaximize(self) -> None:
        """Leave maximized state."""
        self._window_command("unmaximize")

    def toggle_maximize(self) -> None:
        """Toggle maximized state."""
        self._window_command("toggle_maximize")

    def set_fullscreen(self, fullscreen: bool) -> None:
        """Set fullscreen state."""
        self._window_command("set_fullscreen", fullscreen)

    def set_visible(self, visible: bool) -> None:
        """Show or hide the retained window without implicit focus."""
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            retained.set_visible(visible)
        else:
            self._window_command("set_visible", visible)

    def set_focus(self) -> None:
        """Request focus on a ready window."""
        self.focus()

    def set_position(self, x: int, y: int) -> None:
        self.move(x, y)

    def move_to(self, x: int, y: int) -> None:
        self.move(x, y)

    def set_size(self, width: int, height: int) -> None:
        self.resize(width, height)

    def set_window_title(self, title: str) -> None:
        self.title = title

    def set_title(self, title: str) -> None:
        self.set_window_title(title)

    def center(self) -> None:
        self._window_command("center")

    def set_min_size(self, width: int, height: int) -> None:
        self._window_command("set_min_size", width, height)

    def set_max_size(self, width: int, height: int) -> None:
        self._window_command("set_max_size", width, height)

    def set_resizable(self, value: bool) -> None:
        self._window_command("set_resizable", value)

    def set_decorations(self, value: bool) -> None:
        self._window_command("set_decorations", value)

    def sync_bounds(self, width: int, height: int) -> None:
        self._window_command("sync_bounds", width, height)

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode."""
        self._window_command("toggle_fullscreen")

    def set_always_on_top(self, on_top: bool = True) -> None:
        """Set whether the window should always be on top.

        Args:
            on_top: True to keep window on top, False otherwise
        """
        self._window_command("set_always_on_top", on_top)
        self._always_on_top = on_top

    def hide(self) -> None:
        """Hide the window without closing it."""
        self._window_command("hide")

    def focus(self) -> None:
        """Bring the window to the front and give it focus."""
        self._window_command("focus")

    @property
    def width(self) -> int:
        """Get the window width."""
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            return retained._control.snapshot()["width"]
        return self._width

    @property
    def height(self) -> int:
        """Get the window height."""
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            return retained._control.snapshot()["height"]
        return self._height

    @property
    def x(self) -> Optional[int]:
        """Get the window x position."""
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            return retained._control.snapshot()["x"]
        return self._x

    @property
    def y(self) -> Optional[int]:
        """Get the window y position."""
        retained = getattr(self, "_retained_window", None)
        if retained is not None:
            return retained._control.snapshot()["y"]
        return self._y
