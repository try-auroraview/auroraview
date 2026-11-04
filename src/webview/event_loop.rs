//! Improved event loop handling using ApplicationHandler pattern
//!
//! This module provides a better event loop implementation that:
//! - Uses a dedicated event handler structure
//! - Supports both blocking and non-blocking modes
//! - Properly manages window lifecycle
//! - Integrates better with Python's GIL
//! - Emits window events to Python callbacks (inspired by Tauri/Electron)
//!
//! ## Thread Safety Optimizations
//!
//! - Uses `AtomicBool` for `should_exit` flag (lock-free)
//! - Uses `crossbeam-channel` for message queue (lock-free MPMC)
//! - Minimizes lock contention in hot paths
//!
//! ## Error Handling
//!
//! This module uses [`EventLoopError`] for structured error handling with
//! actionable information for debugging production issues.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoop, EventLoopProxy};
use tao::platform::run_return::EventLoopExtRunReturn;
use tao::window::Window;
use thiserror::Error;
use wry::WebView as WryWebView;

use crate::ipc::{MessageQueue, WebViewMessage};
use crate::webview::js_assets;
#[cfg(feature = "python-bindings")]
use crate::webview::window_control::{
    QueuedCommand, RetainedShared, WindowCommand, WindowSnapshot,
};

#[cfg(feature = "python-bindings")]
#[derive(Default)]
struct PendingWindowState {
    minimized: Option<(bool, u64)>,
    maximized: Option<(bool, u64)>,
    fullscreen: Option<(bool, u64)>,
    deferred: Vec<QueuedCommand>,
    sent_visibility_seq: Option<u64>,
}

#[cfg(feature = "python-bindings")]
use crate::ipc::{IpcHandler, WindowEventType};

/// Event loop errors with context for debugging
///
/// These errors provide structured information for diagnosing issues
/// in production environments. Each variant includes relevant context
/// to help identify the root cause.
#[derive(Debug, Error)]
pub enum EventLoopError {
    /// Failed to acquire WebView lock
    #[error("WebView lock failed: {context}")]
    WebViewLock {
        /// Description of what operation was attempted
        context: String,
    },

    /// JavaScript execution failed
    #[error("JavaScript execution failed: {script_preview}")]
    ScriptExecution {
        /// First 100 chars of the script for identification
        script_preview: String,
        /// The underlying error message
        message: String,
    },

    /// Message queue is full (backpressure)
    #[error("Message queue full: {queue_len} messages pending")]
    QueueFull {
        /// Current queue length
        queue_len: usize,
    },

    /// UTF-8 encoding error in message data
    #[error("Encoding error: {message}")]
    Encoding {
        /// Description of the encoding issue
        message: String,
    },

    /// Event loop proxy error (loop may be closed)
    #[error("Event loop closed or unavailable")]
    EventLoopClosed,

    /// Window operation failed
    #[error("Window operation failed: {operation}")]
    WindowOperation {
        /// The operation that failed
        operation: String,
    },

    /// Message processing timeout
    #[error("Message processing timed out after {timeout_ms}ms")]
    Timeout {
        /// Timeout duration in milliseconds
        timeout_ms: u64,
    },
}

/// Result type for event loop operations
pub type EventLoopResult<T> = Result<T, EventLoopError>;

impl EventLoopError {
    /// Create a WebView lock error with context
    pub fn webview_lock(context: impl Into<String>) -> Self {
        Self::WebViewLock {
            context: context.into(),
        }
    }

    /// Create a script execution error with preview
    pub fn script_execution(script: &str, message: impl Into<String>) -> Self {
        let preview = if script.len() > 100 {
            format!("{}...", &script[..100])
        } else {
            script.to_string()
        };
        Self::ScriptExecution {
            script_preview: preview,
            message: message.into(),
        }
    }

    /// Create an encoding error
    pub fn encoding(message: impl Into<String>) -> Self {
        Self::Encoding {
            message: message.into(),
        }
    }

    /// Create a window operation error
    pub fn window_operation(operation: impl Into<String>) -> Self {
        Self::WindowOperation {
            operation: operation.into(),
        }
    }

    /// Create a timeout error
    pub fn timeout(timeout_ms: u64) -> Self {
        Self::Timeout { timeout_ms }
    }
}

/// Custom user event for waking up the event loop
#[derive(Debug, Clone)]
pub enum UserEvent {
    /// Wake up the event loop to process pending messages
    ProcessMessages,
    /// Request to close the window
    CloseWindow,
    /// Tray menu item clicked
    TrayMenuClick(String),
    /// Tray icon clicked (for show/hide window)
    TrayIconClick,
    /// Tray icon double-clicked
    TrayIconDoubleClick,
    /// Request to start native window drag
    DragWindow,
    /// Plugin event to be forwarded to WebView
    PluginEvent { event: String, data: String },
    /// Request to create a new child WebView window
    CreateChildWindow {
        url: String,
        width: u32,
        height: u32,
    },
}

/// Hints for applying Win32 window styles at the correct time.
///
/// On Windows 11, tao/wry may adjust window styles when the window becomes visible.
/// For frameless/transparent tool windows we keep a small set of hints so we can
/// re-apply the desired styles right after `set_visible(true)`.
#[derive(Debug, Clone, Copy)]
pub struct WindowStyleHints {
    #[cfg(target_os = "windows")]
    pub decorations: bool,
    #[cfg(target_os = "windows")]
    pub tool_window: bool,
    #[cfg(target_os = "windows")]
    pub undecorated_shadow: bool,
    #[cfg(target_os = "windows")]
    pub transparent: bool,
}

