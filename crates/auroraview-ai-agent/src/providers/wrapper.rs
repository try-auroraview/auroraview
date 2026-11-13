//! Wrapper around genai crate for unified AI provider access

use std::sync::Arc;

use genai::chat::{ChatMessage, ChatOptions as GenaiChatOptions, ChatRequest};
use genai::Client;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

use crate::error::{AIError, AIResult};
use crate::providers::types::*;

/// AI Client wrapper around genai crate
///
/// Provides a unified interface to multiple AI providers:
/// - OpenAI, Anthropic, Gemini, DeepSeek, Ollama, Groq, xAI, Cohere
///
/// # Example
///
/// ```rust,ignore
/// use auroraview_ai_agent::providers::AIClient;
///
/// let client = AIClient::new();
///
/// // Chat with default model
/// let response = client.chat("gpt-4o", "Hello, how are you?").await?;
///
/// // Chat with conversation history
/// let messages = vec![
///     ("system", "You are a helpful assistant."),
///     ("user", "What is Rust?"),
/// ];
/// let response = client.chat_with_messages("claude-3-5-sonnet-20241022", messages).await?;
/// ```
pub struct AIClient {
    client: Client,
    default_options: Arc<RwLock<ChatOptions>>,
}

impl AIClient {
    /// Normalize a caller-supplied model name before it reaches genai.
    ///
    /// genai 0.6 requires Groq models to be namespaced (`groq::<name>`); bare
    /// names now resolve to the local Ollama adapter. Callers can still pass the
    /// legacy bare Groq ids through `AIConfig::for_model` or `AIClient::chat`,
    /// so map exactly those two ids at the common request boundary to preserve
    /// their pre-upgrade Groq routing. Explicit namespaces (including
    /// `ollama::...`) and every other model name are left untouched.
    /// Public so the shared request boundary can be checked offline.
    pub fn normalize_model(model: &str) -> &str {
        match model {
            "llama-3.3-70b-versatile" => "groq::llama-3.3-70b-versatile",
            "mixtral-8x7b-32768" => "groq::mixtral-8x7b-32768",
            _ => model,
        }
    }

    /// Create new AI client with default configuration
    ///
    /// API keys are automatically loaded from environment variables:
    /// - OPENAI_API_KEY
    /// - ANTHROPIC_API_KEY
    /// - GEMINI_API_KEY
    /// - DEEPSEEK_API_KEY
    /// - etc.
    pub fn new() -> Self {
        Self {
            client: Client::default(),
            default_options: Arc::new(RwLock::new(ChatOptions::default())),
        }
    }

    /// Create client with custom genai Client
    pub fn with_client(client: Client) -> Self {
        Self {
            client,
            default_options: Arc::new(RwLock::new(ChatOptions::default())),
        }
    }

    /// Set default chat options
    pub async fn set_default_options(&self, options: ChatOptions) {
        let mut opts = self.default_options.write().await;
        *opts = options;
    }

    /// Get provider type from model name
    ///
    /// genai 0.6 addresses providers such as Groq through a `namespace::model`
    /// prefix (for example `groq::llama-3.3-70b-versatile`). Resolve a known
    /// namespace first so namespaced catalog models stay aligned with the
    /// adapter genai selects, otherwise match the bare model name against the
    /// usual prefixes:
    /// - "gpt-*", "o1*" -> OpenAI
    /// - "claude-*" -> Anthropic
    /// - "gemini-*" -> Gemini
    /// - "deepseek-*" -> DeepSeek
    /// - "llama*" -> Ollama
    /// - etc.
    pub fn infer_provider(model: &str) -> ProviderType {
        let (namespace, name) = model
            .split_once("::")
            .map_or((None, model), |(ns, rest)| (Some(ns), rest));

        if let Some(provider) = namespace.and_then(|ns| ns.parse::<ProviderType>().ok()) {
            return provider;
        }

        let model_lower = name.to_lowercase();

        if model_lower.starts_with("gpt-") || model_lower.starts_with("o1") {
            ProviderType::OpenAI
        } else if model_lower.starts_with("claude-") {
            ProviderType::Anthropic
        } else if model_lower.starts_with("gemini-") {
            ProviderType::Gemini
        } else if model_lower.starts_with("deepseek-") {
            ProviderType::DeepSeek
        } else if model_lower.starts_with("llama")
            || model_lower.starts_with("mistral")
            || model_lower.starts_with("phi")
            || model_lower.starts_with("qwen")
        {
            // Local models typically run on Ollama
            ProviderType::Ollama
        } else if model_lower.starts_with("grok-") {
            ProviderType::XAI
        } else if model_lower.starts_with("command-") {
            ProviderType::Cohere
        } else {
            ProviderType::Custom
        }
    }

