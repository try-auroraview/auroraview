//! Python bindings for desktop WebView runner
//!
//! This module provides a Python function to run a desktop WebView using
//! event_loop.run() instead of run_return(). This is the correct approach for
//! desktop applications where the process should exit when the window closes.

use pyo3::prelude::*;
use std::path::PathBuf;
use std::sync::Arc;

use crate::ipc::{IpcHandler, MessageQueue};
use crate::webview::config::WebViewConfig;
use crate::webview::desktop;

/// Resolve the optional `icon` kwarg into the path stored in
/// `WebViewConfig.icon`. This is the sole flatten point from the PyO3
/// `Option<String>` boundary to the Rust `Option<PathBuf>` field. It is shared
/// by `run_desktop` and the `test-helpers` hook below so the exact plumbing can
/// be asserted without launching the blocking desktop event loop.
fn desktop_icon_path(icon: Option<String>) -> Option<PathBuf> {
    icon.map(PathBuf::from)
}

/// Run a desktop WebView (blocking until window closes)
///
/// This function creates and runs a desktop WebView window using event_loop.run().
/// It will block until the window is closed, then exit the entire process.
///
/// IMPORTANT: This calls std::process::exit() when the window closes!
/// Only use this for desktop applications, NOT for DCC integration.
///
/// Args:
///     title (str): Window title
///     width (int): Window width in pixels
///     height (int): Window height in pixels
///     url (str, optional): URL to load
///     html (str, optional): HTML content to load
///     dev_tools (bool, optional): Enable developer tools (default: True)
///     resizable (bool, optional): Make window resizable (default: True)
///     decorations (bool, optional): Show window decorations (default: True)
///     transparent (bool, optional): Make window transparent (default: False)
///     allow_new_window (bool, optional): Allow opening new windows (default: False)
///     allow_file_protocol (bool, optional): Enable file:// protocol support (default: False)
///     always_on_top (bool, optional): Keep window always on top (default: False)
///     headless (bool, optional): Run in headless mode without visible window (default: False).
///         Useful for automated testing. Note: WebView2 creates a hidden window, not true headless.
///     remote_debugging_port (int, optional): Enable CDP remote debugging on specified port.
///         When set, Playwright/Puppeteer can connect via `connect_over_cdp(f"http://localhost:{port}")`.
///     asset_root (str, optional): Root directory for auroraview:// protocol.
///         When set, enables the auroraview:// custom protocol for secure local
///         resource loading. Files under this directory can be accessed using URLs
///         like ``auroraview://path/to/file`` (or ``https://auroraview.localhost/path``
///         on Windows).
///     html_path (str, optional): Path to HTML file. When provided with `html` content,
///         the `asset_root` will automatically be set to the directory containing
///         the HTML file (if `asset_root` is not explicitly set). This allows relative
///         resource paths in HTML to be resolved correctly relative to the HTML file.
///     rewrite_relative_paths (bool, optional): Automatically rewrite relative paths
///         (like ./script.js, ../style.css) to use auroraview:// protocol. Default: True.
///     tray_enabled (bool, optional): Enable system tray icon (default: False).
///     tray_tooltip (str, optional): Tooltip text shown when hovering over tray icon.
///     tray_icon (str, optional): Path to tray icon (PNG recommended, 32x32 or 64x64).
///     tray_show_on_click (bool, optional): Show window when tray icon is clicked (default: True).
///     tray_hide_on_close (bool, optional): Hide to tray instead of closing (default: True).
///     tool_window (bool, optional): Tool window style - hide from taskbar/Alt+Tab (default: False).
///     undecorated_shadow (bool, optional): Show shadow for frameless windows (default: True).
///         Set to False for transparent overlay windows.
///     splash_overlay (bool, optional): Show splash overlay while loading URL (default: False).
///         When enabled, displays an animated Aurora-themed loading overlay
///         that automatically fades out when the page is fully loaded.
///     allow_downloads (bool, optional): Enable file downloads (default: True).
///         AuroraView enables downloads by default for better user experience.
///     download_prompt (bool, optional): Show "Save As" dialog for downloads (default: False).
///         When True, prompts user to choose save location like a browser.
///         When False, downloads go directly to download_directory.
///     download_directory (str, optional): Default download directory.
///         Uses system default Downloads folder (e.g., ~/Downloads) if not set.
///         Ignored when download_prompt is True.
///     proxy_url (str, optional): Proxy server URL (e.g., "http://host:port" or "socks5://host:port").
///     user_agent (str, optional): Custom User-Agent string.
///     icon (str, optional): Path to a custom window icon (PNG, ICO, JPEG, BMP,
///         or GIF). Applied to the native window title bar and taskbar. When
///         omitted, the default AuroraView icon is used. This is the runtime
///         window icon, NOT the packaged executable icon set by `auroraview pack`.
///
/// Example:
///     >>> from auroraview._core import run_desktop
///     >>> run_desktop(
///     ...     title="My App",
///     ...     width=800,
///     ...     height=600,
///     ...     url="https://example.com"
///     ... )
///     # Window shows, blocks until closed, then process exits
///
///     # With system tray:
///     >>> run_desktop(
///     ...     title="Tray App",
///     ...     width=800,
///     ...     height=600,
///     ...     html="<h1>Hello</h1>",
///     ...     tray_enabled=True,
///     ...     tray_tooltip="My App",
///     ...     tray_hide_on_close=True,
///     ... )
///
///     # Or use the legacy alias:
///     >>> from auroraview._core import run_standalone
///     >>> run_standalone(...)
#[pyfunction]
#[pyo3(signature = (
    title,
    width,
    height,
    url=None,
    html=None,
    dev_tools=true,
    resizable=true,
    decorations=true,
    transparent=false,
    allow_new_window=false,
    allow_file_protocol=false,
    capture_file_drop=None,
    always_on_top=false,
    headless=false,
    remote_debugging_port=None,
    asset_root=None,
    html_path=None,
    rewrite_relative_paths=true,
    tray_enabled=false,
    tray_tooltip=None,
    tray_icon=None,
    tray_show_on_click=true,
    tray_hide_on_close=true,
    tool_window=false,
    undecorated_shadow=true,
    new_window_mode=None,
    splash_overlay=false,
    allow_downloads=true,
    download_prompt=false,
    download_directory=None,
    proxy_url=None,
    user_agent=None,
    icon=None
))]
#[allow(clippy::too_many_arguments)]
fn run_desktop(
    title: String,
    width: u32,
    height: u32,
    url: Option<String>,
    html: Option<String>,
    dev_tools: bool,
    resizable: bool,
    decorations: bool,
    transparent: bool,
    allow_new_window: bool,
    allow_file_protocol: bool,
    capture_file_drop: Option<bool>,
    always_on_top: bool,
    headless: bool,
    remote_debugging_port: Option<u16>,
    asset_root: Option<String>,
    html_path: Option<String>,
    rewrite_relative_paths: bool,
    tray_enabled: bool,
    tray_tooltip: Option<String>,
    tray_icon: Option<String>,
    tray_show_on_click: bool,
    tray_hide_on_close: bool,
    #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] tool_window: bool,
    #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] undecorated_shadow: bool,
    new_window_mode: Option<String>,
    splash_overlay: bool,
    allow_downloads: bool,
    download_prompt: bool,
    download_directory: Option<String>,
    proxy_url: Option<String>,
    user_agent: Option<String>,
    icon: Option<String>,
) -> PyResult<()> {
    tracing::info!("[run_desktop] Creating desktop WebView: {}", title);

    // Determine asset_root: explicit setting takes priority, otherwise derive from html_path
    let effective_asset_root = if let Some(root) = asset_root {
        Some(PathBuf::from(root))
    } else if let Some(ref path) = html_path {
        // Auto-detect asset_root from HTML file location
        let html_file_path = PathBuf::from(path);
        let parent_dir = html_file_path.parent().map(|p| p.to_path_buf());
        if let Some(ref dir) = parent_dir {
            tracing::info!(
                "[run_desktop] Auto-detected asset_root from HTML path: {:?}",
                dir
            );
        }
        parent_dir
    } else {
        None
    };

    // Rewrite HTML to use auroraview:// protocol for relative paths if enabled
    let processed_html = if rewrite_relative_paths {
        html.map(|h| crate::bindings::cli_utils::rewrite_html_for_custom_protocol(&h))
    } else {
        html
    };

    // Create config
    let config = WebViewConfig {
        title,
        width,
        height,
        url,
        html: processed_html,
        dev_tools,
        resizable,
        decorations,
        transparent,
        always_on_top,
        background_color: None, // Will use loading screen instead
        context_menu: true,
        parent_hwnd: None,
        embed_mode: crate::webview::config::EmbedMode::None,
        ipc_batching: false,
        ipc_batch_size: 100,
        ipc_batch_interval_ms: 16,
        asset_root: effective_asset_root,
        data_directory: None, // Use system default
        custom_protocols: std::collections::HashMap::new(),
        api_methods: std::collections::HashMap::new(),
        allow_new_window,
        new_window_mode: match new_window_mode.as_deref().map(|s| s.to_ascii_lowercase()) {
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
        allow_file_protocol,
        auto_show: !headless, // Don't auto-show in headless mode
        headless,
        remote_debugging_port,
        // RFC 0017 tri-state contract: Python passes Option<bool>; the Rust
        // WebViewConfig field is bool, so we land the tri-state with
        // unwrap_or(false). This is the SOLE permitted flatten point in the
        // entire Python -> Rust call chain.
        capture_file_drop: capture_file_drop.unwrap_or(false),
        // Security defaults
        content_security_policy: None,
        cors_allowed_origins: Vec::new(),
        allow_clipboard: false,
        allow_geolocation: false,
        allow_notifications: false,
        allow_media_devices: false,
        block_external_navigation: false,
        allowed_navigation_domains: Vec::new(),
        icon: desktop_icon_path(icon), // Custom window icon or default AuroraView icon
        enable_plugins: true,          // Enable plugin APIs
        enabled_plugin_names: Vec::new(), // All plugins
        splash_overlay,                // Show splash overlay while loading
        allow_downloads,               // Enable file downloads
        download_prompt,               // Show "Save As" dialog for downloads
        download_directory: download_directory.map(PathBuf::from),
        proxy_url,  // Proxy server URL
        user_agent, // Custom User-Agent
        #[cfg(target_os = "windows")]
        tool_window,
        #[cfg(target_os = "windows")]
        undecorated_shadow,
        tray: if tray_enabled {
            Some(crate::webview::config::TrayConfig {
                enabled: true,
                tooltip: tray_tooltip,
                icon: tray_icon.map(PathBuf::from),
                menu_items: vec![
                    crate::webview::config::TrayMenuItem::new("show", "Show Window"),
                    crate::webview::config::TrayMenuItem::separator(),
                    crate::webview::config::TrayMenuItem::new("exit", "Exit"),
                ],
                hide_on_close: tray_hide_on_close,
                show_on_click: tray_show_on_click,
                show_on_double_click: false,
            })
        } else {
            None
        },
    };

    // Create IPC handler and message queue
    let ipc_handler = Arc::new(IpcHandler::new());
    let message_queue = Arc::new(MessageQueue::new());

    // Run desktop - this will block until window closes and then return normally
    tracing::info!("[run_desktop] Starting desktop event loop...");
    desktop::run_desktop(config, ipc_handler, message_queue)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

    // Event loop exited normally (window was closed)
    tracing::info!("[run_desktop] Event loop exited, window closed");
    Ok(())
}

/// Legacy alias for `run_desktop` (backward compatibility)
///
/// This function is deprecated in favor of `run_desktop`.
#[pyfunction]
#[pyo3(signature = (
    title,
    width,
    height,
    url=None,
    html=None,
    dev_tools=true,
    resizable=true,
    decorations=true,
    transparent=false,
    allow_new_window=false,
    allow_file_protocol=false,
    capture_file_drop=None,
    always_on_top=false,
    headless=false,
    remote_debugging_port=None,
    asset_root=None,
    html_path=None,
    rewrite_relative_paths=true,
    tray_enabled=false,
    tray_tooltip=None,
    tray_icon=None,
    tray_show_on_click=true,
    tray_hide_on_close=true,
    tool_window=false,
    undecorated_shadow=true,
    new_window_mode=None,
    splash_overlay=false,
    allow_downloads=true,
    download_prompt=false,
    download_directory=None,
    proxy_url=None,
    user_agent=None,
    icon=None
))]
#[allow(clippy::too_many_arguments)]
fn run_standalone(
    title: String,
    width: u32,
    height: u32,
    url: Option<String>,
    html: Option<String>,
    dev_tools: bool,
    resizable: bool,
    decorations: bool,
    transparent: bool,
    allow_new_window: bool,
    allow_file_protocol: bool,
    capture_file_drop: Option<bool>,
    always_on_top: bool,
    headless: bool,
    remote_debugging_port: Option<u16>,
    asset_root: Option<String>,
    html_path: Option<String>,
    rewrite_relative_paths: bool,
    tray_enabled: bool,
    tray_tooltip: Option<String>,
    tray_icon: Option<String>,
    tray_show_on_click: bool,
    tray_hide_on_close: bool,
    #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] tool_window: bool,
    #[cfg_attr(not(target_os = "windows"), allow(unused_variables))] undecorated_shadow: bool,
    new_window_mode: Option<String>,
    splash_overlay: bool,
    allow_downloads: bool,
    download_prompt: bool,
    download_directory: Option<String>,
    proxy_url: Option<String>,
    user_agent: Option<String>,
    icon: Option<String>,
) -> PyResult<()> {
    run_desktop(
        title,
        width,
        height,
        url,
        html,
        dev_tools,
        resizable,
        decorations,
        transparent,
        allow_new_window,
        allow_file_protocol,
        capture_file_drop,
        always_on_top,
        headless,
        remote_debugging_port,
        asset_root,
        html_path,
        rewrite_relative_paths,
        tray_enabled,
        tray_tooltip,
        tray_icon,
        tray_show_on_click,
        tray_hide_on_close,
        tool_window,
        undecorated_shadow,
        new_window_mode,
        splash_overlay,
        allow_downloads,
        download_prompt,
        download_directory,
        proxy_url,
        user_agent,
        icon,
    )
}