/// Event loop state management
///
/// ## Thread Safety
/// - `should_exit`: `AtomicBool` for lock-free exit signaling
/// - `webview`: `Arc<Mutex<>>` because WryWebView is not Send/Sync
/// - `message_queue`: Uses `crossbeam-channel` internally (lock-free MPMC)
pub struct EventLoopState {
    /// Whether the event loop should continue running (atomic for lock-free access)
    pub should_exit: Arc<AtomicBool>,
    /// Window reference
    pub window: Option<Window>,
    /// WebView reference for processing messages (wrapped in Arc<Mutex<>> for thread safety)
    pub webview: Option<Arc<Mutex<WryWebView>>>,
    /// Message queue for cross-thread communication
    pub message_queue: Arc<MessageQueue>,
    /// Event loop proxy for waking up the event loop
    pub event_loop_proxy: Option<EventLoopProxy<UserEvent>>,
    /// IPC handler for Python callbacks (window events)
    #[cfg(feature = "python-bindings")]
    pub ipc_handler: Option<Arc<IpcHandler>>,
    /// Optional window style hints for post-show re-application
    pub window_style_hints: Option<WindowStyleHints>,
    /// Track window visibility state for event deduplication
    is_visible: bool,
    /// Track window focus state for event deduplication
    is_focused: bool,
}

impl EventLoopState {
    /// Create a new event loop state
    #[allow(dead_code)]
    #[allow(clippy::arc_with_non_send_sync)]
    pub fn new(window: Window, webview: WryWebView, message_queue: Arc<MessageQueue>) -> Self {
        Self {
            should_exit: Arc::new(AtomicBool::new(false)),
            window: Some(window),
            webview: Some(Arc::new(Mutex::new(webview))),
            message_queue,
            event_loop_proxy: None,
            #[cfg(feature = "python-bindings")]
            ipc_handler: None,
            window_style_hints: None,
            is_visible: false,
            is_focused: false,
        }
    }

    /// Create a new event loop state without webview (for later initialization)
    pub fn new_without_webview(window: Window, message_queue: Arc<MessageQueue>) -> Self {
        Self {
            should_exit: Arc::new(AtomicBool::new(false)),
            window: Some(window),
            webview: None,
            message_queue,
            event_loop_proxy: None,
            #[cfg(feature = "python-bindings")]
            ipc_handler: None,
            window_style_hints: None,
            is_visible: false,
            is_focused: false,
        }
    }

    /// Set the webview reference
    pub fn set_webview(&mut self, webview: Arc<Mutex<WryWebView>>) {
        self.webview = Some(webview);
    }

    /// Set the event loop proxy
    pub fn set_event_loop_proxy(&mut self, proxy: EventLoopProxy<UserEvent>) {
        self.event_loop_proxy = Some(proxy);
    }

    /// Set window style hints for post-show re-application.
    #[allow(dead_code)]
    pub fn set_window_style_hints(&mut self, hints: Option<WindowStyleHints>) {
        self.window_style_hints = hints;
    }

    /// Set the IPC handler for Python callbacks
    #[cfg(feature = "python-bindings")]
    #[allow(dead_code)]
    pub fn set_ipc_handler(&mut self, handler: Arc<IpcHandler>) {
        self.ipc_handler = Some(handler);
    }

    /// Signal the event loop to exit
    ///
    /// Uses ipckit's graceful shutdown mechanism to wait for pending operations.
    /// This method is lock-free for the exit flag (uses AtomicBool).
    pub fn request_exit(&self) {
        // Shutdown the message queue first to prevent background threads
        // from sending messages after the event loop is closed
        self.message_queue.shutdown();

        // Wait for pending operations to complete (with short timeout)
        // This uses ipckit's wait_for_drain mechanism
        if let Err(e) = self
            .message_queue
            .wait_for_drain(Some(std::time::Duration::from_millis(500)))
        {
            tracing::warn!("[EventLoopState] Drain timeout during exit: {}", e);
        }

        // Set exit flag atomically (lock-free)
        self.should_exit.store(true, Ordering::SeqCst);
    }

    /// Check if exit was requested (lock-free)
    pub fn should_exit(&self) -> bool {
        self.should_exit.load(Ordering::SeqCst)
    }

    /// Emit a window event to Python callbacks
    #[cfg(feature = "python-bindings")]
    pub fn emit_window_event(&self, event_type: WindowEventType, data: serde_json::Value) {
        if let Some(handler) = &self.ipc_handler {
            let event_name = event_type.as_str();
            tracing::debug!(
                "Emitting window event: {} with data: {:?}",
                event_name,
                data
            );

            // Call Python callbacks for this event
            let message = crate::ipc::IpcMessage {
                event: event_name.to_string(),
                data: data.clone(),
                id: None,
            };

            if let Err(e) = handler.handle_message(message) {
                // No handler registered is OK - just means no Python callback was set
                if !e.contains("No handler registered") {
                    tracing::warn!("Window event callback error: {}", e);
                }
            }

            // Also emit to JavaScript via message queue
            self.message_queue.push(WebViewMessage::EmitEvent {
                event_name: event_name.to_string(),
                data,
            });
        }
    }

    /// Update visibility state and emit event if changed
    pub fn set_visible(&mut self, visible: bool) {
        if self.is_visible != visible {
            self.is_visible = visible;
            #[cfg(feature = "python-bindings")]
            {
                let event_type = if visible {
                    WindowEventType::Shown
                } else {
                    WindowEventType::Hidden
                };
                self.emit_window_event(event_type, serde_json::json!({}));
            }
        }
    }

    /// Update focus state and emit event if changed
    pub fn set_focused(&mut self, focused: bool) {
        if self.is_focused != focused {
            self.is_focused = focused;
            #[cfg(feature = "python-bindings")]
            {
                let event_type = if focused {
                    WindowEventType::Focused
                } else {
                    WindowEventType::Blurred
                };
                self.emit_window_event(event_type, serde_json::json!({}));
            }
        }
    }

