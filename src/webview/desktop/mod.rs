//! Desktop mode - WebView with its own window
//!
//! This module handles creating WebView instances in desktop mode,
//! where the WebView creates and manages its own window.
//!
//! # Examples
//!
//! From Python (recommended):
//! ```python
//! from auroraview._core import run_desktop
//!
//! run_desktop(
//!     title="My App",
//!     width=800,
//!     height=600,
//!     url="https://example.com"
//! )
//!
//! # Or use the legacy alias:
//! from auroraview._core import run_standalone
//! run_standalone(...)
//! ```
//!
//! From Rust (internal use):
//! ```ignore
//! // This module is internal, use Python bindings instead
//! use auroraview_core::webview::config::WebViewConfig;
//! use auroraview_core::ipc::{IpcHandler, MessageQueue};
//! use std::sync::Arc;
//!
//! let config = WebViewConfig {
//!     title: "My App".to_string(),
//!     width: 800,
//!     height: 600,
//!     url: Some("https://example.com".to_string()),
//!     ..Default::default()
//! };
//!
//! let ipc_handler = Arc::new(IpcHandler::new());
//! let message_queue = Arc::new(MessageQueue::new());
//!
//! // This will create a desktop window and run the event loop
//! // Note: This is a blocking call that will run until the window is closed
//! ```

use std::sync::{Arc, Mutex};

use super::config::WebViewConfig;
use super::event_loop::WindowStyleHints;
use super::webview_inner::WebViewInner;
use crate::ipc::{IpcHandler, MessageQueue};

// Use shared builder utilities from auroraview-core
#[cfg(target_os = "windows")]
use auroraview_core::builder::{
    apply_child_window_style, apply_frameless_popup_window_style, apply_owner_window_style,
    apply_tool_window_style, disable_window_shadow, fix_webview2_child_windows,
    remove_clip_children_style, set_window_class_dark_background, subclass_for_zero_nc_area,
    ChildWindowStyleOptions,
};

// Sub-modules
mod event_loop;
mod icon;
mod webview_builder;
mod window_builder;

// Re-exports
pub use event_loop::run_desktop;
pub use webview_builder::configure_webview_builder;
#[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
pub(crate) use webview_builder::{configure_with_context, create_web_context};
pub use window_builder::create_window_and_event_loop;

