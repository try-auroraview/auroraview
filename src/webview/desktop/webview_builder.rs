//! WebView builder configuration for desktop mode.
//!
//! This module handles configuring the WebView builder with all the handlers
//! and settings required for the desktop mode.

use std::sync::{Arc, Mutex};

use wry::WebViewBuilder as WryWebViewBuilder;
#[cfg(target_os = "windows")]
use wry::WebViewBuilderExtWindows;

use crate::ipc::{IpcHandler, IpcMessage, MessageQueue};
use crate::webview::config::{NewWindowMode, WebViewConfig};
use crate::webview::event_loop::UserEvent;
use crate::webview::{child_window, js_assets};

/// Configures and returns a WebViewBuilder with all handlers and settings.
pub fn configure_webview_builder(
    config: &WebViewConfig,
    ipc_handler: Arc<IpcHandler>,
    message_queue: Arc<MessageQueue>,
    _window: &tao::window::Window,
) -> Result<wry::WebViewBuilder<'static>, Box<dyn std::error::Error>> {
    // Create WebContext with unique user data folder per process.
    // Wry's builder borrows the context for the builder lifetime, so keep it
    // alive for the process lifetime like the previous standalone runtime did.
    let web_context = Box::leak(Box::new(create_web_context(config)?));

    configure_with_context(config, ipc_handler, message_queue, web_context)
}

/// Configure shared transport and options while borrowing an owned context.
pub(crate) fn configure_with_context<'a>(
    config: &WebViewConfig,
    ipc_handler: Arc<IpcHandler>,
    message_queue: Arc<MessageQueue>,
    web_context: &'a mut wry::WebContext,
) -> Result<wry::WebViewBuilder<'a>, Box<dyn std::error::Error>> {
    // Create the WebView builder
    let mut webview_builder = WryWebViewBuilder::new_with_web_context(web_context);

    // Configure dev tools
    if config.dev_tools {
        webview_builder = webview_builder.with_devtools(true);
    }

    // Set remote debugging port
    #[cfg(target_os = "windows")]
    {
        if let Some(port) = config.remote_debugging_port {
            let args = format!("--remote-debugging-port={}", port);
            webview_builder = webview_builder.with_additional_browser_args(&args);
        }
    }

    // Set background color
    if config.transparent {
        webview_builder = webview_builder
            .with_transparent(true)
            .with_background_color((0, 0, 0, 0));
    } else {
        let background_color = auroraview_core::builder::get_background_color();
        webview_builder = webview_builder.with_background_color(background_color);
    }

    // Register auroraview:// protocol
    let asset_root_for_protocol = config.asset_root.clone();
    #[cfg(target_os = "windows")]
    {
        webview_builder = webview_builder.with_https_scheme(true);
    }

    let default_asset_root = std::env::current_dir().unwrap_or_default();
    let protocol_asset_root = asset_root_for_protocol.unwrap_or(default_asset_root);

    webview_builder =
        webview_builder.with_custom_protocol("auroraview".into(), move |_webview_id, request| {
            crate::webview::protocol_handlers::handle_auroraview_protocol(
                &protocol_asset_root,
                request,
            )
        });

    // Register file:// protocol if enabled
    if config.allow_file_protocol {
        webview_builder = webview_builder
            .with_custom_protocol("file".into(), |_webview_id, request| {
                crate::webview::protocol_handlers::handle_file_protocol(request)
            });
    }

    // Build initialization script
    let mut init_script = js_assets::build_init_script(config);
    if config.splash_overlay {
        let splash_js = auroraview_core::assets::get_splash_overlay_js();
        init_script = format!("{}\n\n// Splash Overlay\n{}", init_script, splash_js);
    }
    webview_builder = webview_builder.with_initialization_script(&init_script);

    // Add proxy configuration
    if let Some(ref proxy_url) = config.proxy_url {
        webview_builder = configure_proxy(webview_builder, proxy_url)?;
    }

    // Add navigation handler
    if config.block_external_navigation {
        webview_builder =
            add_navigation_handler(webview_builder, &config.allowed_navigation_domains);
    }

    #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
    if message_queue.hosted_state() != 0 {
        webview_builder = add_hosted_navigation_handler(
            webview_builder,
            config,
            message_queue.clone(),
            ipc_handler.clone(),
        );
    }

    // The experimental single-document owner cannot adopt another window.
    let new_window_mode = config.new_window_mode;
    #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
    let new_window_mode = if message_queue.hosted_state() != 0 {
        NewWindowMode::Deny
    } else {
        new_window_mode
    };
    webview_builder = add_new_window_handler(webview_builder, new_window_mode);

    // Add content loading
    webview_builder = configure_initial_content(webview_builder, config);

    // Add user agent
    if let Some(ref user_agent) = config.user_agent {
        webview_builder = webview_builder.with_user_agent(user_agent);
    }

    // Add page load handler
    webview_builder =
        add_page_load_handler(webview_builder, ipc_handler.clone(), message_queue.clone());

    // Add title change handler
    webview_builder = add_title_change_handler(webview_builder, ipc_handler.clone());

    // Add download handlers
    if config.allow_downloads {
        webview_builder = add_download_handlers(
            webview_builder,
            config,
            ipc_handler.clone(),
            message_queue.clone(),
        );
    }

    // Conditionally attach drag-drop proxy (RFC 0015). Must run before
    // `add_ipc_handler` consumes `ipc_handler`.
    webview_builder = auroraview_core::builder::attach_drag_drop_handler(
        webview_builder,
        config.capture_file_drop,
        &ipc_handler,
    );

    // Add IPC handler
    webview_builder = add_ipc_handler(webview_builder, ipc_handler, message_queue);

    Ok(webview_builder)
}