    /// Simple chat with single user message
    pub async fn chat(&self, model: &str, message: &str) -> AIResult<CompletionResponse> {
        self.chat_with_messages(model, vec![("user", message)])
            .await
    }

    /// Chat with message history
    ///
    /// # Arguments
    ///
    /// * `model` - Model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
    /// * `messages` - List of (role, content) tuples. Role can be "system", "user", "assistant"
    pub async fn chat_with_messages(
        &self,
        model: &str,
        messages: Vec<(&str, &str)>,
    ) -> AIResult<CompletionResponse> {
        let options = self.default_options.read().await.clone();
        self.chat_with_options(model, messages, options).await
    }

    /// Chat with custom options
    pub async fn chat_with_options(
        &self,
        model: &str,
        messages: Vec<(&str, &str)>,
        options: ChatOptions,
    ) -> AIResult<CompletionResponse> {
        debug!("Chat request to model: {}", model);

        // Convert messages to genai format
        let chat_messages: Vec<ChatMessage> = messages
            .into_iter()
            .map(|(role, content)| match role.to_lowercase().as_str() {
                "system" => ChatMessage::system(content),
                "assistant" => ChatMessage::assistant(content),
                _ => ChatMessage::user(content),
            })
            .collect();

        // Build chat request
        let chat_req = ChatRequest::new(chat_messages);

        // Build genai options
        let genai_options = Self::build_genai_options(&options);

        // Execute chat (normalize legacy bare Groq ids at the shared boundary)
        let model = Self::normalize_model(model);
        let chat_res = self
            .client
            .exec_chat(model, chat_req, Some(&genai_options))
            .await
            .map_err(|e| AIError::RequestFailed(e.to_string()))?;

        // Extract content using the genai ChatResponse API
        let content = chat_res.first_text().map(|s| s.to_string());

        // Extract tool calls from response
        let tool_calls = {
            let genai_calls = chat_res.tool_calls();
            if genai_calls.is_empty() {
                None
            } else {
                Some(
                    genai_calls
                        .into_iter()
                        .map(|tc| ToolCall {
                            id: tc.call_id.clone(),
                            name: tc.fn_name.clone(),
                            arguments: tc.fn_arguments.to_string(),
                        })
                        .collect(),
                )
            }
        };

        // Extract reasoning content (DeepSeek R1, Anthropic thinking, etc.)
        let reasoning_content = chat_res.reasoning_content.clone();

        // Extract usage if available
        let usage = {
            let u = &chat_res.usage;
            Some(UsageStats {
                prompt_tokens: u.prompt_tokens.unwrap_or(0) as u32,
                completion_tokens: u.completion_tokens.unwrap_or(0) as u32,
                total_tokens: u.total_tokens.unwrap_or(0) as u32,
            })
        };

        info!(
            "Chat completed, content length: {}",
            content.as_ref().map(|c| c.len()).unwrap_or(0)
        );

        Ok(CompletionResponse {
            content,
            tool_calls,
            reasoning_content,
            finish_reason: None,
            usage,
        })
    }