/// Create desktop WebView with its own window
///
/// This function creates a WebView instance with its own window and event loop.
/// The window starts hidden to avoid white flash and shows a loading screen.
///
/// # Examples
///
/// ```ignore
/// // This is an internal function, use run_desktop from Python bindings instead
/// use auroraview_core::webview::config::WebViewConfig;
/// use auroraview_core::ipc::{IpcHandler, MessageQueue};
/// use std::sync::Arc;
///
/// let config = WebViewConfig {
///     title: "My App".to_string(),
///     width: 800,
///     height: 600,
///     url: Some("https://example.com".to_string()),
///     ..Default::default()
/// };
///
/// let ipc_handler = Arc::new(IpcHandler::new());
/// let message_queue = Arc::new(MessageQueue::new());
///
/// // Internal use only - called by run_desktop
/// // let webview = create_desktop(config, ipc_handler, message_queue).unwrap();
/// ```
pub fn create_desktop(
    config: WebViewConfig,
    ipc_handler: Arc<IpcHandler>,
    message_queue: Arc<MessageQueue>,
) -> Result<WebViewInner, Box<dyn std::error::Error>> {
    // Clean up stale WebView2 user data directories from crashed processes
    // This prevents initialization hangs due to orphaned LOCK files
    #[cfg(target_os = "windows")]
    {
        match super::cleanup::cleanup_stale_webview_dirs() {
            Ok(count) if count > 0 => {
                tracing::info!(
                    "[standalone] Cleaned up {} stale WebView2 directories",
                    count
                );
            }
            Err(e) => {
                tracing::warn!("[standalone] Failed to clean up stale directories: {}", e);
            }
            _ => {}
        }
    }

    // Debug: Log config values
    #[cfg(target_os = "windows")]
    tracing::info!(
        "[standalone] create_desktop config: title='{}', width={}, height={}, decorations={}, transparent={}, undecorated_shadow={}",
        config.title,
        config.width,
        config.height,
        config.decorations,
        config.transparent,
        config.undecorated_shadow
    );

    #[cfg(not(target_os = "windows"))]
    tracing::info!(
        "[standalone] create_desktop config: title='{}', width={}, height={}, decorations={}, transparent={}",
        config.title,
        config.width,
        config.height,
        config.decorations,
        config.transparent
    );

    // Use helper to create window and event loop
    let (window, event_loop) = create_window_and_event_loop(&config)?;

    // Apply window styles based on embed mode
    #[cfg(target_os = "windows")]
    {
        use crate::webview::config::EmbedMode;
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};

        if let Ok(window_handle) = window.window_handle() {
            if let RawWindowHandle::Win32(handle) = window_handle.as_raw() {
                let hwnd = handle.hwnd.get();

                if let Some(parent) = config.parent_hwnd {
                    match config.embed_mode {
                        EmbedMode::Child => {
                            let _ = apply_child_window_style(
                                hwnd,
                                parent as isize,
                                ChildWindowStyleOptions::for_standalone(),
                            );
                        }
                        EmbedMode::Owner => {
                            // Set owner relationship using GWLP_HWNDPARENT
                            apply_owner_window_style(hwnd, parent, config.tool_window);
                        }
                        EmbedMode::None => {}
                    }
                }
                // NOTE: Tool window style for standalone windows (without owner) is
                // applied AFTER WebView2 creation to avoid HRESULT 0x80070057 error.
                // See the apply_tool_window_style call after webview_builder.build().
            }
        }
    }

    // No manual SetParent needed when using builder-ext on Windows

    // Create WebContext with unique user data folder per process
    // Priority: 1. config.data_directory, 2. process-unique cache, 3. system default
    //
    // CRITICAL: On Windows, WebView2 has issues when multiple processes share the same
    // user data folder. The first process becomes the "browser process" and if it exits
    // while other processes are still initializing, those processes will hang indefinitely.
    //
    // Strategy: Use process ID to ensure each process has its own WebView2 data folder.
    // This trades disk space for reliability - each process gets isolated WebView2 state.
    // Use helper to configure WebView builder
    let build_start = std::time::Instant::now();
    let webview_builder =
        configure_webview_builder(&config, ipc_handler.clone(), message_queue.clone(), &window)?;
    let webview = webview_builder.build(&window)?;
    tracing::info!("[standalone] webview_builder.build() returned successfully");
    let build_duration = build_start.elapsed();

    tracing::info!(
        "[standalone] WebView created successfully in {:.2}s",
        build_duration.as_secs_f64()
    );

    // Note: URL or HTML was already loaded via with_url() or with_html() above
    // No need for additional load_url() call

    // Create event loop proxy for sending close events
    let event_loop_proxy = event_loop.create_proxy();

    // CRITICAL: Set event loop proxy in message queue for immediate wake-up
    // Without this, messages pushed to queue won't wake the event loop!
    message_queue.set_event_loop_proxy(event_loop_proxy.clone());
    tracing::info!("[standalone] Event loop proxy set in message queue for wake-up");

    // Create lifecycle manager
    use crate::webview::lifecycle::LifecycleManager;
    let lifecycle = Arc::new(LifecycleManager::new());
    lifecycle.set_state(crate::webview::lifecycle::LifecycleState::Active);

    // Determine auto_show: false in headless mode
    let auto_show = config.auto_show && !config.headless;

    // Cache HWND before creating WebViewInner (window may be moved during event loop)
    #[cfg(target_os = "windows")]
    let cached_hwnd = {
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};
        if let Ok(window_handle) = window.window_handle() {
            let raw_handle = window_handle.as_raw();
            if let RawWindowHandle::Win32(handle) = raw_handle {
                Some(handle.hwnd.get() as u64)
            } else {
                None
            }
        } else {
            None
        }
    };

    // Force-remove title bar/borders if decorations are disabled.
    // This is a Win32 fallback for cases where tao/wry doesn't fully honor with_decorations(false)
    // on Windows 11 (observed with transparent frameless windows).
    #[cfg(target_os = "windows")]
    if !config.decorations {
        if let Some(hwnd) = cached_hwnd {
            let _ = apply_frameless_popup_window_style(hwnd as isize);
        }
    }

    // Apply tool window style AFTER WebView2 is created
    // Doing this before WebView2 creation causes HRESULT 0x80070057 (E_INVALIDARG)
    #[cfg(target_os = "windows")]
    if config.tool_window {
        if let Some(hwnd) = cached_hwnd {
            apply_tool_window_style(hwnd as isize);
        }
    }

    // Disable window shadow for transparent frameless windows
    // undecorated_shadow=false means we want to disable the shadow
    #[cfg(target_os = "windows")]
    if !config.undecorated_shadow {
        if let Some(hwnd) = cached_hwnd {
            disable_window_shadow(hwnd as isize);
            tracing::info!("[standalone] Disabled window shadow (undecorated_shadow=false)");
        }
    }

    // Standalone (top-level) frameless windows need the same anti-white-border
    // treatment as the embedded path:
    //   1. dark window class background brush, so the WebView2 content not yet
    //      covering the client area does not reveal the system white brush;
    //   2. strip the WebView2 child windows' edge extended styles and subclass
    //      them to zero the NC area (the main source of the white border);
    //   3. subclass the top-level WS_POPUP window itself to force WM_NCCALCSIZE
    //      to return a zero NC area. apply_frameless_popup_window_style only
    //      strips style bits + SWP_FRAMECHANGED, which on Windows 11 still leaves
    //      a 1px non-client frame that DefWindowProc paints white. The embedded
    //      path avoids this because apply_child_window_style already subclasses
    //      the top-level HWND; the standalone path must do it explicitly.
    #[cfg(target_os = "windows")]
    if !config.decorations {
        if let Some(hwnd) = cached_hwnd {
            // Transparent windows must NOT get an opaque dark brush — it would
            // show through as a solid #020617 background, defeating transparency.
            // The other frameless fixes (child-window styling, NC-area zeroing)
            // still apply.
            if !config.transparent {
                set_window_class_dark_background(hwnd as isize);
            }
            fix_webview2_child_windows(hwnd as isize, config.transparent);
            subclass_for_zero_nc_area(hwnd as isize);
            tracing::info!("[standalone] Applied frameless white-border fix (dark background brush skipped for transparent={}), fixed WebView2 child windows, and zeroed top-level NC area", config.transparent);
        } else {
            tracing::warn!("[standalone] frameless window requested but no cached HWND is available; skipping white-border fix (dark background, child-window fix, NC-area zeroing)");
        }
    }

    // Extend DWM frame into client area for transparent windows
    // This fixes rendering artifacts (black stripes) when dragging transparent windows
    #[cfg(target_os = "windows")]
    {
        tracing::info!("[standalone] Checking transparent window optimizations: transparent={}, cached_hwnd={:?}", config.transparent, cached_hwnd);
        if config.transparent {
            use auroraview_core::builder::{
                extend_frame_into_client_area, optimize_transparent_window_resize,
            };
            if let Some(hwnd) = cached_hwnd {
                // CRITICAL: Remove WS_CLIPCHILDREN to fix transparency on Windows 11
                // See: https://github.com/tauri-apps/wry/issues/1212
                // tao/winit adds WS_CLIPCHILDREN by default, which prevents child windows
                // (WebView2) from rendering transparent content correctly.
                remove_clip_children_style(hwnd as isize);
                tracing::info!("[standalone] Removed WS_CLIPCHILDREN for transparent window");

                extend_frame_into_client_area(hwnd as isize);
                tracing::info!("[standalone] Extended DWM frame for transparent window");

                // Optimize resize performance for transparent windows
                optimize_transparent_window_resize(hwnd as isize);
                tracing::info!("[standalone] Applied transparent window resize optimization");
            }
        }
    }

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

    // Register instance to file-based registry for MCP discovery
    // This enables unified discovery for both packed and unpacked modes
    let cdp_port = config.remote_debugging_port.unwrap_or(0);
    if cdp_port > 0 {
        let window_id = format!("webview_{}", std::process::id());
        let instance_info =
            crate::service_discovery::InstanceInfo::new(window_id, config.title.clone(), cdp_port);
        if let Err(e) = crate::service_discovery::get_registry().register(&instance_info) {
            tracing::warn!("[standalone] Failed to register instance: {}", e);
        } else {
            tracing::info!(
                "[standalone] Instance registered for CDP discovery (port {})",
                cdp_port
            );
        }
    }

    #[allow(clippy::arc_with_non_send_sync)]
    Ok(WebViewInner {
        webview: Arc::new(Mutex::new(webview)),
        window: Some(window),
        event_loop: Some(event_loop),
        message_queue,
        event_loop_proxy: Some(event_loop_proxy),
        lifecycle,
        auto_show,
        #[cfg(target_os = "windows")]
        backend: None, // Only used in DCC mode
        #[cfg(target_os = "windows")]
        cached_hwnd,
        window_style_hints,
    })
}

