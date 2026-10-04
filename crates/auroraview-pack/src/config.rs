//! Pack configuration types
//!
//! This module provides runtime configuration types for the packer.
//! Common types are re-exported from the `common` module for consistency.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::common::{
    default_module_search_paths, default_optimize, default_python_version, HooksConfig,
};
use crate::error::PackResult;
use crate::manifest::Manifest;
use crate::protection::ProtectionConfig;

// Re-export common types
pub use crate::common::{
    BundleStrategy, DebugConfig, IsolationConfig, LicenseConfig, TargetPlatform, WindowConfig,
    WindowsPlatformConfig,
};

// ============================================================================
// Pack Mode
// ============================================================================

/// Pack mode determines how the application loads content
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum PackMode {
    /// Load content from a URL
    Url {
        /// The URL to load (will be normalized to include https:// if missing)
        url: String,
    },
    /// Load content from embedded frontend assets
    Frontend {
        /// Path to the frontend directory or HTML file
        #[serde(skip)]
        path: PathBuf,
    },
    /// FullStack mode: Frontend + Python backend
    FullStack {
        /// Path to the frontend directory
        #[serde(skip)]
        frontend_path: PathBuf,
        /// Python configuration (boxed to reduce enum size)
        python: Box<PythonBundleConfig>,
    },
}

impl PackMode {
    /// Get the mode name
    pub fn name(&self) -> &'static str {
        match self {
            PackMode::Url { .. } => "url",
            PackMode::Frontend { .. } => "frontend",
            PackMode::FullStack { .. } => "fullstack",
        }
    }

    /// Check if this mode embeds assets
    pub fn embeds_assets(&self) -> bool {
        matches!(self, PackMode::Frontend { .. } | PackMode::FullStack { .. })
    }

    /// Check if this mode includes Python backend
    pub fn has_python(&self) -> bool {
        matches!(self, PackMode::FullStack { .. })
    }

    /// Get the frontend path if applicable
    pub fn frontend_path(&self) -> Option<&PathBuf> {
        match self {
            PackMode::Frontend { path } => Some(path),
            PackMode::FullStack { frontend_path, .. } => Some(frontend_path),
            PackMode::Url { .. } => None,
        }
    }

    /// Get the URL if applicable
    pub fn url(&self) -> Option<&str> {
        match self {
            PackMode::Url { url } => Some(url),
            _ => None,
        }
    }

    /// Get the Python config if applicable
    pub fn python_config(&self) -> Option<&PythonBundleConfig> {
        match self {
            PackMode::FullStack { python, .. } => Some(python),
            _ => None,
        }
    }
}

// ============================================================================
// Python Bundle Configuration
// ============================================================================

/// Python bundle configuration for FullStack mode
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonBundleConfig {
    /// Entry point (e.g., "myapp.main:run" or "main.py")
    pub entry_point: String,

    /// Python source paths to include
    #[serde(default)]
    pub include_paths: Vec<PathBuf>,

    /// Pip packages to install
    #[serde(default)]
    pub packages: Vec<String>,

    /// Path to requirements.txt
    #[serde(default)]
    pub requirements: Option<PathBuf>,

    /// Only allow dependency installation through `vx uv pip` (no fallback to system uv/pip)
    #[serde(default)]
    pub pip_via_vx_only: bool,

    /// Bundle strategy

    #[serde(default)]
    pub strategy: BundleStrategy,

    /// Python version (e.g., "3.11")
    #[serde(default = "default_python_version")]
    pub version: String,

    /// Bytecode optimization level (0, 1, or 2)
    #[serde(default = "default_optimize")]
    pub optimize: u8,

    /// Exclude patterns
    #[serde(default)]
    pub exclude: Vec<String>,

    /// External binaries to bundle (paths to executables)
    #[serde(default)]
    pub external_bin: Vec<PathBuf>,

    /// Additional resource files/directories
    #[serde(default)]
    pub resources: Vec<PathBuf>,

    /// Include pip in the bundle (for PyOxidizer)
    #[serde(default)]
    pub include_pip: bool,

    /// Include setuptools in the bundle (for PyOxidizer)
    #[serde(default)]
    pub include_setuptools: bool,

    /// PyOxidizer distribution flavor
    #[serde(default)]
    pub distribution_flavor: Option<String>,

    /// Custom PyOxidizer executable path
    #[serde(default)]
    pub pyoxidizer_path: Option<PathBuf>,

    /// Module search paths (relative to extract directory).
    /// Special variables: $EXTRACT_DIR, $RESOURCES_DIR, $SITE_PACKAGES, $PYTHON_HOME
    #[serde(default = "default_module_search_paths")]
    pub module_search_paths: Vec<String>,

    /// Whether to use filesystem importer (allows dynamic imports)
    #[serde(default = "default_true")]
    pub filesystem_importer: bool,

    /// Show console window for Python process (Windows only)
    #[serde(default)]
    pub show_console: bool,

    /// Environment isolation configuration
    #[serde(default)]
    pub isolation: IsolationConfig,

    /// Code protection configuration (py2pyd compilation)
    #[serde(default)]
    pub protection: ProtectionConfig,
}

