//! WebViewInner - Core WebView implementation
//!
//! This module contains the internal WebView structure and core operations.

use pyo3::prelude::*;
use std::sync::{Arc, Mutex};
use wry::WebView as WryWebView;

#[cfg(target_os = "windows")]
use super::backend::PyBindingsBackend;
use super::config::WebViewConfig;
use super::event_loop::{EventLoopState, UserEvent, WebViewEventHandler, WindowStyleHints};
use super::js_assets;
use super::lifecycle::LifecycleManager;
use super::message_pump;
use super::standalone;
#[cfg(target_os = "windows")]
use super::window_control::RetainedShared;
use crate::ipc::{IpcHandler, MessageQueue};

/// Internal WebView structure - supports both standalone and embedded modes
pub struct WebViewInner {
    pub(crate) webview: Arc<Mutex<WryWebView>>,
    // For standalone mode only
    #[allow(dead_code)]
    pub(crate) window: Option<tao::window::Window>,
    #[allow(dead_code)]
    pub(crate) event_loop: Option<tao::event_loop::EventLoop<UserEvent>>,
    /// Message queue for thread-safe communication
    pub(crate) message_queue: Arc<MessageQueue>,
    /// Event loop proxy for sending close events (standalone mode only)
    pub(crate) event_loop_proxy: Option<tao::event_loop::EventLoopProxy<UserEvent>>,
    /// Cross-platform lifecycle manager
    pub(crate) lifecycle: Arc<LifecycleManager>,
    /// Whether to auto-show the window (false in headless mode)
    #[allow(dead_code)]
    pub(crate) auto_show: bool,
    /// Backend instance for DCC mode - MUST be kept alive to prevent window destruction
    #[allow(dead_code)]
    #[cfg(target_os = "windows")]
    pub(crate) backend: Option<Box<super::backend::native::NativeBackend>>,
    /// Cached HWND value (Windows only)
    /// This is cached because the window may be moved during event loop execution
    #[cfg(target_os = "windows")]
    pub(crate) cached_hwnd: Option<u64>,

    /// Hints used to re-apply Win32 window styles right after showing the window.
    pub(crate) window_style_hints: Option<WindowStyleHints>,
}

impl Drop for WebViewInner {
    fn drop(&mut self) {
        use scopeguard::defer;

        defer! {
            tracing::warn!("[DROP] [WebViewInner::drop] Cleanup completed");
        }

        tracing::warn!("========================================");
        tracing::warn!("[DROP] WebViewInner is being dropped!");
        tracing::warn!("========================================");
        tracing::info!("[CLOSE] [WebViewInner::drop] Cleaning up WebView resources");

        // Execute lifecycle cleanup handlers
        self.lifecycle.execute_cleanup();

        // Close the window if it exists
        if let Some(window) = self.window.take() {
            tracing::info!("[CLOSE] [WebViewInner::drop] Setting window invisible");
            window.set_visible(false);

            // On Windows, explicitly destroy the window and process cleanup messages
            #[cfg(target_os = "windows")]
            {
                use raw_window_handle::{HasWindowHandle, RawWindowHandle};
                use std::ffi::c_void;
                use windows::Win32::Foundation::HWND;
                use windows::Win32::UI::WindowsAndMessaging::{
                    DestroyWindow, DispatchMessageW, PeekMessageW, TranslateMessage, MSG,
                    PM_REMOVE, WM_DESTROY, WM_NCDESTROY,
                };

                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd_value = handle.hwnd.get();
                        let hwnd = HWND(hwnd_value as *mut c_void);

                        tracing::info!(
                            "[CLOSE] [WebViewInner::drop] Calling DestroyWindow on HWND: {:?}",
                            hwnd
                        );
                        unsafe {
                            let result = DestroyWindow(hwnd);
                            if result.is_ok() {
                                tracing::info!("[OK] [WebViewInner::drop] DestroyWindow succeeded");

                                // Process pending messages to ensure proper cleanup
                                tracing::info!(
                                    "[CLOSE] [WebViewInner::drop] Processing pending window messages..."
                                );
                                let mut msg = MSG::default();
                                let mut processed_count = 0;
                                let max_iterations = 100;

                                while processed_count < max_iterations
                                    && PeekMessageW(&mut msg, Some(hwnd), 0, 0, PM_REMOVE).as_bool()
                                {
                                    processed_count += 1;

                                    if msg.message == WM_DESTROY {
                                        tracing::info!(
                                            "[CLOSE] [WebViewInner::drop] Processing WM_DESTROY"
                                        );
                                    } else if msg.message == WM_NCDESTROY {
                                        tracing::info!(
                                            "[CLOSE] [WebViewInner::drop] Processing WM_NCDESTROY"
                                        );
                                    }

                                    let _ = TranslateMessage(&msg);
                                    DispatchMessageW(&msg);
                                }

                                tracing::info!(
                                    "[OK] [WebViewInner::drop] Processed {} messages",
                                    processed_count
                                );

                                // Small delay to ensure window disappears
                                std::thread::sleep(std::time::Duration::from_millis(50));
                            } else {
                                tracing::warn!(
                                    "[WARNING] [WebViewInner::drop] DestroyWindow failed: {:?}",
                                    result
                                );
                            }
                        }
                    }
                }
            }
        }

        // Drop the event loop (this will clean up any associated resources)
        if let Some(_event_loop) = self.event_loop.take() {
            tracing::info!("[CLOSE] [WebViewInner::drop] Event loop dropped");
        }
    }
}

impl WebViewInner {
    /// Create standalone WebView with its own window
    pub fn create_standalone(
        config: WebViewConfig,
        ipc_handler: Arc<IpcHandler>,
        message_queue: Arc<MessageQueue>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        standalone::create_desktop(config, ipc_handler, message_queue)
    }

