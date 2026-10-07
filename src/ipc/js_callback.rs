//! JavaScript Callback Manager
//!
//! This module manages async JavaScript execution callbacks.
//! It stores Python callbacks keyed by unique IDs, so when JavaScript
//! execution results come back via IPC, we can route them to the correct callback.
//!
//! Features:
//! - Unique callback ID generation
//! - Timeout mechanism for stale callbacks
//! - Lock-scoped ownership transfer; Python is never called or dropped under a lock

use dashmap::DashMap;
#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;
#[cfg(feature = "python-bindings")]
use pyo3::{Py, PyAny};
#[cfg(feature = "python-bindings")]
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
#[cfg(feature = "python-bindings")]
use std::sync::Mutex;
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

#[cfg(feature = "python-bindings")]
#[derive(Default)]
struct CallbackState {
    closed: bool,
    pending: BTreeMap<u64, CallbackEntry>,
    timeout_cursor: Option<u64>,
    // A sweep must not chase new IDs forever while older entries expire.
    timeout_high_water: Option<u64>,
}

/// Stored result for Future-style polling
#[derive(Debug, Clone)]
pub struct StoredResult {
    pub result: Option<String>,
    pub error: Option<String>,
}

/// JavaScript callback manager for async execution
///
/// Transfers callback ownership out of a mutex before invoking or dropping Python.
/// Supports timeout mechanism for cleanup of stale callbacks.
pub struct JsCallbackManager {
    /// Atomic counter for generating unique callback IDs
    next_id: AtomicU64,

    /// Pending Python callbacks keyed by ID (with timeout metadata)
    #[cfg(feature = "python-bindings")]
    pending_callbacks: Mutex<CallbackState>,

    /// Stored results for Future-style polling (for eval_js_future)
    stored_results: Arc<DashMap<u64, StoredResult>>,

    /// Default timeout in milliseconds for callbacks
    default_timeout_ms: u64,
}

impl JsCallbackManager {
    /// Create a new callback manager
    pub fn new() -> Self {
        Self {
            next_id: AtomicU64::new(1),
            #[cfg(feature = "python-bindings")]
            pending_callbacks: Mutex::new(CallbackState::default()),
            stored_results: Arc::new(DashMap::new()),
            default_timeout_ms: 5000,
        }
    }

    /// Generate a unique callback ID
    pub fn next_callback_id(&self) -> u64 {
        self.next_id.fetch_add(1, Ordering::SeqCst)
    }

    /// Register a Python callback; false means shutdown has closed admission.
    #[cfg(feature = "python-bindings")]
    pub fn register_callback(&self, id: u64, callback: Py<PyAny>) -> bool {
        self.register_callback_with_timeout(id, callback, self.default_timeout_ms)
    }

    /// Register without dropping a rejected or replaced Python object under a lock.
    #[cfg(feature = "python-bindings")]
    pub fn register_callback_with_timeout(
        &self,
        id: u64,
        callback: Py<PyAny>,
        timeout_ms: u64,
    ) -> bool {
        let entry = CallbackEntry {
            callback,
            created_at: Instant::now(),
            timeout_ms,
        };
        let mut state = self
            .pending_callbacks
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state.closed {
            drop(state);
            drop(entry);
            return false;
        }
        let replaced = state.pending.insert(id, entry);
        drop(state);
        drop(replaced);
        true
    }

    /// Detach one callback before any Python reference can be released.
    #[cfg(feature = "python-bindings")]
    fn take_callback(&self, id: u64) -> Option<CallbackEntry> {
        let mut state = self
            .pending_callbacks
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let entry = state.pending.remove(&id);
        drop(state);
        entry
    }

    /// Register and admit an async command, rolling back a rejected queue admission.
    #[cfg(feature = "python-bindings")]
    pub fn enqueue_callback(
        &self,
        queue: &super::MessageQueue,
        script: String,
        id: u64,
        callback: Py<PyAny>,
        timeout_ms: u64,
    ) -> Result<(), String> {
        if queue.is_shutdown() {
            return Err("WebView queue is shut down".to_string());
        }
        if !self.register_callback_with_timeout(id, callback, timeout_ms) {
            return Err("JavaScript callback admission is closed".to_string());
        }
        if let Err(error) = queue.try_push(super::WebViewMessage::EvalJsAsync {
            script,
            callback_id: id,
        }) {
            self.cancel_callback(id);
            return Err(error);
        }
        Ok(())
    }