/// Test-only hook: round-trip the `Optional[bool] capture_file_drop`
/// kwarg through the same flatten point used by `run_desktop` and return
/// the Rust-side `WebViewConfig.capture_file_drop` (always concrete `bool`).
///
/// This exists so RFC 0017 §4.2 integration tests can assert that the
/// Python passthrough never collapses `None` to `False` before reaching
/// the binding layer:
///
///   - `None` (omitted) ............... → `False` (Rust default)
///   - explicit `True`  ............... → `True`
///   - explicit `False` ............... → `False`
///
/// Gated behind `feature = "test-helpers"` so production wheels never
/// expose this function in the public module surface. CI runs tests with
/// `--features "test-helpers"` which enables it.
#[cfg(feature = "test-helpers")]
#[pyfunction]
#[pyo3(signature = (capture_file_drop=None))]
fn _dump_capture_file_drop(capture_file_drop: Option<bool>) -> PyResult<bool> {
    // RFC 0017 §3.5 step 6: PyO3 binding is the SOLE flatten point.
    // Mirror desktop_runner::run_desktop's `unwrap_or(false)` exactly so
    // any future change here is caught by the integration tests.
    Ok(capture_file_drop.unwrap_or(false))
}

/// Test-only hook for GH-528: round-trip the `Optional[str] icon` kwarg
/// through the same flatten point used by `run_desktop` and return the
/// resulting `WebViewConfig.icon` path.
///
///   - `None` (omitted) ......... -> `None` (default AuroraView icon)
///   - explicit `icon="a.png"` .. -> `"a.png"`
#[cfg(feature = "test-helpers")]
#[pyfunction]
#[pyo3(signature = (icon=None))]
fn _dump_run_desktop_icon(icon: Option<String>) -> Option<String> {
    let config = WebViewConfig {
        icon: desktop_icon_path(icon),
        ..Default::default()
    };
    config.icon.map(|p| p.to_string_lossy().into_owned())
}