    /// Get the window HWND (Windows only)
    ///
    /// Returns the native window handle for targeted message processing.
    /// This is used to isolate message pump processing to only this window's messages.
    #[cfg(target_os = "windows")]
    pub fn get_hwnd(&self) -> Option<u64> {
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};

        if let Some(window) = &self.window {
            if let Ok(window_handle) = window.window_handle() {
                let raw_handle = window_handle.as_raw();
                if let RawWindowHandle::Win32(handle) = raw_handle {
                    return Some(handle.hwnd.get() as u64);
                }
            }
        }
        None
    }
}

/// Improved event loop handler
pub struct WebViewEventHandler {
    state: Arc<Mutex<EventLoopState>>,
}

/// Process a single WebView message
///
/// This is extracted as a separate function to avoid code duplication
/// across different event handlers (UserEvent::ProcessMessages, MainEventsCleared, poll_events_once).
fn process_webview_message(
    message: &WebViewMessage,
    webview: &WryWebView,
    window: Option<&Window>,
    state: Option<&EventLoopState>,
    #[cfg(feature = "python-bindings")] retained: Option<&RetainedShared>,
) {
    match message {
        WebViewMessage::EvalJs(script) => {
            tracing::debug!("[EventLoop] Executing EvalJs");
            if let Err(e) = webview.evaluate_script(script) {
                tracing::error!("[EventLoop] Failed to execute JavaScript: {}", e);
            }
        }
        WebViewMessage::EmitEvent { event_name, data } => {
            // JSON is already valid JavaScript literal
            let json_str = data.to_string();
            let script = js_assets::build_emit_event_script(event_name, &json_str);
            if let Err(e) = webview.evaluate_script(&script) {
                tracing::error!("Failed to emit event '{}': {}", event_name, e);
            }
        }
        WebViewMessage::LoadUrl(url) => {
            tracing::info!("[EventLoop] Loading URL via native API: {}", url);
            if let Err(e) = webview.load_url(url) {
                tracing::error!("Failed to load URL '{}': {}", url, e);
            }
        }
        WebViewMessage::LoadHtml(html) => {
            tracing::debug!("Processing LoadHtml ({} bytes)", html.len());
            if let Err(e) = webview.load_html(html) {
                tracing::error!("Failed to load HTML: {}", e);
            }
        }
        WebViewMessage::SetVisible(visible) => {
            // Handle at window level
            if let Some(win) = window {
                tracing::debug!("[EventLoop] Setting window visibility: {}", visible);
                win.set_visible(*visible);
            }
        }
        WebViewMessage::WindowEvent { event_type, data } => {
            let event_name = event_type.as_str();
            let json_str = data.to_string();
            let script = js_assets::build_emit_event_script(event_name, &json_str);
            if let Err(e) = webview.evaluate_script(&script) {
                tracing::error!("Failed to emit window event '{}': {}", event_name, e);
            }
        }
        WebViewMessage::EvalJsAsync {
            script,
            callback_id,
        } => {
            let async_script = js_assets::build_eval_js_async_script(script, *callback_id);
            if let Err(e) = webview.evaluate_script(&async_script) {
                tracing::error!(
                    "Failed to execute async JavaScript (id={}): {}",
                    callback_id,
                    e
                );
            }
        }
        WebViewMessage::Reload => {
            if let Err(e) = webview.evaluate_script("location.reload()") {
                tracing::error!("Failed to reload: {}", e);
            }
        }
        WebViewMessage::StopLoading => {
            if let Err(e) = webview.evaluate_script("window.stop()") {
                tracing::error!("Failed to stop loading: {}", e);
            }
        }
        WebViewMessage::Close => {
            #[cfg(feature = "python-bindings")]
            if let Some(shared) = retained {
                shared.control.close();
            }
            tracing::info!("[EventLoop] Close message received, requesting exit");
            if let Some(state) = state {
                state.request_exit();
            }
            if let Some(win) = window {
                win.set_visible(false);
            }
        }
    }
}

impl WebViewEventHandler {
    /// A finite slice of the legacy business queue. Native calls execute
    /// outside EventLoopState's mutex because COM may synchronously enter a
    /// Python callback which in turn needs the event-loop state.
    fn process_queue_batch(
        state: &Arc<Mutex<EventLoopState>>,
        #[cfg(feature = "python-bindings")] retained: Option<&RetainedShared>,
    ) -> usize {
        let (queue, webview) = match state.lock() {
            Ok(guard) => (guard.message_queue.clone(), guard.webview.clone()),
            Err(_) => return 0,
        };
        let mut count = 0;
        while count < 64 {
            #[cfg(feature = "python-bindings")]
            if retained.is_some_and(|shared| shared.control.intent().close) {
                break;
            }
            let Some(message) = queue.pop() else { break };
            count += 1;
            match message {
                WebViewMessage::Close => {
                    #[cfg(feature = "python-bindings")]
                    if let Some(shared) = retained {
                        shared.control.close();
                        break;
                    }
                    if let Ok(guard) = state.lock() {
                        guard.request_exit();
                        if let Some(window) = &guard.window {
                            window.set_visible(false);
                        }
                    }
                    break;
                }
                WebViewMessage::SetVisible(visible) => {
                    #[cfg(feature = "python-bindings")]
                    if let Some(shared) = retained {
                        if visible {
                            let _ = shared.control.show(false);
                        } else {
                            shared.control.hide();
                        }
                        continue;
                    }
                    if let Ok(guard) = state.lock() {
                        if let Some(window) = &guard.window {
                            window.set_visible(visible);
                        }
                    }
                }
                other => {
                    if let Some(webview) = &webview {
                        if let Ok(webview) = webview.lock() {
                            process_webview_message(
                                &other,
                                &webview,
                                None,
                                None,
                                #[cfg(feature = "python-bindings")]
                                retained,
                            );
                        }
                    }
                }
            }
        }
        count
    }

