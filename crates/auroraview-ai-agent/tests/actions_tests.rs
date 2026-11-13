//! Integration tests for action system and provider types

use auroraview_ai_agent::{
    Action, ActionContext, ActionRegistry, ActionResult, ChatOptions, CompletionResponse,
    ModelInfo, ProviderType, StreamEvent, ToolCall, ToolDef, UsageStats,
};
use rstest::rstest;
use serde_json::{json, Value};

// ─────────────────────────────────────────────────────────────
// ActionResult
// ─────────────────────────────────────────────────────────────

#[test]
fn action_result_ok_sets_success_true() {
    let r = ActionResult::ok(json!({"key": "val"}));
    assert!(r.success);
    assert!(r.error.is_none());
    assert!(r.data.is_some());
}

#[test]
fn action_result_ok_data_matches_input() {
    let r = ActionResult::ok(json!({"count": 42}));
    let data = r.data.unwrap();
    assert_eq!(data["count"], 42);
}

#[test]
fn action_result_err_sets_success_false() {
    let r = ActionResult::err("something went wrong");
    assert!(!r.success);
    assert_eq!(r.error.as_deref(), Some("something went wrong"));
    assert!(r.data.is_none());
}

#[test]
fn action_result_empty_success_no_data_no_error() {
    let r = ActionResult::empty();
    assert!(r.success);
    assert!(r.data.is_none());
    assert!(r.error.is_none());
}

// ─────────────────────────────────────────────────────────────
// ActionContext builder
// ─────────────────────────────────────────────────────────────

#[test]
fn action_context_new_defaults_empty() {
    let ctx = ActionContext::new();
    assert!(ctx.current_url.is_none());
    assert!(ctx.page_title.is_none());
}

#[test]
fn action_context_with_url() {
    let ctx = ActionContext::new().with_url("https://example.com");
    assert_eq!(ctx.current_url.as_deref(), Some("https://example.com"));
}

#[test]
fn action_context_with_title() {
    let ctx = ActionContext::new().with_title("My Page");
    assert_eq!(ctx.page_title.as_deref(), Some("My Page"));
}

#[test]
fn action_context_with_data() {
    let ctx = ActionContext::new().with_data(json!({"foo": "bar"}));
    assert_eq!(ctx.data["foo"], "bar");
}

#[test]
fn action_context_chaining() {
    let ctx = ActionContext::new()
        .with_url("https://example.com")
        .with_title("Example")
        .with_data(json!({"x": 1}));
    assert!(ctx.current_url.is_some());
    assert!(ctx.page_title.is_some());
    assert_eq!(ctx.data["x"], 1);
}

// ─────────────────────────────────────────────────────────────
// Built-in actions – execute success paths
// ─────────────────────────────────────────────────────────────

#[test]
fn navigate_action_returns_navigated_url() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("navigate").expect("navigate registered");
    let ctx = ActionContext::new();
    let args = json!({"url": "https://rust-lang.org"});
    let result = action.execute(args, &ctx).unwrap();
    assert!(result.success);
    let data = result.data.unwrap();
    assert_eq!(data["navigated_to"], "https://rust-lang.org");
}

#[test]
fn navigate_action_missing_url_returns_error() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("navigate").unwrap();
    let ctx = ActionContext::new();
    let err = action.execute(json!({}), &ctx);
    assert!(err.is_err());
}

#[rstest]
#[case("google", "google.com")]
#[case("bing", "bing.com")]
#[case("duckduckgo", "duckduckgo.com")]
fn search_action_builds_correct_url(#[case] engine: &str, #[case] domain: &str) {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("search").unwrap();
    let ctx = ActionContext::new();
    let args = json!({"query": "rust", "engine": engine});
    let result = action.execute(args, &ctx).unwrap();
    assert!(result.success);
    let url = result.data.unwrap()["search_url"]
        .as_str()
        .unwrap()
        .to_string();
    assert!(url.contains(domain), "URL {url} should contain {domain}");
}