/// Run desktop WebView with event_loop.run() (blocking until window closes)
///
/// This function is designed for desktop applications where the WebView owns
/// the event loop and the process should exit when the window closes.
/// It uses event_loop.run() which calls std::process::exit() on completion.
///
/// IMPORTANT: This will terminate the entire process when the window closes!
/// Only use this for desktop mode, NOT for DCC integration (embedded mode).
///
/// Use cases:
/// - Desktop Python scripts
/// - CLI applications
/// - Desktop applications
///
/// # Examples
///
/// From Python:
/// ```python
/// from auroraview._core import run_desktop
///
/// run_desktop(
///     title="My App",
///     width=1024,
///     height=768,
///     url="https://example.com"
/// )
///
/// # Or use the legacy alias:
/// from auroraview._core import run_standalone
/// run_standalone(...)
/// ```
///
/// From Rust (internal use):
/// ```ignore
/// // This is an internal function, use Python bindings instead
/// use auroraview_core::webview::config::WebViewConfig;
/// use auroraview_core::ipc::{IpcHandler, MessageQueue};
/// use std::sync::Arc;
///
/// let config = WebViewConfig {
///     title: "My Desktop App".to_string(),
///     width: 1024,
///     height: 768,
///     url: Some("https://example.com".to_string()),
///     ..Default::default()
/// };
///
/// let ipc_handler = Arc::new(IpcHandler::new());
/// let message_queue = Arc::new(MessageQueue::new());
///
/// // This will block until the window is closed and then exit the process
/// // run_desktop(config, ipc_handler, message_queue).unwrap();
/// ```
/// Load window icon from custom path or use embedded default
///
/// # Arguments
/// * `custom_icon` - Optional path to custom icon file (PNG, ICO, JPEG, BMP, GIF)
///
/// # Icon Requirements
/// - **Format**: PNG (recommended), ICO, JPEG, BMP, GIF
/// - **Recommended sizes**: 32x32 (taskbar), 64x64 (alt-tab), 256x256 (high-DPI)
/// - **Color depth**: 32-bit RGBA recommended for transparency support
#[cfg(test)]
mod tests {
    use crate::webview::config::WebViewConfig;
    use std::path::PathBuf;