/// Create WebContext with unique user data folder per process.
pub(crate) fn create_web_context(
    config: &WebViewConfig,
) -> Result<wry::WebContext, Box<dyn std::error::Error>> {
    if let Some(ref data_dir) = config.data_directory {
        Ok(wry::WebContext::new(Some(data_dir.clone())))
    } else {
        #[cfg(target_os = "windows")]
        {
            let local_app_data = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
            let pid = std::process::id();
            let cache_dir = std::path::PathBuf::from(local_app_data)
                .join("AuroraView")
                .join("WebView2")
                .join(format!("process_{}", pid));
            Ok(wry::WebContext::new(Some(cache_dir)))
        }
        #[cfg(not(target_os = "windows"))]
        {
            Ok(wry::WebContext::default())
        }
    }
}

/// Configure proxy settings for WebView builder.
fn configure_proxy<'a>(
    builder: wry::WebViewBuilder<'a>,
    proxy_url: &str,
) -> Result<wry::WebViewBuilder<'a>, Box<dyn std::error::Error>> {
    if let Ok(url) = url::Url::parse(proxy_url) {
        let host = url.host_str().unwrap_or("localhost").to_string();
        let port = url.port().unwrap_or(8080).to_string();
        let endpoint = wry::ProxyEndpoint { host, port };

        let proxy_config = match url.scheme() {
            "socks5" | "socks" => wry::ProxyConfig::Socks5(endpoint),
            _ => wry::ProxyConfig::Http(endpoint),
        };

        Ok(builder.with_proxy_config(proxy_config))
    } else {
        tracing::warn!("[standalone] Invalid proxy URL: {}", proxy_url);
        Ok(builder)
    }
}

/// Add navigation handler for security filtering.
fn add_navigation_handler<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    allowed_domains: &[String],
) -> wry::WebViewBuilder<'a> {
    let allowed_domains = allowed_domains.to_vec();
    builder =
        builder.with_navigation_handler(move |uri| navigation_allowed(&uri, &allowed_domains));
    builder
}

fn navigation_allowed(uri: &str, allowed_domains: &[String]) -> bool {
    if uri.starts_with("auroraview://")
        || uri.starts_with("data:")
        || uri.starts_with("about:")
        || uri.starts_with("blob:")
    {
        return true;
    }
    if let Ok(url) = url::Url::parse(uri) {
        if let Some(host) = url.host_str() {
            for allowed in allowed_domains {
                if host == allowed || host.ends_with(&format!(".{}", allowed)) {
                    return true;
                }
            }
        }
    }
    false
}

