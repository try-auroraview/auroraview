//! AuroraView Core - Constructor, Lifecycle, and Properties
//!
//! This module contains the core WebView functionality:
//! - Constructor (`new`)
//! - Lifecycle methods (`show`, `close`, `run`)
//! - Factory methods (`create_embedded`, `create_embedded_async`)
//! - Property getters (`title`, `url`, `progress`, `loading`)

use pyo3::prelude::*;
use std::cell::RefCell;
use std::rc::Rc;
use std::sync::Arc;

use super::AuroraView;
use crate::ipc::{IpcHandler, JsCallbackManager, MessageQueue, WebViewMessage};
use crate::utils::normalize_url;
use crate::webview::config::WebViewConfig;
use crate::webview::webview_inner::WebViewInner;

#[pymethods]
impl AuroraView {
    /// Create a new WebView instance
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (title="DCC WebView", width=800, height=600, url=None, html=None, dev_tools=true, context_menu=true, resizable=true, decorations=true, parent_hwnd=None, parent_mode=None, asset_root=None, data_directory=None, allow_file_protocol=false, capture_file_drop=None, always_on_top=false, transparent=false, background_color=None, auto_show=true, headless=false, remote_debugging_port=None, ipc_batch_size=0, icon=None, tool_window=false, undecorated_shadow=true, allow_new_window=false, new_window_mode=None, splash_overlay=false, allow_downloads=true, download_prompt=false, download_directory=None, proxy_url=None, user_agent=None))]
    fn new(
        title: &str,
        width: u32,
        height: u32,
        url: Option<&str>,
        html: Option<&str>,
        dev_tools: bool,
        context_menu: bool,
        resizable: bool,
        decorations: bool,
        parent_hwnd: Option<u64>,
        #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] parent_mode: Option<&str>,
        asset_root: Option<&str>,
        data_directory: Option<&str>,
        allow_file_protocol: bool,
        capture_file_drop: Option<bool>,
        always_on_top: bool,
        transparent: bool,
        background_color: Option<&str>,
        auto_show: bool,
        headless: bool,
        remote_debugging_port: Option<u16>,
        ipc_batch_size: usize,
        icon: Option<&str>,
        #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] tool_window: bool,
        #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] undecorated_shadow: bool,
        allow_new_window: bool,
        new_window_mode: Option<&str>,
        splash_overlay: bool,
        allow_downloads: bool,
        download_prompt: bool,
        download_directory: Option<&str>,
        proxy_url: Option<&str>,
        user_agent: Option<&str>,
    ) -> PyResult<Self> {
        tracing::info!(
            "AuroraView::new() called with title: {}, transparent={}, tool_window={}, decorations={}",
            title, transparent, tool_window, decorations
        );

        // Normalize URL if provided
        let normalized_url = url.map(normalize_url);
        if let (Some(orig), Some(ref norm)) = (url, &normalized_url) {
            if orig != norm {
                tracing::info!("URL normalized: {} -> {}", orig, norm);
            }
        }

        #[cfg_attr(not(target_os = "windows"), allow(unused_mut))]
        let mut config = WebViewConfig {
            title: title.to_string(),
            width,
            height,
            url: normalized_url,
            html: html.map(|s| s.to_string()),
            dev_tools,
            context_menu,
            resizable,
            decorations,
            parent_hwnd,
            asset_root: asset_root.map(std::path::PathBuf::from),
            data_directory: data_directory.map(std::path::PathBuf::from),
            allow_file_protocol,
            // RFC 0017 §3 final flatten point: this PyO3 binding is the ONLY
            // place where the Python tri-state `Optional[bool]` collapses
            // into a concrete `bool`. Mirrors `desktop_runner::run_desktop`.
            capture_file_drop: capture_file_drop.unwrap_or(false),
            always_on_top,
            transparent,
            background_color: background_color.map(|s| s.to_string()),
            auto_show: auto_show && !headless, // Don't auto-show in headless mode
            headless,
            remote_debugging_port,
            ipc_batch_size,
            icon: icon.map(std::path::PathBuf::from),
            allow_new_window,
            new_window_mode: match new_window_mode.map(|s| s.to_ascii_lowercase()) {
                Some(ref m) if m == "deny" => crate::webview::config::NewWindowMode::Deny,
                Some(ref m) if m == "system_browser" || m == "systembrowser" => {
                    crate::webview::config::NewWindowMode::SystemBrowser
                }
                Some(ref m) if m == "child_webview" || m == "childwebview" || m == "child" => {
                    crate::webview::config::NewWindowMode::ChildWebView
                }
                _ => {
                    // Default: use SystemBrowser if allow_new_window is true, otherwise Deny
                    if allow_new_window {
                        crate::webview::config::NewWindowMode::SystemBrowser
                    } else {
                        crate::webview::config::NewWindowMode::Deny
                    }
                }
            },
            splash_overlay,
            allow_downloads,
            download_prompt,
            download_directory: download_directory.map(std::path::PathBuf::from),
            proxy_url: proxy_url.map(|s| s.to_string()),
            user_agent: user_agent.map(|s| s.to_string()),
            ..Default::default()
        };

        // Map string to EmbedMode (Windows)
        // Supported modes: "child" (embed in Qt widget), "owner" (floating tool window)
        #[cfg(target_os = "windows")]
        {
            use crate::webview::config::EmbedMode;
            config.embed_mode = match parent_mode.map(|s| s.to_ascii_lowercase()) {
                Some(ref m) if m == "child" => EmbedMode::Child,
                Some(ref m) if m == "owner" => EmbedMode::Owner,
                _ => {
                    // Default: use Child mode if parent_hwnd is provided, otherwise None
                    if parent_hwnd.is_some() {
                        EmbedMode::Child
                    } else {
                        EmbedMode::None
                    }
                }
            };
            config.tool_window = tool_window;
            config.undecorated_shadow = undecorated_shadow;
        }

        // Create IPC handler and JS callback manager
        let js_callback_manager = Arc::new(JsCallbackManager::new());
        let mut ipc_handler = IpcHandler::new();
        ipc_handler.set_js_callback_manager(js_callback_manager.clone());

        Ok(AuroraView {
            inner: Rc::new(RefCell::new(None)),
            config: Rc::new(RefCell::new(config)),
            ipc_handler: Arc::new(ipc_handler),
            message_queue: Arc::new(MessageQueue::new()),
            event_loop_proxy: Rc::new(RefCell::new(None)),
            js_callback_manager,
            on_hwnd_created: Rc::new(RefCell::new(None)),
            #[cfg(target_os = "windows")]
            cached_hwnd: Rc::new(RefCell::new(None)),
        })
    }

    /// Set callback for when WebView2 HWND is created
    ///
    /// The callback receives the HWND (int) as argument.
    /// This is called immediately when the underlying WebView2 window is created.
    fn set_on_hwnd_created(&self, callback: Py<PyAny>) {
        *self.on_hwnd_created.borrow_mut() = Some(callback);
    }

    /// Test method to verify Python bindings work
    fn test_method(&self) -> PyResult<String> {
        Ok("test_method works!".to_string())
    }

    // === Factory Methods ===

    /// Create a WebView instance for embedded mode (static method)
    ///
    /// This creates a WebView that will be embedded into a parent window.
    /// The WebView does not run its own event loop - the host application
    /// must call process_events_ipc_only() periodically.
    ///
    /// # Arguments
    /// * `parent_hwnd` - HWND of the parent window
    /// * `title` - Window title (for debugging)
    /// * `width` - Width in pixels
    /// * `height` - Height in pixels
    #[cfg(target_os = "windows")]
    #[staticmethod]
    #[pyo3(signature = (parent_hwnd, title="Embedded WebView", width=800, height=600))]
    fn create_embedded(parent_hwnd: u64, title: &str, width: u32, height: u32) -> PyResult<Self> {
        use crate::webview::config::EmbedMode;

        tracing::info!(
            "[create_embedded] Creating embedded WebView for parent HWND: 0x{:X}",
            parent_hwnd
        );

        let config = WebViewConfig {
            title: title.to_string(),
            width,
            height,
            parent_hwnd: Some(parent_hwnd),
            embed_mode: EmbedMode::Child,
            dev_tools: true,
            ..Default::default()
        };

        let ipc_handler = Arc::new(IpcHandler::new());
        let message_queue = Arc::new(MessageQueue::new());

        // Create the WebView using the inner create_embedded
        let webview_inner = WebViewInner::create_embedded(
            parent_hwnd,
            config.clone(),
            ipc_handler.clone(),
            message_queue.clone(),
            None,
        )
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        // Get HWND from the created webview
        let cached_hwnd = webview_inner.get_hwnd();

        tracing::info!(
            "[create_embedded] WebView created successfully, HWND: {:?}",
            cached_hwnd
        );

        Ok(Self {
            inner: Rc::new(RefCell::new(Some(webview_inner))),
            config: Rc::new(RefCell::new(config)),
            ipc_handler,
            message_queue,
            event_loop_proxy: Rc::new(RefCell::new(None)),
            js_callback_manager: Arc::new(JsCallbackManager::new()),
            on_hwnd_created: Rc::new(RefCell::new(None)),
            cached_hwnd: Rc::new(RefCell::new(cached_hwnd)),
        })
    }

    // === Lifecycle Methods ===

    /// Show WebView window (standalone mode or embedded mode)
    fn show(&self, py: Python<'_>) -> PyResult<()> {
        use crate::webview::config::EmbedMode;
        let embed_mode = self.config.borrow().embed_mode;

        match embed_mode {
            EmbedMode::None => self.show_window(py),
            #[cfg(target_os = "windows")]
            EmbedMode::Child | EmbedMode::Owner => self.show_embedded(),
        }
    }

    /// Create WebView for standalone mode (creates its own window)
    fn show_window(&self, py: Python<'_>) -> PyResult<()> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "A hosted WebView cannot enter a standalone event loop",
            ));
        }
        let title = self.config.borrow().title.clone();
        tracing::info!("Showing WebView (standalone mode): {}", title);

        #[cfg(target_os = "windows")]
        let mut hwnd_for_callback: Option<u64> = None;

        let mut inner = self.inner.borrow_mut();
        let need_create = inner.as_ref().is_none_or(|e| e.event_loop.is_none());

        if need_create {
            let mut webview = WebViewInner::create_standalone(
                self.config.borrow().clone(),
                self.ipc_handler.clone(),
                self.message_queue.clone(),
            )
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

            if let Some(proxy) = webview.event_loop_proxy.take() {
                *self.event_loop_proxy.borrow_mut() = Some(proxy);
            }

            // Cache HWND at AuroraView level before storing webview
            #[cfg(target_os = "windows")]
            {
                if let Some(hwnd) = webview.get_hwnd() {
                    tracing::debug!(
                        "[show_window] Caching HWND at AuroraView level: 0x{:X}",
                        hwnd
                    );
                    *self.cached_hwnd.borrow_mut() = Some(hwnd);
                    hwnd_for_callback = Some(hwnd);
                }
            }

            *inner = Some(webview);
        }

        drop(inner);

        // Invoke on_hwnd_created callback if set (standalone mode)
        #[cfg(target_os = "windows")]
        if let Some(hwnd) = hwnd_for_callback {
            if let Some(callback) = Python::attach(|py| {
                self.on_hwnd_created
                    .borrow()
                    .as_ref()
                    .map(|cb| cb.clone_ref(py))
            }) {
                tracing::info!(
                    "[show_window] Invoking on_hwnd_created callback with HWND 0x{:X}",
                    hwnd
                );
                Python::attach(|py| {
                    if let Err(e) = callback.call1(py, (hwnd,)) {
                        tracing::error!("Error calling on_hwnd_created callback: {:?}", e);
                        e.print(py);
                    }
                });
            }
        }

        // Run the blocking event loop with the GIL released.
        //
        // `run_event_loop_blocking` parks the calling thread inside the native
        // message pump until a `CloseWindow` user event arrives. Holding the GIL
        // across that call makes every other Python thread un-runnable, which
        // turns `WebView.close()` (and any test teardown running on the main
        // thread) into a deadlock: the window can never be closed and the
        // process can never exit. The event loop re-acquires the GIL itself
        // (`Python::attach`) whenever it needs to invoke a Python callback, so
        // releasing it here is safe.
        //
        // `WebViewInner` is !Send and therefore cannot cross the `detach`
        // boundary, so it is handed over by raw pointer through the local
        // carrier below. The borrow is kept alive in this scope for the whole
        // loop and the closure runs synchronously on this thread.
        //
        // The carrier is deliberately scoped to this function and bound to
        // `WebViewInner` rather than generic: it is only sound because
        // `detach` runs the closure in place, and a reusable `Send` wrapper for
        // arbitrary `T` would silently become unsound if it ever reached a real
        // `thread::spawn`.
        struct LoopTarget(*mut WebViewInner);

        impl LoopTarget {
            /// Exposed as a method on purpose: a method call makes the closure
            /// capture the whole `LoopTarget` (which is `Send`) instead of the
            /// raw field (which is not) under edition 2021's disjoint captures.
            ///
            /// # Safety
            ///
            /// The pointee must be alive and uniquely borrowed for the whole
            /// borrow.
            unsafe fn as_mut(&mut self) -> &mut WebViewInner {
                &mut *self.0
            }
        }

        // SAFETY: the pointee is only ever dereferenced on the thread that
        // created the `LoopTarget`, while `inner_ref` still holds the unique
        // borrow. `detach` does not move the closure to another thread.
        unsafe impl Send for LoopTarget {}

        let mut inner_ref = self.inner.borrow_mut();
        if let Some(webview_inner) = inner_ref.as_mut() {
            let mut loop_target = LoopTarget(webview_inner as *mut WebViewInner);
            py.detach(move || {
                // SAFETY: `inner_ref` keeps the `WebViewInner` alive and uniquely
                // borrowed for the duration of this closure, and the closure runs
                // synchronously on the current thread.
                let webview_inner = unsafe { loop_target.as_mut() };
                webview_inner.run_event_loop_blocking();
            });
        }
        drop(inner_ref);

        *self.inner.borrow_mut() = None;
        Ok(())
    }

    /// Show embedded WebView (non-blocking)
    #[cfg(target_os = "windows")]
    fn show_embedded(&self) -> PyResult<()> {
        let title = self.config.borrow().title.clone();
        tracing::info!("Creating embedded WebView: {}", title);

        // Track if we need to invoke the callback after releasing the borrow
        let mut created_hwnd: Option<u64> = None;

        {
            // Scope the mutable borrow to release it before callback invocation
            let mut inner = self.inner.borrow_mut();
            let need_create = inner.as_ref().is_none_or(|e| e.event_loop.is_none());

            if need_create {
                let config = self.config.borrow().clone();
                let parent_hwnd = config.parent_hwnd.unwrap_or(0);

                // Debug: log config values
                tracing::info!(
                    "[show_embedded] title={}, Config: tool_window={}, undecorated_shadow={}, decorations={}, transparent={}, embed_mode={:?}, parent_hwnd={:?}",
                    config.title,
                    config.tool_window,
                    config.undecorated_shadow,
                    config.decorations,
                    config.transparent,
                    config.embed_mode,
                    config.parent_hwnd
                );

                // Don't pass callback to create_embedded - we'll invoke it after releasing borrow
                // This avoids RefCell borrow conflict when callback tries to access self.inner
                let webview = WebViewInner::create_embedded(
                    parent_hwnd,
                    config,
                    self.ipc_handler.clone(),
                    self.message_queue.clone(),
                    None, // No callback - we'll call it manually after borrow is released
                )
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

                // Get HWND before storing webview
                created_hwnd = webview.get_hwnd();

                *inner = Some(webview);
            }
        } // inner borrow released here

        // Cache HWND at AuroraView level
        if let Some(hwnd) = created_hwnd {
            tracing::info!(
                "[show_embedded] Caching HWND at AuroraView level: 0x{:X}",
                hwnd
            );
            *self.cached_hwnd.borrow_mut() = Some(hwnd);
        }

        // Now safe to invoke callback - self.inner is no longer borrowed
        if let Some(hwnd) = created_hwnd {
            if let Some(callback) = Python::attach(|py| {
                self.on_hwnd_created
                    .borrow()
                    .as_ref()
                    .map(|cb| cb.clone_ref(py))
            }) {
                tracing::info!(
                    "[OK] [show_embedded] Invoking on_hwnd_created callback with HWND 0x{:X}",
                    hwnd
                );
                Python::attach(|py| {
                    if let Err(e) = callback.call1(py, (hwnd,)) {
                        tracing::error!("Error calling on_hwnd_created callback: {:?}", e);
                        e.print(py);
                    }
                });
            }
        }

        Ok(())
    }

    /// Close the WebView window
    ///
    /// The request always travels through the module-level close channel - the
    /// `Arc<MessageQueue>` drained by the owner thread's event loop, plus the
    /// `EventLoopProxy` that wakes it - so the window is only ever torn down on
    /// the thread that owns it.
    fn close(&self) -> PyResult<()> {
        super::request_close_via_channel(&self.message_queue, &self.event_loop_proxy);
        Ok(())
    }

    /// Process messages for DCC integration mode
    fn process_messages(&self) -> PyResult<bool> {
        let inner = self.inner.borrow();
        if let Some(webview) = inner.as_ref() {
            Ok(webview.process_messages())
        } else {
            Ok(false)
        }
    }

    /// Process IPC messages only (no window message pump)
    ///
    /// For embedded integration mode (create_embedded_async), this processes
    /// Python callbacks on the main thread while the background thread
    /// handles the actual WebView event loop.
    fn process_ipc_only(&self) -> PyResult<bool> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            // One shared HostRuntime pumps all views; per-view calls only observe.
            return Ok(self.message_queue.hosted_state() == 3);
        }
        // Use try_borrow to avoid panic during initialization
        match self.inner.try_borrow() {
            Ok(inner_ref) => {
                if let Some(ref inner) = *inner_ref {
                    return Ok(inner.process_ipc_only());
                }
            }
            Err(_) => {
                tracing::trace!("[process_ipc_only] RefCell already borrowed, using async mode");
            }
        }

        // For background thread mode, inner is None
        let queue_len = self.message_queue.len();
        if queue_len > 0 {
            tracing::trace!(
                "[process_ipc_only] Async mode: {} messages in queue (handled by background)",
                queue_len
            );
        }

        Ok(false)
    }

    /// Cleanup timed-out JavaScript callbacks
    fn cleanup_timed_out_callbacks(&self) -> PyResult<usize> {
        Ok(self.js_callback_manager.cleanup_timed_out())
    }

    /// Get the default timeout for JavaScript callbacks
    fn get_js_timeout(&self) -> PyResult<u64> {
        Ok(self.js_callback_manager.default_timeout_ms())
    }

    /// Get the number of pending JavaScript callbacks
    fn pending_js_callbacks(&self) -> PyResult<usize> {
        Ok(self.js_callback_manager.pending_count())
    }

    // === Content Loading ===

    /// Load a URL in the WebView
    ///
    /// Automatically normalizes URLs:
    /// - `baidu.com` -> `https://baidu.com`
    /// - `localhost:8080` -> `https://localhost:8080`
    /// - `/path/to/file.html` -> `file:///path/to/file.html`
    fn load_url(&self, url: &str) -> PyResult<()> {
        let normalized = normalize_url(url);
        tracing::info!("Loading URL: {} (normalized from: {})", normalized, url);

        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return self.message_queue.try_push(WebViewMessage::LoadUrl(normalized))
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }

        if let Some(webview) = self.inner.borrow_mut().as_mut() {
            webview
                .load_url(&normalized)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            return Ok(());
        }

        let has_parent = self.config.borrow().parent_hwnd.is_some();
        if has_parent {
            self.message_queue.push(WebViewMessage::LoadUrl(normalized));
            return Ok(());
        }

        let mut cfg = self.config.borrow_mut();
        cfg.url = Some(normalized);
        cfg.html = None;
        Ok(())
    }

    /// Load HTML content in the WebView
    fn load_html(&self, html: &str) -> PyResult<()> {
        tracing::info!("Loading HTML content ({} bytes)", html.len());

        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return self.message_queue.try_push(WebViewMessage::LoadHtml(html.to_string()))
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }

        if let Some(webview) = self.inner.borrow_mut().as_mut() {
            webview
                .load_html(html)
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
            return Ok(());
        }

        let has_parent = self.config.borrow().parent_hwnd.is_some();
        if has_parent {
            self.message_queue
                .push(WebViewMessage::LoadHtml(html.to_string()));
            return Ok(());
        }

        let mut cfg = self.config.borrow_mut();
        cfg.html = Some(html.to_string());
        cfg.url = None;
        Ok(())
    }

    /// Navigate to a URL (alias for load_url)
    fn navigate(&self, url: &str) -> PyResult<()> {
        self.load_url(url)
    }

    /// Reload the current page
    fn reload(&self) -> PyResult<()> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return self.message_queue.try_push(WebViewMessage::Reload)
                .map_err(pyo3::exceptions::PyRuntimeError::new_err);
        }
        self.message_queue.push(WebViewMessage::Reload);
        Ok(())
    }

    /// Stop loading the current page
    fn stop_loading(&self) -> PyResult<()> {
        self.message_queue.push(WebViewMessage::StopLoading);
        Ok(())
    }

    // === Property Getters ===

    /// Get the window title
    #[getter]
    fn title(&self) -> PyResult<String> {
        Ok(self.config.borrow().title.clone())
    }

    /// Set the window title
    #[setter]
    fn set_title(&mut self, title: String) -> PyResult<()> {
        self.config.borrow_mut().title = title;
        Ok(())
    }

    /// Get the current URL
    #[getter]
    fn url(&self) -> PyResult<String> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .get_url()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Ok(self.config.borrow().url.clone().unwrap_or_default())
        }
    }

    /// Get the current load progress (0-100)
    #[getter]
    fn progress(&self) -> PyResult<u8> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .load_progress()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Ok(0)
        }
    }

    /// Check if page is loading
    #[getter]
    fn loading(&self) -> PyResult<bool> {
        let inner_ref = self.inner.borrow();
        if let Some(ref inner) = *inner_ref {
            inner
                .is_loading()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
        } else {
            Ok(false)
        }
    }

    /// Get the window handle (HWND on Windows)
    fn get_hwnd(&self) -> PyResult<Option<u64>> {
        // First check cached HWND at AuroraView level (always accessible)
        #[cfg(target_os = "windows")]
        {
            let cached = *self.cached_hwnd.borrow();
            if let Some(hwnd) = cached {
                tracing::debug!("[AuroraView::get_hwnd] Returning cached HWND: 0x{:X}", hwnd);
                return Ok(Some(hwnd));
            }
        }

        // Fall back to getting HWND from inner WebViewInner
        // Use try_borrow to avoid panic if RefCell is already borrowed
        // This can happen during callback invocations from show_embedded/create_embedded
        match self.inner.try_borrow() {
            Ok(inner) => {
                if let Some(ref webview) = *inner {
                    let hwnd = webview.get_hwnd();

                    // Cache the HWND for future use
                    #[cfg(target_os = "windows")]
                    if let Some(h) = hwnd {
                        *self.cached_hwnd.borrow_mut() = Some(h);
                    }

                    Ok(hwnd)
                } else {
                    Ok(None)
                }
            }
            Err(_) => {
                // RefCell already borrowed - return None instead of panicking
                tracing::debug!(
                    "[get_hwnd] RefCell already borrowed, returning None (no cached HWND)"
                );
                Ok(None)
            }
        }
    }

    /// Get a thread-safe proxy for cross-thread operations
    ///
    /// Returns a `WebViewProxy` that can be safely shared across threads.
    /// Use this when you need to call `eval_js`, `emit`, etc. from a different
    /// thread than the one that created the WebView.
    ///
    /// This is essential for HWND mode where the WebView runs in a background
    /// thread but you need to call methods from the DCC main thread.
    ///
    /// Returns:
    ///     WebViewProxy: A thread-safe proxy for WebView operations
    ///
    /// Example:
    ///     >>> # In HWND mode - WebView runs in background thread
    ///     >>> def create_webview():
    ///     ...     webview = WebView(...)
    ///     ...     proxy = webview.get_proxy()  # Get thread-safe proxy
    ///     ...     self._proxy = proxy          # Store for later use
    ///     ...     webview.show_blocking()
    ///     ...
    ///     >>> # From DCC main thread - safe!
    ///     >>> self._proxy.eval_js("console.log('Hello!')")
    fn get_proxy(&self) -> crate::webview::proxy::WebViewProxy {
        crate::webview::proxy::WebViewProxy::new(
            self.message_queue.clone(),
            self.js_callback_manager.clone(),
        )
    }

    // === Lifecycle State Query APIs ===

    /// Check if the WebView is alive and ready for operations
    ///
    /// Returns True if the WebView has been created and is not destroyed.
    /// Use this to check if it's safe to call other WebView methods.
    ///
    /// Returns:
    ///     bool: True if WebView is alive, False otherwise
    ///
    /// Example:
    ///     >>> if webview.is_alive():
    ///     ...     webview.eval_js("console.log('Hello!')")
    fn is_alive(&self) -> PyResult<bool> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return Ok(self.message_queue.hosted_state() == 1);
        }
        let inner = self.inner.borrow();
        if let Some(ref webview) = *inner {
            use crate::webview::lifecycle::LifecycleState;
            let state = webview.lifecycle_state();
            Ok(!matches!(
                state,
                LifecycleState::Destroyed
                    | LifecycleState::Destroying
                    | LifecycleState::CloseRequested
            ))
        } else {
            Ok(false)
        }
    }

    /// Get the current lifecycle state as a string
    ///
    /// Returns one of: "creating", "active", "close_requested", "destroying", "destroyed", "none"
    ///
    /// Returns:
    ///     str: Current lifecycle state
    ///
    /// Example:
    ///     >>> state = webview.lifecycle_state
    ///     >>> if state == "active":
    ///     ...     webview.eval_js("console.log('Ready!')")
    #[getter]
    fn lifecycle_state(&self) -> PyResult<String> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        match self.message_queue.hosted_state() {
            1 => return Ok("active".to_string()),
            2 => return Ok("close_requested".to_string()),
            3 => return Ok("destroyed".to_string()),
            _ => {}
        }
        let inner = self.inner.borrow();
        if let Some(ref webview) = *inner {
            use crate::webview::lifecycle::LifecycleState;
            let state = webview.lifecycle_state();
            let state_str = match state {
                LifecycleState::Creating => "creating",
                LifecycleState::Active => "active",
                LifecycleState::CloseRequested => "close_requested",
                LifecycleState::Destroying => "destroying",
                LifecycleState::Destroyed => "destroyed",
            };
            Ok(state_str.to_string())
        } else {
            Ok("none".to_string())
        }
    }

    /// Reset the WebView state for reuse
    ///
    /// This clears internal state so the WebView can be shown again after being closed.
    /// Call this before calling show() a second time on the same instance.
    ///
    /// Example:
    ///     >>> webview.close()
    ///     >>> # ... later ...
    ///     >>> webview.reset()  # Clear old state
    ///     >>> webview.show()   # Show again
    fn reset(&self) -> PyResult<()> {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if self.message_queue.hosted_state() != 0 {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Hosted views are single-use; construct a fresh WebView",
            ));
        }
        tracing::info!("[AuroraView::reset] Resetting WebView state for reuse");

        // Clear the inner WebViewInner
        *self.inner.borrow_mut() = None;

        // Clear the event loop proxy
        *self.event_loop_proxy.borrow_mut() = None;

        // Clear the message queue
        self.message_queue.clear();

        tracing::info!("[AuroraView::reset] WebView state reset complete");
        Ok(())
    }
}