    /// Create embedded WebView for external window integration
    ///
    /// This method creates a WebView that integrates with external applications
    /// (such as DCC applications like Maya, 3ds Max, etc.) by embedding into
    /// their window hierarchy instead of creating its own event loop.
    ///
    /// # Arguments
    /// * `parent_hwnd` - HWND of the parent/owner window
    /// * `config` - WebView configuration
    /// * `ipc_handler` - IPC message handler
    /// * `message_queue` - Message queue for cross-thread communication
    /// * `on_created` - Optional callback invoked when WebView2 HWND is created
    ///
    /// # Returns
    /// A WebViewInner instance without an event loop
    #[cfg(target_os = "windows")]
    pub fn create_embedded(
        parent_hwnd: u64,
        config: WebViewConfig,
        ipc_handler: Arc<IpcHandler>,
        message_queue: Arc<MessageQueue>,
        on_created: Option<Box<dyn Fn(u64) + Send + Sync>>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        use super::backend::native::NativeBackend;
        use super::backend::PyBindingsBackend;

        // Create backend using embedded mode
        let backend = NativeBackend::create_embedded(
            parent_hwnd,
            config.clone(),
            ipc_handler,
            message_queue.clone(),
            on_created,
        )?;

        // Extract webview reference (but keep backend alive!)
        let webview = backend.webview();

        // Cache HWND from backend
        let cached_hwnd = backend.native_handle();

        tracing::info!(
            "[OK] [create_embedded] Keeping backend alive to prevent window destruction"
        );
        tracing::info!(
            "[OK] [create_embedded] process_events() will delegate to backend.process_events()"
        );

        let window_style_hints = Some(WindowStyleHints {
            #[cfg(target_os = "windows")]
            decorations: config.decorations,
            #[cfg(target_os = "windows")]
            tool_window: config.tool_window,
            #[cfg(target_os = "windows")]
            undecorated_shadow: config.undecorated_shadow,
            #[cfg(target_os = "windows")]
            transparent: config.transparent,
        });

        Ok(Self {
            webview,
            window: None,     // Window is owned by backend
            event_loop: None, // Event loop is owned by backend
            message_queue,
            event_loop_proxy: None,
            lifecycle: Arc::new(LifecycleManager::new()),
            auto_show: true, // Embedded mode: visibility controlled by host
            backend: Some(Box::new(backend)), // CRITICAL: Keep backend alive!
            cached_hwnd,
            window_style_hints,
        })
    }

    /// Create embedded WebView (non-Windows platforms)
    #[cfg(not(target_os = "windows"))]
    #[allow(dead_code)]
    pub fn create_embedded(
        _parent_hwnd: u64,
        _config: WebViewConfig,
        _ipc_handler: Arc<IpcHandler>,
        _message_queue: Arc<MessageQueue>,
        _on_created: Option<Box<dyn Fn(u64) + Send + Sync>>,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        Err("Embedded mode is only supported on Windows".into())
    }