/// A fail-closed, single-document boundary, not a cross-document generation protocol.
/// Keep the existing security filter when overriding the one Wry policy handler.
#[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
fn add_hosted_navigation_handler<'a>(
    builder: wry::WebViewBuilder<'a>,
    config: &WebViewConfig,
    queue: Arc<MessageQueue>,
    ipc_handler: Arc<IpcHandler>,
) -> wry::WebViewBuilder<'a> {
    // HostRuntime rejects initial URL content before native construction.
    // Only Wry's initial inline HTML (about:blank) gets a bootstrap exception.
    let block_external = config.block_external_navigation;
    let allowed_domains = config.allowed_navigation_domains.clone();
    builder.with_navigation_handler(move |uri| {
        let is_initial = uri == "about:blank";
        let allowed = !block_external || navigation_allowed(&uri, &allowed_domains);
        let accepted = queue.hosted_navigation_request(is_initial && allowed);
        if !accepted {
            ipc_handler.close_admission();
        }
        accepted
    })
}

/// Add new window handler based on configuration.
fn add_new_window_handler<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    mode: NewWindowMode,
) -> wry::WebViewBuilder<'a> {
    match mode {
        NewWindowMode::Deny => {
            builder =
                builder.with_new_window_req_handler(|_url, _features| wry::NewWindowResponse::Deny);
        }
        NewWindowMode::SystemBrowser => {
            builder = builder.with_new_window_req_handler(|url, _features| {
                let _ = open::that(&url);
                wry::NewWindowResponse::Deny
            });
        }
        NewWindowMode::ChildWebView => {
            builder = builder.with_new_window_req_handler(move |url, features| {
                let width = features.size.map(|s| s.width as u32).unwrap_or(1024);
                let height = features.size.map(|s| s.height as u32).unwrap_or(768);
                let _ = child_window::create_child_webview_window(&url, width, height);
                wry::NewWindowResponse::Deny
            });
        }
    }
    builder
}

/// Configure initial content (HTML or URL) for WebView.
fn configure_initial_content<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    config: &WebViewConfig,
) -> wry::WebViewBuilder<'a> {
    if let Some(ref html) = config.html {
        builder = builder.with_html(html);
    } else if let Some(ref url) = config.url {
        builder = builder.with_url(url);
    } else {
        let loading_html = js_assets::get_loading_html();
        builder = builder.with_html(loading_html);
    }
    builder
}

/// Add page load handler.
fn add_page_load_handler<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    ipc_handler: Arc<IpcHandler>,
    _message_queue: Arc<MessageQueue>,
) -> wry::WebViewBuilder<'a> {
    builder = builder.with_on_page_load_handler(move |event, url| {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if _message_queue.hosted_state() != 0 {
            if matches!(&event, wry::PageLoadEvent::Started)
                && !_message_queue.hosted_document_started(url == "about:blank")
            {
                ipc_handler.close_admission();
                return;
            }
            if !_message_queue.hosted_ipc_allowed() {
                return;
            }
        }
        let event_name = match event {
            wry::PageLoadEvent::Started => "page_load_started",
            wry::PageLoadEvent::Finished => "page_load_finished",
        };

        let ipc_message = IpcMessage {
            event: event_name.to_string(),
            data: serde_json::json!({ "url": url }),
            id: None,
        };

        let _ = ipc_handler.handle_message(ipc_message);
    });
    builder
}

/// Add document title changed handler.
fn add_title_change_handler<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    ipc_handler: Arc<IpcHandler>,
) -> wry::WebViewBuilder<'a> {
    builder = builder.with_document_title_changed_handler(move |title| {
        let ipc_message = IpcMessage {
            event: "title_changed".to_string(),
            data: serde_json::json!({ "title": title }),
            id: None,
        };

        let _ = ipc_handler.handle_message(ipc_message);
    });
    builder
}