fn default_true() -> bool {
    true
}

impl Default for PythonBundleConfig {
    fn default() -> Self {
        Self {
            entry_point: String::new(),
            include_paths: Vec::new(),
            packages: Vec::new(),
            requirements: None,
            pip_via_vx_only: false,
            strategy: BundleStrategy::default(),

            version: default_python_version(),
            optimize: default_optimize(),
            exclude: Vec::new(),
            external_bin: Vec::new(),
            resources: Vec::new(),
            include_pip: false,
            include_setuptools: false,
            distribution_flavor: None,
            pyoxidizer_path: None,
            module_search_paths: default_module_search_paths(),
            filesystem_importer: true,
            show_console: false,
            isolation: IsolationConfig::default(),
            protection: ProtectionConfig::default(),
        }
    }
}

impl PythonBundleConfig {
    /// Create a new Python bundle config with entry point
    pub fn new(entry_point: impl Into<String>) -> Self {
        Self {
            entry_point: entry_point.into(),
            ..Default::default()
        }
    }

    /// Set Python version
    pub fn with_version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Add include paths
    pub fn with_include_paths(mut self, paths: Vec<PathBuf>) -> Self {
        self.include_paths = paths;
        self
    }

    /// Set bundle strategy
    pub fn with_strategy(mut self, strategy: BundleStrategy) -> Self {
        self.strategy = strategy;
        self
    }

    /// Set isolation config
    pub fn with_isolation(mut self, isolation: IsolationConfig) -> Self {
        self.isolation = isolation;
        self
    }
}

// ============================================================================
// Complete Pack Configuration
// ============================================================================

/// Runtime extensions configuration for packed apps
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ExtensionsRuntimeConfig {
    /// Enable extension execution in WebView runtime
    #[serde(default = "default_true")]
    pub enabled: bool,

    /// Bundle local/remote extensions during packing
    #[serde(default)]
    pub bundle: bool,

    /// Local extension directories (pack-time only)
    #[serde(default)]
    pub local: Vec<PathBuf>,

    /// Remote extension archives (pack-time only)
    #[serde(default)]
    pub remote: Vec<ExtensionRemoteSource>,
}

/// Remote extension source configuration
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ExtensionRemoteSource {
    /// Stable extension ID used as install directory name
    pub id: String,

    /// Remote source URL: archive (.zip/.tar/.tar.gz/.tgz/.crx) or store detail page URL
    /// (Chrome Web Store / Microsoft Edge Add-ons)
    pub url: String,

    /// Optional checksum for verification (sha256/sha512)
    #[serde(default)]
    pub checksum: Option<String>,

    /// Number of leading path components to strip during extraction
    #[serde(default)]
    pub strip_components: usize,
}

