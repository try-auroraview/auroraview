//! WebView creation and event loop
//!
//! Handles creating the WebView window and running the main event loop.
//!
//! The code has been refactored from a single large file (1722 lines) into
//! logical submodules:
//!
//! - `helpers` - Utility functions for API registration, timing, and telemetry
//! - `extensions` - Extension installation and resource handling (Windows only)
//! - `ipc` - IPC message handling from WebView

mod extensions;
mod helpers;
mod ipc;

// Re-exports
#[allow(unused_imports)]
pub use helpers::{build_api_registration_script, capture_packed_sentry, duration_to_ms};

#[cfg(target_os = "windows")]
#[allow(unused_imports)]
pub use extensions::{handle_extension_resource_request, install_bundled_extensions_from_assets};

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};

use anyhow::{Context, Result};
use auroraview_core::assets::{
    build_error_page, build_packed_init_script_with_csp, get_loading_html,
};
use auroraview_core::plugins::{PathScope, PluginRequest, ScopeConfig, ShellScope};
use auroraview_core::protocol::MemoryAssets;
use auroraview_pack::{OverlayData, PackMode, PackedMetrics};
use tao::event_loop::{ControlFlow, EventLoop, EventLoopBuilder};
#[cfg(target_os = "windows")]
use tao::platform::windows::EventLoopBuilderExtWindows;
#[cfg(target_os = "windows")]
use wry::WebViewBuilderExtWindows;
use wry::{WebContext, WebViewBuilder as WryWebViewBuilder};

use crate::{load_window_icon, load_window_icon_from_bytes, normalize_url};

use super::backend::{start_python_backend_with_ipc, PythonBackend};
use super::events::UserEvent;
use super::utils::{
    build_css_injection_script, escape_js_string, escape_json_for_js, get_webview_data_dir,
};
#[cfg(target_os = "windows")]
use super::utils::{get_extensions_dir, has_extensions_in_dir, prepare_active_extensions_dir};

// Environment variable for runtime override of `capture_file_drop` in
// packed apps (RFC 0015 §4.3). Re-exported from the workspace-level
// `auroraview_core::constants` so the literal lives in a single place
// and can be referenced by other entry points and CI scripts without drift.
use auroraview_core::constants::parse_truthy;
use auroraview_core::constants::CAPTURE_FILE_DROP_ENV;

/// Resolve the effective `capture_file_drop` value at packed runtime,
/// honoring the [`CAPTURE_FILE_DROP_ENV`] override.
///
/// Falls back to `overlay_value` when the env var is unset or holds an
/// unrecognized literal (in which case a `tracing::warn!` is emitted).
pub fn resolve_packed_capture_file_drop(overlay_value: bool) -> bool {
    let raw = match std::env::var(CAPTURE_FILE_DROP_ENV) {
        Ok(v) => v,
        Err(_) => return overlay_value,
    };

    match parse_truthy(&raw) {
        Some(value) => {
            tracing::info!(
                target: "auroraview::capture_file_drop",
                "capture_file_drop overridden by {}={:?} -> {}",
                CAPTURE_FILE_DROP_ENV,
                raw,
                value
            );
            value
        }
        None => {
            tracing::warn!(
                target: "auroraview::capture_file_drop",
                "{}={:?} is not a recognized boolean literal (expected one of: \
                 1/true/on/yes/enabled / 0/false/off/no/disabled, case-insensitive). \
                 Falling back to overlay value: {}",
                CAPTURE_FILE_DROP_ENV,
                raw,
                overlay_value
            );
            overlay_value
        }
    }
}

