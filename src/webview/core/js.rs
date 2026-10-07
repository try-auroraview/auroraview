//! AuroraView Core - JavaScript Execution Methods
//!
//! This module contains JavaScript execution methods:
//! - `eval_js`: Execute JavaScript synchronously
//! - `eval_js_async`: Execute JavaScript with callback
//! - `eval_js_future`: Execute JavaScript and poll for result
//! - `get_js_result`: Get result of async JavaScript execution

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::AuroraView;
use crate::ipc::WebViewMessage;

// Internal methods (not exposed to Python directly, but callable from other modules)
impl AuroraView {
    /// Internal: Execute JavaScript code asynchronously with result callback
    pub(crate) fn eval_js_async_internal(
        &self,
        script: &str,
        callback: Py<PyAny>,
        timeout_ms: u64,
    ) -> PyResult<()> {
        let callback_id = self.js_callback_manager.next_callback_id();

        tracing::info!(
            "Queueing async JavaScript execution (id={}, timeout={}ms): {}",
            callback_id,
            timeout_ms,
            script
        );

        self.js_callback_manager.enqueue_callback(
            &self.message_queue, script.to_string(), callback_id, callback, timeout_ms,
        ).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;

        Ok(())
    }
}

#[pymethods]
impl AuroraView {
    /// Execute JavaScript code in the WebView
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    fn eval_js(&self, script: &str) -> PyResult<()> {
        tracing::info!("Queueing JavaScript execution: {}", script);
        self.message_queue
            .push(WebViewMessage::EvalJs(script.to_string()));
        Ok(())
    }

    /// Execute JavaScript code asynchronously with result callback
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    ///     callback (callable): Python function(result, error) to call with result
    ///     timeout_ms (int, optional): Timeout in milliseconds (default: 5000)
    ///
    /// Example:
    ///     >>> def on_result(result, error):
    ///     ...     if error:
    ///     ...         print(f"Error: {error}")
    ///     ...     else:
    ///     ...         print(f"Result: {result}")
    ///     >>> webview.eval_js_async("1 + 2", on_result)
    #[pyo3(signature = (script, callback, timeout_ms=5000))]
    fn eval_js_async(&self, script: &str, callback: Py<PyAny>, timeout_ms: u64) -> PyResult<()> {
        let callback_id = self.js_callback_manager.next_callback_id();

        tracing::info!(
            "Queueing async JavaScript execution (id={}, timeout={}ms): {}",
            callback_id,
            timeout_ms,
            script
        );

        self.js_callback_manager.enqueue_callback(
            &self.message_queue, script.to_string(), callback_id, callback, timeout_ms,
        ).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;

        Ok(())
    }

    /// Execute JavaScript and return result as a Future
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    ///     timeout_ms (int): Timeout in milliseconds (default: 5000)
    ///
    /// Returns:
    ///     int: Callback ID for polling result with get_js_result()
    ///
    /// Example:
    ///     >>> callback_id = webview.eval_js_future("1 + 2")
    ///     >>> # Poll for result
    ///     >>> result = webview.get_js_result(callback_id)
    #[pyo3(signature = (script, timeout_ms=5000))]
    fn eval_js_future(&self, script: &str, timeout_ms: u64) -> PyResult<u64> {
        let callback_id = self.js_callback_manager.next_callback_id();

        tracing::info!(
            "Queueing async JavaScript execution for future (id={}, timeout={}ms): {}",
            callback_id,
            timeout_ms,
            script
        );

        let internal_callback = Python::attach(|py| py.None());

        self.js_callback_manager.enqueue_callback(
            &self.message_queue, script.to_string(), callback_id, internal_callback, timeout_ms,
        ).map_err(pyo3::exceptions::PyRuntimeError::new_err)?;

        Ok(callback_id)
    }

    /// Get the result of a JavaScript execution started with eval_js_future
    ///
    /// Args:
    ///     callback_id (int): The callback ID returned by eval_js_future
    ///
    /// Returns:
    ///     dict: A dict with 'status' (pending/complete/error/timeout) and optionally 'result' or 'error'
    fn get_js_result(&self, py: Python<'_>, callback_id: u64) -> PyResult<Py<PyDict>> {
        let result_dict = PyDict::new(py);

        if self.js_callback_manager.has_callback(callback_id) {
            result_dict.set_item("status", "pending")?;
        } else if let Some((result, error)) =
            self.js_callback_manager.get_stored_result(callback_id)
        {
            if let Some(err) = error {
                result_dict.set_item("status", "error")?;
                result_dict.set_item("error", err)?;
            } else {
                result_dict.set_item("status", "complete")?;
                result_dict.set_item("result", result)?;
            }
        } else {
            result_dict.set_item("status", "timeout")?;
        }

        Ok(result_dict.unbind())
    }

    /// Execute JavaScript and emit result via IPC
    ///
    /// Args:
    ///     script (str): JavaScript code to execute
    ///     event_name (str): Event name to emit with result
    #[pyo3(signature = (script, event_name="js_result"))]
    fn eval_js_emit(&self, script: &str, event_name: &str) -> PyResult<()> {
        let wrapped_script = format!(
            r#"(function() {{
                try {{
                    var result = eval({});
                    window.auroraview.emit('{}', {{ success: true, result: result }});
                }} catch(e) {{
                    window.auroraview.emit('{}', {{ success: false, error: e.toString() }});
                }}
            }})()"#,
            serde_json::to_string(script).unwrap_or_else(|_| format!("\"{}\"", script)),
            event_name,
            event_name
        );
        self.message_queue
            .push(WebViewMessage::EvalJs(wrapped_script));
        Ok(())
    }
}