    #[cfg(feature = "python-bindings")]
    fn emit_retained(state: &Arc<Mutex<EventLoopState>>, event: &str, data: serde_json::Value) {
        let (handler, queue) = match state.lock() {
            Ok(guard) => (guard.ipc_handler.clone(), guard.message_queue.clone()),
            Err(_) => return,
        };
        if let Some(handler) = handler {
            let message = crate::ipc::IpcMessage {
                event: event.to_string(),
                data: data.clone(),
                id: None,
            };
            if let Err(error) = handler.handle_message(message) {
                if !error.contains("No handler registered") {
                    tracing::warn!(event, "Retained event callback failed: {}", error);
                }
            }
        }
        queue.push(WebViewMessage::EmitEvent {
            event_name: event.to_string(),
            data,
        });
    }

    #[cfg(feature = "python-bindings")]
    fn snapshot(window: &Window, hwnd: Option<u64>, version: u64) -> WindowSnapshot {
        let inner = window.inner_size();
        let outer = window.outer_size();
        let position = window.outer_position().ok();
        #[cfg(target_os = "windows")]
        let visible = hwnd.is_some_and(|value| {
            use std::ffi::c_void;
            use windows::Win32::Foundation::HWND;
            use windows::Win32::UI::WindowsAndMessaging::IsWindowVisible;
            // SAFETY: this is the owner thread and the HWND is checked by Win32.
            unsafe { IsWindowVisible(HWND(value as *mut c_void)).as_bool() }
        });
        #[cfg(not(target_os = "windows"))]
        let visible = window.is_visible();
        WindowSnapshot {
            version,
            hwnd,
            title: window.title(),
            x: position.as_ref().map_or(0, |p| p.x),
            y: position.as_ref().map_or(0, |p| p.y),
            width: inner.width,
            height: inner.height,
            outer_width: outer.width,
            outer_height: outer.height,
            visible,
            focused: window.is_focused(),
            minimized: window.is_minimized(),
            maximized: window.is_maximized(),
            fullscreen: window.fullscreen().is_some(),
        }
    }

    #[cfg(feature = "python-bindings")]
    fn command_retained(
        window: &Window,
        command: &WindowCommand,
        seq: u64,
        pending: &mut PendingWindowState,
    ) -> Result<(), String> {
        let hidden = !window.is_visible();
        let deferred = hidden
            && matches!(
                command,
                WindowCommand::Minimize
                    | WindowCommand::Maximize
                    | WindowCommand::Unmaximize
                    | WindowCommand::ToggleMaximize
                    | WindowCommand::Restore
                    | WindowCommand::SetFullscreen(..)
                    | WindowCommand::ToggleFullscreen
            );
        match command {
            WindowCommand::Center => {
                let monitor = window
                    .primary_monitor()
                    .or_else(|| window.current_monitor())
                    .ok_or_else(|| "no monitor available".to_string())?;
                let size = monitor.size();
                let origin = monitor.position();
                let outer = window.outer_size();
                window.set_outer_position(tao::dpi::PhysicalPosition::new(
                    origin.x + (size.width as i32 - outer.width as i32) / 2,
                    origin.y + (size.height as i32 - outer.height as i32) / 2,
                ));
            }
            WindowCommand::Move(x, y) => {
                window.set_outer_position(tao::dpi::PhysicalPosition::new(*x, *y))
            }
            WindowCommand::Resize(width, height) => {
                window.set_inner_size(tao::dpi::PhysicalSize::new(*width, *height))
            }
            WindowCommand::Minimize => {
                if hidden {
                    pending.minimized = Some((true, seq));
                } else {
                    window.set_minimized(true);
                }
            }
            WindowCommand::Maximize => {
                if hidden {
                    pending.maximized = Some((true, seq));
                } else {
                    window.set_maximized(true);
                }
            }
            WindowCommand::Unmaximize => {
                if hidden {
                    pending.maximized = Some((false, seq));
                } else {
                    window.set_maximized(false);
                }
            }
            WindowCommand::ToggleMaximize => {
                let current = pending
                    .maximized
                    .map_or(window.is_maximized(), |value| value.0);
                if hidden {
                    pending.maximized = Some((!current, seq));
                } else {
                    window.set_maximized(!current);
                }
            }
            WindowCommand::Restore => {
                if hidden {
                    pending.minimized = Some((false, seq));
                    pending.maximized = Some((false, seq));
                    pending.fullscreen = Some((false, seq));
                } else {
                    window.set_minimized(false);
                    window.set_maximized(false);
                    window.set_fullscreen(None);
                }
            }
            WindowCommand::SetFullscreen(value) => {
                if hidden {
                    pending.fullscreen = Some((*value, seq));
                } else {
                    window
                        .set_fullscreen(value.then_some(tao::window::Fullscreen::Borderless(None)));
                }
            }
            WindowCommand::ToggleFullscreen => {
                let current = pending
                    .fullscreen
                    .map_or(window.fullscreen().is_some(), |value| value.0);
                if hidden {
                    pending.fullscreen = Some((!current, seq));
                } else {
                    window.set_fullscreen(
                        (!current).then_some(tao::window::Fullscreen::Borderless(None)),
                    );
                }
            }
            WindowCommand::SetTitle(title) => window.set_title(title),
            WindowCommand::SetAlwaysOnTop(value) => window.set_always_on_top(*value),
            WindowCommand::SetResizable(value) => window.set_resizable(*value),
            WindowCommand::SetDecorations(value) => window.set_decorations(*value),
            WindowCommand::SetMinSize(width, height) => {
                window.set_min_inner_size(Some(tao::dpi::PhysicalSize::new(*width, *height)))
            }
            WindowCommand::SetMaxSize(width, height) => {
                window.set_max_inner_size(Some(tao::dpi::PhysicalSize::new(*width, *height)))
            }
            WindowCommand::Focus => window.set_focus(),
        }
        if deferred {
            pending.deferred.push(QueuedCommand {
                seq,
                operation: command.clone(),
            });
        }
        Ok(())
    }