    /// Test that config with width=0 should trigger maximize
    #[test]
    fn test_should_maximize_when_width_zero() {
        let config = WebViewConfig {
            width: 0,
            height: 600,
            ..Default::default()
        };
        let should_maximize = config.width == 0 || config.height == 0;
        assert!(should_maximize);
    }

    /// Test that config with height=0 should trigger maximize
    #[test]
    fn test_should_maximize_when_height_zero() {
        let config = WebViewConfig {
            width: 800,
            height: 0,
            ..Default::default()
        };
        let should_maximize = config.width == 0 || config.height == 0;
        assert!(should_maximize);
    }

    /// Test that config with both dimensions zero should trigger maximize
    #[test]
    fn test_should_maximize_when_both_zero() {
        let config = WebViewConfig {
            width: 0,
            height: 0,
            ..Default::default()
        };
        let should_maximize = config.width == 0 || config.height == 0;
        assert!(should_maximize);
    }

    /// Test that config with normal dimensions should NOT maximize
    #[test]
    fn test_should_not_maximize_with_normal_dimensions() {
        let config = WebViewConfig {
            width: 800,
            height: 600,
            ..Default::default()
        };
        let should_maximize = config.width == 0 || config.height == 0;
        assert!(!should_maximize);
    }

    /// Test asset_root config conversion
    #[test]
    fn test_asset_root_config() {
        let config = WebViewConfig {
            asset_root: Some(PathBuf::from("/tmp/assets")),
            ..Default::default()
        };
        assert!(config.asset_root.is_some());
        assert_eq!(
            config.asset_root.as_ref().unwrap().to_str().unwrap(),
            "/tmp/assets"
        );
    }

    /// Test asset_root with None
    #[test]
    fn test_asset_root_none() {
        let config = WebViewConfig::default();
        assert!(config.asset_root.is_none());
    }

    /// Test allow_file_protocol config
    #[test]
    fn test_allow_file_protocol_enabled() {
        let config = WebViewConfig {
            allow_file_protocol: true,
            ..Default::default()
        };
        assert!(config.allow_file_protocol);
    }

