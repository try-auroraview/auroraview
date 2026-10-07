//! AuroraView - Rust-powered WebView for Python & DCC embedding
//!
//! This library provides Python bindings for creating WebView windows in DCC applications
//! like Maya, 3ds Max, Houdini, Blender, etc.
//!
//! ## Architecture Layers
//!
//! - **Runtime Layer**: `auroraview-desktop` (standalone mode), `auroraview-dcc` (DCC embedded mode)
//! - **Application Layer**: `auroraview-tabs`, `auroraview-browser`
//! - **Core Layer**: `auroraview-core` (WebView, IPC protocol, JS injection)

#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;

#[cfg(feature = "python-bindings")]
mod bindings;
pub mod dom;
pub mod ipc;
mod platform;
pub mod service_discovery;
mod utils;
pub mod webview;
#[cfg(feature = "python-bindings")]
pub mod window_utils;

// Re-export runtime crates when enabled
#[cfg(feature = "runtime-dcc")]
pub use auroraview_dcc as dcc;
#[cfg(feature = "runtime-desktop")]
pub use auroraview_desktop as desktop;

#[cfg(feature = "python-bindings")]
#[allow(unused_imports)]
use webview::AuroraView;

pub use webview::{NewWindowMode, WebViewBuilder, WebViewConfig};

/// Python module initialization
#[cfg(feature = "python-bindings")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Initialize logging
    utils::init_logging();

    // IMPORTANT: Allow calling Python from non-Python threads (e.g., Wry IPC thread)
    // This is required so Python callbacks can be invoked safely from Rust-created threads.
    // See PyO3 docs: Python::initialize must be called in extension modules
    // when you'll use Python from threads not created by Python.
    pyo3::Python::initialize();

    // Register WebView class
    m.add_class::<webview::AuroraView>()?;
    #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
    m.add_class::<webview::hosted_gtk::HostRuntime>()?;

    // Register EventEmitter class (thread-safe event emitter for cross-thread operations)
    m.add_class::<webview::EventEmitter>()?;

    // Register WebViewProxy class (thread-safe proxy for cross-thread operations)
    m.add_class::<webview::WebViewProxy>()?;

    // Register PluginManager class (for file system and other native operations)
    m.add_class::<webview::PluginManager>()?;

    // Register PyRegion class (for click-through interactive regions)
    m.add_class::<webview::PyRegion>()?;

    // Register window utilities
    window_utils::register_window_utils(m)?;

    // Register high-performance JSON functions (orjson-equivalent, no Python deps)
    bindings::ipc::register_json_functions(m)?;

    // Register service discovery module
    bindings::service_discovery::register_service_discovery(m)?;

    // Register IPC metrics class
    bindings::ipc_metrics::register_ipc_metrics(m)?;

    // Register CLI utilities (HTML rewriting, URL normalization, etc.)
    bindings::cli_utils::register_cli_utils(m)?;

    // Register desktop runner (uses event_loop.run() for desktop apps)
    // Also registers legacy run_standalone alias for backward compatibility
    bindings::desktop_runner::register_desktop_runner(m)?;

    // Register WebView2 warmup functions (Windows performance optimization)
    bindings::warmup::register_warmup_functions(m)?;

    // Register window manager functions (multi-window support)
    bindings::window_manager::register_window_manager_functions(m)?;

    // Register multi-tab browser (Microsoft WebView2Browser architecture)
    bindings::tab_browser::register_tab_browser(m)?;

    // Register static assets functions (JavaScript, HTML for testing)
    bindings::assets::register_assets_functions(m)?;

    // Register WebView2 cleanup functions (stale directory cleanup)
    bindings::cleanup::register_cleanup_functions(m)?;

    // Register high-performance DOM batch operations
    dom::register_dom_module(m)?;

    // Register signals module (Qt-style signal-slot event system)
    auroraview_signals::python::register_module(m)?;

    // Register testing module (AI-friendly CDP-based testing)
    #[cfg(feature = "testing-python")]
    auroraview_testing::python::register_module(m)?;

    // Register telemetry module (OpenTelemetry-based observability)
    #[cfg(feature = "telemetry-python")]
    auroraview_telemetry::python::register_module(m)?;

    // Windows-only: register minimal WebView2 embedded API (feature-gated)
    #[cfg(all(target_os = "windows", feature = "win-webview2"))]
    bindings::webview2::register_webview2_api(m)?;

    // Register runtime crate bindings (when features enabled)
    #[cfg(feature = "runtime-desktop")]
    bindings::runtime_desktop::register_desktop_runtime(m)?;

    #[cfg(feature = "runtime-dcc")]
    bindings::runtime_dcc::register_dcc_runtime(m)?;

    // Add module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__author__", "Hal Long <hal.long@outlook.com>")?;

    Ok(())
}

// Comprehensive module import tests
#[cfg(test)]
mod tests {
    //! Comprehensive module import tests for AuroraView
    //!
    //! These tests ensure all modules can be compiled and their public APIs are accessible.
    //! This provides broad coverage of the codebase without requiring runtime dependencies.

    use rstest::*;

    /// Test that core webview modules compile and export expected symbols
    #[rstest]
    fn test_webview_module_imports() {
        // Test webview module structure
        use crate::webview;

        // Verify main types are accessible
        #[cfg(feature = "python-bindings")]
        let _: Option<webview::AuroraView> = None;
        let _: Option<webview::WebViewConfig> = None;
        let _: Option<webview::WebViewBuilder> = None;
    }