    #[cfg(feature = "python-bindings")]
    fn process_retained(
        state: &Arc<Mutex<EventLoopState>>,
        shared: &RetainedShared,
        pending: &mut PendingWindowState,
    ) -> bool {
        let intent = shared.control.intent();
        if intent.close {
            shared.control.cancel_dequeued(pending.deferred.drain(..));
            if let Ok(guard) = state.lock() {
                guard.should_exit.store(true, Ordering::SeqCst);
                guard.message_queue.shutdown();
                if let Some(window) = &guard.window {
                    window.set_visible(false);
                }
            }
            return true;
        }
        let commands = shared.control.take_commands(64);
        if intent.seq == shared.control.applied_seq() && commands.is_empty() {
            return false;
        }
        let Ok(guard) = state.lock() else {
            return false;
        };
        let Some(window) = &guard.window else {
            return false;
        };
        let mut failures = Vec::new();
        let mut commands = commands.into_iter();
        while let Some(command) = commands.next() {
            if shared.control.intent().close {
                shared
                    .control
                    .cancel_dequeued(std::iter::once(command).chain(commands));
                break;
            }
            if let Err(error) =
                Self::command_retained(window, &command.operation, command.seq, pending)
            {
                tracing::error!(
                    operation = command.operation.name(),
                    request_seq = command.seq,
                    "Retained window command failed: {}",
                    error
                );
                failures.push((command.operation.name(), command.seq, error));
            }
        }
        // Native commands may synchronously run Win32/COM callbacks. The
        // snapshot taken before that batch is no longer an authority for the
        // visibility action at this boundary.
        let intent = shared.control.intent();
        if intent.close {
            drop(guard);
            for (operation, request_seq, error) in failures {
                Self::emit_retained(
                    state,
                    "window_command_failed",
                    serde_json::json!({
                        "window_id": shared.window_id(),
                        "operation": operation,
                        "request_seq": request_seq,
                        "message": error,
                    }),
                );
            }
            return Self::process_retained(state, shared, pending);
        }
        if intent.seq != shared.control.applied_seq()
            && pending.sent_visibility_seq != Some(intent.seq)
        {
            window.set_visible(intent.visible);
            if intent.visible {
                if let Some((value, _)) = pending.minimized.take() {
                    window.set_minimized(value);
                }
                if let Some((value, _)) = pending.maximized.take() {
                    window.set_maximized(value);
                }
                if let Some((value, _)) = pending.fullscreen.take() {
                    window
                        .set_fullscreen(value.then_some(tao::window::Fullscreen::Borderless(None)));
                }
                if intent.focus {
                    window.set_focus();
                }
                pending.deferred.clear();
            }
            pending.sent_visibility_seq = Some(intent.seq);
        }
        let version = shared
            .control
            .snapshot()
            .map_or(1, |snapshot| snapshot.version + 1);
        let snapshot = Self::snapshot(window, shared.control.hwnd(), version);
        drop(guard);
        if intent.seq != shared.control.applied_seq() {
            if snapshot.visible == intent.visible {
                shared.control.confirm(intent.seq, snapshot);
            } else {
                shared.control.update_snapshot(snapshot);
            }
        } else {
            shared.control.update_snapshot(snapshot);
        }
        for (operation, request_seq, error) in failures {
            Self::emit_retained(
                state,
                "window_command_failed",
                serde_json::json!({
                    "window_id": shared.window_id(),
                    "operation": operation,
                    "request_seq": request_seq,
                    "message": error,
                }),
            );
        }
        false
    }

    /// Create a new event handler
    pub fn new(state: Arc<Mutex<EventLoopState>>) -> Self {
        Self { state }
    }

    /// Handle window events and emit to Python callbacks
    pub fn handle_window_event(&self, event: WindowEvent) {
        match event {
            WindowEvent::CloseRequested => {
                tracing::info!("Close requested - emitting closing event");
                if let Ok(state) = self.state.lock() {
                    // Emit closing event before requesting exit
                    #[cfg(feature = "python-bindings")]
                    state.emit_window_event(WindowEventType::Closing, serde_json::json!({}));

                    state.request_exit();

                    // Emit closed event
                    #[cfg(feature = "python-bindings")]
                    state.emit_window_event(WindowEventType::Closed, serde_json::json!({}));
                }
            }
            WindowEvent::Resized(size) => {
                tracing::debug!("Window resized: {:?}", size);
                #[cfg(feature = "python-bindings")]
                if let Ok(state) = self.state.lock() {
                    state.emit_window_event(
                        WindowEventType::Resized,
                        serde_json::json!({
                            "width": size.width,
                            "height": size.height
                        }),
                    );
                }
            }
            WindowEvent::Moved(position) => {
                tracing::debug!("Window moved: {:?}", position);
                #[cfg(feature = "python-bindings")]
                if let Ok(state) = self.state.lock() {
                    state.emit_window_event(
                        WindowEventType::Moved,
                        serde_json::json!({
                            "x": position.x,
                            "y": position.y
                        }),
                    );
                }
            }
            WindowEvent::Focused(focused) => {
                tracing::debug!("Window focus changed: {}", focused);
                if let Ok(mut state) = self.state.lock() {
                    state.set_focused(focused);
                }
            }
            _ => {}
        }
    }