    /// Test allow_file_protocol default
    #[test]
    fn test_allow_file_protocol_default() {
        let config = WebViewConfig::default();
        assert!(!config.allow_file_protocol);
    }

    /// Test always_on_top config
    #[test]
    fn test_always_on_top_enabled() {
        let config = WebViewConfig {
            always_on_top: true,
            ..Default::default()
        };
        assert!(config.always_on_top);
    }

    /// Test always_on_top default
    #[test]
    fn test_always_on_top_default() {
        let config = WebViewConfig::default();
        assert!(!config.always_on_top);
    }

    /// Test combined asset_root and allow_file_protocol
    #[test]
    fn test_combined_local_file_options() {
        let config = WebViewConfig {
            asset_root: Some(PathBuf::from("./assets")),
            allow_file_protocol: true,
            ..Default::default()
        };
        assert!(config.asset_root.is_some());
        assert!(config.allow_file_protocol);
    }

    /// Test window visibility starts hidden
    #[test]
    fn test_config_transparent() {
        let config = WebViewConfig {
            transparent: true,
            ..Default::default()
        };
        assert!(config.transparent);
    }

    /// Test decorations config
    #[test]
    fn test_config_decorations() {
        let config = WebViewConfig {
            decorations: false,
            ..Default::default()
        };
        assert!(!config.decorations);
    }

    /// Test resizable config
    #[test]
    fn test_config_resizable() {
        let config = WebViewConfig {
            resizable: false,
            ..Default::default()
        };
        assert!(!config.resizable);
    }

    /// Test dev_tools config
    #[test]
    fn test_config_dev_tools() {
        let config = WebViewConfig {
            dev_tools: true,
            ..Default::default()
        };
        assert!(config.dev_tools);
    }

    /// Test dev_tools default is true (enabled for development convenience)
    #[test]
    fn test_config_dev_tools_default() {
        let config = WebViewConfig::default();
        assert!(config.dev_tools);
    }

    /// Test headless config
    #[test]
    fn test_config_headless() {
        let config = WebViewConfig {
            headless: true,
            ..Default::default()
        };
        assert!(config.headless);
    }

    /// Test headless default is false
    #[test]
    fn test_config_headless_default() {
        let config = WebViewConfig::default();
        assert!(!config.headless);
    }

    /// Test auto_show config
    #[test]
    fn test_config_auto_show() {
        let config = WebViewConfig {
            auto_show: false,
            ..Default::default()
        };
        assert!(!config.auto_show);
    }

    /// Test auto_show default is true
    #[test]
    fn test_config_auto_show_default() {
        let config = WebViewConfig::default();
        assert!(config.auto_show);
    }

    /// Test auto_show logic with headless mode
    #[test]
    fn test_auto_show_disabled_in_headless() {
        let config = WebViewConfig {
            auto_show: true,
            headless: true,
            ..Default::default()
        };
        // auto_show should be effectively false when headless is true
        let effective_auto_show = config.auto_show && !config.headless;
        assert!(!effective_auto_show);
    }

    /// Test URL config
    #[test]
    fn test_config_url() {
        let config = WebViewConfig {
            url: Some("https://example.com".to_string()),
            ..Default::default()
        };
        assert_eq!(config.url, Some("https://example.com".to_string()));
    }

    /// Test HTML config
    #[test]
    fn test_config_html() {
        let config = WebViewConfig {
            html: Some("<html><body>Hello</body></html>".to_string()),
            ..Default::default()
        };
        assert!(config.html.is_some());
        assert!(config.html.as_ref().unwrap().contains("Hello"));
    }

    /// Test title config
    #[test]
    fn test_config_title() {
        let config = WebViewConfig {
            title: "My Custom Title".to_string(),
            ..Default::default()
        };
        assert_eq!(config.title, "My Custom Title");
    }

    /// Test default title
    #[test]
    fn test_config_title_default() {
        let config = WebViewConfig::default();
        assert!(!config.title.is_empty());
    }

    /// Test icon config
    #[test]
    fn test_config_icon() {
        let config = WebViewConfig {
            icon: Some(PathBuf::from("/path/to/icon.png")),
            ..Default::default()
        };
        assert!(config.icon.is_some());
        assert_eq!(
            config.icon.as_ref().unwrap().to_str().unwrap(),
            "/path/to/icon.png"
        );
    }

    /// Test icon default is None
    #[test]
    fn test_config_icon_default() {
        let config = WebViewConfig::default();
        assert!(config.icon.is_none());
    }

