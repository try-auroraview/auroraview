//! Offline regressions for provider/model alignment with the genai adapter.
//!
//! These checks never issue a network request and never read credentials. They
//! pin the relationship between the model catalog, local provider inference,
//! and the adapter genai actually selects from a model name.

use auroraview_ai_agent::{AIClient, ChatOptions, ProviderType};
use rstest::rstest;

/// genai 0.6 dropped the implicit Groq model list: a bare
/// `llama-3.3-70b-versatile` now resolves to the local Ollama fallback. Every
/// catalog model must resolve to the adapter matching its provider, and local
/// inference must agree with that same choice.
#[test]
fn catalog_models_match_genai_adapter() {
    let models = AIClient::get_all_models();
    assert!(models.len() > 10, "model catalog unexpectedly empty");

    for model in models {
        let adapter = genai::adapter::AdapterKind::from_model(&model.id)
            .ok()
            .expect("from_model falls back to Ollama and never fails");
        let expected = model.provider.to_string();

        assert_eq!(
            adapter.as_lower_str(),
            expected.as_str(),
            "model `{}` selects genai adapter `{}`, expected `{}`",
            model.id,
            adapter.as_lower_str(),
            expected
        );
        assert_eq!(
            AIClient::infer_provider(&model.id),
            model.provider,
            "model `{}` inferred as `{}`, listed as `{}`",
            model.id,
            AIClient::infer_provider(&model.id),
            model.provider
        );
    }
}

#[rstest]
#[case("groq::llama-3.3-70b-versatile", ProviderType::Groq)]
#[case("groq::mixtral-8x7b-32768", ProviderType::Groq)]
#[case("deepseek::deepseek-chat", ProviderType::DeepSeek)]
#[case("gemini::gemini-2.0-flash-exp", ProviderType::Gemini)]
#[case("ollama::llama3.2", ProviderType::Ollama)]
#[case("gpt-4o", ProviderType::OpenAI)]
#[case("o1", ProviderType::OpenAI)]
#[case("claude-3-5-sonnet-20241022", ProviderType::Anthropic)]
#[case("gemini-2.0-flash-exp", ProviderType::Gemini)]
#[case("deepseek-chat", ProviderType::DeepSeek)]
#[case("llama3.2", ProviderType::Ollama)]
#[case("grok-2", ProviderType::XAI)]
#[case("command-r-plus", ProviderType::Cohere)]
fn infer_provider_resolves_namespaces_and_keeps_existing_rules(
    #[case] model: &str,
    #[case] expected: ProviderType,
) {
    assert_eq!(AIClient::infer_provider(model), expected);
}

#[test]
fn groq_default_model_is_namespaced() {
    let default = ProviderType::Groq.default_model();
    assert_eq!(default, "groq::llama-3.3-70b-versatile");

    let adapter = genai::adapter::AdapterKind::from_model(default)
        .ok()
        .expect("from_model falls back to Ollama and never fails");
    assert_eq!(adapter.as_lower_str(), "groq");
}

/// genai 0.6 made reasoning capture opt-in (Gemini `includeThoughts` and
/// streaming reasoning chunks are gated on it). The options builder must keep
/// it enabled while leaving the pre-existing sampling settings untouched.
#[test]
fn genai_options_enable_reasoning_capture() {
    let default = AIClient::build_genai_options(&ChatOptions::default());
    assert_eq!(default.capture_reasoning_content, Some(true));
    assert_eq!(default.temperature, Some(f64::from(0.7_f32)));
    assert_eq!(default.max_tokens, Some(4096));
    assert_eq!(default.top_p, None);

    let empty = AIClient::build_genai_options(&ChatOptions {
        temperature: None,
        max_tokens: None,
        top_p: None,
        stop: None,
    });
    assert_eq!(empty.temperature, None);
    assert_eq!(empty.max_tokens, None);
    assert_eq!(empty.top_p, None);
    assert_eq!(empty.capture_reasoning_content, Some(true));
}