    /// Process messages for DCC integration mode
    ///
    /// This method should be called periodically from a Qt timer to process
    /// WebView messages without running a dedicated event loop.
    ///
    /// # Returns
    /// `true` if the window should be closed, `false` otherwise
    pub fn process_messages(&self) -> bool {
        // Process Windows messages for this window
        #[cfg(target_os = "windows")]
        {
            use raw_window_handle::{HasWindowHandle, RawWindowHandle};

            if let Some(window) = &self.window {
                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd = handle.hwnd.get() as u64;
                        let should_quit = message_pump::process_messages_for_hwnd(hwnd);

                        // Process message queue
                        if let Ok(webview) = self.webview.lock() {
                            self.message_queue.process_all(|message| {
                                use crate::ipc::WebViewMessage;
                                match message {
                                    WebViewMessage::EvalJs(script) => {
                                        if let Err(e) = webview.evaluate_script(&script) {
                                            tracing::error!("Failed to execute JavaScript: {}", e);
                                        }
                                    }
                                    WebViewMessage::EmitEvent { event_name, data } => {
                                        // JSON is already valid JavaScript literal, no escaping needed
                                        let json_str = data.to_string();
                                        let script = js_assets::build_emit_event_script(
                                            &event_name,
                                            &json_str,
                                        );
                                        if let Err(e) = webview.evaluate_script(&script) {
                                            tracing::error!("Failed to emit event: {}", e);
                                        }
                                    }
                                    WebViewMessage::LoadUrl(url) => {
                                        let script = js_assets::build_load_url_script(&url);
                                        if let Err(e) = webview.evaluate_script(&script) {
                                            tracing::error!("Failed to load URL: {}", e);
                                        }
                                    }
                                    WebViewMessage::LoadHtml(html) => {
                                        if let Err(e) = webview.load_html(&html) {
                                            tracing::error!("Failed to load HTML: {}", e);
                                        }
                                    }
                                    WebViewMessage::WindowEvent { event_type, data } => {
                                        // Window events are handled by emitting to JavaScript
                                        let event_name = event_type.as_str();
                                        // JSON is already valid JavaScript literal, no escaping needed
                                        let json_str = data.to_string();
                                        let script = js_assets::build_emit_event_script(
                                            event_name, &json_str,
                                        );
                                        tracing::debug!(
                                            "[WINDOW_EVENT] Emitting window event: {}",
                                            event_name
                                        );
                                        if let Err(e) = webview.evaluate_script(&script) {
                                            tracing::error!("Failed to emit window event: {}", e);
                                        }
                                    }
                                    WebViewMessage::SetVisible(_) => {
                                        // SetVisible is handled at window level, not webview level
                                        // This is a no-op here
                                    }
                                    WebViewMessage::EvalJsAsync {
                                        script,
                                        callback_id,
                                    } => {
                                        // Execute JavaScript and send result back via IPC
                                        let async_script = js_assets::build_eval_js_async_script(
                                            &script,
                                            callback_id,
                                        );
                                        if let Err(e) = webview.evaluate_script(&async_script) {
                                            tracing::error!(
                                                "Failed to execute async JavaScript (id={}): {}",
                                                callback_id,
                                                e
                                            );
                                        }
                                    }
                                    WebViewMessage::Reload => {
                                        if let Err(e) = webview.evaluate_script("location.reload()")
                                        {
                                            tracing::error!("Failed to reload: {}", e);
                                        }
                                    }
                                    WebViewMessage::StopLoading => {
                                        if let Err(e) = webview.evaluate_script("window.stop()") {
                                            tracing::error!("Failed to stop loading: {}", e);
                                        }
                                    }
                                    WebViewMessage::Close => {
                                        // Close is handled at event loop level
                                        tracing::info!("[WebViewInner] Close message received");
                                    }
                                }
                            });
                        }

                        should_quit
                    } else {
                        false
                    }
                } else {
                    false
                }
            } else {
                false
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            false
        }
    }

    /// Get the current URL
    pub fn get_url(&self) -> Result<String, Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            Ok(webview.url()?.to_string())
        } else {
            Err("Failed to lock webview".into())
        }
    }

    /// Load a URL
    pub fn load_url(&mut self, url: &str) -> Result<(), Box<dyn std::error::Error>> {
        let script = js_assets::build_load_url_script(url);
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(&script)?;
        }
        Ok(())
    }

    /// Load HTML content
    pub fn load_html(&mut self, html: &str) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.load_html(html)?;
        }
        Ok(())
    }

    /// Execute JavaScript
    #[allow(dead_code)]
    pub fn eval_js(&mut self, script: &str) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(script)?;
        }
        Ok(())
    }

    /// Emit an event to JavaScript
    #[allow(dead_code)]
    pub fn emit(
        &mut self,
        event_name: &str,
        data: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error>> {
        // Mark events emitted from Python to avoid being re-forwarded by the bridge (feedback loop)
        let script = format!(
            "window.dispatchEvent(new CustomEvent('{}', {{ detail: Object.assign({{}}, {{__aurora_from_python: true}}, {}) }}))",
            event_name, data
        );
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(&script)?;
        }
        Ok(())
    }

    /// Run the event loop (standalone mode only)
    #[allow(dead_code)]
    pub fn run_event_loop(&mut self, _py: Python) -> PyResult<()> {
        use tao::event_loop::ControlFlow;

        // Show the window
        if let Some(window) = &self.window {
            tracing::info!("Setting window visible");
            window.set_visible(true);
            tracing::info!("Window is now visible");
        }

        // Get the event loop
        if let Some(event_loop) = self.event_loop.take() {
            tracing::info!("Starting event loop");

            // Run the event loop - this will block until the window is closed
            // Note: This is a blocking call that will not return until the user closes the window
            event_loop.run(move |event, _, control_flow| {
                *control_flow = ControlFlow::Wait;

                match event {
                    tao::event::Event::WindowEvent {
                        event: tao::event::WindowEvent::CloseRequested,
                        ..
                    } => {
                        tracing::info!("Close requested");
                        *control_flow = ControlFlow::Exit;
                    }
                    tao::event::Event::WindowEvent {
                        event: tao::event::WindowEvent::Resized(_),
                        ..
                    } => {
                        // Handle window resize
                    }
                    _ => {}
                }
            });

            // This code is unreachable because event_loop.run() never returns
            #[allow(unreachable_code)]
            Ok(())
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "Event loop not available (embedded mode?)",
            ))
        }
    }

    /// Run the event loop without Python GIL (blocking version)
    /// Uses improved event loop handling with better state management
    pub fn run_event_loop_blocking(&mut self) {
        tracing::info!("=== run_event_loop_blocking called (improved version) ===");

        // Validate prerequisites
        if self.window.is_none() {
            tracing::error!("Window is None!");
            return;
        }

        if self.event_loop.is_none() {
            tracing::error!("Event loop is None!");
            return;
        }

        // Take ownership of event loop and window
        let event_loop = match self.event_loop.take() {
            Some(el) => el,
            None => {
                tracing::error!("Failed to take event loop");
                return;
            }
        };

        let window = match self.window.take() {
            Some(w) => w,
            None => {
                tracing::error!("Failed to take window");
                return;
            }
        };

        // Get the webview from Arc<Mutex<>>
        // We need to lock it to get a reference
        let webview_guard = match self.webview.lock() {
            Ok(guard) => guard,
            Err(e) => {
                tracing::error!("Failed to lock webview: {:?}", e);
                return;
            }
        };

        // We can't move the webview out of the Arc<Mutex<>>, so we need to
        // restructure this. Let's just pass None for now and fix the architecture later.
        drop(webview_guard);

        // TEMPORARY FIX: Create state without webview
        // TODO: Refactor EventLoopState to accept Arc<Mutex<WryWebView>>
        tracing::warn!("Creating EventLoopState without webview - this needs architectural fix");

        #[allow(clippy::arc_with_non_send_sync)]
        let state = Arc::new(Mutex::new(EventLoopState::new_without_webview(
            window,
            self.message_queue.clone(),
        )));

        // Store webview reference + style hints in state after creation
        if let Ok(mut state_guard) = state.lock() {
            state_guard.set_webview(self.webview.clone());
            state_guard.set_window_style_hints(self.window_style_hints);
        }

        // Run the improved event loop
        // ALWAYS show window when run_event_loop_blocking is explicitly called
        // The auto_show config only controls automatic showing after create()
        // When show() is explicitly called, the window should always be visible
        WebViewEventHandler::run_blocking(event_loop, state, true);

        tracing::info!("Event loop exited");
    }

    /// Run a retained window while its owner keeps all native state local.
    #[cfg(target_os = "windows")]
    pub fn run_event_loop_retained(
        &mut self,
        shared: Arc<RetainedShared>,
        handler: Arc<IpcHandler>,
    ) {
        let (Some(event_loop), Some(window)) = (self.event_loop.take(), self.window.take()) else {
            shared
                .control
                .fail("retained native window was not created".into());
            return;
        };
        #[allow(clippy::arc_with_non_send_sync)]
        let state = Arc::new(Mutex::new(EventLoopState::new_without_webview(
            window,
            self.message_queue.clone(),
        )));
        if let Ok(mut guard) = state.lock() {
            guard.set_webview(self.webview.clone());
            guard.set_window_style_hints(self.window_style_hints);
            guard.set_ipc_handler(handler);
        }
        WebViewEventHandler::run_blocking_retained(event_loop, state, shared);
    }
    /// Set whether the window should always be on top of other windows.
    ///
    /// # Arguments
    /// * `always_on_top` - If true, the window will stay on top of other windows
    ///
    /// # Platform-specific behavior
    /// - Windows: Uses SetWindowPos with HWND_TOPMOST/HWND_NOTOPMOST
    /// - macOS/Linux: Uses tao's set_always_on_top method
    pub fn set_always_on_top(&self, always_on_top: bool) {
        if let Some(window) = &self.window {
            #[cfg(target_os = "windows")]
            {
                use raw_window_handle::{HasWindowHandle, RawWindowHandle};
                use std::ffi::c_void;

                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd = handle.hwnd.get() as *mut c_void;
                        let insert_after = if always_on_top {
                            -1isize as *mut c_void // HWND_TOPMOST
                        } else {
                            -2isize as *mut c_void // HWND_NOTOPMOST
                        };
                        const SWP_NOMOVE: u32 = 0x0002;
                        const SWP_NOSIZE: u32 = 0x0001;
                        const SWP_NOACTIVATE: u32 = 0x0010;

                        #[link(name = "user32")]
                        extern "system" {
                            fn SetWindowPos(
                                hwnd: *mut c_void,
                                insert_after: *mut c_void,
                                x: i32,
                                y: i32,
                                cx: i32,
                                cy: i32,
                                flags: u32,
                            ) -> i32;
                        }

                        unsafe {
                            let result = SetWindowPos(
                                hwnd,
                                insert_after,
                                0,
                                0,
                                0,
                                0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                            );

                            if result != 0 {
                                tracing::debug!(
                                    "[OK] [set_always_on_top] Window always_on_top set to {}",
                                    always_on_top
                                );
                            } else {
                                tracing::error!(
                                    "[ERROR] [set_always_on_top] Failed to set always_on_top to {}",
                                    always_on_top
                                );
                            }
                        }
                    }
                }
            }

            #[cfg(not(target_os = "windows"))]
            {
                window.set_always_on_top(always_on_top);
                tracing::debug!(
                    "[OK] [set_always_on_top] Window always_on_top set to {}",
                    always_on_top
                );
            }
        } else {
            tracing::warn!("[WARNING] [set_always_on_top] No window available");
        }
    }

    /// Get window handle (HWND on Windows)
    ///
    /// Returns the native window handle for the WebView window.
    /// On Windows, this is the HWND value as a u64.
    ///
    /// # Returns
    /// - `Some(hwnd)` - Window handle on Windows
    /// - `None` - No window available or not on Windows
    ///
    /// # Example
    /// ```ignore
    /// let hwnd = webview_inner.get_hwnd();
    /// if let Some(hwnd) = hwnd {
    ///     println!("Window HWND: 0x{:x}", hwnd);
    /// }
    /// ```
    pub fn get_hwnd(&self) -> Option<u64> {
        #[cfg(target_os = "windows")]
        {
            use raw_window_handle::{HasWindowHandle, RawWindowHandle};

            // First check cached HWND (set during window creation)
            if let Some(hwnd) = self.cached_hwnd {
                tracing::debug!(
                    "[WebViewInner::get_hwnd] Returning cached HWND: 0x{:x}",
                    hwnd
                );
                return Some(hwnd);
            }

            // Try to get HWND from self.window (standalone mode)
            if let Some(window) = &self.window {
                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd_value = handle.hwnd.get() as u64;
                        tracing::debug!(
                            "[WebViewInner::get_hwnd] Returning window HWND: 0x{:x}",
                            hwnd_value
                        );
                        return Some(hwnd_value);
                    }
                }
            }

            // If self.window is None, try to get HWND from backend (DCC mode)
            if let Some(backend) = &self.backend {
                if let Some(window) = backend.window() {
                    if let Ok(window_handle) = window.window_handle() {
                        let raw_handle = window_handle.as_raw();
                        if let RawWindowHandle::Win32(handle) = raw_handle {
                            let hwnd_value = handle.hwnd.get() as u64;
                            tracing::debug!(
                                "[WebViewInner::get_hwnd] Returning backend HWND: 0x{:x}",
                                hwnd_value
                            );
                            return Some(hwnd_value);
                        }
                    }
                }
            }

            tracing::debug!("[WebViewInner::get_hwnd] No HWND found, returning None");
        }

        #[cfg(not(target_os = "windows"))]
        {
            // Not supported on non-Windows platforms
        }

        None
    }

    /// Check if the window is still valid (Windows only)
    ///
    /// This method checks if the window handle is still valid.
    /// Useful for detecting when a window has been closed externally.
    ///
    /// Returns true if the window is valid, false otherwise.
    #[allow(dead_code)] // Part of BOM API, exposed to Python bindings
    pub fn is_window_valid(&self) -> bool {
        #[cfg(target_os = "windows")]
        {
            use raw_window_handle::{HasWindowHandle, RawWindowHandle};

            if let Some(window) = &self.window {
                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd_value = handle.hwnd.get() as u64;
                        return message_pump::is_window_valid(hwnd_value);
                    }
                }
            }
            false
        }

        #[cfg(not(target_os = "windows"))]
        {
            // On non-Windows platforms, assume window is valid if it exists
            self.window.is_some()
        }
    }

    /// Get the current lifecycle state
    ///
    /// Returns the current lifecycle state of the WebView.
    /// This is useful for checking if the WebView is ready for operations.
    pub fn lifecycle_state(&self) -> super::lifecycle::LifecycleState {
        self.lifecycle.state()
    }

    /// Process pending window messages (for embedded mode)
    ///
    /// This method processes all pending Windows messages without blocking.
    /// It should be called periodically (e.g., from a Maya timer) to keep
    /// the window responsive in embedded mode.
    ///
    /// Returns true if the window should be closed, false otherwise.
    pub fn process_events(&self) -> bool {
        use crate::webview::lifecycle::LifecycleState;
        use scopeguard::defer;

        defer! {
            tracing::trace!("[process_events] tick completed");
        }

        // Check lifecycle state first
        match self.lifecycle.state() {
            LifecycleState::Destroyed => {
                tracing::warn!("[process_events] Window already destroyed");
                return true;
            }
            LifecycleState::CloseRequested | LifecycleState::Destroying => {
                tracing::info!("[process_events] Close already in progress");
                return true;
            }
            _ => {}
        }

        // Check for close signal from lifecycle manager
        if let Some(reason) = self.lifecycle.check_close_requested() {
            tracing::info!(
                "[process_events] Close requested via lifecycle: {:?}",
                reason
            );
            return true;
        }

        // CRITICAL: If backend exists (DCC mode), delegate to backend.process_events()
        // This ensures Windows messages are processed even when self.window is None
        #[cfg(target_os = "windows")]
        if let Some(backend) = &self.backend {
            use super::backend::ProcessResult;
            tracing::trace!("[process_events] Delegating to backend.process_events()");
            return matches!(backend.process_events(), ProcessResult::CloseRequested);
        }

        // Get the window HWND for targeted message processing
        #[cfg(target_os = "windows")]
        let hwnd = {
            use raw_window_handle::{HasWindowHandle, RawWindowHandle};

            if let Some(window) = &self.window {
                if let Ok(window_handle) = window.window_handle() {
                    let raw_handle = window_handle.as_raw();
                    if let RawWindowHandle::Win32(handle) = raw_handle {
                        let hwnd_value = handle.hwnd.get() as u64;
                        Some(hwnd_value)
                    } else {
                        None
                    }
                } else {
                    None
                }
            } else {
                None
            }
        };

        #[cfg(not(target_os = "windows"))]
        let hwnd: Option<u64> = None;

        // Process Windows messages with specific HWND if available
        let should_quit = if let Some(hwnd_value) = hwnd {
            let b1 = message_pump::process_messages_for_hwnd(hwnd_value);
            // Also service child/IPC windows (e.g., WebView2) in the same thread.
            // Use full-thread scan on Windows to ensure we don't miss SC_CLOSE/WM_CLOSE.
            #[cfg(target_os = "windows")]
            let b2 = message_pump::process_all_messages();
            #[cfg(not(target_os = "windows"))]
            let b2 = message_pump::process_all_messages_limited(1024);
            b1 || b2
        } else {
            // If we don't yet have a window handle, don't pull host messages.
            false
        };

        if should_quit {
            tracing::debug!(
                "[process_events] should_quit=true; close signal detected; returning to Python"
            );
            return true;
        }

        // Process message queue using unified message processor
        tracing::trace!("[process_events] processing queue");
        let (_count, close_requested) = super::message_processor::process_message_queue(
            &self.webview,
            &self.message_queue,
            "process_events",
        );

        if close_requested {
            tracing::info!("[process_events] Close message received, requesting close");
            let _ = self
                .lifecycle
                .request_close(crate::webview::lifecycle::CloseReason::AppRequest);

            // Best-effort: post WM_CLOSE so the host/native pump can destroy the window.
            #[cfg(target_os = "windows")]
            {
                use std::ffi::c_void;
                use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
                use windows::Win32::UI::WindowsAndMessaging::{PostMessageW, WM_CLOSE};

                if let Some(hwnd_value) = self.get_hwnd() {
                    let hwnd = HWND(hwnd_value as *mut c_void);
                    unsafe {
                        let _ = PostMessageW(Some(hwnd), WM_CLOSE, WPARAM(0), LPARAM(0));
                    }
                }
            }

            return true;
        }

        tracing::trace!("[process_events] end");

        false
    }

    /// Process only internal IPC/messages without touching the host's
    /// native message loop.
    ///
    /// This is intended for host-driven embedding scenarios (Qt, DCC, etc.)
    /// where the parent application owns the Win32/OS event loop and is
    /// responsible for pumping window messages. We only:
    ///   * honor lifecycle close requests, and
    ///   * drain the WebView message queue (JS <-> Python IPC).
    ///
    /// Returns true if the window should be closed, false otherwise.
    pub fn process_ipc_only(&self) -> bool {
        use crate::webview::lifecycle::LifecycleState;
        use scopeguard::defer;

        defer! {
            tracing::trace!("[process_ipc_only] tick completed");
        }

        // Check lifecycle state first
        match self.lifecycle.state() {
            LifecycleState::Destroyed => {
                tracing::warn!("[process_ipc_only] Window already destroyed");
                return true;
            }
            LifecycleState::CloseRequested | LifecycleState::Destroying => {
                tracing::info!("[process_ipc_only] Close already in progress");
                return true;
            }
            _ => {}
        }

        // Check for close signal from lifecycle manager
        if let Some(reason) = self.lifecycle.check_close_requested() {
            tracing::info!(
                "[process_ipc_only] Close requested via lifecycle: {:?}",
                reason
            );
            return true;
        }

        // Process message queue using unified message processor
        // (same semantics as process_events but without driving any native message pump)
        tracing::trace!("[process_ipc_only] processing queue");
        let (_count, close_requested) = super::message_processor::process_message_queue(
            &self.webview,
            &self.message_queue,
            "process_ipc_only",
        );

        if close_requested {
            tracing::info!("[process_ipc_only] Close message received, requesting close");
            let _ = self
                .lifecycle
                .request_close(crate::webview::lifecycle::CloseReason::AppRequest);

            // In IPC-only mode we do not own the message pump, but posting WM_CLOSE
            // allows the host (Qt/DCC) to process the close on its own loop.
            #[cfg(target_os = "windows")]
            {
                use std::ffi::c_void;
                use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
                use windows::Win32::UI::WindowsAndMessaging::{PostMessageW, WM_CLOSE};

                if let Some(hwnd_value) = self.get_hwnd() {
                    let hwnd = HWND(hwnd_value as *mut c_void);
                    unsafe {
                        let _ = PostMessageW(Some(hwnd), WM_CLOSE, WPARAM(0), LPARAM(0));
                    }
                }
            }

            return true;
        }

        tracing::trace!("[process_ipc_only] end");

        false
    }

    // ========================================
    // BOM Navigation APIs
    // ========================================

    /// Navigate back in history (like browser back button)
    pub fn go_back(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(auroraview_core::bom::js::GO_BACK)?;
            tracing::debug!("[BOM] go_back() executed");
        }
        Ok(())
    }

    /// Navigate forward in history (like browser forward button)
    pub fn go_forward(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(auroraview_core::bom::js::GO_FORWARD)?;
            tracing::debug!("[BOM] go_forward() executed");
        }
        Ok(())
    }

    /// Stop loading current page
    pub fn stop(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(auroraview_core::bom::js::STOP)?;
            tracing::debug!("[BOM] stop() executed");
        }
        Ok(())
    }

    /// Check if can navigate back in history
    /// Note: This is a synchronous check based on history.length
    pub fn can_go_back(&self) -> Result<bool, Box<dyn std::error::Error>> {
        // Use history.length > 1 as a heuristic
        // A more accurate check would require async JS evaluation
        if let Ok(webview) = self.webview.lock() {
            // Execute script that stores result in a known location
            webview.evaluate_script("window.__auroraview_can_go_back = history.length > 1;")?;
            tracing::debug!("[BOM] can_go_back() - history.length > 1 check executed");
        }
        // For now, return true as a reasonable default
        // Real implementation would need async callback
        Ok(true)
    }

    /// Check if can navigate forward in history
    /// Note: Browser doesn't expose forward history directly, so this is tracked via popstate
    pub fn can_go_forward(&self) -> Result<bool, Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            // Check the tracked forward navigation flag
            webview.evaluate_script(auroraview_core::bom::js::CAN_GO_FORWARD)?;
            tracing::debug!("[BOM] can_go_forward() check executed");
        }
        // For now, return false as a reasonable default
        // Real implementation would need async callback
        Ok(false)
    }

    /// Check if page is currently loading
    ///
    /// Note: This triggers a JS execution to check the current loading state.
    /// For accurate async results, use eval_js_async with IS_LOADING script.
    pub fn is_loading(&self) -> Result<bool, Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            // Execute script to update the tracked loading state
            webview.evaluate_script(auroraview_core::bom::js::IS_LOADING)?;
            tracing::debug!("[BOM] is_loading() check executed");
        }
        // Return a heuristic value - actual value requires async callback
        // The navigation tracker script maintains this state
        Ok(false)
    }

    /// Get current load progress (0-100)
    ///
    /// Note: This triggers a JS execution to check the current progress.
    /// For accurate async results, use eval_js_async with GET_LOAD_PROGRESS script.
    pub fn load_progress(&self) -> Result<u8, Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(auroraview_core::bom::js::GET_LOAD_PROGRESS)?;
            tracing::debug!("[BOM] load_progress() check executed");
        }
        // Return a heuristic value - actual value requires async callback
        // The navigation tracker script maintains this state
        Ok(100)
    }

    // ========================================
    // BOM Zoom APIs
    // ========================================

    /// Set zoom level (1.0 = 100%, 1.5 = 150%, etc.)
    pub fn set_zoom(&self, scale_factor: f64) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.zoom(scale_factor)?;
            tracing::debug!("[BOM] set_zoom({}) executed", scale_factor);
        }
        Ok(())
    }

    // ========================================
    // BOM Window Control APIs
    // ========================================

    /// Minimize window
    pub fn minimize(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_minimized(true);
            tracing::debug!("[BOM] minimize() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Maximize window
    pub fn maximize(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_maximized(true);
            tracing::debug!("[BOM] maximize() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Unmaximize (restore) window
    pub fn unmaximize(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_maximized(false);
            tracing::debug!("[BOM] unmaximize() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Toggle maximize state
    pub fn toggle_maximize(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            let is_maximized = window.is_maximized();
            window.set_maximized(!is_maximized);
            tracing::debug!(
                "[BOM] toggle_maximize() executed, now maximized={}",
                !is_maximized
            );
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Check if window is maximized
    pub fn is_maximized(&self) -> bool {
        self.window
            .as_ref()
            .map(|w| w.is_maximized())
            .unwrap_or(false)
    }

    /// Check if window is minimized
    pub fn is_minimized(&self) -> bool {
        self.window
            .as_ref()
            .map(|w| w.is_minimized())
            .unwrap_or(false)
    }

    /// Set fullscreen mode
    pub fn set_fullscreen(&self, fullscreen: bool) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            if fullscreen {
                window.set_fullscreen(Some(tao::window::Fullscreen::Borderless(None)));
            } else {
                window.set_fullscreen(None);
            }
            tracing::debug!("[BOM] set_fullscreen({}) executed", fullscreen);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Check if window is in fullscreen mode
    pub fn is_fullscreen(&self) -> bool {
        self.window
            .as_ref()
            .map(|w| w.fullscreen().is_some())
            .unwrap_or(false)
    }

    /// Set window visibility
    pub fn set_visible(&self, visible: bool) -> Result<(), Box<dyn std::error::Error>> {
        // Try window first (standalone mode)
        if let Some(window) = &self.window {
            window.set_visible(visible);
            tracing::debug!("[BOM] set_visible({}) via window", visible);
            return Ok(());
        }

        // Try backend (DCC/embedded mode) - Windows only
        #[cfg(target_os = "windows")]
        if let Some(backend) = &self.backend {
            backend.set_visible(visible)?;
            tracing::debug!("[BOM] set_visible({}) via backend", visible);
            return Ok(());
        }

        Err("Window not available (neither window nor backend present)".into())
    }

    /// Check if window is visible
    pub fn is_visible(&self) -> bool {
        self.window
            .as_ref()
            .map(|w| w.is_visible())
            .unwrap_or(false)
    }

    /// Check if window has focus
    pub fn is_focused(&self) -> bool {
        self.window
            .as_ref()
            .map(|w| w.is_focused())
            .unwrap_or(false)
    }

    /// Request focus for the window
    pub fn set_focus(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_focus();
            tracing::debug!("[BOM] set_focus() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Set window title
    pub fn set_window_title(&self, title: &str) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_title(title);
            tracing::debug!("[BOM] set_title('{}') executed", title);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Get window title
    pub fn window_title(&self) -> Option<String> {
        self.window.as_ref().map(|w| w.title())
    }

    /// Set window size
    pub fn set_size(&self, width: u32, height: u32) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            let size = tao::dpi::PhysicalSize::new(width, height);
            window.set_inner_size(size);
            tracing::debug!("[BOM] set_size({}, {}) executed", width, height);

            // Also sync WebView bounds for Qt6 compatibility
            // In Qt6 createWindowContainer mode, the window size is managed by Qt,
            // but WebView2's controller bounds may not auto-sync
            self.sync_webview_bounds(width, height);

            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Sync WebView bounds with container size
    ///
    /// This is critical for Qt6 where createWindowContainer manages the native window
    /// but WebView2's internal controller bounds may not automatically update.
    /// Call this after any size change to ensure WebView content fills the container.
    ///
    /// This method uses wry's set_bounds() API which internally:
    /// 1. Calls ICoreWebView2Controller::SetBounds (WebView2 controller bounds)
    /// 2. Calls SetWindowPos (native window bounds)
    pub fn sync_webview_bounds(&self, width: u32, height: u32) {
        tracing::info!("[BOM] sync_webview_bounds({}, {}) called", width, height);

        // First, use Win32 API to force the tao window position and size
        // This ensures the window is always at (0, 0) within its parent
        #[cfg(target_os = "windows")]
        {
            if let Some(hwnd) = self.get_hwnd() {
                use std::ffi::c_void;
                use windows::Win32::Foundation::HWND;
                use windows::Win32::UI::WindowsAndMessaging::{
                    SetWindowPos, SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOZORDER,
                };

                unsafe {
                    let hwnd_win = HWND(hwnd as *mut c_void);
                    // Force position to (0, 0) and set size
                    let result = SetWindowPos(
                        hwnd_win,
                        None,
                        0, // X - always at origin
                        0, // Y - always at origin
                        width as i32,
                        height as i32,
                        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                    );
                    if result.is_ok() {
                        tracing::debug!(
                            "[BOM] SetWindowPos succeeded: pos=(0,0) size={}x{}",
                            width,
                            height
                        );
                    } else {
                        tracing::warn!("[BOM] SetWindowPos failed");
                    }
                }
            }
        }

        // Then, use wry's set_bounds to sync WebView2 controller bounds
        if let Ok(webview) = self.webview.lock() {
            // Use Physical size to avoid DPI scaling issues
            // wry's set_bounds will convert this to the correct coordinates
            let bounds = wry::Rect {
                position: wry::dpi::Position::Physical(wry::dpi::PhysicalPosition::new(0, 0)),
                size: wry::dpi::Size::Physical(wry::dpi::PhysicalSize::new(width, height)),
            };
            match webview.set_bounds(bounds) {
                Ok(_) => {
                    tracing::info!(
                        "[BOM] sync_webview_bounds via wry::set_bounds succeeded: {}x{}",
                        width,
                        height
                    );
                }
                Err(e) => {
                    tracing::warn!(
                        "[BOM] sync_webview_bounds via wry::set_bounds failed: {:?}",
                        e
                    );
                }
            }
        }
    }

    /// Get window inner size
    pub fn inner_size(&self) -> auroraview_core::bom::PhysicalSize {
        self.window
            .as_ref()
            .map(|w| {
                let size = w.inner_size();
                auroraview_core::bom::PhysicalSize::new(size.width, size.height)
            })
            .unwrap_or_default()
    }

    /// Get window outer size (including decorations)
    pub fn outer_size(&self) -> auroraview_core::bom::PhysicalSize {
        self.window
            .as_ref()
            .map(|w| {
                let size = w.outer_size();
                auroraview_core::bom::PhysicalSize::new(size.width, size.height)
            })
            .unwrap_or_default()
    }

    /// Get window position
    pub fn position(&self) -> Option<auroraview_core::bom::PhysicalPosition> {
        self.window.as_ref().and_then(|w| {
            w.outer_position()
                .ok()
                .map(|pos| auroraview_core::bom::PhysicalPosition::new(pos.x, pos.y))
        })
    }

    /// Set window position
    pub fn set_position(&self, x: i32, y: i32) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_outer_position(tao::dpi::PhysicalPosition::new(x, y));
            tracing::debug!("[BOM] set_position({}, {}) executed", x, y);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Center window on screen
    pub fn center(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            // Get the primary monitor
            let monitor = window
                .primary_monitor()
                .or_else(|| window.current_monitor())
                .ok_or("No monitor found")?;

            let monitor_size = monitor.size();
            let monitor_pos = monitor.position();
            let window_size = window.outer_size();

            // Calculate center position
            let x = monitor_pos.x + (monitor_size.width as i32 - window_size.width as i32) / 2;
            let y = monitor_pos.y + (monitor_size.height as i32 - window_size.height as i32) / 2;

            window.set_outer_position(tao::dpi::PhysicalPosition::new(x, y));
            tracing::debug!("[BOM] center() executed, position=({}, {})", x, y);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Set window decorations (title bar, borders)
    pub fn set_decorations(&self, decorations: bool) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_decorations(decorations);
            tracing::debug!("[BOM] set_decorations({}) executed", decorations);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Set window resizable
    pub fn set_resizable(&self, resizable: bool) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_resizable(resizable);
            tracing::debug!("[BOM] set_resizable({}) executed", resizable);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Set minimum window size
    pub fn set_min_size(&self, width: u32, height: u32) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            let size = tao::dpi::PhysicalSize::new(width, height);
            window.set_min_inner_size(Some(size));
            tracing::debug!("[BOM] set_min_size({}, {}) executed", width, height);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Set maximum window size
    pub fn set_max_size(&self, width: u32, height: u32) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            let size = tao::dpi::PhysicalSize::new(width, height);
            window.set_max_inner_size(Some(size));
            tracing::debug!("[BOM] set_max_size({}, {}) executed", width, height);
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Toggle fullscreen mode
    #[allow(dead_code)] // Part of BOM API, will be exposed to Python bindings
    pub fn toggle_fullscreen(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            let is_fullscreen = window.fullscreen().is_some();
            if is_fullscreen {
                window.set_fullscreen(None);
            } else {
                window.set_fullscreen(Some(tao::window::Fullscreen::Borderless(None)));
            }
            tracing::debug!(
                "[BOM] toggle_fullscreen() executed, now fullscreen={}",
                !is_fullscreen
            );
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Hide window
    #[allow(dead_code)] // Part of BOM API, will be exposed to Python bindings
    pub fn hide(&self) -> Result<(), Box<dyn std::error::Error>> {
        self.set_visible(false)
    }

    /// Show window and request focus
    #[allow(dead_code)] // Part of BOM API, will be exposed to Python bindings
    pub fn focus(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_visible(true);
            window.set_focus();
            tracing::debug!("[BOM] focus() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    /// Restore window from minimized/maximized state
    pub fn restore(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Some(window) = &self.window {
            window.set_minimized(false);
            window.set_maximized(false);
            tracing::debug!("[BOM] restore() executed");
            Ok(())
        } else {
            Err("Window not available".into())
        }
    }

    // ========================================
    // BOM Clear Data APIs
    // ========================================

    /// Clear all browsing data (localStorage, sessionStorage, IndexedDB, cookies)
    pub fn clear_all_browsing_data(&self) -> Result<(), Box<dyn std::error::Error>> {
        if let Ok(webview) = self.webview.lock() {
            webview.evaluate_script(auroraview_core::bom::js::CLEAR_ALL_BROWSING_DATA)?;
            tracing::debug!("[BOM] clear_all_browsing_data() executed");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::WebViewMessage;

    #[test]
    fn test_webview_inner_has_message_queue() {
        // Test that message queue is accessible
        let queue = Arc::new(MessageQueue::new());
        assert!(queue.is_empty());
    }

    #[test]
    fn test_webview_inner_lifecycle_manager() {
        // Test lifecycle manager creation
        let lifecycle = Arc::new(LifecycleManager::new());
        assert_eq!(
            lifecycle.state(),
            crate::webview::lifecycle::LifecycleState::Creating
        );
    }

    #[test]
    fn test_webview_message_eval_js() {
        // Test that EvalJs message can be created
        let msg = WebViewMessage::EvalJs("console.log('test')".to_string());
        match msg {
            WebViewMessage::EvalJs(script) => {
                assert_eq!(script, "console.log('test')");
            }
            _ => panic!("Wrong message type"),
        }
    }

    #[test]
    fn test_webview_message_emit_event() {
        // Test that EmitEvent message can be created
        let data = serde_json::json!({"key": "value"});
        let msg = WebViewMessage::EmitEvent {
            event_name: "test_event".to_string(),
            data: data.clone(),
        };

        match msg {
            WebViewMessage::EmitEvent {
                event_name,
                data: event_data,
            } => {
                assert_eq!(event_name, "test_event");
                assert_eq!(event_data, data);
            }
            _ => panic!("Wrong message type"),
        }
    }

    #[test]
    fn test_webview_message_load_url() {
        // Test that LoadUrl message can be created
        let msg = WebViewMessage::LoadUrl("https://example.com".to_string());
        match msg {
            WebViewMessage::LoadUrl(url) => {
                assert_eq!(url, "https://example.com");
            }
            _ => panic!("Wrong message type"),
        }
    }

    #[test]
    fn test_webview_message_load_html() {
        // Test that LoadHtml message can be created
        let html = "<h1>Test</h1>".to_string();
        let msg = WebViewMessage::LoadHtml(html.clone());
        match msg {
            WebViewMessage::LoadHtml(content) => {
                assert_eq!(content, html);
            }
            _ => panic!("Wrong message type"),
        }
    }

    #[test]
    fn test_message_queue_operations() {
        // Test message queue push and pop
        let queue = MessageQueue::new();
        let msg = WebViewMessage::EvalJs("test".to_string());

        assert!(queue.is_empty());
        queue.push(msg);
        assert!(!queue.is_empty());

        let popped = queue.pop();
        assert!(popped.is_some());
        assert!(queue.is_empty());
    }

    #[test]
    fn test_lifecycle_state_transitions() {
        // Test lifecycle state management
        let lifecycle = LifecycleManager::new();

        assert_eq!(
            lifecycle.state(),
            crate::webview::lifecycle::LifecycleState::Creating
        );

        lifecycle.set_state(crate::webview::lifecycle::LifecycleState::Active);
        assert_eq!(
            lifecycle.state(),
            crate::webview::lifecycle::LifecycleState::Active
        );
    }

    #[test]
    fn test_event_json_escaping() {
        // Test JSON escaping for event emission
        let json_str = r#"{"key": "value with 'quotes'"}"#;
        let escaped = json_str.replace('\\', "\\\\").replace('\'', "\\'");
        assert!(escaped.contains("\\'"));
    }

    #[test]
    fn test_load_url_script_generation() {
        // Test that load URL script can be generated
        let url = "https://example.com";
        let script = js_assets::build_load_url_script(url);
        assert!(script.contains(url));
        assert!(script.contains("window.location.href"));
    }
}