    /// Chat with streaming response
    ///
    /// # Arguments
    ///
    /// * `model` - Model name
    /// * `messages` - Message history
    /// * `on_event` - Callback for stream events
    pub async fn chat_stream<F>(
        &self,
        model: &str,
        messages: Vec<(&str, &str)>,
        on_event: F,
    ) -> AIResult<CompletionResponse>
    where
        F: Fn(StreamEvent) + Send + Sync + 'static,
    {
        let options = self.default_options.read().await.clone();
        self.chat_stream_with_options(model, messages, options, on_event)
            .await
    }

    /// Chat with streaming and custom options
    pub async fn chat_stream_with_options<F>(
        &self,
        model: &str,
        messages: Vec<(&str, &str)>,
        options: ChatOptions,
        on_event: F,
    ) -> AIResult<CompletionResponse>
    where
        F: Fn(StreamEvent) + Send + Sync + 'static,
    {
        use futures::StreamExt;
        use genai::chat::ChatStreamEvent;

        debug!("Stream chat request to model: {}", model);

        // Convert messages
        let chat_messages: Vec<ChatMessage> = messages
            .into_iter()
            .map(|(role, content)| match role.to_lowercase().as_str() {
                "system" => ChatMessage::system(content),
                "assistant" => ChatMessage::assistant(content),
                _ => ChatMessage::user(content),
            })
            .collect();

        let chat_req = ChatRequest::new(chat_messages);
        let genai_options = Self::build_genai_options(&options);

        // Execute streaming chat (same shared model normalization as non-streaming)
        let model = Self::normalize_model(model);
        let stream_res = self
            .client
            .exec_chat_stream(model, chat_req, Some(&genai_options))
            .await
            .map_err(|e| AIError::RequestFailed(e.to_string()))?;

        let mut full_content = String::new();
        let stream_id = uuid::Uuid::new_v4().to_string();

        // Emit start event
        on_event(StreamEvent::TextStart {
            id: stream_id.clone(),
        });

        // Process stream events - ChatStreamResponse exposes .stream
        // ChatStream yields Result<ChatStreamEvent, genai::Error>
        let mut stream = stream_res.stream;
        while let Some(result) = stream.next().await {
            match result {
                Ok(event) => match event {
                    ChatStreamEvent::Chunk(chunk) => {
                        // StreamChunk has .content field
                        let text = &chunk.content;
                        if !text.is_empty() {
                            full_content.push_str(text);
                            on_event(StreamEvent::TextDelta {
                                id: stream_id.clone(),
                                delta: text.clone(),
                            });
                        }
                    }
                    ChatStreamEvent::ReasoningChunk(chunk) => {
                        // Handle reasoning/thinking content (for DeepSeek R1, etc.)
                        let text = &chunk.content;
                        if !text.is_empty() {
                            on_event(StreamEvent::ThinkingDelta {
                                id: stream_id.clone(),
                                delta: text.clone(),
                            });
                        }
                    }
                    ChatStreamEvent::End(_end) => {
                        on_event(StreamEvent::TextEnd {
                            id: stream_id.clone(),
                        });
                    }
                    ChatStreamEvent::Start => {
                        // Already emitted TextStart
                    }
                    _ => {
                        // Handle other event types (ToolCallChunk, ThoughtSignatureChunk)
                    }
                },
                Err(e) => {
                    warn!("Stream error: {}", e);
                    on_event(StreamEvent::Error {
                        message: e.to_string(),
                    });
                    return Err(AIError::RequestFailed(e.to_string()));
                }
            }
        }

        on_event(StreamEvent::Done);

        Ok(CompletionResponse {
            content: if full_content.is_empty() {
                None
            } else {
                Some(full_content)
            },
            tool_calls: None,
            reasoning_content: None,
            finish_reason: Some("stop".to_string()),
            usage: None, // Streaming typically doesn't return usage
        })
    }

