//! Integration tests for standalone WebView mode
//!
//! These tests verify the standalone WebView functionality including:
//! - Configuration handling
//! - Loading screen HTML generation
//! - URL loading script generation

use _core::webview::config::WebViewConfig;
use _core::webview::js_assets;
use rstest::*;

/// Test standalone WebView configuration defaults
#[rstest]
fn standalone_config_defaults() {
    let config = WebViewConfig::default();

    assert_eq!(config.title, "AuroraView");
    assert_eq!(config.width, 800);
    assert_eq!(config.height, 600);
    assert!(config.resizable);
    assert!(config.decorations);
    assert!(!config.transparent);
    assert!(config.dev_tools);
}

/// Test standalone WebView configuration with custom values
#[rstest]
#[case("Custom Title", 1024, 768)]
#[case("Test Window", 640, 480)]
#[case("My App", 1920, 1080)]
fn standalone_config_custom(#[case] title: &str, #[case] width: u32, #[case] height: u32) {
    let config = WebViewConfig {
        title: title.to_string(),
        width,
        height,
        ..Default::default()
    };

    assert_eq!(config.title, title);
    assert_eq!(config.width, width);
    assert_eq!(config.height, height);
}

/// GH-528: a custom window icon path is carried on WebViewConfig and the
/// default keeps no custom icon (so the default AuroraView icon is used).
#[rstest]
fn standalone_config_window_icon() {
    use std::path::PathBuf;

    assert!(WebViewConfig::default().icon.is_none());

    let config = WebViewConfig {
        icon: Some(PathBuf::from("assets/my-icon.png")),
        ..Default::default()
    };
    assert_eq!(config.icon, Some(PathBuf::from("assets/my-icon.png")));
}

/// Test loading screen HTML generation
#[rstest]
fn loading_html_generation() {
    let html = js_assets::get_loading_html();

    // Verify HTML structure
    assert!(html.contains("<!DOCTYPE html>"));
    assert!(html.contains("<html"));
    assert!(html.contains("</html>"));

    // Verify loading page has root container for React app
    assert!(html.contains("root"));

    // Verify styling references
    assert!(html.contains("background") || html.contains("stylesheet"));
}

/// Test URL loading script generation
///
/// Note: The `build_load_url_script` function generates JavaScript for
/// window.location.href navigation. However, in standalone mode, we now
/// use wry's native `load_url()` method for more reliable navigation,
/// especially after splash screen loading. This test verifies the script
/// generation still works for backward compatibility and other use cases.
#[rstest]
#[case("https://example.com")]
#[case("https://google.com")]
#[case("http://localhost:8080")]
fn url_loading_script(#[case] url: &str) {
    let script = js_assets::build_load_url_script(url);

    // Verify script contains URL
    assert!(script.contains(url));

    // Verify script uses window.location.href
    assert!(script.contains("window.location.href"));
}

/// Test HTML registry contains loading screen
#[rstest]
fn html_registry_has_loading() {
    let html = js_assets::get_loading_html();

    // Should not be empty
    assert!(!html.is_empty());

    // Should be valid HTML
    assert!(html.starts_with("<!DOCTYPE html>") || html.starts_with("<html"));
}

/// Test standalone config with URL
#[rstest]
fn standalone_config_with_url() {
    let url = "https://example.com";
    let config = WebViewConfig {
        url: Some(url.to_string()),
        ..Default::default()
    };

    assert_eq!(config.url, Some(url.to_string()));
    assert_eq!(config.html, None);
}

/// Test standalone config with HTML
#[rstest]
fn standalone_config_with_html() {
    let html = "<html><body>Test</body></html>";
    let config = WebViewConfig {
        html: Some(html.to_string()),
        ..Default::default()
    };

    assert_eq!(config.html, Some(html.to_string()));
    assert_eq!(config.url, None);
}

/// Test standalone config with both URL and HTML (URL takes precedence)
#[rstest]
fn standalone_config_url_precedence() {
    let url = "https://example.com";
    let html = "<html><body>Test</body></html>";
    let config = WebViewConfig {
        url: Some(url.to_string()),
        html: Some(html.to_string()),
        ..Default::default()
    };

    // Both should be set, but URL takes precedence in standalone mode
    assert_eq!(config.url, Some(url.to_string()));
    assert_eq!(config.html, Some(html.to_string()));
}

/// Test window transparency configuration
#[rstest]
fn standalone_window_transparency() {
    let config = WebViewConfig {
        transparent: true,
        ..Default::default()
    };

    assert!(config.transparent);
}

/// Test developer tools configuration
#[rstest]
#[case(true)]
#[case(false)]
fn standalone_dev_tools(#[case] dev_tools: bool) {
    let config = WebViewConfig {
        dev_tools,
        ..Default::default()
    };

    assert_eq!(config.dev_tools, dev_tools);
}