/// Run WebView from overlay data
///
/// Note: This function uses event_loop.run() which never returns.
/// It will call std::process::exit() when the window closes.
#[allow(unreachable_code)]
pub fn run_packed_webview(overlay: OverlayData, mut metrics: PackedMetrics) -> Result<()> {
    let overlay = Arc::new(overlay);
    let config = &overlay.config;
    let is_fullstack = matches!(config.mode, PackMode::FullStack { .. });

    tracing::info!(
        "[Rust] Pack mode: {:?}, is_fullstack: {}",
        config.mode,
        is_fullstack
    );

    // Create event loop with user event support
    #[cfg(target_os = "windows")]
    let event_loop: EventLoop<UserEvent> = EventLoopBuilder::<UserEvent>::with_user_event()
        .with_any_thread(true)
        .build();

    #[cfg(not(target_os = "windows"))]
    let event_loop: EventLoop<UserEvent> = EventLoopBuilder::<UserEvent>::with_user_event().build();

    let proxy = event_loop.create_proxy();

    // Create PluginRouter with all built-in plugins and secure default scope
    let default_scope = {
        let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));

        let fs_scope = PathScope::new().allow(&cwd);

        #[cfg(target_os = "windows")]
        let fs_scope = {
            let extensions_dir = get_extensions_dir();
            let active_dir = dirs::data_local_dir()
                .unwrap_or_else(|| std::path::PathBuf::from("."))
                .join("AuroraView")
                .join("ExtensionsActive");
            fs_scope.allow(&extensions_dir).allow(&active_dir)
        };

        ScopeConfig::new()
            .with_fs_scope(fs_scope)
            .with_shell_scope(ShellScope::new())
    };

    let plugin_router = Arc::new(RwLock::new(auroraview_plugins::create_router_with_scope(
        default_scope,
    )));

    // Set up event callback for plugins to emit events to WebView
    let proxy_for_events = proxy.clone();
    {
        if let Ok(router) = plugin_router.read() {
            router.set_event_callback(Arc::new(
                move |event_name: &str, data: serde_json::Value| {
                    let data_str = serde_json::to_string(&data).unwrap_or_default();
                    let _ = proxy_for_events.send_event(UserEvent::PluginEvent {
                        event: event_name.to_string(),
                        data: data_str,
                    });
                },
            ));
        } else {
            tracing::error!("Failed to set event callback: plugin router lock poisoned");
        }
    }

    let needs_python_backend = matches!(config.mode, PackMode::FullStack { .. });
    let python_backend_state: Arc<RwLock<Option<Arc<PythonBackend>>>> = Arc::new(RwLock::new(None));

    // Track loading state for FullStack mode
    let loading_screen_ready = Arc::new(AtomicBool::new(false));
    let python_ready = Arc::new(AtomicBool::new(false));
    let waiting_for_python = Arc::new(AtomicBool::new(needs_python_backend));
    let registered_handlers: Arc<RwLock<Vec<String>>> = Arc::new(RwLock::new(Vec::new()));

    // Ready timeout guard for packed FullStack
    if needs_python_backend {
        let python_ready_for_timeout = python_ready.clone();
        let proxy_for_timeout = proxy.clone();
        let backend_for_timeout = python_backend_state.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(10));
            let is_ready = python_ready_for_timeout.load(Ordering::Relaxed);
            if !is_ready {
                tracing::warn!("[Rust] Python backend not ready after 10s, showing warning...");
                let _ = proxy_for_timeout.send_event(UserEvent::BackendError {
                    message: "Python backend initialization taking longer than expected..."
                        .to_string(),
                    source: "startup".to_string(),
                });
                let _ = proxy_for_timeout.send_event(UserEvent::LoadingUpdate {
                    progress: None,
                    text: Some("Backend initialization slow, please wait...".to_string()),
                    step_id: None,
                    step_text: None,
                    step_status: None,
                });

                std::thread::sleep(std::time::Duration::from_secs(20));
                let is_ready_final = python_ready_for_timeout.load(Ordering::Relaxed);
                if !is_ready_final {
                    let stderr = backend_for_timeout
                        .read()
                        .ok()
                        .and_then(|backend| {
                            backend.as_ref().map(|backend| backend.get_last_stderr())
                        })
                        .unwrap_or_default();
                    tracing::error!(
                        "[Rust] Python backend ready timeout after 30s, showing error page"
                    );
                    let _ = proxy_for_timeout.send_event(UserEvent::ShowError {
                        code: 503,
                        title: "Backend Initialization Failed".to_string(),
                        message: "The Python backend failed to initialize within the expected time.\n\nThis could be caused by:\n- Missing Python dependencies\n- Syntax errors in your application code\n- Import errors in your modules".to_string(),
                        details: Some(format!("The backend process may have crashed or is stuck.\nCheck the console output for more details.\n\n{stderr}")),
                        source: "python".to_string(),
                    });
                    let _ = proxy_for_timeout.send_event(UserEvent::PythonReady {
                        handlers: Vec::new(),
                    });
                }
            }
        });
    }

    // Create window
    let mut window_builder = tao::window::WindowBuilder::new()
        .with_title(&config.window.title)
        .with_inner_size(tao::dpi::LogicalSize::new(
            config.window.width,
            config.window.height,
        ))
        .with_resizable(config.window.resizable)
        .with_decorations(!config.window.frameless)
        .with_transparent(config.window.transparent)
        .with_always_on_top(config.window.always_on_top);

    if let (Some(min_w), Some(min_h)) = (config.window.min_width, config.window.min_height) {
        window_builder =
            window_builder.with_min_inner_size(tao::dpi::LogicalSize::new(min_w, min_h));
    }

    let icon = if let Some(ref icon_data) = config.window_icon {
        tracing::info!("Using custom window icon ({} bytes)", icon_data.len());
        load_window_icon_from_bytes(icon_data)
    } else {
        tracing::info!("Using default window icon");
        load_window_icon()
    };
    if let Some(icon) = icon {
        window_builder = window_builder.with_window_icon(Some(icon));
    }

    let window = window_builder
        .build(&event_loop)
        .with_context(|| "Failed to create window")?;

    metrics.mark_window_created();

    // Create WebContext
    let data_dir = get_webview_data_dir();
    let mut web_context = WebContext::new(Some(data_dir));

    // Build initialization script
    let mut init_script = build_packed_init_script_with_csp(
        config.content_security_policy.as_deref(),
        config.window.strict_csp,
    );

    if let Some(ref js_code) = config.inject_js {
        if !js_code.trim().is_empty() {
            tracing::info!("[packed] Injecting custom JS ({} bytes)", js_code.len());
            init_script.push('\n');
            init_script.push_str(js_code);
        }
    }

    if let Some(ref css_code) = config.inject_css {
        if !css_code.trim().is_empty() {
            tracing::info!("[packed] Injecting custom CSS ({} bytes)", css_code.len());
            let css_script = build_css_injection_script(css_code);
            init_script.push('\n');
            init_script.push_str(&css_script);
        }
    }

    // Clone for IPC handler
    let python_backend_for_ipc = python_backend_state.clone();
    let plugin_router_for_ipc = plugin_router.clone();
    let proxy_for_ipc = proxy.clone();

    // Drag-drop sink (RFC 0015) — single Arc shared across both PackMode
    // arms. Default `capture_file_drop = false` means the helper short-
    // circuits and the sink is never invoked.
    let dragdrop_sink = Arc::new(ipc::PackedDragDropSink::new(
        python_backend_state.clone(),
        plugin_router.clone(),
        proxy.clone(),
    ));
    let capture_file_drop = resolve_packed_capture_file_drop(config.capture_file_drop);

    // Create WebView
    let webview = match &config.mode {
        PackMode::Url { url } => {
            let normalized_url = normalize_url(url)?;
            tracing::info!("Loading URL: {}", normalized_url);

            let mut builder = WryWebViewBuilder::new_with_web_context(&mut web_context)
                .with_url(&normalized_url)
                .with_initialization_script(&init_script)
                .with_ipc_handler(move |request| {
                    ipc::handle_ipc_message(
                        request.body(),
                        &python_backend_for_ipc,
                        &plugin_router_for_ipc,
                        &proxy_for_ipc,
                    );
                })
                .with_devtools(config.debug);

            builder = auroraview_core::builder::attach_drag_drop_handler(
                builder,
                capture_file_drop,
                &dragdrop_sink,
            );

            builder
                .build(&window)
                .with_context(|| "Failed to create WebView")?
        }
        PackMode::Frontend { .. } | PackMode::FullStack { .. } => {
            let mut memory_assets = MemoryAssets::from_vec(overlay.assets.clone())
                .with_loading_html(get_loading_html());

            for path in auroraview_assets::list_assets() {
                if let Some(data) = auroraview_assets::get_asset(&path) {
                    memory_assets.insert(path, data.into_owned());
                }
            }

            let all_paths = memory_assets.list_paths();
            let _index_path = all_paths
                .iter()
                .find(|path| {
                    **path == "index.html"
                        || **path == "frontend/index.html"
                        || path.ends_with("/index.html")
                })
                .map(|p| (*p).clone())
                .unwrap_or_else(|| "index.html".to_string());

            #[cfg(target_os = "windows")]
            let (initial_url, _app_url) = if is_fullstack {
                (
                    "https://auroraview.localhost/__loading__",
                    "https://auroraview.localhost/index.html",
                )
            } else {
                (
                    "https://auroraview.localhost/index.html",
                    "https://auroraview.localhost/index.html",
                )
            };

            #[cfg(not(target_os = "windows"))]
            let (initial_url, _app_url) = if is_fullstack {
                (
                    "auroraview://localhost/__loading__",
                    "auroraview://localhost/index.html",
                )
            } else {
                (
                    "auroraview://localhost/index.html",
                    "auroraview://localhost/index.html",
                )
            };

            #[allow(unused_mut)]
            let mut builder = WryWebViewBuilder::new_with_web_context(&mut web_context);

            #[cfg(target_os = "windows")]
            let builder = builder.with_https_scheme(true);

            #[cfg(target_os = "windows")]
            let builder = {
                if config.extensions.bundle {
                    match extensions::install_bundled_extensions_from_assets(&overlay) {
                        Ok(count) => tracing::info!(
                            "[packed] Installed {} bundled extension asset file(s)",
                            count
                        ),
                        Err(e) => {
                            tracing::error!("[packed] Failed to install bundled extensions: {}", e)
                        }
                    }
                }

                let active_ext_dir = match prepare_active_extensions_dir(config.extensions.enabled)
                {
                    Ok(dir) => dir,
                    Err(e) => {
                        tracing::error!(
                            "[packed] Failed to prepare active extensions directory: {}",
                            e
                        );
                        get_extensions_dir()
                    }
                };

                if has_extensions_in_dir(&active_ext_dir) {
                    builder
                        .with_browser_extensions_enabled(true)
                        .with_extensions_path(active_ext_dir)
                } else {
                    tracing::info!("[packed] No enabled extensions to load");
                    builder
                }
            };

            #[cfg(target_os = "windows")]
            let builder = if let Some(port) = config.remote_debugging_port {
                let args = format!("--remote-debugging-port={}", port);
                builder.with_additional_browser_args(&args)
            } else {
                builder
            };

            let builder = builder
                .with_custom_protocol("auroraview".to_string(), move |_webview_id, request| {
                    let uri = request.uri();
                    let path = uri.path().trim_start_matches('/');

                    #[cfg(target_os = "windows")]
                    let allowed_origin = "https://auroraview.localhost";
                    #[cfg(not(target_os = "windows"))]
                    let allowed_origin = "auroraview://localhost";

                    #[cfg(target_os = "windows")]
                    if let Some(ext_path) = path.strip_prefix("extension/") {
                        return extensions::handle_extension_resource_request(
                            ext_path,
                            allowed_origin,
                        );
                    }

                    let response = memory_assets.handle_request(path);

                    wry::http::Response::builder()
                        .status(response.status)
                        .header("Content-Type", &response.mime_type)
                        .header("Access-Control-Allow-Origin", allowed_origin)
                        .body(response.data.into_owned().into())
                        .unwrap_or_else(|_| {
                            wry::http::Response::builder()
                                .status(500)
                                .body(Vec::new().into())
                                .expect("fallback 500 response with empty body")
                        })
                })
                .with_initialization_script(&init_script)
                .with_ipc_handler(move |request| {
                    ipc::handle_ipc_message(
                        request.body(),
                        &python_backend_for_ipc,
                        &plugin_router_for_ipc,
                        &proxy_for_ipc,
                    );
                })
                .with_url(initial_url)
                .with_devtools(config.debug);

            let builder = auroraview_core::builder::attach_drag_drop_handler(
                builder,
                capture_file_drop,
                &dragdrop_sink,
            );

            builder
                .build(&window)
                .with_context(|| "Failed to create WebView")?
        }
    };

    // Start Python backend
    if let PackMode::FullStack { ref python, .. } = config.mode {
        let overlay_for_backend = overlay.clone();
        let python_config = python.clone();
        let proxy_for_backend = proxy.clone();
        let backend_state_for_start = python_backend_state.clone();

        std::thread::spawn(move || {
            let mut backend_metrics = PackedMetrics::default();
            match start_python_backend_with_ipc(
                overlay_for_backend.as_ref(),
                &python_config,
                proxy_for_backend.clone(),
                &mut backend_metrics,
            ) {
                Ok(backend) => {
                    if let Ok(mut state) = backend_state_for_start.write() {
                        *state = Some(Arc::new(backend));
                    } else {
                        tracing::error!("Failed to store Python backend state: lock poisoned");
                    }
                }
                Err(e) => {
                    tracing::error!("Failed to start Python backend: {}", e);
                    let _ = proxy_for_backend.send_event(UserEvent::BackendError {
                        message: format!("Failed to start Python backend: {}", e),
                        source: "startup".to_string(),
                    });
                    let _ = proxy_for_backend.send_event(UserEvent::PythonReady {
                        handlers: Vec::new(),
                    });
                }
            }
        });
    }

    metrics.mark_webview_created();
    metrics.mark_total();

    tracing::info!(
        "Startup completed in {:.2}ms",
        metrics.elapsed().as_secs_f64() * 1000.0
    );
    metrics.log_report();

    let startup_metrics_payload = serde_json::json!({
        "total_ms": duration_to_ms(metrics.total),
        "overlay_read_ms": duration_to_ms(metrics.overlay_read),
        "config_decompress_ms": duration_to_ms(metrics.config_decompress),
        "assets_decompress_ms": duration_to_ms(metrics.assets_decompress),
        "tar_extract_ms": duration_to_ms(metrics.tar_extract),
        "python_runtime_extract_ms": duration_to_ms(metrics.python_runtime_extract),
        "python_files_extract_ms": duration_to_ms(metrics.python_files_extract),
        "resources_extract_ms": duration_to_ms(metrics.resources_extract),
        "python_start_ms": duration_to_ms(metrics.python_start),
        "window_created_ms": duration_to_ms(metrics.window_created),
        "webview_created_ms": duration_to_ms(metrics.webview_created),
        "is_fullstack": is_fullstack,
        "content_hash": overlay.content_hash,
    });
    let startup_metrics_payload_escaped = escape_json_for_js(&startup_metrics_payload.to_string());
    let startup_metrics_message = format!("[packed.startup.metrics] {}", startup_metrics_payload);
    capture_packed_sentry("info", &startup_metrics_message);
    let mut startup_metrics_sent = false;

    // Start process monitor thread
    if needs_python_backend {
        let backend_state_for_monitor = python_backend_state.clone();
        let proxy_for_monitor = proxy.clone();
        let python_ready_for_monitor = python_ready.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(1));

            loop {
                std::thread::sleep(std::time::Duration::from_millis(500));

                let backend = backend_state_for_monitor
                    .read()
                    .ok()
                    .and_then(|state| state.clone());

                let Some(backend) = backend else {
                    continue;
                };

                if backend.is_shutting_down() {
                    tracing::debug!("[ProcessMonitor] Shutdown detected, stopping monitor");
                    break;
                }

                if !backend.is_alive() {
                    let exit_code = backend.get_exit_code();
                    let stderr_output = backend.get_last_stderr();
                    let during_startup = !python_ready_for_monitor.load(Ordering::Relaxed);

                    tracing::error!(
                        "[ProcessMonitor] Python process crashed! exit_code={:?}, during_startup={}, stderr_len={}",
                        exit_code,
                        during_startup,
                        stderr_output.len()
                    );

                    let _ = proxy_for_monitor.send_event(UserEvent::PythonCrash {
                        exit_code,
                        stderr_output,
                        during_startup,
                    });
                    break;
                }
            }
            tracing::info!("[ProcessMonitor] Monitor thread exiting");
        });
    }

    // Wrap webview and window
    let webview = std::rc::Rc::new(std::cell::RefCell::new(webview));
    let webview_for_event = webview.clone();
    let window = std::rc::Rc::new(std::cell::RefCell::new(window));
    let window_for_event = window.clone();

    // Run event loop
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            tao::event::Event::WindowEvent {
                event: tao::event::WindowEvent::CloseRequested,
                ..
            } => {
                if let Ok(router) = plugin_router.read() {
                    let request = PluginRequest::new("process", "kill_all", serde_json::json!({}));
                    let _ = router.handle(request);
                }
                if let Some(backend) = python_backend_state
                    .read()
                    .ok()
                    .and_then(|state| state.clone())
                {
                    tracing::info!("Stopping Python backend...");
                    backend.shutdown();
                }
                *control_flow = ControlFlow::Exit;
            }
            tao::event::Event::UserEvent(user_event) => {
                if let Ok(wv) = webview_for_event.try_borrow() {
                    match user_event {
                        UserEvent::LoadingScreenReady => {
                            tracing::info!("[Rust] Loading screen is ready (DOM rendered)");
                            loading_screen_ready.store(true, Ordering::Relaxed);
                            if python_ready.load(Ordering::Relaxed) {
                                let script = r#"
                                    (function() {
                                        if (window.auroraview && window.auroraview.trigger) {
                                            window.auroraview.trigger('backend_ready', { ready: true });
                                        }
                                    })()
                                "#;
                                let _ = wv.evaluate_script(script);
                            }
                        }
                        UserEvent::PythonReady { handlers } => {
                            tracing::info!("[Rust] Python backend ready with {} handlers", handlers.len());
                            python_ready.store(true, Ordering::Relaxed);

                            if let Ok(mut stored) = registered_handlers.write() {
                                *stored = handlers.clone();
                            }

                            let register_script = helpers::build_api_registration_script(&handlers);
                            if !register_script.is_empty() {
                                let _ = wv.evaluate_script(&register_script);
                            }

                            if loading_screen_ready.load(Ordering::Relaxed) {
                                let script = r#"
                                    (function() {
                                        if (window.auroraview && window.auroraview.trigger) {
                                            window.auroraview.trigger('backend_ready', { ready: true });
                                        }
                                    })()
                                "#;
                                let _ = wv.evaluate_script(script);
                            }
                        }
                        UserEvent::NavigateToApp => {
                            tracing::info!("[Rust] Frontend requested navigation to app");
                            waiting_for_python.store(false, Ordering::Relaxed);
                            let do_navigate = |wv: &wry::WebView| {
                                #[cfg(target_os = "windows")]
                                let target_url = "https://auroraview.localhost/index.html";
                                #[cfg(not(target_os = "windows"))]
                                let target_url = "auroraview://localhost/index.html";

                                tracing::info!("[Rust] Navigating to: {}", target_url);
                                match wv.load_url(target_url) {
                                    Ok(_) => {
                                        tracing::info!("[Rust] Navigation initiated successfully");
                                    }
                                    Err(e) => {
                                        tracing::error!("[Rust] Failed to navigate to application: {}", e);
                                        capture_packed_sentry(
                                            "error",
                                            &format!("[packed.navigation] failed to navigate to app: {}", e),
                                        );
                                    }
                                }
                            };
                            do_navigate(&wv);
                        }
                        UserEvent::PageReady => {
                            tracing::info!("[Rust] Page ready - re-registering API methods");
                            if let Ok(handlers) = registered_handlers.read() {
                                if !handlers.is_empty() {
                                    let register_script = helpers::build_api_registration_script(&handlers);
                                    if !register_script.is_empty() {
                                        tracing::info!(
                                            "[Rust] Re-registering {} API handlers",
                                            handlers.len()
                                        );
                                        let _ = wv.evaluate_script(&register_script);
                                    }
                                }
                            }

                            if !startup_metrics_sent {
                                let startup_script = format!(
                                    r#"(function() {{
                                        try {{
                                            var data = JSON.parse('{}');
                                            if (window.auroraview && window.auroraview.trigger) {{
                                                window.auroraview.trigger('packed_startup_metrics', data);
                                            }}
                                        }} catch (e) {{
                                            console.error('[AuroraView] Failed to emit packed_startup_metrics:', e);
                                        }}
                                    }})()"#,
                                    startup_metrics_payload_escaped
                                );
                                match wv.evaluate_script(&startup_script) {
                                    Ok(_) => {
                                        startup_metrics_sent = true;
                                        tracing::info!("[Rust] Emitted packed_startup_metrics event");
                                    }
                                    Err(e) => {
                                        tracing::warn!(
                                            "[Rust] Failed to emit packed_startup_metrics event: {}",
                                            e
                                        );
                                    }
                                }
                            }
                        }
                        UserEvent::PythonResponse(response) => {
                            let escaped = escape_json_for_js(&response);
                            let script = format!(
                                r#"(function() {{
                                    if (window.auroraview && window.auroraview.trigger) {{
                                        try {{
                                            var data = JSON.parse("{}");
                                            window.auroraview.trigger('__auroraview_call_result', data);
                                        }} catch (e) {{
                                            console.error('[AuroraView] Failed to parse response:', e);
                                        }}
                                    }}
                                }})()"#,
                                escaped
                            );
                            let _ = wv.evaluate_script(&script);
                        }
                        UserEvent::PluginEvent { event, data } => {
                            tracing::debug!(
                                "[Rust:WebView] Received PluginEvent: event={}, data_len={}",
                                event,
                                data.len()
                            );
                            let script = format!(
                                r#"(function() {{
                                    if (window.auroraview && window.auroraview.trigger) {{
                                        try {{
                                            var data = {};
                                            window.auroraview.trigger('{}', data);
                                        }} catch (e) {{
                                            console.error('[AuroraView] Failed to process event data:', e);
                                        }}
                                    }} else {{
                                        console.warn('[AuroraView] Bridge not ready for event:', '{}');
                                    }}
                                }})()"#,
                                data, event, event
                            );
                            let _ = wv.evaluate_script(&script);
                        }
                        UserEvent::LoadingUpdate {
                            progress,
                            text,
                            step_id,
                            step_text,
                            step_status,
                        } => {
                            let mut updates = Vec::new();

                            if let Some(p) = progress {
                                updates.push(format!("window.auroraLoading.setProgress({});", p));
                            }
                            if let Some(t) = text {
                                let escaped_text = escape_js_string(&t);
                                updates.push(format!(
                                    "window.auroraLoading.setText('{}');",
                                    escaped_text
                                ));
                            }
                            if let (Some(id), Some(txt), Some(status)) =
                                (step_id, step_text, step_status)
                            {
                                let escaped_id = escape_js_string(&id);
                                let escaped_txt = escape_js_string(&txt);
                                let escaped_status = escape_js_string(&status);
                                updates.push(format!(
                                    "window.auroraLoading.setStep('{}', '{}', '{}');",
                                    escaped_id, escaped_txt, escaped_status
                                ));
                            }

                            if !updates.is_empty() {
                                let script = format!(
                                    "(function() {{ if (window.auroraLoading) {{ {} }} }})()",
                                    updates.join(" ")
                                );
                                let _ = wv.evaluate_script(&script);
                            }
                        }
                        UserEvent::BackendError { message, source } => {
                            let escaped_msg = escape_js_string(&message);
                            let escaped_source = escape_js_string(&source);
                            let script = format!(
                                r#"(function() {{
                                    if (window.auroraLoading && window.auroraLoading.addError) {{
                                        window.auroraLoading.addError('{}', '{}');
                                    }}
                                    if (window.auroraview && window.auroraview.trigger) {{
                                        window.auroraview.trigger('backend_error', {{
                                            message: '{}',
                                            source: '{}'
                                        }});
                                    }}
                                    console.error('[Backend:{}] {}');
                                }})()"#,
                                escaped_msg,
                                escaped_source,
                                escaped_msg,
                                escaped_source,
                                escaped_source,
                                escaped_msg
                            );
                            let _ = wv.evaluate_script(&script);
                            capture_packed_sentry(
                                "error",
                                &format!("[packed.backend_error][{}] {}", source, message),
                            );
                        }
                        UserEvent::SetHtml { html, title } => {
                            if let Some(new_title) = title {
                                if let Ok(win) = window_for_event.try_borrow() {
                                    win.set_title(&new_title);
                                }
                            }

                            let escaped_html = html
                                .replace('\\', "\\\\")
                                .replace('`', "\\`")
                                .replace("${", "\\${");

                            let script = format!(
                                r#"(function() {{
                                    document.open();
                                    document.write(`{}`);
                                    document.close();
                                }})()"#,
                                escaped_html
                            );

                            match wv.evaluate_script(&script) {
                                Ok(_) => {
                                    tracing::info!("[Rust] SetHtml: Successfully loaded dynamic HTML");
                                }
                                Err(e) => {
                                    tracing::error!(
                                        "[Rust] SetHtml: Failed to load HTML: {}",
                                        e
                                    );
                                }
                            }
                        }
                        UserEvent::CloseWindow => {
                            if let Ok(router) = plugin_router.read() {
                                let request = PluginRequest::new("process", "kill_all", serde_json::json!({}));
                                let _ = router.handle(request);
                            }
                            if let Some(backend) = python_backend_state
                                .read()
                                .ok()
                                .and_then(|state| state.clone())
                            {
                                tracing::info!("Stopping Python backend...");
                                backend.shutdown();
                            }
                            *control_flow = ControlFlow::Exit;
                        }
                        UserEvent::PythonCrash {
                            exit_code,
                            stderr_output,
                            during_startup,
                        } => {
                            let exit_info = match exit_code {
                                Some(code) => format!("Process exited with code: {}", code),
                                None => "Process terminated unexpectedly".to_string(),
                            };

                            let title = if during_startup {
                                "Python Backend Failed to Start"
                            } else {
                                "Python Backend Crashed"
                            };

                            let message = if during_startup {
                                format!(
                                    "The Python backend failed to start properly.\n\n{}\n\nCommon causes:\n- Syntax errors in Python code\n- Missing dependencies\n- Import errors\n- Invalid configuration",
                                    exit_info
                                )
                            } else {
                                format!(
                                    "The Python backend has unexpectedly terminated.\n\n{}\n\nThis may be caused by:\n- Unhandled exceptions\n- Memory issues\n- External termination",
                                    exit_info
                                )
                            };

                            let details = if stderr_output.is_empty() {
                                Some("No error output captured.".to_string())
                            } else {
                                let lines: Vec<&str> = stderr_output.lines().collect();
                                let truncated = if lines.len() > 50 {
                                    format!(
                                        "... ({} lines truncated)\n{}",
                                        lines.len() - 50,
                                        lines[lines.len() - 50..].join("\n")
                                    )
                                } else {
                                    stderr_output.clone()
                                };
                                Some(truncated)
                            };

                            let error_html = build_error_page(
                                500,
                                title,
                                &message,
                                details.as_deref(),
                                None,
                            );

                            let escaped_html = error_html
                                .replace('\\', "\\\\")
                                .replace('`', "\\`")
                                .replace("${", "\\${");

                            let script = format!(
                                r#"(function() {{
                                    document.open();
                                    document.write(`{}`);
                                    document.close();
                                }})()"#,
                                escaped_html
                            );

                            match wv.evaluate_script(&script) {
                                Ok(_) => {
                                    tracing::info!("[Rust] PythonCrash: Error page displayed successfully");
                                }
                                Err(e) => {
                                    tracing::error!(
                                        "[Rust] PythonCrash: Failed to display error page: {}",
                                        e
                                    );
                                }
                            }
                        }
                        UserEvent::ShowError {
                            code,
                            title,
                            message,
                            details,
                            source,
                        } => {
                            let sentry_detail_preview = details
                                .as_deref()
                                .map(|d| d.chars().take(2000).collect::<String>())
                                .unwrap_or_default();

                            capture_packed_sentry(
                                "error",
                                &format!(
                                    "[packed.show_error] code={} title={} source={} message={} details={}",
                                    code, title, source, message, sentry_detail_preview
                                ),
                            );

                            let error_html = build_error_page(
                                code,
                                &title,
                                &message,
                                details.as_deref(),
                                None,
                            );

                            let error_html_with_source = error_html.replace(
                                "</body>",
                                &format!(
                                    r#"<script>
                                    if (window._errorInfo) {{
                                        window._errorInfo.source = '{}';
                                    }}
                                    </script></body>"#,
                                    source
                                ),
                            );

                            let escaped_html = error_html_with_source
                                .replace('\\', "\\\\")
                                .replace('`', "\\`")
                                .replace("${", "\\${");

                            let script = format!(
                                r#"(function() {{
                                    document.open();
                                    document.write(`{}`);
                                    document.close();
                                }})()"#,
                                escaped_html
                            );

                            match wv.evaluate_script(&script) {
                                Ok(_) => {
                                    tracing::info!("[Rust] ShowError: Error page displayed successfully");
                                }
                                Err(e) => {
                                    tracing::error!(
                                        "[Rust] ShowError: Failed to display error page: {}",
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
            _ => {}
        }

        let _ = &webview;
        let _ = &window;
    });

    #[allow(unreachable_code)]
    Ok(())
}