#[test]
fn search_action_defaults_to_google() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("search").unwrap();
    let ctx = ActionContext::new();
    let result = action.execute(json!({"query": "rust"}), &ctx).unwrap();
    let url = result.data.unwrap()["search_url"]
        .as_str()
        .unwrap()
        .to_string();
    assert!(url.contains("google.com"));
}

#[test]
fn search_action_missing_query_returns_error() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("search").unwrap();
    let err = action.execute(json!({}), &ActionContext::new());
    assert!(err.is_err());
}

#[test]
fn click_action_with_selector() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("click").unwrap();
    let ctx = ActionContext::new();
    let result = action.execute(json!({"selector": "#btn"}), &ctx).unwrap();
    assert!(result.success);
    assert_eq!(result.data.unwrap()["clicked"], true);
}

#[test]
fn click_action_with_text() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("click").unwrap();
    let ctx = ActionContext::new();
    let result = action.execute(json!({"text": "Submit"}), &ctx).unwrap();
    assert!(result.success);
}

#[test]
fn click_action_no_args_returns_error() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("click").unwrap();
    let err = action.execute(json!({}), &ActionContext::new());
    assert!(err.is_err());
}

#[test]
fn type_action_success() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("type_text").unwrap();
    let ctx = ActionContext::new();
    let result = action
        .execute(json!({"selector": "#input", "text": "hello"}), &ctx)
        .unwrap();
    assert!(result.success);
    let data = result.data.unwrap();
    assert_eq!(data["text"], "hello");
    assert_eq!(data["cleared"], false);
}

#[test]
fn type_action_with_clear_flag() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("type_text").unwrap();
    let result = action
        .execute(
            json!({"selector": "#input", "text": "world", "clear": true}),
            &ActionContext::new(),
        )
        .unwrap();
    assert_eq!(result.data.unwrap()["cleared"], true);
}

#[test]
fn type_action_missing_selector_returns_error() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("type_text").unwrap();
    let err = action.execute(json!({"text": "hi"}), &ActionContext::new());
    assert!(err.is_err());
}

#[test]
fn screenshot_action_viewport_by_default() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("screenshot").unwrap();
    let result = action.execute(json!({}), &ActionContext::new()).unwrap();
    assert!(result.success);
    let data = result.data.unwrap();
    assert_eq!(data["full_page"], false);
}

#[test]
fn screenshot_action_full_page() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("screenshot").unwrap();
    let result = action
        .execute(json!({"full_page": true}), &ActionContext::new())
        .unwrap();
    assert_eq!(result.data.unwrap()["full_page"], true);
}

#[rstest]
#[case("up")]
#[case("down")]
#[case("left")]
#[case("right")]
fn scroll_action_all_directions(#[case] direction: &str) {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("scroll").unwrap();
    let result = action
        .execute(json!({"direction": direction}), &ActionContext::new())
        .unwrap();
    assert!(result.success);
    let data = result.data.unwrap();
    assert_eq!(data["direction"], direction);
    assert_eq!(data["amount"], 300);
}

#[test]
fn scroll_action_custom_amount() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("scroll").unwrap();
    let result = action
        .execute(
            json!({"direction": "down", "amount": 100}),
            &ActionContext::new(),
        )
        .unwrap();
    assert_eq!(result.data.unwrap()["amount"], 100);
}

#[test]
fn scroll_action_missing_direction_returns_error() {
    let registry = ActionRegistry::with_defaults();
    let action = registry.get("scroll").unwrap();
    let err = action.execute(json!({}), &ActionContext::new());
    assert!(err.is_err());
}

// ─────────────────────────────────────────────────────────────
// ActionRegistry
// ─────────────────────────────────────────────────────────────

#[test]
fn registry_new_is_empty() {
    let r = ActionRegistry::new();
    assert!(r.is_empty());
    assert_eq!(r.len(), 0);
}

#[test]
fn registry_with_defaults_has_six_actions() {
    let r = ActionRegistry::with_defaults();
    assert_eq!(r.len(), 6);
}

#[test]
fn registry_with_defaults_contains_expected_names() {
    let r = ActionRegistry::with_defaults();
    for name in [
        "navigate",
        "search",
        "click",
        "type_text",
        "screenshot",
        "scroll",
    ] {
        assert!(r.contains(name), "should contain '{name}'");
    }
}