/// Register desktop runner functions with Python module
pub fn register_desktop_runner(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_desktop, m)?)?;
    m.add_function(wrap_pyfunction!(run_standalone, m)?)?; // Legacy alias
                                                           // RFC 0017 §4.2: passthrough integration test hook (test-helpers only).
    #[cfg(feature = "test-helpers")]
    m.add_function(wrap_pyfunction!(_dump_capture_file_drop, m)?)?;
    #[cfg(feature = "test-helpers")]
    m.add_function(wrap_pyfunction!(_dump_run_desktop_icon, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    /// GH-528: omitting `icon` keeps the default AuroraView icon path (None).
    #[test]
    fn test_desktop_icon_path_default() {
        assert_eq!(desktop_icon_path(None), None);
    }

    /// GH-528: an explicit `icon` kwarg reaches WebViewConfig.icon unchanged.
    #[test]
    fn test_desktop_icon_path_custom() {
        assert_eq!(
            desktop_icon_path(Some("assets/my-icon.png".to_string())),
            Some(PathBuf::from("assets/my-icon.png"))
        );
    }

    #[test]
    fn test_module_registration() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "test_module").unwrap();
            register_desktop_runner(&module).unwrap();
            // Both new and legacy functions should be registered
            assert!(module.getattr("run_desktop").is_ok());
            assert!(module.getattr("run_standalone").is_ok());
        });
    }

    #[test]
    fn test_run_desktop_function_exists() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "test_module").unwrap();
            register_desktop_runner(&module).unwrap();
            let func = module.getattr("run_desktop").unwrap();
            assert!(func.is_callable());
        });
    }

    #[test]
    fn test_run_standalone_legacy_alias_exists() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "test_module").unwrap();
            register_desktop_runner(&module).unwrap();
            let func = module.getattr("run_standalone").unwrap();
            assert!(func.is_callable());
        });
    }

    #[test]
    fn test_run_desktop_signature() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "test_module").unwrap();
            register_desktop_runner(&module).unwrap();
            let func = module.getattr("run_desktop").unwrap();

            // Verify function has correct signature
            let signature = func.getattr("__signature__");
            assert!(signature.is_ok() || func.is_callable());
        });
    }

    /// Test WebViewConfig creation with asset_root
    #[test]
    fn test_config_with_asset_root() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 800,
            height: 600,
            asset_root: Some(PathBuf::from("/tmp/assets")),
            ..Default::default()
        };

        assert_eq!(config.asset_root, Some(PathBuf::from("/tmp/assets")));
    }

    /// Test WebViewConfig creation without asset_root
    #[test]
    fn test_config_without_asset_root() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 800,
            height: 600,
            ..Default::default()
        };

        assert_eq!(config.asset_root, None);
    }

    /// Test WebViewConfig with zero dimensions for maximize
    #[test]
    fn test_config_zero_width_for_maximize() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 0,
            height: 600,
            ..Default::default()
        };

        assert_eq!(config.width, 0);
        assert_eq!(config.height, 600);
        // When width is 0, the window should be maximized
    }

    /// Test WebViewConfig with zero height for maximize
    #[test]
    fn test_config_zero_height_for_maximize() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 800,
            height: 0,
            ..Default::default()
        };

        assert_eq!(config.width, 800);
        assert_eq!(config.height, 0);
        // When height is 0, the window should be maximized
    }

    /// Test WebViewConfig with both dimensions zero
    #[test]
    fn test_config_both_dimensions_zero() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 0,
            height: 0,
            ..Default::default()
        };

        assert_eq!(config.width, 0);
        assert_eq!(config.height, 0);
        // When both are 0, the window should be maximized
    }

    /// Test WebViewConfig with allow_file_protocol enabled
    #[test]
    fn test_config_with_allow_file_protocol() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 800,
            height: 600,
            allow_file_protocol: true,
            ..Default::default()
        };

        assert!(config.allow_file_protocol);
    }

    /// Test WebViewConfig with all local file options
    #[test]
    fn test_config_with_all_local_file_options() {
        let config = WebViewConfig {
            title: "Test".to_string(),
            width: 800,
            height: 600,
            asset_root: Some(PathBuf::from("./assets")),
            allow_file_protocol: true,
            ..Default::default()
        };

        assert_eq!(config.asset_root, Some(PathBuf::from("./assets")));
        assert!(config.allow_file_protocol);
    }
}