/// CLI parameter metadata embedded in the overlay (RFC 0018 §13.2).
///
/// Mirrors the per-parameter dict produced by the Python
/// `CliCommandMeta.params()` introspection so the runtime `-h`/`list` path can
/// render argument help without starting Python.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CliParamMeta {
    /// Parameter name (as declared in the Python signature).
    pub name: String,

    /// Annotation name (`str`/`int`/...), or `"any"` when unannotated.
    #[serde(default = "default_param_type")]
    pub r#type: String,

    /// Whether the parameter is required (no default value).
    #[serde(default)]
    pub required: bool,

    /// Default value when the parameter is optional (`null` when required).
    #[serde(default)]
    pub default: serde_json::Value,

    /// Per-parameter help text (from `args_help`), empty when absent.
    #[serde(default)]
    pub help: String,
}

fn default_param_type() -> String {
    "any".to_string()
}

/// CLI command metadata embedded in the overlay (RFC 0018 §13.2).
///
/// Collected at pack time by running the bundled entry point with
/// `AURORAVIEW_CLI_DUMP=1` and serialized into [`PackConfig::cli_commands`].
/// The runtime `-h`/`list` path reads this verbatim — no Python launch.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CliCommandMeta {
    /// Canonical command name.
    pub name: String,

    /// CLI aliases (`cli="x"` / `cli=["x","y"]`); empty for `cli=True`.
    #[serde(default)]
    pub aliases: Vec<String>,

    /// Help text; the Python side falls back to the docstring first line.
    #[serde(default)]
    pub help: String,

    /// Ordered parameter metadata.
    #[serde(default)]
    pub params: Vec<CliParamMeta>,
}

/// Complete pack configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackConfig {
    /// Pack mode (URL, Frontend, or FullStack)
    pub mode: PackMode,

    /// Output executable name (without extension)
    pub output_name: String,

    /// Output directory
    #[serde(skip)]
    pub output_dir: PathBuf,

    /// Window configuration
    pub window: WindowConfig,

    /// Target platform
    #[serde(default)]
    pub target_platform: TargetPlatform,

    /// Enable debug mode
    #[serde(default)]
    pub debug: bool,

    /// Allow opening new windows
    #[serde(default)]
    pub allow_new_window: bool,

    /// Custom user agent
    #[serde(default)]
    pub user_agent: Option<String>,

    /// JavaScript to inject
    #[serde(default)]
    pub inject_js: Option<String>,

    /// CSS to inject
    #[serde(default)]
    pub inject_css: Option<String>,

    /// Icon path (for resource injection)
    #[serde(skip)]
    pub icon_path: Option<PathBuf>,

    /// Window icon PNG data (embedded at pack time)
    #[serde(default)]
    #[serde(with = "serde_bytes_base64")]
    pub window_icon: Option<Vec<u8>>,

    /// Environment variables to inject at runtime
    #[serde(default)]
    pub env: HashMap<String, String>,

    /// License configuration for authorization
    #[serde(default)]
    pub license: Option<LicenseConfig>,

    /// Hooks configuration for collecting additional files
    #[serde(default)]
    pub hooks: Option<HooksConfig>,

    /// Remote debugging port for CDP connections
    #[serde(default)]
    pub remote_debugging_port: Option<u16>,

    /// Windows-specific resource configuration
    #[serde(skip)]
    pub windows_resource: WindowsPlatformConfig,

    /// Vx configuration for dependency bootstrap
    #[serde(default)]
    pub vx: Option<crate::manifest::VxConfig>,

    /// Downloads configuration for embedding external dependencies
    #[serde(default)]
    pub downloads: Vec<crate::manifest::DownloadEntry>,

    /// Compression level for assets (1-22, default 19 for best ratio)
    /// Higher levels = better compression but slower packing
    /// Recommended: 19 for release, 3 for development
    #[serde(default = "default_compression_level")]
    pub compression_level: i32,

    /// Extensions behavior (runtime + pack-time bundle inputs)
    #[serde(default)]
    pub extensions: ExtensionsRuntimeConfig,

    /// Content Security Policy injected as a `<meta>` tag before page scripts run.
    ///
    /// When set, the CSP policy string is injected into every page via a `<meta
    /// http-equiv="Content-Security-Policy">` element inserted by the WebView
    /// initialization script.
    ///
    /// Example: `"default-src 'self'; script-src 'self' 'unsafe-inline'"`
    ///
    /// Set to `None` (default) to disable CSP injection.
    #[serde(default)]
    pub content_security_policy: Option<String>,

    /// Capture file drop events as IPC `file_drop_*` events.
    ///
    /// `false` (default) → use browser-native HTML5 drag-drop.
    /// `true` → register `with_drag_drop_handler` and forward events
    /// through the IPC pipeline. See RFC 0015 §2 for the wry/WebView2
    /// trade-off.
    #[serde(default)]
    pub capture_file_drop: bool,

    /// CLI command metadata collected at pack time (RFC 0018 §13.3).
    ///
    /// Populated by running the bundled entry point with
    /// `AURORAVIEW_CLI_DUMP=1` during packing. The runtime `-h`/`list` path
    /// renders directly from this, so no Python is started. Empty when the app
    /// exposes no CLI commands or when the pack-time dump could not run (e.g.
    /// cross-platform packing).
    #[serde(default)]
    pub cli_commands: Vec<CliCommandMeta>,
}

