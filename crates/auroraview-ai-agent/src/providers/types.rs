//! Provider types and enums

use serde::{Deserialize, Serialize};
use std::fmt;

/// Supported AI provider types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ProviderType {
    /// OpenAI (GPT-4, GPT-4o, etc.)
    OpenAI,
    /// Anthropic (Claude 3, etc.)
    Anthropic,
    /// Google Gemini
    Gemini,
    /// DeepSeek
    DeepSeek,
    /// Ollama (local models)
    Ollama,
    /// Groq
    Groq,
    /// xAI (Grok)
    XAI,
    /// Cohere
    Cohere,
    /// Custom provider (OpenAI-compatible)
    Custom,
}

impl ProviderType {
    /// Get default model for this provider
    ///
    /// Groq models carry the `groq::` namespace required by genai 0.6 so that
    /// requests reach the Groq adapter instead of the local Ollama fallback.
    pub fn default_model(&self) -> &'static str {
        match self {
            Self::OpenAI => "gpt-4o",
            Self::Anthropic => "claude-3-5-sonnet-20241022",
            Self::Gemini => "gemini-2.0-flash-exp",
            Self::DeepSeek => "deepseek-chat",
            Self::Ollama => "llama3.2",
            Self::Groq => "groq::llama-3.3-70b-versatile",
            Self::XAI => "grok-2",
            Self::Cohere => "command-r-plus",
            Self::Custom => "default",
        }
    }

    /// Get environment variable name for API key
    pub fn env_key(&self) -> &'static str {
        match self {
            Self::OpenAI => "OPENAI_API_KEY",
            Self::Anthropic => "ANTHROPIC_API_KEY",
            Self::Gemini => "GEMINI_API_KEY",
            Self::DeepSeek => "DEEPSEEK_API_KEY",
            Self::Ollama => "OLLAMA_API_KEY",
            Self::Groq => "GROQ_API_KEY",
            Self::XAI => "XAI_API_KEY",
            Self::Cohere => "COHERE_API_KEY",
            Self::Custom => "AI_API_KEY",
        }
    }

    /// Check if this provider typically requires an API key
    pub fn requires_api_key(&self) -> bool {
        !matches!(self, Self::Ollama)
    }
}

impl fmt::Display for ProviderType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::OpenAI => write!(f, "openai"),
            Self::Anthropic => write!(f, "anthropic"),
            Self::Gemini => write!(f, "gemini"),
            Self::DeepSeek => write!(f, "deepseek"),
            Self::Ollama => write!(f, "ollama"),
            Self::Groq => write!(f, "groq"),
            Self::XAI => write!(f, "xai"),
            Self::Cohere => write!(f, "cohere"),
            Self::Custom => write!(f, "custom"),
        }
    }
}

impl std::str::FromStr for ProviderType {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "openai" => Ok(Self::OpenAI),
            "anthropic" | "claude" => Ok(Self::Anthropic),
            "gemini" | "google" => Ok(Self::Gemini),
            "deepseek" => Ok(Self::DeepSeek),
            "ollama" => Ok(Self::Ollama),
            "groq" => Ok(Self::Groq),
            "xai" | "grok" => Ok(Self::XAI),
            "cohere" => Ok(Self::Cohere),
            "custom" => Ok(Self::Custom),
            _ => Err(format!("Unknown provider: {}", s)),
        }
    }
}

/// Model information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelInfo {
    /// Model ID (used in API calls)
    pub id: String,
    /// Display name
    pub name: String,
    /// Description
    pub description: Option<String>,
    /// Context window size (tokens)
    pub context_window: Option<u32>,
    /// Max output tokens
    pub max_output_tokens: Option<u32>,
    /// Supports vision (image input)
    pub vision: bool,
    /// Supports function calling
    pub function_calling: bool,
    /// Provider type
    pub provider: ProviderType,
}

impl ModelInfo {
    /// Create new model info
    pub fn new(id: impl Into<String>, name: impl Into<String>, provider: ProviderType) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            description: None,
            context_window: None,
            max_output_tokens: None,
            vision: false,
            function_calling: true,
            provider,
        }
    }

    /// Set description
    pub fn with_description(mut self, desc: impl Into<String>) -> Self {
        self.description = Some(desc.into());
        self
    }

    /// Set context window
    pub fn with_context_window(mut self, tokens: u32) -> Self {
        self.context_window = Some(tokens);
        self
    }

    /// Set max output tokens
    pub fn with_max_output(mut self, tokens: u32) -> Self {
        self.max_output_tokens = Some(tokens);
        self
    }

    /// Set vision support
    pub fn with_vision(mut self, vision: bool) -> Self {
        self.vision = vision;
        self
    }

    /// Set function calling support
    pub fn with_function_calling(mut self, fc: bool) -> Self {
        self.function_calling = fc;
        self
    }
}

/// Stream events for real-time UI updates (AGUI-compatible)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum StreamEvent {
    /// Text generation started
    #[serde(rename = "text_start")]
    TextStart { id: String },

    /// Text chunk received
    #[serde(rename = "text_delta")]
    TextDelta { id: String, delta: String },

    /// Text generation completed
    #[serde(rename = "text_end")]
    TextEnd { id: String },

    /// Tool call started
    #[serde(rename = "tool_call_start")]
    ToolCallStart { id: String, name: String },

    /// Tool call arguments chunk
    #[serde(rename = "tool_call_delta")]
    ToolCallDelta { id: String, delta: String },

    /// Tool call completed
    #[serde(rename = "tool_call_end")]
    ToolCallEnd { id: String },

    /// Reasoning/thinking started (for models like DeepSeek R1)
    #[serde(rename = "thinking_start")]
    ThinkingStart { id: String },

    /// Reasoning/thinking chunk
    #[serde(rename = "thinking_delta")]
    ThinkingDelta { id: String, delta: String },

    /// Reasoning/thinking completed
    #[serde(rename = "thinking_end")]
    ThinkingEnd { id: String },

    /// Error occurred
    #[serde(rename = "error")]
    Error { message: String },

    /// Stream completed
    #[serde(rename = "done")]
    Done,
}

/// Chat options for AI completion
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatOptions {
    /// Temperature (0.0 - 2.0)
    pub temperature: Option<f32>,
    /// Max tokens to generate
    pub max_tokens: Option<u32>,
    /// Top-p sampling
    pub top_p: Option<f32>,
    /// Stop sequences
    pub stop: Option<Vec<String>>,
}

impl Default for ChatOptions {
    fn default() -> Self {
        Self {
            temperature: Some(0.7),
            max_tokens: Some(4096),
            top_p: None,
            stop: None,
        }
    }
}

/// Usage statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageStats {
    /// Input/prompt tokens
    pub prompt_tokens: u32,
    /// Output/completion tokens
    pub completion_tokens: u32,
    /// Total tokens
    pub total_tokens: u32,
}

/// Completion response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletionResponse {
    /// Generated content
    pub content: Option<String>,
    /// Tool calls (if any)
    pub tool_calls: Option<Vec<ToolCall>>,
    /// Reasoning content (for models like DeepSeek R1)
    pub reasoning_content: Option<String>,
    /// Finish reason
    pub finish_reason: Option<String>,
    /// Usage statistics
    pub usage: Option<UsageStats>,
}

/// Tool call in response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Tool call ID
    pub id: String,
    /// Function/tool name
    pub name: String,
    /// Arguments as JSON string
    pub arguments: String,
}

/// Tool definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDef {
    /// Tool name
    pub name: String,
    /// Tool description
    pub description: String,
    /// Parameters schema (JSON Schema)
    pub parameters: serde_json::Value,
}
