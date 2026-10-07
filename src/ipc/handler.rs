//! IPC Handler for WebView Communication
//!
//! This module manages communication between Python and JavaScript,
//! handling event callbacks and message routing.

use dashmap::DashMap;
#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;
#[cfg(feature = "python-bindings")]
use pyo3::{Py, PyAny};
use std::sync::{Arc, Mutex};

// Re-export IpcMessage from backend module
pub use super::backend::IpcMessage;
pub use super::message_queue::{MessageQueue, WebViewMessage};

#[cfg(feature = "python-bindings")]
use super::js_callback::{JsCallbackManager, JsCallbackResult};

/// IPC callback type (Rust closures)
pub type IpcCallback = Arc<dyn Fn(IpcMessage) -> Result<serde_json::Value, String> + Send + Sync>;

/// Python callback wrapper - stores Python callable objects
#[cfg(feature = "python-bindings")]
pub struct PythonCallback {
    /// Python callable object
    pub callback: Py<PyAny>,
}

#[cfg(feature = "python-bindings")]
impl PythonCallback {
    /// Create a new Python callback wrapper
    pub fn new(callback: Py<PyAny>) -> Self {
        Self { callback }
    }

    /// Call the Python callback with the given data
    pub fn call(&self, data: super::json::Value) -> Result<(), String> {
        Python::attach(|py| {
            // Convert JSON value to Python object using the optimized json module
            let py_data = match super::json::json_to_python(py, &data) {
                Ok(obj) => obj,
                Err(e) => {
                    tracing::error!("Failed to convert JSON to Python: {}", e);
                    return Err(format!("Failed to convert JSON to Python: {}", e));
                }
            };

            // Call the Python callback
            match self.callback.call1(py, (py_data,)) {
                Ok(_) => {
                    tracing::debug!("Python callback executed successfully");
                    Ok(())
                }
                Err(e) => {
                    tracing::error!("Python callback error: {}", e);
                    Err(format!("Python callback error: {}", e))
                }
            }
        })
    }
}

/// IPC handler for managing communication between Python and JavaScript
///
/// Uses sharded callback storage with explicit admission and ownership transfer.
/// Application callbacks and finalizers run without map or admission locks.
pub struct IpcHandler {
    /// Serializes registration versus detachment; never held while invoking/dropping callbacks.
    admission_closed: Mutex<bool>,
    /// Registered event callbacks (Rust closures) - sharded concurrent map
    callbacks: Arc<DashMap<String, Vec<IpcCallback>>>,

    /// Registered Python callbacks - sharded concurrent map
    #[cfg(feature = "python-bindings")]
    python_callbacks: Arc<DashMap<String, Vec<Arc<PythonCallback>>>>,

    /// JavaScript callback manager for async execution results
    #[cfg(feature = "python-bindings")]
    js_callback_manager: Option<Arc<JsCallbackManager>>,

    /// Message queue for sending events to WebView
    message_queue: Option<Arc<MessageQueue>>,
}

impl IpcHandler {
    /// Create a new IPC handler
    pub fn new() -> Self {
        Self {
            admission_closed: Mutex::new(false),
            callbacks: Arc::new(DashMap::new()),
            #[cfg(feature = "python-bindings")]
            python_callbacks: Arc::new(DashMap::new()),
            #[cfg(feature = "python-bindings")]
            js_callback_manager: None,
            message_queue: None,
        }
    }

    /// Set the message queue for sending events to WebView
    pub fn set_message_queue(&mut self, queue: Arc<MessageQueue>) {
        self.message_queue = Some(queue);
    }

    /// Set the JavaScript callback manager for handling async execution results
    #[cfg(feature = "python-bindings")]
    pub fn set_js_callback_manager(&mut self, manager: Arc<JsCallbackManager>) {
        self.js_callback_manager = Some(manager);
    }

    /// Register a Rust callback for an event
    #[allow(dead_code)]
    pub fn on<F>(&self, event: &str, callback: F)
    where
        F: Fn(IpcMessage) -> Result<serde_json::Value, String> + Send + Sync + 'static,
    {
        let closed = self
            .admission_closed
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if *closed {
            drop(closed);
            drop(callback);
            return;
        }
        self.callbacks
            .entry(event.to_string())
            .or_default()
            .push(Arc::new(callback));
    }

    /// Register a Python callback for an event
    #[cfg(feature = "python-bindings")]
    pub fn register_python_callback(&self, event: &str, callback: Py<PyAny>) {
        let closed = self
            .admission_closed
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if *closed {
            drop(closed);
            drop(callback);
            return;
        }
        self.python_callbacks
            .entry(event.to_string())
            .or_default()
            .push(Arc::new(PythonCallback::new(callback)));
        drop(closed);
        tracing::debug!("Registered Python callback for event: {}", event);
    }