    /// Run the event loop (blocking)
    ///
    /// CRITICAL: Uses run_return() instead of run() to prevent process exit.
    /// The run() method calls std::process::exit() when the event loop exits,
    /// which would terminate the entire DCC application (Maya, Houdini, etc.).
    /// The run_return() method returns normally, allowing the DCC to continue running.
    ///
    /// # Arguments
    /// * `event_loop` - The event loop to run
    /// * `state` - The event loop state
    /// * `auto_show` - Whether to automatically show the window
    pub fn run_blocking(
        event_loop: EventLoop<UserEvent>,
        state: Arc<Mutex<EventLoopState>>,
        auto_show: bool,
    ) {
        Self::run_blocking_inner(event_loop, state, auto_show, None);
    }

    #[cfg(feature = "python-bindings")]
    pub fn run_blocking_retained(
        event_loop: EventLoop<UserEvent>,
        state: Arc<Mutex<EventLoopState>>,
        shared: Arc<RetainedShared>,
    ) {
        Self::run_blocking_inner(event_loop, state, false, Some(shared));
    }

    fn run_blocking_inner(
        mut event_loop: EventLoop<UserEvent>,
        state: Arc<Mutex<EventLoopState>>,
        auto_show: bool,
        #[cfg(feature = "python-bindings")] retained: Option<Arc<RetainedShared>>,
        #[cfg(not(feature = "python-bindings"))] _retained: Option<()>,
    ) {
        tracing::info!(
            "[WARNING] [run_blocking] Starting event loop (blocking mode with run_return, auto_show={})",
            auto_show
        );

        // Create event loop proxy and store it in state
        tracing::info!("[WARNING] [run_blocking] Creating event loop proxy...");
        let proxy = event_loop.create_proxy();

        #[cfg(feature = "python-bindings")]
        if let Some(shared) = &retained {
            shared.install_wake(proxy.clone());
            let hwnd = state.lock().ok().and_then(|guard| guard.get_hwnd());
            if let Some(hwnd) = hwnd {
                if let Ok(guard) = state.lock() {
                    if let Some(window) = &guard.window {
                        shared.control.ready(Self::snapshot(window, Some(hwnd), 1));
                    }
                }
            } else {
                shared
                    .control
                    .fail("retained native window has no HWND".into());
            }
        }

        tracing::info!("[WARNING] [run_blocking] Storing proxy in EventLoopState...");
        if let Ok(mut state_guard) = state.lock() {
            state_guard.set_event_loop_proxy(proxy.clone());
            tracing::info!("[OK] [run_blocking] Event loop proxy stored in EventLoopState");
        } else {
            tracing::error!("[ERROR] [run_blocking] Failed to lock state for storing proxy");
        }

        // Also store proxy in message queue for immediate wake-up
        tracing::info!("[WARNING] [run_blocking] Storing proxy in MessageQueue...");
        if let Ok(state_guard) = state.lock() {
            state_guard.message_queue.set_event_loop_proxy(proxy);
            tracing::info!("[OK] [run_blocking] Event loop proxy stored in MessageQueue");
        } else {
            tracing::error!(
                "[ERROR] [run_blocking] Failed to lock state for storing proxy in MessageQueue"
            );
        }

        // Only show window if auto_show is true
        if auto_show {
            tracing::info!("[WARNING] [run_blocking] Making window visible (auto_show=true)...");
            if let Ok(mut state_guard) = state.lock() {
                // First set visible to emit the event
                state_guard.set_visible(true);

                if let Some(window) = &state_guard.window {
                    window.set_visible(true);
                    tracing::info!("[OK] [run_blocking] Window is now visible");

                    // Re-apply Win32 window styles right after showing the window.
                    // On Windows 11, tao/wry may adjust styles at show-time.
                    #[cfg(target_os = "windows")]
                    {
                        if let (Some(hints), Some(hwnd)) =
                            (state_guard.window_style_hints, state_guard.get_hwnd())
                        {
                            use auroraview_core::builder::{
                                apply_frameless_popup_window_style, apply_tool_window_style,
                                disable_window_shadow, extend_frame_into_client_area,
                                optimize_transparent_window_resize, remove_clip_children_style,
                            };

                            if !hints.decorations {
                                let _ = apply_frameless_popup_window_style(hwnd as isize);
                            }

                            if hints.tool_window {
                                apply_tool_window_style(hwnd as isize);
                            }
                            if !hints.undecorated_shadow {
                                disable_window_shadow(hwnd as isize);
                            }
                            if hints.transparent {
                                remove_clip_children_style(hwnd as isize);
                                extend_frame_into_client_area(hwnd as isize);
                                optimize_transparent_window_resize(hwnd as isize);
                            }
                        }
                    }

                    // CRITICAL FIX: Request a redraw to wake up the event loop

                    // Without this, run_return() may hang on Windows waiting for the first event
                    window.request_redraw();
                    tracing::info!(
                        "[OK] [run_blocking] Requested window redraw to wake event loop"
                    );
                } else {
                    tracing::warn!("[WARNING] [run_blocking] Window is None");
                }
            } else {
                tracing::error!("[ERROR] [run_blocking] Failed to lock state for showing window");
            }
        } else {
            tracing::info!("[OK] [run_blocking] Window stays hidden (auto_show=false)");
            // Still request redraw to wake event loop
            if let Ok(state_guard) = state.lock() {
                if let Some(window) = &state_guard.window {
                    window.request_redraw();
                    tracing::info!(
                        "[OK] [run_blocking] Requested window redraw to wake event loop"
                    );
                }
            }
        }

        let state_clone = state.clone();
        #[cfg(feature = "python-bindings")]
        let mut pending = PendingWindowState::default();
        let exit_code = event_loop.run_return(move |event, _, control_flow| {
            // CRITICAL: Use Poll mode for WebView2 compatibility on Windows
            // WebView2 requires continuous message pump processing for:
            // - COM message handling
            // - IPC message processing
            // - JavaScript execution results
            // - Rendering updates
            // Poll mode ensures the Windows message loop runs continuously
            *control_flow = ControlFlow::Poll;

            #[cfg(feature = "python-bindings")]
            if let Some(shared) = &retained {
                if Self::process_retained(&state_clone, shared, &mut pending) {
                    *control_flow = ControlFlow::Exit;
                    return;
                }
            }

            match event {
                Event::UserEvent(UserEvent::ProcessMessages) => {
                    tracing::debug!("[EventLoop] Processing UserEvent::ProcessMessages");
                    let count = Self::process_queue_batch(
                        &state_clone,
                        #[cfg(feature = "python-bindings")]
                        retained.as_deref(),
                    );
                    if count > 0 {
                        tracing::debug!("[EventLoop] Processed {} messages via UserEvent", count);
                    }
                    if state_clone.lock().is_ok_and(|guard| guard.should_exit()) {
                        *control_flow = ControlFlow::Exit;
                    }
                }
                Event::UserEvent(UserEvent::CloseWindow) => {
                    #[cfg(feature = "python-bindings")]
                    if let Some(shared) = &retained {
                        shared.control.close();
                    }
                    tracing::info!("[CLOSE] [EventLoop] UserEvent::CloseWindow received");
                    tracing::info!("[CLOSE] [EventLoop] Requesting window close via event loop");

                    // Request exit through the state
                    if let Ok(state_guard) = state_clone.lock() {
                        state_guard.request_exit();

                        // Hide window immediately
                        if let Some(window) = &state_guard.window {
                            window.set_visible(false);
                            tracing::info!("[OK] [EventLoop] Window hidden");
                        }

                        // Set control flow to exit
                        *control_flow = ControlFlow::Exit;
                        tracing::info!("[OK] [EventLoop] Control flow set to Exit");
                    } else {
                        tracing::error!("[ERROR] [EventLoop] Failed to lock state for close");
                    }
                }
                Event::UserEvent(UserEvent::DragWindow) => {
                    tracing::debug!("[EventLoop] UserEvent::DragWindow received");
                    if let Ok(state_guard) = state_clone.lock() {
                        if let Some(window) = &state_guard.window {
                            if let Err(e) = window.drag_window() {
                                tracing::warn!("[EventLoop] Failed to start window drag: {:?}", e);
                            } else {
                                tracing::debug!("[EventLoop] Window drag started");
                            }
                        }
                    }
                }
                Event::UserEvent(UserEvent::PluginEvent { event, data }) => {
                    tracing::debug!("[EventLoop] UserEvent::PluginEvent received: {}", event);
                    if let Ok(state_guard) = state_clone.lock() {
                        if let Some(webview_arc) = &state_guard.webview {
                            if let Ok(webview) = webview_arc.lock() {
                                // data is already a JSON string, no escaping needed
                                let script = js_assets::build_emit_event_script(&event, &data);
                                if let Err(e) = webview.evaluate_script(&script) {
                                    tracing::error!("[EventLoop] Failed to emit plugin event '{}': {}", event, e);
                                }
                            }
                        }
                    }
                }
                Event::UserEvent(UserEvent::CreateChildWindow { url, width, height }) => {
                    tracing::info!("[EventLoop] UserEvent::CreateChildWindow received: {}", url);
                    #[cfg(target_os = "windows")]
                    {
                        // Create child window on the main thread
                        if let Err(e) = super::child_window::create_child_webview_window(&url, width, height) {
                            tracing::error!("[EventLoop] Failed to create child window: {}", e);
                        }
                    }
                    #[cfg(not(target_os = "windows"))]
                    {
                        // Suppress unused variable warnings on non-Windows platforms
                        let _ = (width, height);
                        // On non-Windows platforms, fall back to system browser
                        tracing::warn!("[EventLoop] Child window not supported on this platform, opening in browser");
                        if let Err(e) = open::that(&url) {
                            tracing::error!("[EventLoop] Failed to open URL in browser: {}", e);
                        }
                    }
                }
                Event::UserEvent(_) => {
                    // Handle other user events (TrayMenuClick, TrayIconClick, etc.) - currently no-op
                }
                Event::WindowEvent { event, .. } => {
                    tracing::debug!("Window event: {:?}", event);
                    #[cfg(feature = "python-bindings")]
                    if let Some(shared) = &retained {
                        if matches!(event, WindowEvent::CloseRequested | WindowEvent::Destroyed) {
                            shared.control.close();
                        }
                        if let Ok(guard) = state_clone.lock() {
                            if let Some(window) = &guard.window {
                                let version = shared.control.snapshot().map_or(1, |s| s.version + 1);
                                shared.control.update_snapshot(Self::snapshot(window, shared.control.hwnd(), version));
                            }
                        }
                        if matches!(event, WindowEvent::CloseRequested | WindowEvent::Destroyed) {
                            *control_flow = ControlFlow::Exit;
                        }
                        return;
                    }
                    let handler = WebViewEventHandler::new(state_clone.clone());
                    handler.handle_window_event(event);

                    // Check if we should exit after handling the event
                    if let Ok(state_guard) = state_clone.lock() {
                        if state_guard.should_exit() {
                            tracing::info!("Window close requested, hiding window and exiting event loop");
                            // Hide the window before exiting to prevent visual artifacts
                            if let Some(window) = &state_guard.window {
                                window.set_visible(false);
                                tracing::info!("Window hidden");
                            }
                            *control_flow = ControlFlow::Exit;
                            tracing::info!("Control flow set to Exit");
                        }
                    }
                }
                Event::MainEventsCleared => {
                    // CRITICAL: Explicitly pump Windows messages for WebView2
                    // tao's run_return() may not process all Windows messages that
                    // WebView2 needs for proper rendering and COM message handling.
                    // This ensures the WebView2 message pump stays active.
                    //
                    // OPTIMIZATION: Only process messages for the WebView window (not all thread messages)
                    // This prevents interfering with DCC host application's message pump.
                    #[cfg(target_os = "windows")]
                    {
                        use super::message_pump;

                        // Get the window HWND for targeted message processing
                        // CRITICAL: Release the lock BEFORE calling process_messages_for_hwnd
                        // because DestroyWindow may trigger WM_DESTROY which could cause deadlock
                        let (hwnd_opt, should_exit_arc) = {
                            if let Ok(state_guard) = state_clone.lock() {
                                (state_guard.get_hwnd(), state_guard.should_exit.clone())
                            } else {
                                (None, Arc::new(AtomicBool::new(false)))
                            }
                        };

                        if let Some(hwnd) = hwnd_opt {
                            // Process only this window's messages (isolated from DCC main thread)
                            // CRITICAL: Check return value for close intent
                            #[cfg(feature = "python-bindings")]
                            let should_close = if retained.is_some() {
                                message_pump::process_retained_messages_for_hwnd(hwnd);
                                retained.as_ref().is_some_and(|shared| shared.control.intent().close)
                            } else {
                                message_pump::process_messages_for_hwnd(hwnd)
                            };
                            #[cfg(not(feature = "python-bindings"))]
                            let should_close = message_pump::process_messages_for_hwnd(hwnd);
                            if should_close {
                                tracing::info!("[EventLoop] Close detected from message pump, requesting exit");
                                // Set exit flag directly using AtomicBool (lock-free)
                                should_exit_arc.store(true, Ordering::SeqCst);
                            }
                        } else {
                            // Fallback: If HWND not available, use limited global processing
                            // This should rarely happen (only during initialization)
                            tracing::trace!("[event_loop] HWND not available, using fallback message pump");
                            let _ = message_pump::process_all_messages_limited(100);
                        }
                    }

                    // Process pending messages from the queue
                    let count = Self::process_queue_batch(
                        &state_clone,
                        #[cfg(feature = "python-bindings")]
                        retained.as_deref(),
                    );
                    if count > 0 {
                        tracing::debug!("Processed {} messages in MainEventsCleared", count);
                    }
                    if state_clone.lock().is_ok_and(|guard| guard.should_exit()) {
                        tracing::info!("Exit requested in MainEventsCleared, exiting event loop gracefully");
                        *control_flow = ControlFlow::Exit;
                    }

                    // In Poll mode, add a small sleep to reduce CPU usage
                    // This is a workaround for WebView2 compatibility - we need Poll mode
                    // for WebView2 message pump, but pure polling uses 100% CPU
                    // 2ms sleep gives us ~500 iterations/second which is plenty for UI
                    std::thread::sleep(std::time::Duration::from_millis(2));
                }
                Event::LoopDestroyed => {
                    tracing::info!("Event loop destroyed");
                }
                _ => {}
            }
        });

        tracing::info!("Event loop exited with code: {}", exit_code);
    }