/// Default compression level (19 = high compression, good for releases)
fn default_compression_level() -> i32 {
    19
}

/// Serde helper module for serializing `Option<Vec<u8>>` as base64
mod serde_bytes_base64 {
    use base64::{engine::general_purpose::STANDARD, Engine};
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S>(data: &Option<Vec<u8>>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match data {
            Some(bytes) => serializer.serialize_some(&STANDARD.encode(bytes)),
            None => serializer.serialize_none(),
        }
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Option<Vec<u8>>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let opt: Option<String> = Option::deserialize(deserializer)?;
        match opt {
            Some(s) => STANDARD
                .decode(&s)
                .map(Some)
                .map_err(serde::de::Error::custom),
            None => Ok(None),
        }
    }
}

impl PackConfig {
    /// Build a `PackConfig` skeleton with sane defaults for every field
    /// other than `mode` and `output_name`.
    ///
    /// Centralizes the default values previously duplicated across the
    /// four public constructors (`url` / `frontend` / `fullstack` /
    /// `fullstack_with_config`). When a new field is added to
    /// `PackConfig`, only this skeleton needs to set its default — the
    /// public constructors automatically inherit it.
    fn skeleton(mode: PackMode, output_name: String) -> Self {
        Self {
            mode,
            output_name,
            output_dir: PathBuf::from("."),
            window: WindowConfig::default(),
            target_platform: TargetPlatform::Current,
            debug: false,
            allow_new_window: false,
            user_agent: None,
            inject_js: None,
            inject_css: None,
            icon_path: None,
            window_icon: None,
            env: HashMap::new(),
            license: None,
            hooks: None,
            remote_debugging_port: None,
            windows_resource: WindowsPlatformConfig::default(),
            vx: None,
            downloads: vec![],
            compression_level: default_compression_level(),
            extensions: ExtensionsRuntimeConfig::default(),
            content_security_policy: None,
            capture_file_drop: false,
            cli_commands: Vec::new(),
        }
    }

    /// Create a URL mode configuration
    pub fn url(url: impl Into<String>) -> Self {
        let url = url.into();
        let output_name = url
            .replace("https://", "")
            .replace("http://", "")
            .replace("www.", "")
            .split('.')
            .next()
            .unwrap_or("app")
            .to_string();

        Self::skeleton(PackMode::Url { url }, output_name)
    }

    /// Create a frontend mode configuration
    pub fn frontend(path: impl Into<PathBuf>) -> Self {
        let path = path.into();
        let output_name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("app")
            .to_string();

        Self::skeleton(PackMode::Frontend { path }, output_name)
    }

    /// Create a fullstack mode configuration (frontend + Python backend)
    pub fn fullstack(frontend_path: impl Into<PathBuf>, entry_point: impl Into<String>) -> Self {
        let frontend_path = frontend_path.into();
        let output_name = frontend_path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("app")
            .to_string();

        Self::skeleton(
            PackMode::FullStack {
                frontend_path,
                python: Box::new(PythonBundleConfig::new(entry_point)),
            },
            output_name,
        )
    }