    /// Build genai `ChatOptions` from our `ChatOptions`.
    ///
    /// Public so callers (and offline tests) can inspect the exact options
    /// handed to genai without issuing a request. genai 0.6 made reasoning
    /// capture opt-in: Gemini `includeThoughts` and streamed reasoning chunks
    /// are now gated on it. Keep it enabled so `reasoning_content` and
    /// `ThinkingDelta` stay available as they were before the upgrade.
    pub fn build_genai_options(options: &ChatOptions) -> GenaiChatOptions {
        let mut genai_opts = GenaiChatOptions::default();

        if let Some(temp) = options.temperature {
            genai_opts = genai_opts.with_temperature(temp as f64);
        }

        if let Some(max_tokens) = options.max_tokens {
            genai_opts = genai_opts.with_max_tokens(max_tokens);
        }

        if let Some(top_p) = options.top_p {
            genai_opts = genai_opts.with_top_p(top_p as f64);
        }

        genai_opts = genai_opts.with_capture_reasoning_content(true);

        genai_opts
    }

    /// Get list of common models for each provider
    pub fn get_models(provider: ProviderType) -> Vec<ModelInfo> {
        match provider {
            ProviderType::OpenAI => vec![
                ModelInfo::new("gpt-4o", "GPT-4o", ProviderType::OpenAI)
                    .with_description("Most capable GPT-4 model")
                    .with_context_window(128000)
                    .with_vision(true),
                ModelInfo::new("gpt-4o-mini", "GPT-4o Mini", ProviderType::OpenAI)
                    .with_description("Fast and affordable")
                    .with_context_window(128000)
                    .with_vision(true),
                ModelInfo::new("o1", "O1", ProviderType::OpenAI)
                    .with_description("Reasoning model")
                    .with_context_window(200000),
                ModelInfo::new("o1-mini", "O1 Mini", ProviderType::OpenAI)
                    .with_description("Fast reasoning model")
                    .with_context_window(128000),
            ],
            ProviderType::Anthropic => vec![
                ModelInfo::new(
                    "claude-3-5-sonnet-20241022",
                    "Claude 3.5 Sonnet",
                    ProviderType::Anthropic,
                )
                .with_description("Most intelligent Claude model")
                .with_context_window(200000)
                .with_vision(true),
                ModelInfo::new(
                    "claude-3-5-haiku-20241022",
                    "Claude 3.5 Haiku",
                    ProviderType::Anthropic,
                )
                .with_description("Fast and efficient")
                .with_context_window(200000),
                ModelInfo::new(
                    "claude-3-opus-20240229",
                    "Claude 3 Opus",
                    ProviderType::Anthropic,
                )
                .with_description("Most powerful Claude 3")
                .with_context_window(200000)
                .with_vision(true),
            ],
            ProviderType::Gemini => vec![
                ModelInfo::new(
                    "gemini-2.0-flash-exp",
                    "Gemini 2.0 Flash",
                    ProviderType::Gemini,
                )
                .with_description("Latest Gemini model")
                .with_context_window(1000000)
                .with_vision(true),
                ModelInfo::new("gemini-1.5-pro", "Gemini 1.5 Pro", ProviderType::Gemini)
                    .with_description("Advanced reasoning")
                    .with_context_window(2000000)
                    .with_vision(true),
                ModelInfo::new("gemini-1.5-flash", "Gemini 1.5 Flash", ProviderType::Gemini)
                    .with_description("Fast and efficient")
                    .with_context_window(1000000)
                    .with_vision(true),
            ],
            ProviderType::DeepSeek => vec![
                ModelInfo::new("deepseek-chat", "DeepSeek Chat", ProviderType::DeepSeek)
                    .with_description("General chat model")
                    .with_context_window(64000),
                ModelInfo::new("deepseek-reasoner", "DeepSeek R1", ProviderType::DeepSeek)
                    .with_description("Reasoning model with chain-of-thought")
                    .with_context_window(64000),
            ],
            ProviderType::Ollama => vec![
                ModelInfo::new("llama3.2", "Llama 3.2", ProviderType::Ollama)
                    .with_description("Meta's latest open model")
                    .with_context_window(128000),
                ModelInfo::new("mistral", "Mistral 7B", ProviderType::Ollama)
                    .with_description("Efficient open model")
                    .with_context_window(32000),
                ModelInfo::new("qwen2.5", "Qwen 2.5", ProviderType::Ollama)
                    .with_description("Alibaba's multilingual model")
                    .with_context_window(128000),
            ],
            ProviderType::Groq => vec![
                ModelInfo::new(
                    "groq::llama-3.3-70b-versatile",
                    "Llama 3.3 70B",
                    ProviderType::Groq,
                )
                .with_description("Fast inference on Groq")
                .with_context_window(128000),
                ModelInfo::new(
                    "groq::mixtral-8x7b-32768",
                    "Mixtral 8x7B",
                    ProviderType::Groq,
                )
                .with_description("MoE model on Groq")
                .with_context_window(32768),
            ],
            ProviderType::XAI => vec![
                ModelInfo::new("grok-2", "Grok 2", ProviderType::XAI)
                    .with_description("xAI's latest model")
                    .with_context_window(128000),
                ModelInfo::new("grok-2-vision", "Grok 2 Vision", ProviderType::XAI)
                    .with_description("Grok with vision")
                    .with_context_window(128000)
                    .with_vision(true),
            ],
            ProviderType::Cohere => vec![
                ModelInfo::new("command-r-plus", "Command R+", ProviderType::Cohere)
                    .with_description("Most capable Cohere model")
                    .with_context_window(128000),
                ModelInfo::new("command-r", "Command R", ProviderType::Cohere)
                    .with_description("Efficient Cohere model")
                    .with_context_window(128000),
            ],
            ProviderType::Custom => vec![],
        }
    }

