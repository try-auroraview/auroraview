//! AuroraView Core - Browser Object Model (BOM) APIs
//!
//! This module contains BOM-related methods (Tauri-aligned):
//! - Navigation APIs (go_back, go_forward, reload, stop)
//! - Loading state APIs (is_loading, load_progress)
//! - Zoom APIs (set_zoom)
//! - Window control APIs (minimize, maximize, fullscreen, etc.)

use pyo3::prelude::*;

use super::AuroraView;
use crate::ipc::WebViewMessage;
use crate::webview::window_control::WindowCommand;

#[pymethods]
impl AuroraView {
    // ========================================
    // BOM Navigation APIs
    // ========================================

    /// Navigate back in history
    fn go_back(&self) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .go_back()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Navigate forward in history
    fn go_forward(&self) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .go_forward()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Stop loading current page
    fn stop(&self) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .stop()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if can navigate back in history
    fn can_go_back(&self) -> PyResult<bool> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .can_go_back()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if can navigate forward in history
    fn can_go_forward(&self) -> PyResult<bool> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .can_go_forward()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    // ========================================
    // BOM Loading State APIs
    // ========================================

    /// Check if the page is currently loading
    fn is_loading(&self) -> PyResult<bool> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .is_loading()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Get the current page load progress (0-100)
    fn load_progress(&self) -> PyResult<u8> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .load_progress()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    // ========================================
    // BOM Zoom APIs
    // ========================================

    /// Set zoom level (1.0 = 100%, 1.5 = 150%, etc.)
    fn set_zoom(&self, scale_factor: f64) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_zoom(scale_factor)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    // ========================================
    // BOM Window Control APIs
    // ========================================