    /// Register multiple Python callbacks at once (batch registration)
    ///
    /// Each registration obeys the same permanent shutdown admission gate.
    #[cfg(feature = "python-bindings")]
    pub fn register_python_callbacks_batch(&self, callbacks: Vec<(String, Py<PyAny>)>) {
        for (event, callback) in callbacks {
            self.register_python_callback(&event, callback);
        }
    }

    /// Get the count of registered events (both Rust and Python callbacks)
    pub fn registered_event_count(&self) -> usize {
        let rust_count = self.callbacks.len();
        #[cfg(feature = "python-bindings")]
        let python_count = self.python_callbacks.len();
        #[cfg(not(feature = "python-bindings"))]
        let python_count = 0;
        rust_count + python_count
    }

    /// Emit an event to JavaScript
    ///
    /// Sends an event to the WebView via the message queue.
    /// The event will be dispatched to JavaScript handlers registered with `auroraview.on()`.
    #[allow(dead_code)]
    pub fn emit(&self, event: &str, data: serde_json::Value) -> Result<(), String> {
        tracing::debug!("Emitting IPC event: {}", event);

        if let Some(ref queue) = self.message_queue {
            queue.push(WebViewMessage::EmitEvent {
                event_name: event.to_string(),
                data,
            });
            Ok(())
        } else {
            let err = "Message queue not set - cannot emit event to WebView".to_string();
            tracing::warn!("{}", err);
            Err(err)
        }
    }

    /// Handle incoming message from JavaScript
    #[allow(dead_code)]
    pub fn handle_message(&self, message: IpcMessage) -> Result<serde_json::Value, String> {
        tracing::debug!("Handling IPC message: {}", message.event);
        if *self
            .admission_closed
            .lock()
            .unwrap_or_else(|error| error.into_inner())
        {
            return Err("IPC handler is shut down".to_string());
        }

        // Handle internal JS callback result event
        #[cfg(feature = "python-bindings")]
        if message.event == "__js_callback_result__" {
            return self.handle_js_callback_result(&message.data);
        }

        // Handle internal ready event
        // Note: We still process Python callbacks for this event so users can hook into it
        if message.event == "__auroraview_ready" {
            tracing::debug!("WebView bridge ready: {:?}", message.data);
        }

        // Snapshot Arc ownership, then release the shard before any application code.
        #[cfg(feature = "python-bindings")]
        let callbacks = self
            .python_callbacks
            .get(&message.event)
            .map(|callbacks| callbacks.value().clone());
        #[cfg(feature = "python-bindings")]
        if let Some(callbacks) = callbacks {
            for callback in callbacks {
                let closed = *self
                    .admission_closed
                    .lock()
                    .unwrap_or_else(|error| error.into_inner());
                if closed {
                    return Err("IPC handler is shut down".to_string());
                }
                callback.call(message.data.clone())?;
            }
            return Ok(serde_json::json!({"status": "ok"}));
        }

        // For __auroraview_ready, return success even if no Python callback is registered
        if message.event == "__auroraview_ready" {
            return Ok(serde_json::json!({"status": "ok", "message": "ready acknowledged"}));
        }

        // Rust callbacks may also reenter registration or shutdown.
        let callback = self
            .callbacks
            .get(&message.event)
            .and_then(|callbacks| callbacks.value().first().cloned());
        if let Some(callback) = callback {
            return callback(message.clone());
        }

        // No callback found
        Err(format!(
            "No handler registered for event: {}",
            message.event
        ))
    }

    /// Handle JavaScript callback result from async execution
    #[cfg(feature = "python-bindings")]
    fn handle_js_callback_result(
        &self,
        data: &serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let callback_id = data
            .get("callback_id")
            .and_then(|v| v.as_u64())
            .ok_or_else(|| "Missing callback_id in JS callback result".to_string())?;

        let result_value = data.get("result").cloned();
        let error_value = data.get("error").cloned();

        tracing::debug!(
            "Processing JS callback result: id={}, has_result={}, has_error={}",
            callback_id,
            result_value.is_some(),
            error_value.is_some()
        );

        // Build the callback result
        let js_result = JsCallbackResult {
            value: result_value,
            error: error_value.and_then(|e| {
                e.get("message")
                    .and_then(|m| m.as_str())
                    .map(|s| s.to_string())
            }),
        };

        // Complete the callback if we have a manager
        if let Some(ref manager) = self.js_callback_manager {
            if let Err(e) = manager.complete_callback(callback_id, js_result) {
                tracing::error!("Failed to complete JS callback {}: {}", callback_id, e);
                return Err(e);
            }
        } else {
            tracing::warn!(
                "JS callback result received but no callback manager set (id={})",
                callback_id
            );
        }

        Ok(serde_json::json!({"status": "ok"}))
    }