/// Add download handlers.
fn add_download_handlers<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    config: &WebViewConfig,
    ipc_handler: Arc<IpcHandler>,
    _message_queue: Arc<MessageQueue>,
) -> wry::WebViewBuilder<'a> {
    let download_dir = config
        .download_directory
        .clone()
        .or_else(dirs::download_dir);
    let download_prompt = config.download_prompt;
    let ipc_handler_for_download_start = ipc_handler.clone();
    let ipc_handler_for_download_complete = ipc_handler.clone();

    builder = builder.with_download_started_handler(move |url, path| {
        // Get the filename from the original path
        let filename = path
            .file_name()
            .map(|f| f.to_string_lossy().to_string())
            .unwrap_or_else(|| "download".to_string());

        // If download_prompt is enabled, show "Save As" dialog
        if download_prompt {
            use rfd::FileDialog;

            let mut dialog = FileDialog::new().set_file_name(&filename);

            // Set initial directory to download_dir if available
            if let Some(ref dir) = download_dir {
                dialog = dialog.set_directory(dir);
            }

            // Try to set file filter based on extension
            if let Some(ext) = path.extension() {
                let ext_str = ext.to_string_lossy().to_string();
                dialog = dialog.add_filter(ext_str.to_uppercase(), &[&ext_str]);
            }
            dialog = dialog.add_filter("All Files", &["*"]);

            if let Some(save_path) = dialog.save_file() {
                *path = save_path.clone();
            } else {
                // User cancelled the dialog
                let ipc_message = IpcMessage {
                    event: "download_cancelled".to_string(),
                    data: serde_json::json!({
                        "url": url,
                        "filename": filename
                    }),
                    id: None,
                };
                let _ = ipc_handler_for_download_start.handle_message(ipc_message);
                return false;
            }
        } else {
            // Use download directory (custom or system default)
            if let Some(ref dir) = download_dir {
                if let Some(fname) = path.file_name() {
                    *path = dir.join(fname);
                }
            }
        }

        // Emit event to JavaScript
        let ipc_message = IpcMessage {
            event: "download_started".to_string(),
            data: serde_json::json!({
                "url": url,
                "path": path.to_string_lossy()
            }),
            id: None,
        };

        let _ = ipc_handler_for_download_start.handle_message(ipc_message);

        true
    });

    builder = builder.with_download_completed_handler(move |url, path, success| {
        // Emit event to JavaScript
        let ipc_message = IpcMessage {
            event: "download_completed".to_string(),
            data: serde_json::json!({
                "url": url,
                "path": path.map(|p| p.to_string_lossy().to_string()),
                "success": success
            }),
            id: None,
        };

        let _ = ipc_handler_for_download_complete.handle_message(ipc_message);
    });

    builder
}

