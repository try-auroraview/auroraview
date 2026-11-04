//! JavaScript Callback Manager
//!
//! This module manages async JavaScript execution callbacks.
//! It stores Python callbacks keyed by unique IDs, so when JavaScript
//! execution results come back via IPC, we can route them to the correct callback.
//!
//! Features:
//! - Unique callback ID generation
//! - Timeout mechanism for stale callbacks
//! - Thread-safe concurrent access via DashMap

#[cfg(feature = "python-bindings")]
use crate::webview::window_control::WindowControl;
use dashmap::DashMap;
#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;
#[cfg(feature = "python-bindings")]
use pyo3::{Py, PyAny};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
#[cfg(feature = "python-bindings")]
use std::sync::OnceLock;
#[cfg(feature = "python-bindings")]
use std::time::Instant;

/// JavaScript callback result
#[derive(Debug, Clone)]
pub struct JsCallbackResult {
    /// The result value as JSON
    pub value: Option<serde_json::Value>,
    /// Error message if execution failed
    pub error: Option<String>,
}

/// Callback entry with metadata for timeout tracking
#[cfg(feature = "python-bindings")]
struct CallbackEntry {
    callback: Py<PyAny>,
    created_at: Instant,
    timeout_ms: u64,
}

/// Stored result for Future-style polling
#[derive(Debug, Clone)]
pub struct StoredResult {
    pub result: Option<String>,
    pub error: Option<String>,
}

/// JavaScript callback manager for async execution
///
/// Uses DashMap for lock-free concurrent callback storage.
/// Supports timeout mechanism for cleanup of stale callbacks.
pub struct JsCallbackManager {
    /// Atomic counter for generating unique callback IDs
    next_id: AtomicU64,

    /// Pending Python callbacks keyed by ID (with timeout metadata)
    #[cfg(feature = "python-bindings")]
    pending_callbacks: Arc<DashMap<u64, CallbackEntry>>,

    /// Stored results for Future-style polling (for eval_js_future)
    stored_results: Arc<DashMap<u64, StoredResult>>,

    /// Default timeout in milliseconds for callbacks
    default_timeout_ms: u64,
    #[cfg(feature = "python-bindings")]
    retained_control: OnceLock<Arc<WindowControl>>,
}

impl JsCallbackManager {
    /// Create a new callback manager
    pub fn new() -> Self {
        Self {
            next_id: AtomicU64::new(1),
            #[cfg(feature = "python-bindings")]
            pending_callbacks: Arc::new(DashMap::new()),
            stored_results: Arc::new(DashMap::new()),
            default_timeout_ms: 5000,
            #[cfg(feature = "python-bindings")]
            retained_control: OnceLock::new(),
        }
    }

    #[cfg(feature = "python-bindings")]
    pub fn set_retained_control(&self, control: Arc<WindowControl>) -> Result<(), String> {
        self.retained_control
            .set(control)
            .map_err(|_| "retained control already attached".to_string())
    }

    /// Generate a unique callback ID
    pub fn next_callback_id(&self) -> u64 {
        self.next_id.fetch_add(1, Ordering::SeqCst)
    }

    /// Register a Python callback for async JavaScript execution
    #[cfg(feature = "python-bindings")]
    pub fn register_callback(&self, id: u64, callback: Py<PyAny>) {
        self.register_callback_with_timeout(id, callback, self.default_timeout_ms);
    }

    /// Register a Python callback with custom timeout
    #[cfg(feature = "python-bindings")]
    pub fn register_callback_with_timeout(&self, id: u64, callback: Py<PyAny>, timeout_ms: u64) {
        if self
            .retained_control
            .get()
            .is_some_and(|control| control.intent().close)
        {
            return;
        }
        let entry = CallbackEntry {
            callback,
            created_at: Instant::now(),
            timeout_ms,
        };
        self.pending_callbacks.insert(id, entry);
        if self
            .retained_control
            .get()
            .is_some_and(|control| control.intent().close)
        {
            self.pending_callbacks.remove(&id);
            return;
        }
        tracing::debug!(
            "Registered JS callback with ID: {} (timeout: {}ms)",
            id,
            timeout_ms
        );
    }