#[test]
fn registry_get_returns_some_for_known_action() {
    let r = ActionRegistry::with_defaults();
    assert!(r.get("navigate").is_some());
}

#[test]
fn registry_get_returns_none_for_unknown_action() {
    let r = ActionRegistry::with_defaults();
    assert!(r.get("nonexistent").is_none());
}

#[test]
fn registry_remove_decreases_len() {
    let mut r = ActionRegistry::with_defaults();
    let removed = r.remove("navigate");
    assert!(removed.is_some());
    assert_eq!(r.len(), 5);
    assert!(!r.contains("navigate"));
}

#[test]
fn registry_remove_nonexistent_returns_none() {
    let mut r = ActionRegistry::with_defaults();
    assert!(r.remove("nope").is_none());
}

#[test]
fn registry_names_returns_all_names() {
    let r = ActionRegistry::with_defaults();
    let names = r.names();
    assert_eq!(names.len(), 6);
}

#[test]
fn registry_get_tools_returns_tool_defs_with_names() {
    let r = ActionRegistry::with_defaults();
    let tools = r.get_tools();
    assert_eq!(tools.len(), 6);
    let names: Vec<&str> = tools.iter().map(|t| t.name.as_str()).collect();
    assert!(names.contains(&"navigate"));
    assert!(names.contains(&"search"));
}

#[test]
fn registry_get_tools_schema_is_object() {
    let r = ActionRegistry::with_defaults();
    let tools = r.get_tools();
    for tool in &tools {
        assert_eq!(
            tool.parameters.get("type").and_then(|v| v.as_str()),
            Some("object"),
            "tool '{}' schema should be type:object",
            tool.name
        );
    }
}

// ─────────────────────────────────────────────────────────────
// Custom action registration
// ─────────────────────────────────────────────────────────────

struct PingAction;