    /// Test data_directory config
    #[test]
    fn test_config_data_directory() {
        let config = WebViewConfig {
            data_directory: Some(PathBuf::from("/tmp/webview_data")),
            ..Default::default()
        };
        assert!(config.data_directory.is_some());
    }

    /// Test data_directory default is None
    #[test]
    fn test_config_data_directory_default() {
        let config = WebViewConfig::default();
        assert!(config.data_directory.is_none());
    }

    /// Test remote_debugging_port config
    #[test]
    fn test_config_remote_debugging_port() {
        let config = WebViewConfig {
            remote_debugging_port: Some(9222),
            ..Default::default()
        };
        assert_eq!(config.remote_debugging_port, Some(9222));
    }

    /// Test remote_debugging_port default is None
    #[test]
    fn test_config_remote_debugging_port_default() {
        let config = WebViewConfig::default();
        assert!(config.remote_debugging_port.is_none());
    }

    /// Test block_external_navigation config
    #[test]
    fn test_config_block_external_navigation() {
        let config = WebViewConfig {
            block_external_navigation: true,
            ..Default::default()
        };
        assert!(config.block_external_navigation);
    }

    /// Test block_external_navigation default
    #[test]
    fn test_config_block_external_navigation_default() {
        let config = WebViewConfig::default();
        assert!(!config.block_external_navigation);
    }

    /// Test allowed_navigation_domains config
    #[test]
    fn test_config_allowed_navigation_domains() {
        let config = WebViewConfig {
            allowed_navigation_domains: vec!["example.com".to_string(), "test.org".to_string()],
            ..Default::default()
        };
        assert_eq!(config.allowed_navigation_domains.len(), 2);
        assert!(config
            .allowed_navigation_domains
            .contains(&"example.com".to_string()));
    }

    /// Test allowed_navigation_domains default is empty
    #[test]
    fn test_config_allowed_navigation_domains_default() {
        let config = WebViewConfig::default();
        assert!(config.allowed_navigation_domains.is_empty());
    }

    /// Test parent_hwnd config
    #[test]
    fn test_config_parent_hwnd() {
        let config = WebViewConfig {
            parent_hwnd: Some(12345),
            ..Default::default()
        };
        assert_eq!(config.parent_hwnd, Some(12345));
    }

    /// Test parent_hwnd default is None
    #[test]
    fn test_config_parent_hwnd_default() {
        let config = WebViewConfig::default();
        assert!(config.parent_hwnd.is_none());
    }

    /// Test combined config for DCC embedding
    #[test]
    fn test_config_dcc_embedding() {
        let config = WebViewConfig {
            parent_hwnd: Some(0x12345678),
            decorations: false,
            resizable: true,
            transparent: false,
            ..Default::default()
        };
        assert!(config.parent_hwnd.is_some());
        assert!(!config.decorations);
        assert!(config.resizable);
        assert!(!config.transparent);
    }

    /// Test combined config for standalone app
    #[test]
    fn test_config_standalone_app() {
        let config = WebViewConfig {
            title: "My App".to_string(),
            width: 1024,
            height: 768,
            url: Some("https://myapp.com".to_string()),
            dev_tools: true,
            decorations: true,
            resizable: true,
            ..Default::default()
        };
        assert_eq!(config.title, "My App");
        assert_eq!(config.width, 1024);
        assert_eq!(config.height, 768);
        assert!(config.url.is_some());
        assert!(config.dev_tools);
        assert!(config.decorations);
        assert!(config.resizable);
    }

    /// Test combined config for headless testing
    #[test]
    fn test_config_headless_testing() {
        let config = WebViewConfig {
            headless: true,
            auto_show: false,
            remote_debugging_port: Some(9222),
            url: Some("https://test.example.com".to_string()),
            ..Default::default()
        };
        assert!(config.headless);
        assert!(!config.auto_show);
        assert_eq!(config.remote_debugging_port, Some(9222));
    }

    /// Test combined config for local development
    #[test]
    fn test_config_local_development() {
        let config = WebViewConfig {
            asset_root: Some(PathBuf::from("./frontend/dist")),
            allow_file_protocol: true,
            dev_tools: true,
            url: Some("auroraview://localhost/index.html".to_string()),
            ..Default::default()
        };
        assert!(config.asset_root.is_some());
        assert!(config.allow_file_protocol);
        assert!(config.dev_tools);
    }
}