    /// Process events once (non-blocking) for embedded mode
    ///
    /// This method processes pending window events without blocking.
    /// It should be called periodically (e.g., from a timer) to keep the window responsive.
    ///
    /// Returns true if the window should be closed, false otherwise.
    #[allow(dead_code)]
    pub fn poll_events_once(
        event_loop: &mut EventLoop<UserEvent>,
        state: Arc<Mutex<EventLoopState>>,
    ) -> bool {
        use tao::event_loop::ControlFlow;

        let should_close = false;
        let state_clone = state.clone();

        // Process events with ControlFlow::Poll (non-blocking)
        event_loop.run_return(move |event, _, control_flow| {
            *control_flow = ControlFlow::Poll; // Non-blocking mode

            match event {
                Event::UserEvent(UserEvent::ProcessMessages) => {
                    tracing::debug!("[OK] [poll_events_once] Processing messages");
                    Self::process_queue_batch(
                        &state_clone,
                        #[cfg(feature = "python-bindings")]
                        None,
                    );
                }
                Event::WindowEvent { event, .. } => {
                    tracing::debug!("[OK] [poll_events_once] Window event: {:?}", event);
                    let handler = WebViewEventHandler::new(state_clone.clone());
                    handler.handle_window_event(event);

                    // Check if we should exit
                    if let Ok(state_guard) = state_clone.lock() {
                        if state_guard.should_exit() {
                            tracing::info!("[OK] [poll_events_once] Window close requested");
                            *control_flow = ControlFlow::Exit;
                        }
                    }
                }
                Event::UserEvent(UserEvent::CloseWindow) => {
                    tracing::info!("[OK] [poll_events_once] CloseWindow user event received");
                    if let Ok(state_guard) = state_clone.lock() {
                        state_guard.request_exit();
                    }
                    *control_flow = ControlFlow::Exit;
                }
                Event::MainEventsCleared => {
                    // Exit immediately after processing all events (non-blocking)
                    *control_flow = ControlFlow::Exit;
                }
                _ => {}
            }
        });

        should_close
    }
}
