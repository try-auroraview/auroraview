//! AuroraView Core - Python-facing WebView class
//!
//! This module is split into multiple files for maintainability:
//! - `main.rs`: Constructor, lifecycle methods, property getters
//! - `js.rs`: JavaScript execution methods
//! - `storage.rs`: Storage and Cookie APIs
//! - `events.rs`: Event callback methods
//! - `dialogs.rs`: File and message dialog methods
//! - `bom.rs`: Browser Object Model APIs
//! - `multiwindow.rs`: Multi-window management APIs
//! - `plugins.rs`: Plugin system integration

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::cell::RefCell;
use std::rc::Rc;
use std::sync::Arc;

use super::config::WebViewConfig;
use super::event_loop::UserEvent;
use super::webview_inner::WebViewInner;
use super::window_control::{WindowCommand, WindowSnapshot};
use crate::bindings::webview::py_dict_to_json;
use crate::ipc::{IpcHandler, JsCallbackManager, MessageQueue, WebViewMessage};

// Module-level close channel.
//
// `AuroraView` is `#[pyclass(unsendable)]`, so PyO3 aborts any `#[pymethods]`
// body that runs on a thread other than the one that created the object, and
// `wry`/`tao` windows must be destroyed on their creator thread as well
// (violating that is a hard main-thread crash on macOS).
//
// Closing is the one operation that has to stay reachable from anywhere - a
// DCC host closes a window from its main thread while the WebView lives on a
// background thread - so the request is never executed inline. It is always
// handed back to the owner thread through this module-level channel, which is
// built from state that is already shared cross-thread: the
// `Arc<MessageQueue>` drained by the owner thread's event loop, plus the
// `EventLoopProxy` that wakes that loop up.
//
// Both halves are `Send`, so no part of this module ever needs to borrow the
// `unsendable` object to ask for a close.

// Sub-modules containing #[pymethods] implementations
#[cfg(feature = "templates")]
mod api; // API registration methods (uses Askama templates)
mod bom;
mod dialogs;
mod dom; // DOM operation methods (high-performance)
mod effects; // Window effects (click-through, vibrancy)
mod events;
mod js;
mod main;
mod multiwindow;
pub mod plugins;
mod storage;

pub use effects::PyRegion;
pub use plugins::PluginManager;

/// Ask the owner thread's event loop to close the window.
///
/// Both halves are `Send`, so this is safe to call from any thread, and no
/// `unsendable` state is borrowed. The queued `Close` message covers
/// host-driven pumps (the embedded/DCC path has no event loop proxy), while
/// `UserEvent::CloseWindow` wakes a blocking event loop immediately.
///
/// Returns `true` when a running event loop was woken through its proxy.
pub(crate) fn request_close_via_channel(
    message_queue: &Arc<MessageQueue>,
    event_loop_proxy: &Rc<RefCell<Option<tao::event_loop::EventLoopProxy<UserEvent>>>>,
) -> bool {
    message_queue.push(WebViewMessage::Close);

    // A drop must never panic and must never block, so a proxy held by the
    // event loop is skipped rather than waited for.
    match event_loop_proxy.try_borrow() {
        Ok(guard) => match guard.as_ref() {
            Some(proxy) => proxy.send_event(UserEvent::CloseWindow).is_ok(),
            None => false,
        },
        Err(_) => false,
    }
}

/// Thread-safe event emitter for cross-thread event emission
///
/// This class can be safely used from any thread (including ProcessPlugin background threads)
/// to emit events to the JavaScript frontend. It only holds an Arc<MessageQueue> which is
/// thread-safe.
///
/// Example:
///     emitter = webview.create_emitter()
///     # Can be used from any thread:
///     emitter.emit("my_event", {"data": "value"})
#[pyclass(name = "EventEmitter")]
pub struct EventEmitter {
    message_queue: Arc<MessageQueue>,
}

#[pymethods]
impl EventEmitter {
    /// Emit an event to JavaScript (thread-safe)
    ///
    /// Args:
    ///     event_name (str): Name of the event
    ///     data (dict): Data to send with the event
    ///
    /// Note: data can be any Python object that can be converted to a dict.
    /// This is more flexible to support callbacks from PluginManager.
    fn emit(&self, event_name: &str, data: &Bound<'_, PyAny>) -> PyResult<()> {
        // Try to extract as PyDict first, then try to convert
        let json_data = if let Ok(dict) = data.cast::<PyDict>() {
            py_dict_to_json(dict)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?
        } else {
            // Try to convert to dict using Python's dict() constructor
            let dict = PyDict::new(data.py());
            if let Ok(mapping) = data.call_method0("items") {
                for item in mapping.try_iter()? {
                    let item = item?;
                    let key = item.get_item(0)?;
                    let value = item.get_item(1)?;
                    dict.set_item(key, value)?;
                }
            }
            py_dict_to_json(&dict)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?
        };

        self.message_queue.push(WebViewMessage::EmitEvent {
            event_name: event_name.to_string(),
            data: json_data,
        });

        Ok(())
    }
}

