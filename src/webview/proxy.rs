//! Thread-safe WebView Proxy for cross-thread operations
//!
//! This module provides a `WebViewProxy` that can be safely shared across threads.
//! It only contains thread-safe fields (`Arc<...>`) and allows operations like
//! `eval_js`, `emit`, etc. to be called from any thread.
//!
//! ## Problem
//! `AuroraView` is marked as `unsendable` because it contains non-Send fields
//! like `Rc<RefCell<...>>`. When calling methods from a different thread than
//! the one that created the WebView, PyO3 panics with:
//! ```text
//! assertion `left == right` failed: _core::webview::core::AuroraView is unsendable,
//! but sent to another thread
//! ```
//!
//! ## Solution
//! `WebViewProxy` only contains `Arc<...>` fields which are `Send + Sync`.
//! Operations are performed via the thread-safe `MessageQueue` which is
//! processed by the WebView's event loop on the correct thread.
//!
//! ## Usage
//! ```python
//! # In HWND mode - WebView runs in background thread
//! def create_webview_thread():
//!     webview = WebView(...)
//!     proxy = webview.get_proxy()  # Get thread-safe proxy
//!     self._proxy = proxy          # Store for cross-thread access
//!     webview.show_blocking()
//!
//! # From DCC main thread - safe!
//! self._proxy.eval_js("console.log('Hello from DCC!')")
//! ```

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::Arc;

use crate::ipc::{JsCallbackManager, MessageQueue, WebViewMessage};
use crate::webview::window_control::{RetainedShared, WindowCommand, WindowSnapshot};

/// Thread-safe proxy for cross-thread WebView operations
///
/// This proxy can be safely shared across threads and used to
/// communicate with the WebView running in another thread.
/// All operations are performed via a message queue that is
/// processed by the WebView's event loop.
#[pyclass(name = "WebViewProxy")]
#[derive(Clone)]
pub struct WebViewProxy {
    /// Thread-safe message queue for WebView operations
    message_queue: Arc<MessageQueue>,
    /// Thread-safe JavaScript callback manager
    js_callback_manager: Arc<JsCallbackManager>,
    pub(crate) retained: Option<Arc<RetainedShared>>,
}

// SAFETY: WebViewProxy only contains Arc<...> fields which are Send + Sync
unsafe impl Send for WebViewProxy {}
unsafe impl Sync for WebViewProxy {}

impl WebViewProxy {
    fn guard_activity(&self) -> PyResult<()> {
        if self
            .retained
            .as_ref()
            .is_some_and(|shared| shared.control.intent().close)
        {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "retained window is closing",
            ));
        }
        Ok(())
    }

    fn retained(&self) -> PyResult<&RetainedShared> {
        self.retained.as_deref().ok_or_else(|| {
            pyo3::exceptions::PyRuntimeError::new_err("window operation requires a retained proxy")
        })
    }

    fn command(&self, operation: WindowCommand) -> PyResult<()> {
        let shared = self.retained()?;
        shared
            .control
            .enqueue(operation)
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        if let Err(error) = shared.signal() {
            tracing::warn!("Accepted retained command wake failed: {}", error);
        }
        Ok(())
    }

    fn snapshot(&self) -> PyResult<WindowSnapshot> {
        self.retained()?
            .control
            .snapshot()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    /// Create a new WebViewProxy from the given components
    pub fn new(
        message_queue: Arc<MessageQueue>,
        js_callback_manager: Arc<JsCallbackManager>,
    ) -> Self {
        Self {
            message_queue,
            js_callback_manager,
            retained: None,
        }
    }
}