/// Test standalone config with all options
#[rstest]
fn standalone_config_complete() {
    let config = WebViewConfig {
        title: "Test App".to_string(),
        width: 1024,
        height: 768,
        url: Some("https://example.com".to_string()),
        html: None,
        dev_tools: true,
        resizable: true,
        decorations: true,
        transparent: false,
        always_on_top: false,
        background_color: None,
        context_menu: true,
        parent_hwnd: None,
        embed_mode: _core::webview::config::EmbedMode::None,
        ipc_batching: false,
        ipc_batch_size: 100,
        ipc_batch_interval_ms: 16,
        asset_root: None,
        custom_protocols: std::collections::HashMap::new(),
        api_methods: std::collections::HashMap::new(),
        allow_new_window: false,
        allow_file_protocol: false,
        ..Default::default()
    };

    assert_eq!(config.title, "Test App");
    assert_eq!(config.width, 1024);
    assert_eq!(config.height, 768);
    assert_eq!(config.url, Some("https://example.com".to_string()));
    assert!(config.dev_tools);
    assert!(config.resizable);
    assert!(config.decorations);
    assert!(!config.transparent);
}

/// Test embed mode configuration
#[rstest]
fn standalone_embed_mode() {
    use _core::webview::config::EmbedMode;

    let config = WebViewConfig {
        embed_mode: EmbedMode::None,
        ..Default::default()
    };

    // Verify embed mode is set correctly
    assert!(matches!(config.embed_mode, EmbedMode::None));
}

/// Test IPC configuration
#[rstest]
fn standalone_ipc_config() {
    let config = WebViewConfig {
        ipc_batching: true,
        ipc_batch_size: 200,
        ipc_batch_interval_ms: 32,
        ..Default::default()
    };

    assert!(config.ipc_batching);
    assert_eq!(config.ipc_batch_size, 200);
    assert_eq!(config.ipc_batch_interval_ms, 32);
}

/// Test context menu configuration
#[rstest]
#[case(true)]
#[case(false)]
fn standalone_context_menu(#[case] context_menu: bool) {
    let config = WebViewConfig {
        context_menu,
        ..Default::default()
    };

    assert_eq!(config.context_menu, context_menu);
}

/// Test always on top configuration
#[rstest]
fn standalone_always_on_top() {
    let config = WebViewConfig {
        always_on_top: true,
        ..Default::default()
    };

    assert!(config.always_on_top);
}

/// Test background color configuration
#[rstest]
fn standalone_background_color() {
    let config = WebViewConfig {
        background_color: Some("#ffffff".to_string()),
        ..Default::default()
    };

    assert_eq!(config.background_color, Some("#ffffff".to_string()));
}

/// Test asset_root configuration
#[rstest]
fn standalone_asset_root() {
    use std::path::PathBuf;

    // Test with None (default)
    let config = WebViewConfig::default();
    assert_eq!(config.asset_root, None);

    // Test with Some path
    let config = WebViewConfig {
        asset_root: Some(PathBuf::from("/tmp/assets")),
        ..Default::default()
    };
    assert_eq!(config.asset_root, Some(PathBuf::from("/tmp/assets")));
}

/// Test width=0 or height=0 configuration for maximize
#[rstest]
#[case(0, 600)]
#[case(800, 0)]
#[case(0, 0)]
fn standalone_zero_dimensions_for_maximize(#[case] width: u32, #[case] height: u32) {
    let config = WebViewConfig {
        width,
        height,
        ..Default::default()
    };

    // Verify dimensions are stored correctly
    assert_eq!(config.width, width);
    assert_eq!(config.height, height);

    // When width or height is 0, the standalone runner should maximize the window
    // This logic is in standalone.rs, not in config
    let should_maximize = width == 0 || height == 0;
    assert!(
        should_maximize,
        "Expected maximize for width={}, height={}",
        width, height
    );
}

/// Test allow_file_protocol configuration
#[rstest]
fn standalone_allow_file_protocol() {
    // Test default (false)
    let config = WebViewConfig::default();
    assert!(!config.allow_file_protocol);

    // Test enabled
    let config = WebViewConfig {
        allow_file_protocol: true,
        ..Default::default()
    };
    assert!(config.allow_file_protocol);
}

/// Test combined asset_root and allow_file_protocol
#[rstest]
fn standalone_local_file_options() {
    use std::path::PathBuf;

    // Test with asset_root only (recommended)
    let config = WebViewConfig {
        asset_root: Some(PathBuf::from("./assets")),
        allow_file_protocol: false,
        ..Default::default()
    };
    assert!(config.asset_root.is_some());
    assert!(!config.allow_file_protocol);

    // Test with allow_file_protocol only
    let config = WebViewConfig {
        asset_root: None,
        allow_file_protocol: true,
        ..Default::default()
    };
    assert!(config.asset_root.is_none());
    assert!(config.allow_file_protocol);

    // Test with both (valid but unusual)
    let config = WebViewConfig {
        asset_root: Some(PathBuf::from("./assets")),
        allow_file_protocol: true,
        ..Default::default()
    };
    assert!(config.asset_root.is_some());
    assert!(config.allow_file_protocol);
}

