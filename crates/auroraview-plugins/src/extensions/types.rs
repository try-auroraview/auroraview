//! Extensions Plugin Types
//!
//! All type definitions for the extensions plugin.

use std::collections::HashMap;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::Value;

// ============================================================================
// Callback types
// ============================================================================

/// Callback for navigating to a URL (tabs.create, tabs.update)
pub type NavigateCallback = Box<dyn Fn(&str) + Send + Sync>;

/// Callback for sending messages to content scripts
pub type SendMessageCallback = Box<dyn Fn(i32, Value) -> Option<Value> + Send + Sync>;

/// Callback for opening a popup
pub type OpenPopupCallback = Box<dyn Fn(&str, Option<&str>) + Send + Sync>;

/// Callback for opening an options page
pub type OpenOptionsPageCallback = Box<dyn Fn(&str, &str) + Send + Sync>;

/// Callback for reloading a page
pub type ReloadPageCallback = Box<dyn Fn() + Send + Sync>;

/// Callback for reloading an extension
pub type ReloadExtensionCallback = Box<dyn Fn(&str) + Send + Sync>;

/// Callback for executing a script
pub type ExecuteScriptCallback = Box<dyn Fn(&str, &Value) -> Vec<Value> + Send + Sync>;

/// Callback for injecting/removing CSS
pub type CssCallback = Box<dyn Fn(&str, &Value) + Send + Sync>;

/// Callback for showing a system notification
pub type NotificationCallback = Box<dyn Fn(&NotificationInfo) + Send + Sync>;

/// Callback for creating a window
pub type CreateWindowCallback = Box<dyn Fn(&Value) -> Value + Send + Sync>;

/// Callback for dispatching an event to an extension
pub type EventDispatchCallback = Box<dyn Fn(&str, &str, &str, &[Value]) + Send + Sync>;

/// Callback for persisting storage data
pub type StoragePersistCallback = Box<dyn Fn(&str, &str, &HashMap<String, Value>) + Send + Sync>;

/// Callback for runtime message routing
pub type RuntimeMessageCallback = Box<dyn Fn(&str, Value) -> Option<Value> + Send + Sync>;

// ============================================================================
// Callback struct
// ============================================================================

/// Callbacks for the extensions plugin
#[derive(Default)]
pub struct ExtensionsCallbacks {
    /// Navigation callback (tabs.create, tabs.update)
    pub on_navigate: Option<NavigateCallback>,
    /// Send message to content scripts
    pub on_send_message: Option<SendMessageCallback>,
    /// Open popup
    pub on_open_popup: Option<OpenPopupCallback>,
    /// Open options page
    pub on_open_options_page: Option<OpenOptionsPageCallback>,
    /// Reload the current page
    pub on_reload_page: Option<ReloadPageCallback>,
    /// Reload an extension
    pub on_reload_extension: Option<ReloadExtensionCallback>,
    /// Execute script
    pub on_execute_script: Option<ExecuteScriptCallback>,
    /// Insert CSS
    pub on_insert_css: Option<CssCallback>,
    /// Remove CSS
    pub on_remove_css: Option<CssCallback>,
    /// Show system notification
    pub on_notification: Option<NotificationCallback>,
    /// Create window
    pub on_create_window: Option<CreateWindowCallback>,
    /// Dispatch event to extension
    pub on_event_dispatch: Option<EventDispatchCallback>,
    /// Persist storage data
    pub on_storage_persist: Option<StoragePersistCallback>,
    /// Runtime message routing
    pub on_runtime_message: Option<RuntimeMessageCallback>,
}

// ============================================================================
// State structs
// ============================================================================

/// State for the extensions plugin
#[derive(Default)]
pub struct ExtensionsState {
    /// Loaded extensions
    pub extensions: HashMap<String, ExtensionInfo>,
    /// Storage data per extension per area
    pub storage: HashMap<String, HashMap<String, Value>>,
    /// Side panel state per extension
    pub side_panels: HashMap<String, SidePanelState>,
    /// Action state per extension
    pub actions: HashMap<String, ActionState>,
    /// Alarms per extension
    pub alarms: HashMap<String, HashMap<String, AlarmInfo>>,
    /// Notifications per extension
    pub notifications: HashMap<String, HashMap<String, NotificationInfo>>,
    /// Context menus per extension
    pub context_menus: HashMap<String, HashMap<String, MenuItemInfo>>,
    /// Registered content scripts
    pub content_scripts: HashMap<String, Vec<ContentScriptInfo>>,
    /// Message handlers (for runtime.onMessage)
    pub message_handlers: HashMap<String, Vec<String>>,
    /// Extensions directory
    pub extensions_dir: Option<PathBuf>,
    /// Storage directory
    pub storage_dir: Option<PathBuf>,
}