#[pymethods]
impl WebViewProxy {
    fn show(&self) -> PyResult<()> {
        let shared = self.retained()?;
        shared
            .control
            .show(true)
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn set_visible(&self, visible: bool) -> PyResult<()> {
        let shared = self.retained()?;
        if visible {
            shared
                .control
                .show(false)
                .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        } else {
            shared.control.hide();
        }
        shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn hide(&self) -> PyResult<()> {
        self.set_visible(false)
    }

    fn focus(&self) -> PyResult<()> {
        let shared = self.retained()?;
        shared
            .control
            .snapshot()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        shared
            .control
            .show(true)
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn set_focus(&self) -> PyResult<()> {
        self.focus()
    }

    fn move_to(&self, x: i32, y: i32) -> PyResult<()> {
        self.command(WindowCommand::Move(x, y))
    }

    fn set_position(&self, x: i32, y: i32) -> PyResult<()> {
        self.move_to(x, y)
    }

    fn center(&self) -> PyResult<()> {
        self.command(WindowCommand::Center)
    }

    fn resize(&self, width: u32, height: u32) -> PyResult<()> {
        self.command(WindowCommand::Resize(width, height))
    }

    fn set_size(&self, width: u32, height: u32) -> PyResult<()> {
        self.resize(width, height)
    }

    fn sync_bounds(&self, width: u32, height: u32) -> PyResult<()> {
        self.resize(width, height)
    }

    fn minimize(&self) -> PyResult<()> {
        self.command(WindowCommand::Minimize)
    }

    fn maximize(&self) -> PyResult<()> {
        self.command(WindowCommand::Maximize)
    }

    fn unmaximize(&self) -> PyResult<()> {
        self.command(WindowCommand::Unmaximize)
    }

    fn toggle_maximize(&self) -> PyResult<()> {
        self.command(WindowCommand::ToggleMaximize)
    }

    fn restore(&self) -> PyResult<()> {
        self.command(WindowCommand::Restore)
    }

    fn set_fullscreen(&self, fullscreen: bool) -> PyResult<()> {
        self.command(WindowCommand::SetFullscreen(fullscreen))
    }

    fn toggle_fullscreen(&self) -> PyResult<()> {
        self.command(WindowCommand::ToggleFullscreen)
    }

    fn set_title(&self, title: String) -> PyResult<()> {
        self.command(WindowCommand::SetTitle(title))
    }

    fn set_window_title(&self, title: String) -> PyResult<()> {
        self.set_title(title)
    }

    fn set_always_on_top(&self, value: bool) -> PyResult<()> {
        self.command(WindowCommand::SetAlwaysOnTop(value))
    }

    fn set_resizable(&self, value: bool) -> PyResult<()> {
        self.command(WindowCommand::SetResizable(value))
    }

    fn set_decorations(&self, value: bool) -> PyResult<()> {
        self.command(WindowCommand::SetDecorations(value))
    }

    fn set_min_size(&self, width: u32, height: u32) -> PyResult<()> {
        self.command(WindowCommand::SetMinSize(width, height))
    }

    fn set_max_size(&self, width: u32, height: u32) -> PyResult<()> {
        self.command(WindowCommand::SetMaxSize(width, height))
    }

    fn window_title(&self) -> PyResult<Option<String>> {
        Ok(Some(self.snapshot()?.title))
    }

    fn position(&self) -> PyResult<Option<(i32, i32)>> {
        let snapshot = self.snapshot()?;
        Ok(Some((snapshot.x, snapshot.y)))
    }

    fn inner_size(&self) -> PyResult<(u32, u32)> {
        let snapshot = self.snapshot()?;
        Ok((snapshot.width, snapshot.height))
    }

    fn outer_size(&self) -> PyResult<(u32, u32)> {
        let snapshot = self.snapshot()?;
        Ok((snapshot.outer_width, snapshot.outer_height))
    }

    fn is_visible(&self) -> PyResult<bool> {
        Ok(self.snapshot()?.visible)
    }

    fn is_focused(&self) -> PyResult<bool> {
        Ok(self.snapshot()?.focused)
    }

    fn is_minimized(&self) -> PyResult<bool> {
        Ok(self.snapshot()?.minimized)
    }

    fn is_maximized(&self) -> PyResult<bool> {
        Ok(self.snapshot()?.maximized)
    }

    fn is_fullscreen(&self) -> PyResult<bool> {
        Ok(self.snapshot()?.fullscreen)
    }

    fn get_hwnd(&self) -> PyResult<Option<u64>> {
        Ok(self.retained()?.control.hwnd())
    }

    /// Execute JavaScript code in the WebView (thread-safe)
    ///
    /// This method can be called from ANY thread. The script is queued
    /// and will be executed by the WebView's event loop.
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    ///
    /// Example:
    ///     >>> proxy = webview.get_proxy()
    ///     >>> proxy.eval_js("console.log('Hello from another thread!')")
    fn eval_js(&self, script: &str) -> PyResult<()> {
        self.guard_activity()?;
        tracing::debug!("[WebViewProxy] Queueing JavaScript execution: {}", script);
        self.message_queue
            .push(WebViewMessage::EvalJs(script.to_string()));
        Ok(())
    }

    /// Execute JavaScript code asynchronously with result callback (thread-safe)
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    ///     callback (callable): Python function(result, error) to call with result
    ///     timeout_ms (int): Timeout in milliseconds (default: 5000)
    #[pyo3(signature = (script, callback, timeout_ms=5000))]
    fn eval_js_async(&self, script: &str, callback: Py<PyAny>, timeout_ms: u64) -> PyResult<()> {
        self.guard_activity()?;
        let callback_id = self.js_callback_manager.next_callback_id();

        tracing::debug!(
            "[WebViewProxy] Queueing async JavaScript (id={}, timeout={}ms): {}",
            callback_id,
            timeout_ms,
            script
        );

        self.js_callback_manager
            .register_callback_with_timeout(callback_id, callback, timeout_ms);

        self.message_queue.push(WebViewMessage::EvalJsAsync {
            script: script.to_string(),
            callback_id,
        });

        Ok(())
    }

    /// Emit an event to JavaScript (thread-safe)
    ///
    /// Args:
    ///     event_name (str): Name of the event
    ///     data (dict): Data to send with the event
    fn emit(&self, event_name: &str, data: &Bound<'_, PyDict>) -> PyResult<()> {
        self.guard_activity()?;
        tracing::debug!("[WebViewProxy] Emitting event: {}", event_name);

        // Convert Python dict to JSON
        let json_data = crate::ipc::dict_to_json(data)?;

        self.message_queue.push(WebViewMessage::EmitEvent {
            event_name: event_name.to_string(),
            data: json_data,
        });

        Ok(())
    }

    /// Load a URL in the WebView (thread-safe)
    ///
    /// Args:
    ///     url (str): URL to load
    fn load_url(&self, url: &str) -> PyResult<()> {
        self.guard_activity()?;
        tracing::debug!("[WebViewProxy] Loading URL: {}", url);
        self.message_queue
            .push(WebViewMessage::LoadUrl(url.to_string()));
        Ok(())
    }

    /// Load HTML content in the WebView (thread-safe)
    ///
    /// Args:
    ///     html (str): HTML content to load
    fn load_html(&self, html: &str) -> PyResult<()> {
        self.guard_activity()?;
        tracing::debug!("[WebViewProxy] Loading HTML content");
        self.message_queue
            .push(WebViewMessage::LoadHtml(html.to_string()));
        Ok(())
    }

    /// Reload the current page (thread-safe)
    fn reload(&self) -> PyResult<()> {
        self.guard_activity()?;
        tracing::debug!("[WebViewProxy] Reloading page");
        self.message_queue.push(WebViewMessage::Reload);
        Ok(())
    }

    /// Close the WebView window (thread-safe)
    ///
    /// This sends a close message to the WebView's event loop,
    /// which will trigger the window to close and the event loop to exit.
    ///
    /// Example:
    ///     >>> proxy = webview.get_proxy()
    ///     >>> proxy.close()  # Closes the window from another thread
    fn close(&self) -> PyResult<()> {
        tracing::info!("[WebViewProxy] Requesting window close");
        if let Some(shared) = &self.retained {
            shared.control.close();
            return shared
                .signal()
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }
        self.message_queue.push(WebViewMessage::Close);
        Ok(())
    }

    /// Check if the proxy is valid (message queue is available)
    fn is_valid(&self) -> bool {
        if let Some(shared) = &self.retained {
            return !shared.control.intent().close;
        }
        // The proxy is always valid as long as it exists
        // The message queue might be disconnected but that's handled in push()
        true
    }

    fn __repr__(&self) -> String {
        format!(
            "WebViewProxy(queue_len={}, pending_callbacks={})",
            self.message_queue.len(),
            self.js_callback_manager.pending_count()
        )
    }
}