    /// Get all available models across all providers
    pub fn get_all_models() -> Vec<ModelInfo> {
        let providers = [
            ProviderType::OpenAI,
            ProviderType::Anthropic,
            ProviderType::Gemini,
            ProviderType::DeepSeek,
            ProviderType::Ollama,
            ProviderType::Groq,
            ProviderType::XAI,
            ProviderType::Cohere,
        ];

        providers
            .iter()
            .flat_map(|p| Self::get_models(*p))
            .collect()
    }
}

impl Default for AIClient {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_infer_provider() {
        assert_eq!(AIClient::infer_provider("gpt-4o"), ProviderType::OpenAI);
        assert_eq!(AIClient::infer_provider("gpt-4"), ProviderType::OpenAI);
        assert_eq!(AIClient::infer_provider("o1"), ProviderType::OpenAI);
        assert_eq!(
            AIClient::infer_provider("claude-3-5-sonnet-20241022"),
            ProviderType::Anthropic
        );
        assert_eq!(
            AIClient::infer_provider("gemini-2.0-flash-exp"),
            ProviderType::Gemini
        );
        assert_eq!(
            AIClient::infer_provider("deepseek-chat"),
            ProviderType::DeepSeek
        );
        assert_eq!(AIClient::infer_provider("llama3.2"), ProviderType::Ollama);
        assert_eq!(AIClient::infer_provider("grok-2"), ProviderType::XAI);
        assert_eq!(
            AIClient::infer_provider("command-r-plus"),
            ProviderType::Cohere
        );
    }

    #[test]
    fn test_provider_default_model() {
        assert_eq!(ProviderType::OpenAI.default_model(), "gpt-4o");
        assert_eq!(
            ProviderType::Anthropic.default_model(),
            "claude-3-5-sonnet-20241022"
        );
        assert_eq!(ProviderType::Gemini.default_model(), "gemini-2.0-flash-exp");
    }

    #[test]
    fn test_get_models() {
        let openai_models = AIClient::get_models(ProviderType::OpenAI);
        assert!(!openai_models.is_empty());
        assert!(openai_models.iter().any(|m| m.id == "gpt-4o"));

        let all_models = AIClient::get_all_models();
        assert!(all_models.len() > 10);
    }
}