impl Action for PingAction {
    fn name(&self) -> &str {
        "ping"
    }
    fn description(&self) -> &str {
        "Ping a host"
    }
    fn parameters(&self) -> Value {
        json!({"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]})
    }
    fn execute(
        &self,
        args: Value,
        _ctx: &ActionContext,
    ) -> Result<ActionResult, auroraview_ai_agent::AIError> {
        let host = args
            .get("host")
            .and_then(|v| v.as_str())
            .unwrap_or("localhost");
        Ok(ActionResult::ok(json!({"pong": host})))
    }
}

#[test]
fn custom_action_can_be_registered() {
    let mut r = ActionRegistry::new();
    r.register(PingAction);
    assert!(r.contains("ping"));
    assert_eq!(r.len(), 1);
}

#[test]
fn custom_action_executes_correctly() {
    let mut r = ActionRegistry::new();
    r.register(PingAction);
    let action = r.get("ping").unwrap();
    let result = action
        .execute(json!({"host": "127.0.0.1"}), &ActionContext::new())
        .unwrap();
    assert!(result.success);
    assert_eq!(result.data.unwrap()["pong"], "127.0.0.1");
}

// ─────────────────────────────────────────────────────────────
// ProviderType
// ─────────────────────────────────────────────────────────────

#[rstest]
#[case(ProviderType::OpenAI, "gpt-4o")]
#[case(ProviderType::Anthropic, "claude-3-5-sonnet-20241022")]
#[case(ProviderType::Gemini, "gemini-2.0-flash-exp")]
#[case(ProviderType::DeepSeek, "deepseek-chat")]
#[case(ProviderType::Ollama, "llama3.2")]
#[case(ProviderType::Groq, "groq::llama-3.3-70b-versatile")]
fn provider_default_model(#[case] provider: ProviderType, #[case] expected: &str) {
    assert_eq!(provider.default_model(), expected);
}

#[rstest]
#[case(ProviderType::OpenAI, "OPENAI_API_KEY")]
#[case(ProviderType::Anthropic, "ANTHROPIC_API_KEY")]
#[case(ProviderType::Gemini, "GEMINI_API_KEY")]
fn provider_env_key(#[case] provider: ProviderType, #[case] expected: &str) {
    assert_eq!(provider.env_key(), expected);
}

#[test]
fn ollama_does_not_require_api_key() {
    assert!(!ProviderType::Ollama.requires_api_key());
}

#[rstest]
#[case(ProviderType::OpenAI, true)]
#[case(ProviderType::Anthropic, true)]
#[case(ProviderType::Ollama, false)]
fn provider_requires_api_key(#[case] provider: ProviderType, #[case] expected: bool) {
    assert_eq!(provider.requires_api_key(), expected);
}

#[rstest]
#[case("openai", ProviderType::OpenAI)]
#[case("anthropic", ProviderType::Anthropic)]
#[case("claude", ProviderType::Anthropic)]
#[case("gemini", ProviderType::Gemini)]
#[case("google", ProviderType::Gemini)]
#[case("deepseek", ProviderType::DeepSeek)]
#[case("ollama", ProviderType::Ollama)]
#[case("groq", ProviderType::Groq)]
#[case("xai", ProviderType::XAI)]
#[case("grok", ProviderType::XAI)]
#[case("cohere", ProviderType::Cohere)]
#[case("custom", ProviderType::Custom)]
fn provider_from_str(#[case] input: &str, #[case] expected: ProviderType) {
    let parsed: ProviderType = input.parse().unwrap();
    assert_eq!(parsed, expected);
}

#[test]
fn provider_from_str_unknown_returns_err() {
    let err = "unknown_provider".parse::<ProviderType>();
    assert!(err.is_err());
}

#[rstest]
#[case(ProviderType::OpenAI, "openai")]
#[case(ProviderType::Anthropic, "anthropic")]
#[case(ProviderType::Gemini, "gemini")]
#[case(ProviderType::DeepSeek, "deepseek")]
#[case(ProviderType::Ollama, "ollama")]
fn provider_display(#[case] provider: ProviderType, #[case] expected: &str) {
    assert_eq!(provider.to_string(), expected);
}

#[test]
fn provider_serialization_roundtrip() {
    let p = ProviderType::Anthropic;
    let json = serde_json::to_string(&p).unwrap();
    let back: ProviderType = serde_json::from_str(&json).unwrap();
    assert_eq!(p, back);
}

// ─────────────────────────────────────────────────────────────
// ModelInfo
// ─────────────────────────────────────────────────────────────

#[test]
fn model_info_new_defaults() {
    let m = ModelInfo::new("gpt-4o", "GPT-4o", ProviderType::OpenAI);
    assert_eq!(m.id, "gpt-4o");
    assert_eq!(m.name, "GPT-4o");
    assert_eq!(m.provider, ProviderType::OpenAI);
    assert!(!m.vision);
    assert!(m.function_calling);
    assert!(m.description.is_none());
}

#[test]
fn model_info_builder_methods() {
    let m = ModelInfo::new("gpt-4o", "GPT-4o", ProviderType::OpenAI)
        .with_description("Powerful model")
        .with_context_window(128_000)
        .with_max_output(4096)
        .with_vision(true)
        .with_function_calling(true);
    assert_eq!(m.description.as_deref(), Some("Powerful model"));
    assert_eq!(m.context_window, Some(128_000));
    assert_eq!(m.max_output_tokens, Some(4096));
    assert!(m.vision);
    assert!(m.function_calling);
}

#[test]
fn model_info_serialization_roundtrip() {
    let m = ModelInfo::new("claude-3-5-sonnet", "Claude 3.5", ProviderType::Anthropic)
        .with_vision(true);
    let json = serde_json::to_string(&m).unwrap();
    let back: ModelInfo = serde_json::from_str(&json).unwrap();
    assert_eq!(back.id, m.id);
    assert_eq!(back.vision, m.vision);
    assert_eq!(back.provider, m.provider);
}

// ─────────────────────────────────────────────────────────────
// StreamEvent serialization
// ─────────────────────────────────────────────────────────────

#[test]
fn stream_event_text_delta_roundtrip() {
    let ev = StreamEvent::TextDelta {
        id: "msg_1".into(),
        delta: "hello".into(),
    };
    let json = serde_json::to_string(&ev).unwrap();
    assert!(json.contains("text_delta"));
    let back: StreamEvent = serde_json::from_str(&json).unwrap();
    if let StreamEvent::TextDelta { id, delta } = back {
        assert_eq!(id, "msg_1");
        assert_eq!(delta, "hello");
    } else {
        panic!("wrong variant");
    }
}

#[test]
fn stream_event_done_roundtrip() {
    let ev = StreamEvent::Done;
    let json = serde_json::to_string(&ev).unwrap();
    assert!(json.contains("done"));
    let _back: StreamEvent = serde_json::from_str(&json).unwrap();
}

#[test]
fn stream_event_error_roundtrip() {
    let ev = StreamEvent::Error {
        message: "something failed".into(),
    };
    let json = serde_json::to_string(&ev).unwrap();
    let back: StreamEvent = serde_json::from_str(&json).unwrap();
    if let StreamEvent::Error { message } = back {
        assert_eq!(message, "something failed");
    } else {
        panic!("wrong variant");
    }
}

// ─────────────────────────────────────────────────────────────
// ChatOptions
// ─────────────────────────────────────────────────────────────

#[test]
fn chat_options_default_temperature() {
    let opts = ChatOptions::default();
    assert_eq!(opts.temperature, Some(0.7));
    assert_eq!(opts.max_tokens, Some(4096));
    assert!(opts.top_p.is_none());
    assert!(opts.stop.is_none());
}

#[test]
fn chat_options_serialization_roundtrip() {
    let opts = ChatOptions {
        temperature: Some(0.5),
        max_tokens: Some(1024),
        top_p: Some(0.9),
        stop: Some(vec!["STOP".into()]),
    };
    let json = serde_json::to_string(&opts).unwrap();
    let back: ChatOptions = serde_json::from_str(&json).unwrap();
    assert_eq!(back.temperature, Some(0.5));
    assert_eq!(back.stop.as_ref().unwrap()[0], "STOP");
}

// ─────────────────────────────────────────────────────────────
// UsageStats & CompletionResponse
// ─────────────────────────────────────────────────────────────

#[test]
fn usage_stats_serialization_roundtrip() {
    let u = UsageStats {
        prompt_tokens: 100,
        completion_tokens: 50,
        total_tokens: 150,
    };
    let json = serde_json::to_string(&u).unwrap();
    let back: UsageStats = serde_json::from_str(&json).unwrap();
    assert_eq!(back.total_tokens, 150);
}

#[test]
fn completion_response_with_content() {
    let r = CompletionResponse {
        content: Some("Hello!".into()),
        tool_calls: None,
        reasoning_content: None,
        finish_reason: Some("stop".into()),
        usage: Some(UsageStats {
            prompt_tokens: 10,
            completion_tokens: 5,
            total_tokens: 15,
        }),
    };
    assert_eq!(r.content.as_deref(), Some("Hello!"));
    assert_eq!(r.finish_reason.as_deref(), Some("stop"));
    assert_eq!(r.usage.as_ref().unwrap().total_tokens, 15);
}

#[test]
fn tool_call_serialization_roundtrip() {
    let tc = ToolCall {
        id: "call_abc".into(),
        name: "navigate".into(),
        arguments: r#"{"url":"https://example.com"}"#.into(),
    };
    let json = serde_json::to_string(&tc).unwrap();
    let back: ToolCall = serde_json::from_str(&json).unwrap();
    assert_eq!(back.id, "call_abc");
    assert_eq!(back.name, "navigate");
}

#[test]
fn tool_def_serialization_roundtrip() {
    let td = ToolDef {
        name: "search".into(),
        description: "Search the web".into(),
        parameters: json!({"type": "object"}),
    };
    let json = serde_json::to_string(&td).unwrap();
    let back: ToolDef = serde_json::from_str(&json).unwrap();
    assert_eq!(back.name, "search");
    assert_eq!(back.description, "Search the web");
}