    /// Complete a callback with the result
    #[cfg(feature = "python-bindings")]
    pub fn complete_callback(&self, id: u64, result: JsCallbackResult) -> Result<(), String> {
        let _flight = if let Some(control) = self.retained_control.get() {
            match control.begin_callback() {
                Some(flight) => Some(flight),
                None => {
                    self.pending_callbacks.clear();
                    return Err("retained window is closing; script callbacks are cancelled".into());
                }
            }
        } else {
            None
        };
        if let Some((_, entry)) = self.pending_callbacks.remove(&id) {
            Python::attach(|py| {
                // Convert result to Python objects
                let py_result = match &result.value {
                    Some(val) => match super::json::json_to_python(py, val) {
                        Ok(obj) => obj,
                        Err(e) => {
                            return Err(format!("Failed to convert result to Python: {}", e));
                        }
                    },
                    None => py.None(),
                };

                let py_error: Py<PyAny> = match &result.error {
                    Some(err) => {
                        // Convert error string to Python string
                        match err.clone().into_pyobject(py) {
                            Ok(obj) => obj.as_any().clone().unbind(),
                            Err(_) => py.None(),
                        }
                    }
                    None => py.None(),
                };

                // Call the callback with (result, error)
                match entry.callback.call1(py, (py_result, py_error)) {
                    Ok(_) => {
                        tracing::debug!("JS callback {} completed successfully", id);
                        Ok(())
                    }
                    Err(e) => {
                        tracing::error!("JS callback {} failed: {}", id, e);
                        Err(format!("Callback error: {}", e))
                    }
                }
            })
        } else {
            tracing::warn!("No pending callback found for ID: {}", id);
            Err(format!("No pending callback for ID: {}", id))
        }
    }

    /// Check for and cleanup timed-out callbacks
    ///
    /// Returns the number of callbacks that were timed out and cleaned up.
    /// Each timed-out callback is called with (None, "Timeout error") before removal.
    #[cfg(feature = "python-bindings")]
    pub fn cleanup_timed_out(&self) -> usize {
        let _flight = if let Some(control) = self.retained_control.get() {
            match control.begin_callback() {
                Some(flight) => Some(flight),
                None => {
                    self.pending_callbacks.clear();
                    return 0;
                }
            }
        } else {
            None
        };
        let now = Instant::now();
        let mut timed_out_ids = Vec::new();

        // Find timed-out callbacks
        for entry in self.pending_callbacks.iter() {
            let elapsed = now.duration_since(entry.value().created_at);
            if elapsed.as_millis() as u64 > entry.value().timeout_ms {
                timed_out_ids.push(*entry.key());
            }
        }

        // Complete timed-out callbacks with error
        let mut completed = 0;
        for id in &timed_out_ids {
            if self
                .retained_control
                .get()
                .is_some_and(|control| control.intent().close)
            {
                self.pending_callbacks.clear();
                break;
            }
            if let Some((_, entry)) = self.pending_callbacks.remove(id) {
                completed += 1;
                tracing::warn!("JS callback {} timed out after {}ms", id, entry.timeout_ms);

                // Call the callback with timeout error
                Python::attach(|py| {
                    let timeout_error = format!(
                        "JavaScript execution timed out after {}ms",
                        entry.timeout_ms
                    );
                    let py_error: Py<PyAny> = match timeout_error.into_pyobject(py) {
                        Ok(obj) => obj.as_any().clone().unbind(),
                        Err(_) => py.None(),
                    };

                    if let Err(e) = entry.callback.call1(py, (py.None(), py_error)) {
                        tracing::error!("Failed to notify timeout for callback {}: {}", id, e);
                    }
                });
            }
        }

        completed
    }

    /// Cancel a pending callback
    #[cfg(feature = "python-bindings")]
    pub fn cancel_callback(&self, id: u64) {
        if self.pending_callbacks.remove(&id).is_some() {
            tracing::debug!("Cancelled JS callback with ID: {}", id);
        }
    }

    /// Get the number of pending callbacks
    #[cfg(feature = "python-bindings")]
    pub fn pending_count(&self) -> usize {
        self.pending_callbacks.len()
    }

    /// Get the default timeout
    pub fn default_timeout_ms(&self) -> u64 {
        self.default_timeout_ms
    }

    /// Set the default timeout
    pub fn set_default_timeout_ms(&mut self, timeout_ms: u64) {
        self.default_timeout_ms = timeout_ms;
    }

    /// Check if a callback is still pending
    #[cfg(feature = "python-bindings")]
    pub fn has_callback(&self, id: u64) -> bool {
        self.pending_callbacks.contains_key(&id)
    }

    /// Store a result for Future-style polling
    pub fn store_result(&self, id: u64, result: Option<String>, error: Option<String>) {
        #[cfg(feature = "python-bindings")]
        if self
            .retained_control
            .get()
            .is_some_and(|control| control.intent().close)
        {
            return;
        }
        self.stored_results
            .insert(id, StoredResult { result, error });
    }

    /// Get and remove a stored result
    pub fn get_stored_result(&self, id: u64) -> Option<(Option<String>, Option<String>)> {
        self.stored_results
            .remove(&id)
            .map(|(_, r)| (r.result, r.error))
    }

    /// Complete a callback and store result for Future-style polling
    #[cfg(feature = "python-bindings")]
    pub fn complete_callback_and_store(
        &self,
        id: u64,
        result: JsCallbackResult,
    ) -> Result<(), String> {
        // Store result for polling
        let result_str = result.value.as_ref().map(|v| v.to_string());
        let error_str = result.error.clone();
        self.store_result(id, result_str, error_str);

        // Also complete the callback if one exists
        self.complete_callback(id, result)
    }
}

impl Default for JsCallbackManager {
    fn default() -> Self {
        Self::new()
    }
}
