//!
//! Extensions Plugin
//!
//! Provides Chrome Extension API compatibility for AuroraView.
//! This plugin handles API calls from extensions and routes them to the
//! appropriate handlers in auroraview-extensions crate.
//!
//! ## Commands
//!
//! - `api_call` - Route an API call to the extension system
//! - `get_side_panel` - Get side panel HTML for an extension
//! - `list_extensions` - List all loaded extensions
//! - `get_extension` - Get details about a specific extension
//! - `open_side_panel` - Open the side panel for an extension
//! - `close_side_panel` - Close the side panel for an extension
//! - `get_side_panel_state` - Get the current side panel visibility state
//! - `get_polyfill` - Get the Chrome API polyfill script
//! - `dispatch_event` - Dispatch an event to extension listeners
//!
//! ## Example
//!
//! ```javascript
//! // Call a Chrome API from extension context
//! const result = await auroraview.invoke("plugin:extensions|api_call", {
//!     extensionId: "my-extension",
//!     api: "storage",
//!     method: "get",
//!     params: { area: "local", keys: ["key1"] }
//! });
//!
//! // List loaded extensions
//! const extensions = await auroraview.invoke("plugin:extensions|list_extensions");
//!
//! // Open side panel
//! await auroraview.invoke("plugin:extensions|open_side_panel", {
//!     extensionId: "my-extension"
//! });
//! ```

// Re-export types module
pub mod types;
pub use types::*;

// API handlers submodule
pub mod api;
#[allow(unused_imports)]
pub use api::*;

// PluginHandler implementation
mod plugin;

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::RwLock;
use serde_json::Value;

/// Request structure for api_call command
#[derive(serde::Deserialize)]
pub struct ApiCallRequest {
    #[serde(alias = "extensionId")]
    pub extension_id: String,
    pub api: String,
    pub method: String,
    pub params: Value,
}

/// Request structure for extension ID-based commands
#[derive(serde::Deserialize)]
pub struct ExtensionIdRequest {
    #[serde(alias = "extensionId")]
    pub extension_id: String,
}

/// Request structure for view ID-based commands
#[derive(serde::Deserialize)]
pub struct ViewIdRequest {
    #[serde(alias = "viewId")]
    pub view_id: String,
}

/// Request structure for create_view command
#[derive(serde::Deserialize)]
pub struct CreateViewRequest {
    #[serde(alias = "extensionId")]
    pub extension_id: String,
    #[serde(alias = "viewType")]
    pub view_type: ViewTypeRequest,
    #[serde(alias = "htmlPath")]
    pub html_path: Option<String>,
    pub title: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    #[serde(alias = "devTools")]
    pub dev_tools: Option<bool>,
    #[serde(alias = "debugPort")]
    pub debug_port: Option<u16>,
    pub visible: Option<bool>,
    #[serde(alias = "parentHwnd")]
    pub parent_hwnd: Option<u64>,
}

/// Request structure for dispatch_event command
#[derive(serde::Deserialize)]
pub struct EventDispatchRequest {
    #[serde(alias = "extensionId")]
    pub extension_id: String,
    pub api: String,
    pub event: String,
    pub args: Vec<Value>,
}

/// Extensions plugin - provides Chrome Extension API compatibility
pub struct ExtensionsPlugin {
    name: String,
    state: Arc<RwLock<ExtensionsState>>,
    callbacks: Arc<RwLock<ExtensionsCallbacks>>,
}

impl ExtensionsPlugin {
    /// Create a new extensions plugin
    pub fn new() -> Self {
        Self {
            name: "extensions".to_string(),
            state: Arc::new(RwLock::new(ExtensionsState::default())),
            callbacks: Arc::new(RwLock::new(ExtensionsCallbacks::default())),
        }
    }

    /// Create with shared state
    pub fn with_state(state: Arc<RwLock<ExtensionsState>>) -> Self {
        Self {
            name: "extensions".to_string(),
            state,
            callbacks: Arc::new(RwLock::new(ExtensionsCallbacks::default())),
        }
    }

    /// Get the shared state
    pub fn state(&self) -> Arc<RwLock<ExtensionsState>> {
        self.state.clone()
    }

    /// Get the callbacks reference
    pub fn callbacks(&self) -> Arc<RwLock<ExtensionsCallbacks>> {
        self.callbacks.clone()
    }