    /// Complete a callback with the result
    #[cfg(feature = "python-bindings")]
    pub fn complete_callback(&self, id: u64, result: JsCallbackResult) -> Result<(), String> {
        if let Some(entry) = self.take_callback(id) {
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

    /// Start a fresh sweep over the current pending count (legacy explicit cleanup API).
    #[cfg(feature = "python-bindings")]
    pub fn cleanup_timed_out(&self) -> usize {
        let count = {
            let mut state = self
                .pending_callbacks
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            state.timeout_cursor = None;
            state.timeout_high_water = None;
            state.pending.len()
        };
        self.cleanup_timed_out_bounded(count)
    }

    /// Inspect at most `limit` callbacks on the caller's thread.
    /// Each sweep has a captured high-water ID, so arrivals cannot prevent a
    /// return to old unexpired entries. The hosted owner calls this every pump.
    /// No lock spans Python execution.
    #[cfg(feature = "python-bindings")]
    pub fn cleanup_timed_out_bounded(&self, limit: usize) -> usize {
        self.cleanup_timed_out_while(limit, || true)
    }

    /// Stop notifying expired callbacks once the hosted owner observes close intent.
    /// Detached expired entries are still released outside all locks.
    #[cfg(feature = "python-bindings")]
    pub fn cleanup_timed_out_while(
        &self,
        limit: usize,
        mut running: impl FnMut() -> bool,
    ) -> usize {
        use std::ops::Bound::{Excluded, Included, Unbounded};
        if limit == 0 {
            return 0;
        }
        let now = Instant::now();
        let expired = {
            let mut state = self
                .pending_callbacks
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            let high_water = match state.timeout_high_water {
                Some(id) => id,
                None => {
                    let Some((&id, _)) = state.pending.last_key_value() else {
                        return 0;
                    };
                    state.timeout_cursor = None;
                    state.timeout_high_water = Some(id);
                    id
                }
            };
            let ids: Vec<u64> = state
                .pending
                .range((
                    state.timeout_cursor.map_or(Unbounded, Excluded),
                    Included(high_water),
                ))
                .take(limit)
                .map(|(id, _)| *id)
                .collect();
            // An empty tail (including removal of the captured high-water entry)
            // ends this sweep. New arrivals belong to the next one, even if this
            // poll has unused inspection capacity.
            let sweep_complete = ids.len() < limit || ids.last() == Some(&high_water);
            let mut expired = Vec::new();
            for id in ids {
                state.timeout_cursor = Some(id);
                if state.pending.get(&id).is_some_and(|entry| {
                    now.duration_since(entry.created_at).as_millis() >= u128::from(entry.timeout_ms)
                }) {
                    if let Some(entry) = state.pending.remove(&id) {
                        expired.push((id, entry));
                    }
                }
            }
            if sweep_complete {
                state.timeout_cursor = None;
                state.timeout_high_water = None;
            }
            expired
        };
        let count = expired.len();
        for (id, entry) in expired {
            // A previous timeout callback may have requested close. Do not invoke
            // more application callbacks after callback admission closes.
            let closed = self
                .pending_callbacks
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .closed;
            if closed || !running() {
                break;
            }
            Python::attach(|py| {
                let error = format!(
                    "JavaScript execution timed out after {}ms",
                    entry.timeout_ms
                );
                if let Err(error) = entry.callback.call1(py, (py.None(), error)) {
                    tracing::error!("Failed to notify timeout for callback {}: {}", id, error);
                }
            });
        }
        count
    }

    /// Close admission without releasing references, so all lifecycle gates can close first.
    #[cfg(feature = "python-bindings")]
    pub fn close_admission(&self) {
        self.pending_callbacks
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .closed = true;
    }

    /// Permanently close admission and detach all callbacks before releasing Python.
    #[cfg(feature = "python-bindings")]
    pub fn cancel_all_hosted(&self) {
        let detached = {
            let mut state = self
                .pending_callbacks
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            state.closed = true;
            std::mem::take(&mut state.pending)
        };
        self.stored_results.clear(); // Contains only Rust-owned strings.
        drop(detached); // Owner thread, with no map, admission, or registry lock held.
    }

    /// Cancel a pending callback outside the ownership lock.
    #[cfg(feature = "python-bindings")]
    pub fn cancel_callback(&self, id: u64) {
        drop(self.take_callback(id));
    }

    /// Get the number of pending callbacks.
    #[cfg(feature = "python-bindings")]
    pub fn pending_count(&self) -> usize {
        self.pending_callbacks
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .pending
            .len()
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
        self.pending_callbacks
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .pending
            .contains_key(&id)
    }

    /// Store a result for Future-style polling
    pub fn store_result(&self, id: u64, result: Option<String>, error: Option<String>) {
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