    /// Create a fullstack mode configuration with full Python config
    pub fn fullstack_with_config(
        frontend_path: impl Into<PathBuf>,
        python: PythonBundleConfig,
    ) -> Self {
        let frontend_path = frontend_path.into();
        let output_name = frontend_path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("app")
            .to_string();

        Self::skeleton(
            PackMode::FullStack {
                frontend_path,
                python: Box::new(python),
            },
            output_name,
        )
    }

    /// Set the output name
    pub fn with_output(mut self, name: impl Into<String>) -> Self {
        self.output_name = name.into();
        self
    }

    /// Set the output directory
    pub fn with_output_dir(mut self, dir: impl Into<PathBuf>) -> Self {
        self.output_dir = dir.into();
        self
    }

    /// Set the window title
    pub fn with_title(mut self, title: impl Into<String>) -> Self {
        self.window.title = title.into();
        self
    }

    /// Set the window size
    pub fn with_size(mut self, width: u32, height: u32) -> Self {
        self.window.width = width;
        self.window.height = height;
        self
    }

    /// Set debug mode
    pub fn with_debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }

    /// Set frameless mode
    pub fn with_frameless(mut self, frameless: bool) -> Self {
        self.window.frameless = frameless;
        self
    }

    /// Set always on top
    pub fn with_always_on_top(mut self, always_on_top: bool) -> Self {
        self.window.always_on_top = always_on_top;
        self
    }

    /// Set resizable
    pub fn with_resizable(mut self, resizable: bool) -> Self {
        self.window.resizable = resizable;
        self
    }

    /// Set user agent
    pub fn with_user_agent(mut self, user_agent: impl Into<String>) -> Self {
        self.user_agent = Some(user_agent.into());
        self
    }

    /// Set icon path
    pub fn with_icon(mut self, path: impl Into<PathBuf>) -> Self {
        self.icon_path = Some(path.into());
        self
    }

    /// Set environment variables
    pub fn with_env(mut self, env: HashMap<String, String>) -> Self {
        self.env = env;
        self
    }

    /// Add a single environment variable
    pub fn with_env_var(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.env.insert(key.into(), value.into());
        self
    }

    /// Set license configuration
    pub fn with_license(mut self, license: LicenseConfig) -> Self {
        self.license = Some(license);
        self
    }

    /// Set remote debugging port for CDP connections
    pub fn with_remote_debugging_port(mut self, port: u16) -> Self {
        self.remote_debugging_port = Some(port);
        self
    }

    /// Set expiration date (enables license)
    pub fn with_expiration(mut self, expires_at: impl Into<String>) -> Self {
        self.license = Some(LicenseConfig::time_limited(expires_at));
        self
    }

    /// Require token for authorization
    pub fn with_token_required(mut self) -> Self {
        let mut license = self.license.unwrap_or_default();
        license.enabled = true;
        license.require_token = true;
        self.license = Some(license);
        self
    }

    /// Set hooks configuration for collecting additional files
    pub fn with_hooks(mut self, hooks: HooksConfig) -> Self {
        self.hooks = Some(hooks);
        self
    }

    /// Get debug configuration
    pub fn debug_config(&self) -> DebugConfig {
        DebugConfig {
            enabled: self.debug,
            devtools: self.debug,
            verbose: false,
            remote_debugging_port: self.remote_debugging_port,
        }
    }

    /// Create PackConfig from Manifest
    pub fn from_manifest(manifest: &Manifest, base_dir: &Path) -> PackResult<Self> {
        use crate::error::PackError;

        // Helper to resolve paths relative to base_dir
        let resolve_path = |path: &PathBuf| -> PathBuf {
            let joined = if path.is_absolute() {
                path.clone()
            } else {
                base_dir.join(path)
            };
            // Normalize path by removing . and resolving ..
            let mut components = Vec::new();
            for component in joined.components() {
                match component {
                    std::path::Component::CurDir => {}
                    std::path::Component::ParentDir => {
                        if let Some(std::path::Component::Normal(_)) = components.last() {
                            components.pop();
                        } else {
                            components.push(component);
                        }
                    }
                    _ => components.push(component),
                }
            }
            components.iter().collect()
        };

        // Determine pack mode from manifest
        let mode = if let Some(url) = manifest.get_frontend_url() {
            PackMode::Url { url }
        } else if let Some(backend) = manifest.backend.as_ref() {
            if backend.backend_type == crate::manifest::BackendType::Python {
                let python_config =
                    manifest.get_python_bundle_config(base_dir).ok_or_else(|| {
                        PackError::Config("Missing Python backend config".to_string())
                    })?;
                let frontend_path = manifest
                    .get_frontend_path()
                    .ok_or_else(|| PackError::Config("Missing frontend path".to_string()))?;
                let resolved_path = resolve_path(&frontend_path);
                PackMode::FullStack {
                    frontend_path: resolved_path,
                    python: Box::new(python_config),
                }
            } else {
                let frontend_path = manifest
                    .get_frontend_path()
                    .ok_or_else(|| PackError::Config("Missing frontend path".to_string()))?;
                let resolved_path = resolve_path(&frontend_path);
                PackMode::Frontend {
                    path: resolved_path,
                }
            }
        } else {
            let frontend_path = manifest
                .get_frontend_path()
                .ok_or_else(|| PackError::Config("Missing frontend path".to_string()))?;
            let resolved_path = resolve_path(&frontend_path);
            PackMode::Frontend {
                path: resolved_path,
            }
        };

        // Determine output directory
        let output_dir = manifest
            .build
            .out_dir
            .as_ref()
            .map(resolve_path)
            .unwrap_or_else(|| base_dir.join("pack-output"));

        // Build PackConfig
        let config = Self {
            mode,
            output_name: manifest.package.name.clone(),
            output_dir,
            window: manifest.get_window_config(),
            target_platform: TargetPlatform::Current,
            debug: manifest.debug.enabled,
            allow_new_window: manifest.package.allow_new_window,
            user_agent: manifest.get_user_agent(),
            inject_js: manifest.inject.as_ref().and_then(|inj| inj.js_code.clone()),
            inject_css: manifest
                .inject
                .as_ref()
                .and_then(|inj| inj.css_code.clone()),
            icon_path: manifest.get_icon_path().cloned().map(|p| resolve_path(&p)),
            window_icon: None,
            env: manifest
                .runtime
                .as_ref()
                .map(|r| r.env.clone())
                .unwrap_or_default(),
            license: manifest.license.clone(),
            hooks: manifest.hooks.as_ref().map(|h| h.to_hooks_config(base_dir)),
            remote_debugging_port: manifest.debug.remote_debugging_port,
            windows_resource: manifest.get_windows_resource_config(),
            vx: manifest.vx.clone(),
            downloads: manifest.downloads.clone(),
            compression_level: manifest.build.compression_level,
            extensions: manifest
                .extensions
                .as_ref()
                .map(|ext| ExtensionsRuntimeConfig {
                    enabled: ext.enabled,
                    bundle: ext.bundle,
                    local: ext.local.iter().map(&resolve_path).collect(),
                    remote: ext
                        .remote
                        .iter()
                        .map(|r| ExtensionRemoteSource {
                            id: r.id.clone(),
                            url: r.url.clone(),
                            checksum: r.checksum.clone(),
                            strip_components: r.strip_components,
                        })
                        .collect(),
                })
                .unwrap_or_default(),
            content_security_policy: manifest
                .security
                .as_ref()
                .and_then(|s| s.content_security_policy.clone()),
            capture_file_drop: manifest
                .security
                .as_ref()
                .and_then(|s| s.capture_file_drop)
                .unwrap_or(false),
            // RFC 0018: populated later in the pack flow by the pack-time dump.
            cli_commands: Vec::new(),
        };

        Ok(config)
    }
}