    /// Remove all callbacks for an event
    #[allow(dead_code)]
    pub fn off(&self, event: &str) {
        self.callbacks.remove(event);
        #[cfg(feature = "python-bindings")]
        self.python_callbacks.remove(event);
    }

    /// Clear callbacks without running user destructors under a shard or admission lock.
    #[allow(dead_code)]
    pub fn clear(&self) {
        self.detach_callbacks(false);
    }

    /// Close registration without dropping callbacks; callable finalizers can reenter safely.
    pub fn close_admission(&self) {
        *self
            .admission_closed
            .lock()
            .unwrap_or_else(|error| error.into_inner()) = true;
    }

    /// Close registration permanently before releasing hosted callback ownership.
    pub fn shutdown_hosted(&self) {
        self.detach_callbacks(true);
    }

    fn detach_callbacks(&self, shutdown: bool) {
        let mut closed = self
            .admission_closed
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        *closed |= shutdown;
        let keys: Vec<String> = self
            .callbacks
            .iter()
            .map(|entry| entry.key().clone())
            .collect();
        let detached: Vec<_> = keys
            .iter()
            .filter_map(|key| self.callbacks.remove(key))
            .collect();
        #[cfg(feature = "python-bindings")]
        let detached_python = {
            let keys: Vec<String> = self
                .python_callbacks
                .iter()
                .map(|entry| entry.key().clone())
                .collect();
            keys.iter()
                .filter_map(|key| self.python_callbacks.remove(key))
                .collect::<Vec<_>>()
        };
        drop(closed);
        drop(detached);
        #[cfg(feature = "python-bindings")]
        drop(detached_python);
    }
}

impl Default for IpcHandler {
    fn default() -> Self {
        Self::new()
    }
}

/// Wrap the `String`-typed `IpcHandler::handle_message` error so it can be
/// boxed into [`auroraview_core::builder::DispatchError::Backend`].
#[derive(Debug, thiserror::Error)]
#[error("{0}")]
struct IpcStringError(String);