// ============================================================================
// Extension information structs
// ============================================================================

/// Extension information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExtensionInfo {
    /// Extension ID
    pub id: String,
    /// Extension name
    pub name: String,
    /// Extension version
    pub version: String,
    /// Extension description
    pub description: String,
    /// Whether extension is enabled
    pub enabled: bool,
    /// Side panel path (if any)
    pub side_panel_path: Option<String>,
    /// Popup path (if any)
    pub popup_path: Option<String>,
    /// Options page path (if any)
    pub options_page: Option<String>,
    /// Root directory
    pub root_dir: String,
    /// Permissions
    pub permissions: Vec<String>,
    /// Host permissions
    pub host_permissions: Vec<String>,
    /// Manifest data
    pub manifest: Option<Value>,
}

/// Side panel state
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SidePanelState {
    /// Whether the panel is open
    pub is_open: bool,
    /// Current path
    pub path: Option<String>,
    /// Panel options
    pub options: Option<SidePanelOptions>,
}

/// Side panel options
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SidePanelOptions {
    pub path: Option<String>,
    pub enabled: Option<bool>,
}

/// Action (toolbar button) state
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActionState {
    pub title: Option<String>,
    pub badge_text: Option<String>,
    pub badge_background_color: Option<String>,
    pub badge_text_color: Option<String>,
    pub popup: Option<String>,
    pub enabled: bool,
    pub icon: Option<Value>,
}

/// Alarm information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AlarmInfo {
    pub name: String,
    pub scheduled_time: f64,
    pub period_in_minutes: Option<f64>,
}

/// Notification information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NotificationInfo {
    pub id: String,
    pub title: String,
    pub message: String,
    pub icon_url: Option<String>,
    pub notification_type: String,
    pub created_at: i64,
}

/// Context menu item information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MenuItemInfo {
    pub id: String,
    pub title: Option<String>,
    pub item_type: String,
    pub contexts: Vec<String>,
    pub parent_id: Option<String>,
    pub enabled: bool,
    pub visible: bool,
}

/// Content script information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContentScriptInfo {
    pub id: String,
    pub matches: Vec<String>,
    pub js: Vec<String>,
    pub css: Vec<String>,
    pub run_at: String,
    pub all_frames: bool,
}

// ============================================================================
// Request structs
// ============================================================================

/// API call request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ApiCallRequest {
    /// Extension ID
    #[serde(alias = "extension_id")]
    pub extension_id: String,
    /// API namespace (storage, tabs, etc.)
    pub api: String,
    /// Method name
    pub method: String,
    /// Parameters
    #[serde(default)]
    pub params: Value,
}

/// Extension ID request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExtensionIdRequest {
    /// Extension ID
    #[serde(alias = "extension_id")]
    pub extension_id: String,
}

/// Event dispatch request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EventDispatchRequest {
    #[serde(alias = "extension_id")]
    pub extension_id: String,
    pub api: String,
    pub event: String,
    pub args: Vec<Value>,
}

/// View type for API requests
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ViewTypeRequest {
    ServiceWorker,
    Popup,
    SidePanel,
    Options,
    DevToolsPanel,
}

impl From<ViewTypeRequest> for auroraview_extensions::ExtensionViewType {
    fn from(req: ViewTypeRequest) -> Self {
        match req {
            ViewTypeRequest::ServiceWorker => {
                auroraview_extensions::ExtensionViewType::ServiceWorker
            }
            ViewTypeRequest::Popup => auroraview_extensions::ExtensionViewType::Popup,
            ViewTypeRequest::SidePanel => auroraview_extensions::ExtensionViewType::SidePanel,
            ViewTypeRequest::Options => auroraview_extensions::ExtensionViewType::Options,
            ViewTypeRequest::DevToolsPanel => {
                auroraview_extensions::ExtensionViewType::DevToolsPanel
            }
        }
    }
}

/// Create view request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateViewRequest {
    #[serde(alias = "extension_id")]
    pub extension_id: String,
    #[serde(alias = "view_type")]
    pub view_type: ViewTypeRequest,
    #[serde(alias = "html_path")]
    pub html_path: String,
    pub title: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    #[serde(alias = "dev_tools")]
    pub dev_tools: Option<bool>,
    #[serde(alias = "debug_port")]
    pub debug_port: Option<u16>,
    pub visible: Option<bool>,
    #[serde(alias = "parent_hwnd")]
    pub parent_hwnd: Option<u64>,
}

/// View ID request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ViewIdRequest {
    #[serde(alias = "view_id")]
    pub view_id: String,
}
