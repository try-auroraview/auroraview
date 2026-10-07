//! AuroraView Core - Multi-Window APIs
//!
//! This module contains multi-window management methods (Tauri-aligned):
//! - Window label management
//! - Window info queries
//! - Inter-window communication
//! - Clear browsing data

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::AuroraView;

#[pymethods]
impl AuroraView {
    // ========================================
    // BOM Clear Data APIs
    // ========================================

    /// Clear all browsing data (localStorage, sessionStorage, IndexedDB, cookies)
    fn clear_all_browsing_data(&self) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .clear_all_browsing_data()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    /// Restore window from minimized/maximized state
    fn restore(&self) -> PyResult<()> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .restore()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "WebView not initialized",
            ))
        }
    }

    // ========================================
    // Multi-Window APIs (Tauri-aligned)
    // ========================================

    /// Get the window label for this WebView
    fn get_window_label(&self) -> String {
        self.config.borrow().title.clone()
    }

    /// Get all window labels in the application
    fn get_all_window_labels(&self) -> Vec<String> {
        crate::webview::window_manager::WindowManager::global().get_all_labels()
    }

    /// Get window count
    fn get_window_count(&self) -> usize {
        crate::webview::window_manager::WindowManager::global().window_count()
    }

    /// Check if a window exists by label
    fn has_window(&self, label: &str) -> bool {
        crate::webview::window_manager::WindowManager::global().has_window(label)
    }

    /// Get window info by label
    fn get_window_info(&self, py: Python<'_>, label: &str) -> Option<Py<PyDict>> {
        let info = crate::webview::window_manager::WindowManager::global().get_window(label)?;
        let dict = PyDict::new(py);
        dict.set_item("label", &info.label).ok()?;
        dict.set_item("title", &info.title).ok()?;
        dict.set_item("is_main", info.is_main).ok()?;
        dict.set_item("url", &info.url).ok()?;
        dict.set_item("width", info.width).ok()?;
        dict.set_item("height", info.height).ok()?;
        dict.set_item("visible", info.visible).ok()?;
        dict.set_item("focused", info.focused).ok()?;
        dict.set_item("parent_label", &info.parent_label).ok()?;
        Some(dict.into())
    }

    /// Emit event to a specific window
    fn emit_to_window(&self, label: &str, event: &str, data: &str) -> bool {
        let data: serde_json::Value = serde_json::from_str(data).unwrap_or(serde_json::Value::Null);
        crate::webview::window_manager::WindowManager::global().emit_to(label, event, data)
    }

    /// Emit event to all windows
    fn emit_to_all_windows(&self, event: &str, data: &str) {
        let data: serde_json::Value = serde_json::from_str(data).unwrap_or(serde_json::Value::Null);
        crate::webview::window_manager::WindowManager::global().emit_all(event, data);
    }

    /// Emit event to all windows except this one
    fn emit_to_other_windows(&self, event: &str, data: &str) {
        let label = self.get_window_label();
        let data: serde_json::Value = serde_json::from_str(data).unwrap_or(serde_json::Value::Null);
        crate::webview::window_manager::WindowManager::global().emit_others(&label, event, data);
    }

    // ========================================
    // Misc APIs
    // ========================================

    /// Process pending window events (for embedded mode)
    ///
    /// Returns `false` if the WebView is not yet initialized (safe to retry).
    /// Returns `true` if the window should be closed.
    fn process_events(&self) -> PyResult<bool> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return Ok(self.message_queue.hosted_state() == 3);
        }
        // Use try_borrow to avoid panic during initialization
        match self.inner.try_borrow() {
            Ok(inner_ref) => {
                if let Some(ref inner) = *inner_ref {
                    Ok(inner.process_events())
                } else {
                    // WebView not yet initialized, safe to retry later
                    tracing::trace!("[process_events] WebView inner not initialized yet");
                    Ok(false)
                }
            }
            Err(_) => {
                // RefCell is borrowed (likely during initialization), skip this tick
                tracing::trace!("[process_events] RefCell already borrowed, skipping tick");
                Ok(false)
            }
        }
    }

    /// Get IPC metrics
    fn get_ipc_metrics(&self) -> crate::bindings::ipc_metrics::PyIpcMetrics {
        let snapshot = self.message_queue.get_metrics_snapshot();
        snapshot.into()
    }

    /// Reset IPC metrics
    fn reset_ipc_metrics(&self) {
        tracing::warn!("[IPC] reset_ipc_metrics() not yet implemented");
    }

    /// Python representation
    fn __repr__(&self) -> String {
        let cfg = self.config.borrow();
        format!(
            "WebView(title='{}', width={}, height={})",
            cfg.title, cfg.width, cfg.height
        )
    }
}
