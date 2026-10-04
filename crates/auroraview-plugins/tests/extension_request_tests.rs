//! Extension request compatibility at the plugin and shared DTO boundaries.

use auroraview_plugins::extensions::{
    types, CreateViewRequest, EventDispatchRequest, ExtensionIdRequest, ExtensionsPlugin,
    ViewIdRequest, ViewTypeRequest,
};
use auroraview_plugins::PluginHandler;
use rstest::rstest;
use serde_json::{json, Value};

fn view_args(camel_case: bool) -> Value {
    if camel_case {
        json!({
            "extensionId": "request-ext", "viewType": "popup", "htmlPath": "popup.html",
            "title": "Popup", "width": 320, "height": 240,
            "devTools": true, "debugPort": 9222, "visible": false, "parentHwnd": 1234
        })
    } else {
        json!({
            "extension_id": "request-ext", "view_type": "popup", "html_path": "popup.html",
            "title": "Popup", "width": 320, "height": 240,
            "dev_tools": true, "debug_port": 9222, "visible": false, "parent_hwnd": 1234
        })
    }
}

#[rstest]
fn api_call_routes_both_id_formats(#[values("extensionId", "extension_id")] id_key: &str) {
    let plugin = ExtensionsPlugin::new();
    let mut args = json!({
        "api": "storage", "method": "set",
        "params": { "area": "local", "items": { "key": "value" } }
    });
    args[id_key] = json!("request-ext");
    plugin
        .handle("api_call", args.clone(), &Default::default())
        .unwrap();

    args["method"] = json!("get");
    args["params"] = json!({ "area": "local", "keys": ["key"] });
    let result = plugin
        .handle("api_call", args, &Default::default())
        .unwrap();
    assert_eq!(result, json!({ "key": "value" }));
}

#[rstest]
fn extension_id_accepts_both_formats(#[values("extensionId", "extension_id")] id_key: &str) {
    let mut args = json!({});
    args[id_key] = json!("request-ext");
    let request: ExtensionIdRequest = serde_json::from_value(args).unwrap();
    assert_eq!(request.extension_id, "request-ext");
}

#[rstest]
fn view_id_accepts_both_formats(#[values("viewId", "view_id")] id_key: &str) {
    let mut args = json!({});
    args[id_key] = json!("view-1");
    let request: ViewIdRequest = serde_json::from_value(args).unwrap();
    assert_eq!(request.view_id, "view-1");
}

#[rstest]
fn create_view_preserves_options(#[values(true, false)] camel_case: bool) {
    let request: CreateViewRequest = serde_json::from_value(view_args(camel_case)).unwrap();
    assert_eq!(request.extension_id, "request-ext");
    assert!(matches!(request.view_type, ViewTypeRequest::Popup));
    assert_eq!(request.html_path.as_deref(), Some("popup.html"));
    assert_eq!(request.title.as_deref(), Some("Popup"));
    assert_eq!(request.width, Some(320));
    assert_eq!(request.height, Some(240));
    assert_eq!(request.dev_tools, Some(true));
    assert_eq!(request.debug_port, Some(9222));
    assert_eq!(request.visible, Some(false));
    assert_eq!(request.parent_hwnd, Some(1234));
}

#[rstest]
fn event_dispatch_accepts_both_formats(#[values("extensionId", "extension_id")] id_key: &str) {
    let mut args = json!({ "api": "storage", "event": "onChanged", "args": ["change"] });
    args[id_key] = json!("request-ext");
    let request: EventDispatchRequest = serde_json::from_value(args).unwrap();
    assert_eq!(request.extension_id, "request-ext");
    assert_eq!(request.api, "storage");
    assert_eq!(request.event, "onChanged");
    assert_eq!(request.args, vec![json!("change")]);
}

#[rstest]
fn shared_create_view_serializes_camel_case(#[values(true, false)] camel_case: bool) {
    let request: types::CreateViewRequest = serde_json::from_value(view_args(camel_case)).unwrap();
    assert_eq!(serde_json::to_value(request).unwrap(), view_args(true));
}

#[rstest]
#[case("api_call", json!({ "api": "storage", "method": "get", "params": {} }))]
#[case("extension", json!({}))]
#[case("event", json!({ "api": "storage", "event": "onChanged", "args": [] }))]
fn shared_extension_requests_serialize_camel_case(
    #[case] request_type: &str,
    #[case] mut args: Value,
    #[values("extensionId", "extension_id")] id_key: &str,
) {
    let mut expected = args.clone();
    expected["extensionId"] = json!("request-ext");
    args[id_key] = json!("request-ext");
    let actual = match request_type {
        "api_call" => {
            serde_json::to_value(serde_json::from_value::<types::ApiCallRequest>(args).unwrap())
        }
        "extension" => {
            serde_json::to_value(serde_json::from_value::<types::ExtensionIdRequest>(args).unwrap())
        }
        "event" => serde_json::to_value(
            serde_json::from_value::<types::EventDispatchRequest>(args).unwrap(),
        ),
        _ => unreachable!(),
    }
    .unwrap();
    assert_eq!(actual, expected);
}

#[rstest]
fn shared_view_id_serializes_camel_case(#[values("viewId", "view_id")] id_key: &str) {
    let mut args = json!({});
    args[id_key] = json!("view-1");
    let request: types::ViewIdRequest = serde_json::from_value(args).unwrap();
    assert_eq!(
        serde_json::to_value(request).unwrap(),
        json!({ "viewId": "view-1" })
    );
}

#[rstest]
#[case("api_call", json!({ "api": "storage", "method": "get", "params": {} }), "extension_id")]
#[case("get_extension", json!({}), "extension_id")]
#[case("show_view", json!({}), "view_id")]
#[case("create_view", json!({ "viewType": "popup" }), "extension_id")]
#[case("dispatch_event", json!({ "api": "storage", "event": "onChanged", "args": [] }), "extension_id")]
fn missing_id_is_rejected(#[case] command: &str, #[case] args: Value, #[case] field: &str) {
    let plugin = ExtensionsPlugin::new();
    let error = plugin
        .handle(command, args, &Default::default())
        .unwrap_err();
    assert_eq!(error.code(), "INVALID_ARGS");
    assert!(error.message().contains(field));
}