impl auroraview_core::builder::DragDropIpcSink for IpcHandler {
    fn dispatch(
        &self,
        event_name: &str,
        data: serde_json::Value,
    ) -> Result<(), auroraview_core::builder::DispatchError> {
        self.handle_message(IpcMessage {
            event: event_name.to_string(),
            data,
            id: None,
        })
        .map(|_| ())
        .map_err(|s| auroraview_core::builder::DispatchError::backend(IpcStringError(s)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(feature = "python-bindings")]
    use pyo3::types::{PyList, PyModule};

    #[cfg(feature = "python-bindings")]
    fn py_append_collector() -> (Py<PyAny>, Py<PyAny>) {
        Python::attach(|py| {
            let seen = PyList::new(py, [py.None()])?;
            let m = PyModule::from_code(
                py,
                c"def make_cb(seen):\n    def cb(x):\n        seen.append(x)\n    return cb\n",
                c"m.py",
                c"m",
            )
            .unwrap();
            let make_cb = m.getattr("make_cb").unwrap();
            // Keep an owned handle to the list so we can inspect it later
            let seen_obj: Py<PyAny> = seen.clone().unbind().into();
            let seen_bound = seen_obj.bind(py).cast::<PyList>().unwrap();
            let cb = make_cb.call1((seen_bound,)).unwrap().clone().unbind();
            Ok::<(Py<PyAny>, Py<PyAny>), pyo3::PyErr>((cb, seen_obj))
        })
        .unwrap()
    }

    #[cfg(feature = "python-bindings")]
    #[test]
    fn test_python_callback_flow() {
        let handler = IpcHandler::new();
        let (cb, seen_obj) = py_append_collector();
        handler.register_python_callback("evt", cb);

        let msg = IpcMessage {
            event: "evt".to_string(),
            data: serde_json::json!({"a":1}),
            id: None,
        };
        let res = handler.handle_message(msg);
        assert!(res.is_ok());

        Python::attach(|py| {
            let seen = seen_obj.bind(py).cast::<PyList>().unwrap();
            assert_eq!(seen.len(), 1);
            let first = seen.get_item(0).unwrap();
            // first is a Python object converted from JSON dict
            let dict = first.cast::<pyo3::types::PyDict>().unwrap();
            if let Ok(Some(a_val)) = dict.get_item("a") {
                let a: i64 = a_val.extract().unwrap();
                assert_eq!(a, 1);
            } else {
                panic!("missing key a");
            }
        });
    }

    #[test]
    fn test_rust_callback_flow_and_no_handler() {
        let handler = IpcHandler::new();
        handler.on("evt2", |m| {
            assert_eq!(m.event, "evt2");
            Ok(serde_json::json!({"ok": true}))
        });
        let res = handler.handle_message(IpcMessage {
            event: "evt2".to_string(),
            data: serde_json::json!({}),
            id: None,
        });
        assert_eq!(res.unwrap(), serde_json::json!({"ok": true}));

        // No handler case
        let err = handler
            .handle_message(IpcMessage {
                event: "unknown".to_string(),
                data: serde_json::json!({}),
                id: None,
            })
            .unwrap_err();
        assert!(err.contains("No handler registered"));
    }

    #[test]
    fn test_emit_without_message_queue() {
        let handler = IpcHandler::new();
        // Without message queue, emit should return an error
        let result = handler.emit("test_event", serde_json::json!({"data": "test"}));
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Message queue not set"));
    }

    #[test]
    fn test_emit_with_message_queue() {
        let mut handler = IpcHandler::new();
        let queue = Arc::new(MessageQueue::new());
        handler.set_message_queue(queue.clone());

        // With message queue, emit should succeed
        let result = handler.emit("test_event", serde_json::json!({"data": "test"}));
        assert!(result.is_ok());

        // Verify message was pushed to queue
        assert_eq!(queue.len(), 1);
    }

    // ------------------------------------------------------------------
    // RFC 0015 §3.1 — `impl DragDropIpcSink for IpcHandler` coverage.
    //
    // These tests exercise the trait method directly so the bridging
    // glue between `auroraview_core::builder::DragDropIpcSink` and the
    // PyO3-side `IpcHandler::handle_message` (`String` error → boxed
    // `IpcStringError` → `DispatchError::Backend`) stays observable in
    // unit tests, independent of the wry/WebView2 native backend.
    // ------------------------------------------------------------------

    #[test]
    fn test_dragdrop_sink_dispatch_success() {
        use auroraview_core::builder::DragDropIpcSink;

        let handler = IpcHandler::new();
        // Register a Rust callback for the drag-drop event so
        // `handle_message` succeeds. The callback does not need to do
        // anything meaningful — we only care that `dispatch` returns
        // `Ok(())` when the underlying handler succeeds.
        handler.on("file_drop_hover", |m| {
            assert_eq!(m.event, "file_drop_hover");
            Ok(serde_json::json!({"ok": true}))
        });

        let result = handler.dispatch(
            "file_drop_hover",
            serde_json::json!({"paths": ["/tmp/a.txt"]}),
        );

        assert!(
            result.is_ok(),
            "dispatch should succeed when a handler is registered"
        );
    }

    #[test]
    fn test_dragdrop_sink_dispatch_propagates_handler_error() {
        use auroraview_core::builder::DispatchError;
        use auroraview_core::builder::DragDropIpcSink;

        let handler = IpcHandler::new();
        // Intentionally do NOT register any handler, so
        // `handle_message` returns the "No handler registered" error
        // string. The sink must convert it into
        // `DispatchError::Backend(IpcStringError(...))`.
        let err = handler
            .dispatch("file_drop", serde_json::json!({}))
            .expect_err("dispatch must fail when no handler is registered");

        // The single non-exhaustive variant `Backend(...)` is the only
        // shape we care about today. If new variants are added later,
        // the wildcard arm will fail loudly so the test can be revisited.
        match err {
            DispatchError::Backend(boxed) => {
                let msg = boxed.to_string();
                assert!(
                    msg.contains("No handler registered"),
                    "expected the underlying handler error to be wrapped \
                     verbatim into DispatchError::Backend, got: {msg}"
                );
            }
            other => {
                panic!("unexpected DispatchError variant from IpcHandler::dispatch: {other:?}")
            }
        }
    }
}

#[cfg(test)]
mod off_clear_tests {
    use super::*;

    #[test]
    fn test_off_and_clear() {
        let handler = IpcHandler::new();
        handler.on("evt", |_m| Ok(serde_json::json!({})));
        assert_eq!(handler.registered_event_count(), 1);

        handler.off("evt");
        assert_eq!(handler.registered_event_count(), 0);

        handler.on("evt2", |_m| Ok(serde_json::json!({})));
        handler.on("evt3", |_m| Ok(serde_json::json!({})));
        assert_eq!(handler.registered_event_count(), 2);

        handler.clear();
        assert_eq!(handler.registered_event_count(), 0);
    }
}