    /// Set the navigation callback
    pub fn set_on_navigate<F>(&self, callback: F)
    where
        F: Fn(&str) + Send + Sync + 'static,
    {
        self.callbacks.write().on_navigate = Some(Box::new(callback));
    }

    /// Set the send message callback
    pub fn set_on_send_message<F>(&self, callback: F)
    where
        F: Fn(i32, Value) -> Option<Value> + Send + Sync + 'static,
    {
        self.callbacks.write().on_send_message = Some(Box::new(callback));
    }

    /// Set the open popup callback
    pub fn set_on_open_popup<F>(&self, callback: F)
    where
        F: Fn(&str, Option<&str>) + Send + Sync + 'static,
    {
        self.callbacks.write().on_open_popup = Some(Box::new(callback));
    }

    /// Set the open options page callback
    pub fn set_on_open_options_page<F>(&self, callback: F)
    where
        F: Fn(&str, &str) + Send + Sync + 'static,
    {
        self.callbacks.write().on_open_options_page = Some(Box::new(callback));
    }

    /// Set the page reload callback
    pub fn set_on_reload_page<F>(&self, callback: F)
    where
        F: Fn() + Send + Sync + 'static,
    {
        self.callbacks.write().on_reload_page = Some(Box::new(callback));
    }

    /// Set the extension reload callback
    pub fn set_on_reload_extension<F>(&self, callback: F)
    where
        F: Fn(&str) + Send + Sync + 'static,
    {
        self.callbacks.write().on_reload_extension = Some(Box::new(callback));
    }

    /// Set the execute script callback
    pub fn set_on_execute_script<F>(&self, callback: F)
    where
        F: Fn(&str, &Value) -> Vec<Value> + Send + Sync + 'static,
    {
        self.callbacks.write().on_execute_script = Some(Box::new(callback));
    }

    /// Set the insert CSS callback
    pub fn set_on_insert_css<F>(&self, callback: F)
    where
        F: Fn(&str, &Value) + Send + Sync + 'static,
    {
        self.callbacks.write().on_insert_css = Some(Box::new(callback));
    }

    /// Set the remove CSS callback
    pub fn set_on_remove_css<F>(&self, callback: F)
    where
        F: Fn(&str, &Value) + Send + Sync + 'static,
    {
        self.callbacks.write().on_remove_css = Some(Box::new(callback));
    }

    /// Set the notification callback
    pub fn set_on_notification<F>(&self, callback: F)
    where
        F: Fn(&NotificationInfo) + Send + Sync + 'static,
    {
        self.callbacks.write().on_notification = Some(Box::new(callback));
    }

    /// Set the create window callback
    pub fn set_on_create_window<F>(&self, callback: F)
    where
        F: Fn(&Value) -> Value + Send + Sync + 'static,
    {
        self.callbacks.write().on_create_window = Some(Box::new(callback));
    }

    /// Set the event dispatch callback
    pub fn set_on_event_dispatch<F>(&self, callback: F)
    where
        F: Fn(&str, &str, &str, &[Value]) + Send + Sync + 'static,
    {
        self.callbacks.write().on_event_dispatch = Some(Box::new(callback));
    }

    /// Set the storage persist callback
    pub fn set_on_storage_persist<F>(&self, callback: F)
    where
        F: Fn(&str, &str, &HashMap<String, Value>) + Send + Sync + 'static,
    {
        self.callbacks.write().on_storage_persist = Some(Box::new(callback));
    }

    /// Set the runtime message callback
    pub fn set_on_runtime_message<F>(&self, callback: F)
    where
        F: Fn(&str, Value) -> Option<Value> + Send + Sync + 'static,
    {
        self.callbacks.write().on_runtime_message = Some(Box::new(callback));
    }

    /// Register an extension
    pub fn register_extension(&self, info: ExtensionInfo) {
        let mut state = self.state.write();
        let id = info.id.clone();
        state.extensions.insert(id.clone(), info);
        // Initialize default states
        state
            .actions
            .entry(id.clone())
            .or_insert_with(|| ActionState {
                enabled: true,
                ..Default::default()
            });
        state.side_panels.entry(id.clone()).or_default();
        state.alarms.entry(id.clone()).or_default();
        state.notifications.entry(id.clone()).or_default();
        state.context_menus.entry(id).or_default();
    }
}