/// Add IPC handler for JavaScript communication.
fn add_ipc_handler<'a>(
    mut builder: wry::WebViewBuilder<'a>,
    ipc_handler: Arc<IpcHandler>,
    message_queue: Arc<MessageQueue>,
) -> wry::WebViewBuilder<'a> {
    // Create event loop proxy holder for native window operations
    let event_loop_proxy_holder: Arc<Mutex<Option<tao::event_loop::EventLoopProxy<UserEvent>>>> =
        Arc::new(Mutex::new(None));
    let event_loop_proxy_for_ipc = event_loop_proxy_holder.clone();

    // Create plugin router for handling plugin commands
    let plugin_router = Arc::new(std::sync::RwLock::new(
        auroraview_core::plugins::create_router_with_scope(
            auroraview_core::plugins::ScopeConfig::permissive(),
        ),
    ));
    let plugin_router_clone = plugin_router.clone();

    builder = builder.with_ipc_handler(move |request| {
        #[cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]
        if message_queue.hosted_state() != 0 && !message_queue.hosted_ipc_allowed() { return; }
        let body_str = request.body();
        if let Ok(message) = serde_json::from_str::<serde_json::Value>(body_str) {
            if let Some(msg_type) = message.get("type").and_then(|v| v.as_str()) {
                // Handle internal window operations
                if msg_type == "__internal" {
                    if let Some(action) = message.get("action").and_then(|v| v.as_str()) {
                        if action == "drag_window" {
                            if let Ok(proxy_guard) = event_loop_proxy_for_ipc.lock() {
                                if let Some(proxy) = proxy_guard.as_ref() {
                                    let _ = proxy.send_event(UserEvent::DragWindow);
                                }
                            }
                        }
                    }
                } else if msg_type == "event" {
                    if let Some(event_name) = message.get("event").and_then(|v| v.as_str()) {
                        let detail = message
                            .get("detail")
                            .cloned()
                            .unwrap_or(serde_json::Value::Null);
                        let ipc_message = IpcMessage {
                            event: event_name.to_string(),
                            data: detail,
                            id: None,
                        };
                        let _ = ipc_handler.handle_message(ipc_message);
                    }
                } else if msg_type == "js_callback_result" {
                    // Reuse the existing native callback manager for Wry too.
                    // The same message is already handled by the Windows backend.
                    let _ = ipc_handler.handle_message(IpcMessage {
                        event: "__js_callback_result__".to_string(),
                        data: message.clone(),
                        id: None,
                    });
                } else if msg_type == "call" {
                    if let Some(method) = message.get("method").and_then(|v| v.as_str()) {
                        let id = message
                            .get("id")
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string());
                        let params = message.get("params").cloned();

                        let mut payload = serde_json::Map::new();
                        if let Some(ref call_id) = id {
                            payload.insert("id".to_string(), serde_json::Value::String(call_id.clone()));
                        }
                        if let Some(p) = params {
                            payload.insert("params".to_string(), p);
                        }

                        let ipc_message = IpcMessage {
                            event: method.to_string(),
                            data: serde_json::Value::Object(payload),
                            id,
                        };
                        let _ = ipc_handler.handle_message(ipc_message);
                    }
                } else if msg_type == "invoke" {
                    // Handle plugin invoke commands
                    let cmd = message.get("cmd").and_then(|v| v.as_str());
                    let args = message
                        .get("args")
                        .cloned()
                        .unwrap_or(serde_json::Value::Object(serde_json::Map::new()));
                    let id = message
                        .get("id")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string());

                    if let Some(invoke_cmd) = cmd {
                        let response = if let Ok(router) = plugin_router_clone.read() {
                            if let Some(request) =
                                auroraview_core::plugins::PluginRequest::from_invoke(invoke_cmd, args)
                            {
                                router.handle(request)
                            } else {
                                auroraview_core::plugins::PluginResponse::err(
                                    format!("Invalid plugin command: {}", invoke_cmd),
                                    "INVALID_COMMAND",
                                )
                            }
                        } else {
                            auroraview_core::plugins::PluginResponse::err(
                                "Plugin router lock failed",
                                "INTERNAL_ERROR",
                            )
                        };

                        // Send result back to JavaScript
                        if let Some(call_id) = id {
                            let result_payload = if response.success {
                                serde_json::json!({
                                    "type": "call_result",
                                    "id": call_id,
                                    "ok": true,
                                    "result": response.data
                                })
                            } else {
                                serde_json::json!({
                                    "type": "call_result",
                                    "id": call_id,
                                    "ok": false,
                                    "error": {
                                        "name": "PluginError",
                                        "message": response.error.unwrap_or_default(),
                                        "code": response.code
                                    }
                                })
                            };

                            let json_str = result_payload.to_string();
                            let script = format!(
                                "(function() {{
                                    if (window.auroraview && window.auroraview.trigger) {{
                                        window.auroraview.trigger('__auroraview_call_result', {});
                                    }} else {{
                                        console.error('[AuroraView] Event bridge not ready, cannot emit call_result');
                                    }}
                                }})();",
                                json_str
                            );
                            message_queue.push(crate::ipc::WebViewMessage::EvalJs(script));
                        }
                    }
                }
            }
        }
    });

    builder
}