    /// Test IPC module imports
    #[rstest]
    fn test_ipc_module_imports() {
        use crate::ipc;

        // Verify IPC types are accessible
        let _: Option<ipc::IpcHandler> = None;
        let _: Option<ipc::MessageQueue> = None;
        let _: Option<ipc::IpcMetrics> = None;
    }

    /// Test DOM module imports
    #[rstest]
    fn test_dom_module_imports() {
        use crate::dom;

        // Verify DOM types are accessible
        let _: Option<dom::DomBatch> = None;
        let _: Option<dom::DomOp> = None;
    }

    /// Test service discovery module imports
    #[rstest]
    fn test_service_discovery_imports() {
        use crate::service_discovery;

        // Verify service discovery types are accessible
        let _: Option<service_discovery::PortAllocator> = None;
    }

    /// Test window utilities module imports
    #[cfg(feature = "python-bindings")]
    #[rstest]
    fn test_window_utils_imports() {
        use crate::window_utils;

        // Verify window utils functions are accessible (compile-time check)
        let _ = window_utils::get_all_windows;
    }

    /// Test platform-specific modules compile
    #[rstest]
    fn test_platform_module_imports() {
        #[cfg(target_os = "windows")]
        {
            // Verify Windows platform module compiles
            #[allow(unused_imports)]
            use crate::platform::windows;
            // Module exists and compiles
            let _: Option<()> = None;
        }
    }

    /// Test utils module imports
    #[rstest]
    fn test_utils_module_imports() {
        use crate::utils;

        // Verify utils functions are accessible
        let _ = utils::init_logging;
    }

    /// Test webview submodules
    #[rstest]
    fn test_webview_submodules() {
        // Test backend module (public)
        use crate::webview::backend;
        let _: Option<backend::BackendType> = None;

        // Test js_assets module (public)
        use crate::webview::js_assets;
        // Verify functions are accessible
        let event_bridge = js_assets::event_bridge();
        assert!(!event_bridge.is_empty());

        // Keep this as a compile-time smoke test only; built frontend assets are not guaranteed
        // to exist in source checkouts.
        let _ = js_assets::get_loading_html as fn() -> String;
    }

    /// Test desktop module functions
    #[rstest]
    fn test_desktop_module() {
        use crate::webview::js_assets;

        // Keep this as a compile-time smoke test only; built frontend assets are not guaranteed
        // to exist in source checkouts.
        let _ = js_assets::get_loading_html as fn() -> String;

        // Test URL loading script generation

        let script = js_assets::build_load_url_script("https://example.com");
        assert!(script.contains("https://example.com"));
        assert!(script.contains("window.location.href"));
    }

    /// Test IPC submodules
    #[rstest]
    fn test_ipc_submodules() {
        // Test handler module
        use crate::ipc::handler;
        let _: Option<handler::IpcHandler> = None;

        // Test message queue module
        use crate::ipc::message_queue;
        let _: Option<message_queue::MessageQueue> = None;

        // Test IPC metrics (from core)
        use crate::ipc::IpcMetrics;
        let _: Option<IpcMetrics> = None;

        // Test backend module
        use crate::ipc::backend;
        let _: Option<backend::IpcMessage> = None;
    }

    /// Test threaded module (requires python-bindings feature)
    #[cfg(feature = "python-bindings")]
    #[rstest]
    fn test_ipc_threaded_module() {
        use crate::ipc::threaded;
        let _: Option<threaded::ThreadedBackend> = None;
    }

    /// Test that Python bindings module compiles (when feature is enabled)
    #[cfg(feature = "python-bindings")]
    #[rstest]
    fn test_python_bindings_imports() {
        use crate::bindings;

        // Verify bindings modules compile
        let _ = bindings::ipc::register_json_functions;
        let _ = bindings::service_discovery::register_service_discovery;
        let _ = bindings::ipc_metrics::register_ipc_metrics;
    }

    /// Test WebView2 bindings (Windows + feature flag)
    #[cfg(all(
        target_os = "windows",
        feature = "win-webview2",
        feature = "python-bindings"
    ))]
    #[rstest]
    fn test_webview2_bindings_imports() {
        use crate::bindings::webview2;

        // Verify WebView2 bindings compile
        let _ = webview2::register_webview2_api;
    }

    /// Test that all public re-exports are accessible
    #[rstest]
    fn test_public_api_exports() {
        // Test top-level exports from lib.rs
        let _: Option<crate::WebViewConfig> = None;
        let _: Option<crate::WebViewBuilder> = None;
        #[cfg(feature = "python-bindings")]
        let _: Option<crate::webview::AuroraView> = None;
    }

    /// Test runtime crate re-exports (when features enabled)
    #[cfg(feature = "runtime-desktop")]
    #[rstest]
    fn test_desktop_runtime_exports() {
        use crate::desktop;
        let _: Option<desktop::DesktopConfig> = None;
        let _: Option<desktop::WindowManager> = None;
        let _: Option<desktop::IpcRouter> = None;
    }

    #[cfg(feature = "runtime-dcc")]
    #[rstest]
    fn test_dcc_runtime_exports() {
        use crate::dcc;
        let _: Option<dcc::DccConfig> = None;
        let _: Option<dcc::WindowManager> = None;
        let _: Option<dcc::IpcRouter> = None;
    }

    /// Python module initialization test
    #[cfg(feature = "python-bindings")]
    #[rstest]
    fn test_pymodule_init_registers_symbols() {
        use super::*;

        pyo3::Python::attach(|py| {
            let m = pyo3::types::PyModule::new(py, "auroraview_test").unwrap();
            _core(&m).expect("module init should succeed");
            assert!(m.getattr("get_all_windows").is_ok());
            Ok::<(), pyo3::PyErr>(())
        })
        .unwrap();
    }
}