/// Python-facing WebView class
/// Supports both standalone and embedded modes (for DCC integration)
#[pyclass(name = "WebView", unsendable)]
pub struct AuroraView {
    pub(crate) inner: Rc<RefCell<Option<WebViewInner>>>,
    pub(crate) config: Rc<RefCell<WebViewConfig>>,
    pub(crate) ipc_handler: Arc<IpcHandler>,
    /// Thread-safe message queue for cross-thread communication
    pub(crate) message_queue: Arc<MessageQueue>,
    /// Event loop proxy for sending close events (standalone mode only)
    pub(crate) event_loop_proxy: Rc<RefCell<Option<tao::event_loop::EventLoopProxy<UserEvent>>>>,
    /// JavaScript callback manager for async execution
    pub(crate) js_callback_manager: Arc<JsCallbackManager>,
    /// Callback invoked when WebView2 HWND is created (Windows only)
    pub(crate) on_hwnd_created: Rc<RefCell<Option<Py<PyAny>>>>,
    pub(crate) retained: Rc<RefCell<Option<Arc<super::window_control::RetainedShared>>>>,
    /// Cached HWND value (Windows only) - stored at AuroraView level
    /// so it can be accessed even when inner RefCell is borrowed
    #[cfg(target_os = "windows")]
    pub(crate) cached_hwnd: Rc<RefCell<Option<u64>>>,
}

impl AuroraView {
    fn retained_command(&self, command: WindowCommand) -> Option<PyResult<()>> {
        self.retained.borrow().as_ref().map(|shared| {
            shared
                .control
                .enqueue(command)
                .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
            if let Err(error) = shared.signal() {
                tracing::warn!("Accepted retained command wake failed: {}", error);
            }
            Ok(())
        })
    }

    fn retained_snapshot(&self) -> Option<PyResult<WindowSnapshot>> {
        self.retained.borrow().as_ref().map(|shared| {
            shared
                .control
                .snapshot()
                .map_err(pyo3::exceptions::PyRuntimeError::new_err)
        })
    }
}

#[pymethods]
impl AuroraView {
    /// Create a thread-safe event emitter
    ///
    /// Returns an EventEmitter that can be used from any thread to emit events
    /// to the JavaScript frontend. This is useful for plugin callbacks that run
    /// on background threads.
    ///
    /// Example:
    ///     emitter = webview.create_emitter()
    ///     plugins.set_emit_callback(emitter.emit)
    fn create_emitter(&self) -> EventEmitter {
        EventEmitter {
            message_queue: Arc::clone(&self.message_queue),
        }
    }
}

/// Implement Drop to release the native window when the Python object dies.
///
/// Python users (and test fixtures) frequently let a `WebView` go out of scope
/// instead of calling `close()`. Previously `drop` only logged, so the native
/// window stayed alive until the process exited - which is exactly the
/// "unit tests never close the window" symptom. Dropping now asks the event
/// loop to exit and then releases the inner WebView, whose own `Drop` destroys
/// the window.
///
/// Cross-thread destruction cannot be fixed here. `AuroraView` is
/// `#[pyclass(unsendable)]`, so PyO3 gates deallocation on its thread checker:
/// when the object is released on a thread other than the creating one, PyO3
/// writes an unraisable `RuntimeError`, skips the value destructor entirely and
/// leaks the object - `AuroraView::drop` is never entered. That is PyO3's
/// unsendable contract, not something this `Drop` impl can route around, so
/// callers that need a cross-thread teardown must go through `close()`, which is
/// reachable from any thread via the module-level close channel.
impl Drop for AuroraView {
    fn drop(&mut self) {
        // The blocking event loop now runs with the GIL released (see
        // `show_window`), so Python may garbage-collect this object *while* the
        // loop still holds a mutable borrow of `inner`. Every borrow below is
        // therefore non-blocking: a drop must never panic, and it must never
        // deadlock waiting on a borrow held by the loop it is trying to stop.
        let title = self
            .config
            .try_borrow()
            .map(|c| c.title.clone())
            .unwrap_or_else(|_| "<borrowed>".to_string());
        tracing::warn!(
            "[CLOSE] [AuroraView::drop] WebView '{}' is being destroyed!",
            title
        );

        // Ask a running event loop to exit, and make the intent visible to any
        // host-driven message pump (the embedded/DCC path has no event loop
        // proxy, so it relies on the queued message).
        let asked_event_loop =
            request_close_via_channel(&self.message_queue, &self.event_loop_proxy);
        if asked_event_loop {
            tracing::info!(
                "[CLOSE] [AuroraView::drop] Sent CloseWindow to the event loop for '{}'",
                title
            );
        } else {
            tracing::info!(
                "[CLOSE] [AuroraView::drop] Queued Close message for '{}' (no event loop proxy)",
                title
            );
        }

        // Drop the event-loop proxy first so the loop is free to exit.
        if let Ok(mut proxy_guard) = self.event_loop_proxy.try_borrow_mut() {
            if let Some(proxy) = proxy_guard.take() {
                drop(proxy);
            }
        }

        // Release the inner WebView; `WebViewInner::drop` destroys the window.
        // If the event loop still owns the borrow, it will drop the inner WebView
        // itself when it unwinds - panicking here would abort the process.
        match self.inner.try_borrow_mut() {
            Ok(mut inner_guard) => {
                if let Some(inner) = inner_guard.take() {
                    drop(inner);
                    tracing::info!(
                        "[CLOSE] [AuroraView::drop] Released inner WebView for '{}'",
                        title
                    );
                }
            }
            Err(_) => {
                tracing::warn!(
                    "[CLOSE] [AuroraView::drop] inner is borrowed by a running event loop; \
                     the loop will release the WebView for '{}' when it exits",
                    title
                );
            }
        }
    }
}