    /// Minimize window
    fn minimize(&self) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Minimize) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .minimize()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Maximize window
    fn maximize(&self) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Maximize) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .maximize()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Unmaximize (restore) window
    fn unmaximize(&self) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Unmaximize) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .unmaximize()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Toggle maximize state
    fn toggle_maximize(&self) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::ToggleMaximize) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .toggle_maximize()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if window is maximized
    fn is_maximized(&self) -> PyResult<bool> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(result?.maximized);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.is_maximized())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if window is minimized
    fn is_minimized(&self) -> PyResult<bool> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(result?.minimized);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.is_minimized())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set fullscreen mode
    fn set_fullscreen(&self, fullscreen: bool) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetFullscreen(fullscreen)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_fullscreen(fullscreen)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if window is in fullscreen mode
    fn is_fullscreen(&self) -> PyResult<bool> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(result?.fullscreen);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.is_fullscreen())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set window visibility
    fn set_visible(&self, visible: bool) -> PyResult<()> {
        if let Some(shared) = self.retained.borrow().as_ref() {
            if visible {
                shared
                    .control
                    .show(false)
                    .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
            } else {
                shared.control.hide();
            }
            return shared
                .signal()
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }
        if let Ok(inner_ref) = self.inner.try_borrow() {
            if let Some(ref inner) = *inner_ref {
                return inner
                    .set_visible(visible)
                    .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()));
            }
        }
        // Fall back to message queue (async mode)
        self.message_queue.push(WebViewMessage::SetVisible(visible));
        Ok(())
    }

    /// Check if window is visible
    fn is_visible(&self) -> PyResult<bool> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(result?.visible);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.is_visible())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Check if window has focus
    fn is_focused(&self) -> PyResult<bool> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(result?.focused);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.is_focused())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Request focus for the window
    fn set_focus(&self) -> PyResult<()> {
        if let Some(shared) = self.retained.borrow().as_ref() {
            shared
                .control
                .snapshot()
                .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
            shared
                .control
                .show(true)
                .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
            return shared
                .signal()
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_focus()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set always on top
    fn set_always_on_top(&self, always_on_top: bool) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetAlwaysOnTop(always_on_top)) {
            return result;
        }
        match self.inner.try_borrow() {
            Ok(inner_ref) => {
                if let Some(ref inner) = *inner_ref {
                    inner.set_always_on_top(always_on_top);
                }
                Ok(())
            }
            Err(_) => Ok(()),
        }
    }

    /// Set window title
    fn set_window_title(&self, title: &str) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetTitle(title.to_string())) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_window_title(title)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Get window title
    fn window_title(&self) -> PyResult<Option<String>> {
        if let Some(result) = self.retained_snapshot() {
            return Ok(Some(result?.title));
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.window_title())
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set window size
    fn set_size(&self, width: u32, height: u32) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Resize(width, height)) {
            return result;
        }
        // Use try_borrow to avoid panic if RefCell is already borrowed
        // This can happen during callback invocations from show_embedded/create_embedded
        match self.inner.try_borrow() {
            Ok(inner_ref) => {
                if let Some(ref inner) = *inner_ref {
                    inner
                        .set_size(width, height)
                        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
                } else {
                    Err(pyo3::exceptions::PyRuntimeError::new_err(
                        "WebView not initialized",
                    ))
                }
            }
            Err(_) => {
                // RefCell already borrowed - this is expected during initialization callbacks
                // Log and return Ok since the size will be set when the borrow is released
                tracing::debug!("[set_size] RefCell already borrowed, deferring size update");
                Ok(())
            }
        }
    }

    /// Sync WebView bounds with container size (Qt6 compatibility)
    ///
    /// This is critical for Qt6 where createWindowContainer manages the native window
    /// but WebView2's internal controller bounds may not automatically update.
    /// Call this after any size change to ensure WebView content fills the container.
    fn sync_bounds(&self, width: u32, height: u32) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Resize(width, height)) {
            return result;
        }
        match self.inner.try_borrow() {
            Ok(inner_ref) => {
                if let Some(ref inner) = *inner_ref {
                    inner.sync_webview_bounds(width, height);
                    Ok(())
                } else {
                    Err(pyo3::exceptions::PyRuntimeError::new_err(
                        "WebView not initialized",
                    ))
                }
            }
            Err(_) => {
                tracing::debug!("[sync_bounds] RefCell already borrowed, deferring bounds sync");
                Ok(())
            }
        }
    }

    /// Get window inner size
    fn inner_size(&self) -> PyResult<(u32, u32)> {
        if let Some(result) = self.retained_snapshot() {
            let s = result?;
            return Ok((s.width, s.height));
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            let size = inner.inner_size();
            Ok((size.width, size.height))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Get window outer size (including decorations)
    fn outer_size(&self) -> PyResult<(u32, u32)> {
        if let Some(result) = self.retained_snapshot() {
            let s = result?;
            return Ok((s.outer_width, s.outer_height));
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            let size = inner.outer_size();
            Ok((size.width, size.height))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Get window position
    fn position(&self) -> PyResult<Option<(i32, i32)>> {
        if let Some(result) = self.retained_snapshot() {
            let s = result?;
            return Ok(Some((s.x, s.y)));
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            Ok(inner.position().map(|p| (p.x, p.y)))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Center window on screen
    fn center(&self) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Center) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .center()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set window decorations (title bar, borders)
    fn set_decorations(&self, decorations: bool) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetDecorations(decorations)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_decorations(decorations)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set window resizable
    fn set_resizable(&self, resizable: bool) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetResizable(resizable)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_resizable(resizable)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set minimum window size
    fn set_min_size(&self, width: u32, height: u32) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetMinSize(width, height)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_min_size(width, height)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set maximum window size
    fn set_max_size(&self, width: u32, height: u32) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::SetMaxSize(width, height)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_max_size(width, height)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Set window position
    fn set_position(&self, x: i32, y: i32) -> PyResult<()> {
        if let Some(result) = self.retained_command(WindowCommand::Move(x, y)) {
            return result;
        }
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .set_position(x, y)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }
}