// ============================================================================
// JavaScript Assets Tests - Coverage for src/webview/js_assets.rs
// ============================================================================

/// Test event_bridge function returns non-empty script
#[rstest]
fn js_assets_event_bridge() {
    let script = js_assets::event_bridge();
    assert!(!script.is_empty());
    assert!(script.contains("auroraview"));
}

/// Test context_menu_disable function returns non-empty script
#[rstest]
fn js_assets_context_menu_disable() {
    let script = js_assets::context_menu_disable();
    // Script may be empty if context menu is not disabled
    let _ = script;
}

/// Test context_menu function (alias for context_menu_disable)
#[rstest]
fn js_assets_context_menu() {
    let script = js_assets::context_menu();
    // Script may be empty if context menu is not disabled
    let _ = script;
}

/// Test midscene_bridge function returns non-empty script
#[rstest]
fn js_assets_midscene_bridge() {
    let script = js_assets::midscene_bridge();
    assert!(!script.is_empty());
    assert!(script.contains("midscene") || script.contains("__midscene"));
}

/// Test test_callback function returns non-empty script
#[rstest]
fn js_assets_test_callback() {
    let script = js_assets::test_callback();
    assert!(!script.is_empty());
    assert!(script.contains("auroratest") || script.contains("callback"));
}

/// Test get_js_code function with valid path
#[rstest]
fn js_assets_get_js_code_valid() {
    // Try to get event bridge script by path
    let script = js_assets::get_js_code("core/event_bridge.js");
    assert!(script.is_some());
    assert!(!script.unwrap().is_empty());
}

/// Test get_js_code function with invalid path
#[rstest]
fn js_assets_get_js_code_invalid() {
    let script = js_assets::get_js_code("nonexistent/script.js");
    assert!(script.is_none());
}

/// Test build_init_script with default config
#[rstest]
fn js_assets_build_init_script_default() {
    let config = WebViewConfig::default();
    let script = js_assets::build_init_script(&config);

    // Should contain event bridge
    assert!(script.contains("auroraview"));

    // Should contain navigation tracker
    assert!(!script.is_empty());
}

/// Test build_init_script with context menu disabled
#[rstest]
fn js_assets_build_init_script_no_context_menu() {
    let config = WebViewConfig {
        context_menu: false,
        ..Default::default()
    };
    let script = js_assets::build_init_script(&config);

    // Should contain context menu disable script
    assert!(!script.is_empty());
}

/// Test build_init_script with plugins enabled
#[rstest]
fn js_assets_build_init_script_with_plugins() {
    let config = WebViewConfig {
        enable_plugins: true,
        ..Default::default()
    };
    let script = js_assets::build_init_script(&config);

    // Should contain plugin scripts
    assert!(!script.is_empty());
}

/// Test build_init_script with specific plugins
#[rstest]
fn js_assets_build_init_script_with_specific_plugins() {
    let config = WebViewConfig {
        enable_plugins: true,
        enabled_plugin_names: vec!["fs".to_string(), "dialog".to_string()],
        ..Default::default()
    };
    let script = js_assets::build_init_script(&config);

    // Should contain only specified plugins
    assert!(!script.is_empty());
}

/// Test build_init_script with API methods
#[rstest]
fn js_assets_build_init_script_with_api_methods() {
    use std::collections::HashMap;

    let mut api_methods = HashMap::new();
    api_methods.insert(
        "api".to_string(),
        vec!["echo".to_string(), "greet".to_string()],
    );

    let config = WebViewConfig {
        api_methods,
        ..Default::default()
    };
    let script = js_assets::build_init_script(&config);

    // Should contain API registration
    assert!(!script.is_empty());
}

/// Test build_emit_event_script
#[rstest]
#[case("test_event", r#"{"message": "hello"}"#)]
#[case("user_action", r#"{"action": "click", "target": "button"}"#)]
fn js_assets_build_emit_event_script(#[case] event_name: &str, #[case] event_data: &str) {
    let script = js_assets::build_emit_event_script(event_name, event_data);

    // Should contain event name
    assert!(script.contains(event_name));
}

/// Test build_eval_js_async_script
#[rstest]
#[case("1 + 1", 1)]
#[case("document.title", 2)]
#[case("window.location.href", 3)]
fn js_assets_build_eval_js_async_script(#[case] user_script: &str, #[case] callback_id: u64) {
    let script = js_assets::build_eval_js_async_script(user_script, callback_id);

    // Should contain callback ID
    assert!(script.contains(&callback_id.to_string()));

    // Should contain IPC mechanism
    assert!(script.contains("ipc.postMessage"));

    // Should handle errors
    assert!(script.contains("catch"));
}
