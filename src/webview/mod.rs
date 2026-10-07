//! WebView module - Core WebView functionality

#![allow(clippy::useless_conversion)]

// Module declarations - Python bindings
#[cfg(feature = "python-bindings")]
mod core;
#[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
pub(crate) mod hosted_gtk;
#[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
pub mod hosted_pump;
#[cfg(feature = "python-bindings")]
mod proxy;
#[cfg(feature = "python-bindings")]
mod webview_inner;

// Core modules (always available)
pub mod backend;
pub(crate) mod child_window; // Child WebView window creation
pub mod cleanup; // WebView2 user data directory cleanup
pub mod config; // Public for testing
#[cfg(feature = "python-bindings")]
pub(crate) mod desktop;
pub mod devtools; // DevTools window management
pub(crate) mod event_loop;
pub mod features; // Feature integration (RFC 0007 Phase 4)
pub mod js_assets; // JavaScript assets management
#[cfg(feature = "templates")]
pub mod js_templates; // Type-safe JS templates using Askama
pub mod lifecycle; // Public for testing
mod message_processor; // Unified message processing
mod message_pump;
pub mod protocol;
pub mod protocol_handlers; // Custom protocol handlers
#[cfg(feature = "python-bindings")]
pub(crate) use desktop as standalone; // Backward compatibility alias
pub mod tab_manager; // Multi-tab browser support
pub mod timer;
pub mod tray; // System tray support
pub mod window_manager; // Multi-window support

// Public exports
pub use backend::BackendType;
pub use config::{
    NewWindowMode, TrayConfig, TrayMenuItem, TrayMenuItemType, WebViewBuilder, WebViewConfig,
};
#[cfg(feature = "python-bindings")]
pub use core::AuroraView;
#[cfg(feature = "python-bindings")]
pub use core::EventEmitter;
#[cfg(feature = "python-bindings")]
pub use core::PluginManager;
#[cfg(feature = "python-bindings")]
pub use core::PyRegion;
pub use devtools::{DevToolsManager, DevToolsWindowConfig, DevToolsWindowInfo};
pub use event_loop::{EventLoopError, EventLoopResult};
pub use features::{Features, FeaturesConfig};
#[cfg(feature = "python-bindings")]
pub use proxy::WebViewProxy;
pub use window_manager::{WindowInfo, WindowManager};
