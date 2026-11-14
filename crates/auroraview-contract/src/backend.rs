//! Pluggable render-backend contract.
//!
//! A *render backend* owns the actual web surface. Two families must be
//! reachable through the same contract:
//!
//! * [`BackendFamily::Native`] -- the platform webview (WebView2 on Windows,
//!   WKWebView on macOS, WebKitGTK on Linux). Small, no bundled runtime.
//! * [`BackendFamily::Chromium`] -- a bundled Chromium-class engine. Heavy, but
//!   the only path that gives a real CDP endpoint, DevTools protocol parity and
//!   identical rendering across platforms.
//!
//! # Relationship to the existing `auroraview-core::backend`
//!
//! `auroraview-core::backend` already defines `WebViewBackend`, but its
//! `BackendFactory` is a closed `match` over a `BackendType` enum: adding a
//! backend means editing core, and `BackendType::WebView2` on Windows silently
//! returns the same `WryBackend` as `BackendType::Wry`. This module keeps the
//! trait design and replaces the closed factory with a registry, so a backend
//! becomes a registration instead of a core edit.
//!
//! # Probing never fails
//!
//! [`RenderBackend::probe`] returns [`CapabilitySupport`] -- see
//! [`crate::capability`]. A backend that is not linked into the build reports
//! `Unsupported` with a build flag to flip, rather than panicking or returning
//! an opaque internal error.

use std::fmt;
use std::sync::Arc;

use crate::capability::{CapabilityProbe, CapabilityReport, CapabilitySupport, Features};
use crate::registry::{Registry, Selection};

/// Environment variable used to pin a render backend.
pub const ENV_BACKEND: &str = "AURORAVIEW_BACKEND";

/// Engine family behind a backend.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
/// Adding a variant is a minor (additive) change; removing or renaming one
/// is breaking and requires a major bump coordinated across every host
/// repository. See the version policy in `Cargo.toml`.
#[non_exhaustive]
pub enum BackendFamily {
    /// The platform's own webview control.
    Native,
    /// A bundled Chromium-class engine.
    Chromium,
    /// Anything else (embedded browser supplied by an adapter).
    Other,
}

impl BackendFamily {
    /// Stable snake-case name.
    pub fn name(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Chromium => "chromium",
            Self::Other => "other",
        }
    }
}

/// Description of a surface to create.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SurfaceSpec {
    /// Window title.
    pub title: String,
    /// Initial width in pixels.
    pub width: u32,
    /// Initial height in pixels.
    pub height: u32,
    /// URL to load, if any.
    pub url: Option<String>,
    /// Inline HTML to load, if any.
    pub html: Option<String>,
    /// Native parent window handle, when embedding into a host window.
    ///
    /// The contract representation is `u64`. Convert signed native values with
    /// `u64::try_from`; backends requiring `isize` must use `isize::try_from`
    /// rather than silently narrowing or reinterpreting the value.
    pub parent_handle: Option<u64>,
    /// Request a transparent (per-pixel alpha) surface.
    pub transparent: bool,
    /// Enable the inspector / DevTools.
    pub devtools: bool,
}

impl Default for SurfaceSpec {
    fn default() -> Self {
        Self {
            title: "AuroraView".to_string(),
            width: 800,
            height: 600,
            url: None,
            html: None,
            parent_handle: None,
            transparent: false,
            devtools: true,
        }
    }
}

impl SurfaceSpec {
    /// Start a spec from a URL.
    pub fn with_url(url: impl Into<String>) -> Self {
        Self {
            url: Some(url.into()),
            ..Self::default()
        }
    }

    /// Start a spec from inline HTML.
    pub fn with_html(html: impl Into<String>) -> Self {
        Self {
            html: Some(html.into()),
            ..Self::default()
        }
    }

    /// Attach the surface to a host window.
    pub fn with_parent_handle(mut self, handle: u64) -> Self {
        self.parent_handle = Some(handle);
        self
    }
}

/// A backend operation that could not be performed.
#[derive(Debug, Clone)]
pub struct BackendError {
    /// Operation that failed.
    pub operation: &'static str,
    /// Why it failed.
    pub reason: String,
    /// What the integrator should do about it.
    pub how_to_enable: Option<String>,
}

impl BackendError {
    /// Build an "unsupported by this backend" error.
    pub fn unsupported(
        operation: &'static str,
        reason: impl Into<String>,
        how_to_enable: impl Into<String>,
    ) -> Self {
        Self {
            operation,
            reason: reason.into(),
            how_to_enable: Some(how_to_enable.into()),
        }
    }

    /// Build an error with no remediation hint.
    pub fn failed(operation: &'static str, reason: impl Into<String>) -> Self {
        Self {
            operation,
            reason: reason.into(),
            how_to_enable: None,
        }
    }
}

impl fmt::Display for BackendError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.how_to_enable {
            Some(hint) => write!(
                f,
                "{} failed: {} (to enable: {})",
                self.operation, self.reason, hint
            ),
            None => write!(f, "{} failed: {}", self.operation, self.reason),
        }
    }
}

impl std::error::Error for BackendError {}

/// Result alias for backend operations.
pub type BackendResult<T> = Result<T, BackendError>;

/// A live web surface created by a [`RenderBackend`].
pub trait RenderSurface: Send + Sync {
    /// Id of the backend that created this surface.
    fn backend_id(&self) -> &'static str;

    /// Navigate to a URL.
    fn navigate(&self, url: &str) -> BackendResult<()>;

    /// Load inline HTML.
    fn load_html(&self, html: &str) -> BackendResult<()>;

    /// Evaluate a script, discarding the result.
    fn eval_js(&self, script: &str) -> BackendResult<()>;

    /// Move and resize the surface.
    fn set_bounds(&self, x: i32, y: i32, width: u32, height: u32) -> BackendResult<()>;

    /// Show or hide the surface.
    fn set_visible(&self, visible: bool) -> BackendResult<()>;

    /// Native window handle, once the surface has been realised.
    fn native_handle(&self) -> Option<u64>;

    /// Pump one round of events.
    ///
    /// Returns `Ok(true)` while the surface is alive, `Ok(false)` when it has
    /// been closed.
    fn process_events(&self) -> BackendResult<bool>;

    /// Tear the surface down.
    fn close(&self) -> BackendResult<()>;
}

/// The render-backend contract.
pub trait RenderBackend: Send + Sync {
    /// Stable machine-readable id (`"native"`, `"chromium"`).
    fn id(&self) -> &'static str;

    /// Human readable name.
    fn display_name(&self) -> &'static str;

    /// Engine family.
    fn family(&self) -> BackendFamily;

    /// Whether this backend can actually create surfaces in this build.
    ///
    /// Cheap and non-panicking: it reports linkage/runtime presence, it does not
    /// create anything.
    fn available(&self) -> bool;

    /// What is missing when [`RenderBackend::available`] is `false`.
    fn missing_requirement(&self) -> Option<String>;

    /// Capabilities this backend declares when available.
    fn capabilities(&self) -> Features;

    /// Probe one capability.
    fn probe(&self, feature: Features) -> CapabilitySupport;

    /// Create a surface.
    ///
    /// A backend that is registered but not linked must return
    /// [`BackendError::unsupported`] with a build hint, never panic.
    fn create_surface(&self, spec: &SurfaceSpec) -> BackendResult<Box<dyn RenderSurface>>;
}

impl CapabilityProbe for dyn RenderBackend {
    fn subject(&self) -> String {
        self.id().to_string()
    }

    fn capabilities(&self) -> Features {
        RenderBackend::capabilities(self)
    }

    fn probe(&self, feature: Features) -> CapabilitySupport {
        RenderBackend::probe(self, feature)
    }
}

/// Registry of render backends.
pub struct BackendRegistry {
    registry: Registry<Arc<dyn RenderBackend>>,
}

impl Default for BackendRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Debug for BackendRegistry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("BackendRegistry")
            .field("backends", &self.registry.names())
            .finish()
    }
}

impl BackendRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            registry: Registry::new(),
        }
    }

    /// Register a backend built by `factory`.
    pub fn register(
        &mut self,
        name: impl Into<String>,
        priority: i32,
        factory: impl Fn() -> Arc<dyn RenderBackend> + Send + Sync + 'static,
    ) {
        self.registry.register(name, priority, factory);
    }

    /// Register a [`Default`]-constructible backend.
    pub fn register_default<B>(&mut self, priority: i32)
    where
        B: RenderBackend + Default + 'static,
    {
        let name = B::default().id().to_string();
        self.registry.register(name, priority, || {
            Arc::new(B::default()) as Arc<dyn RenderBackend>
        });
    }

    /// Registered backend ids in priority order.
    pub fn ids(&self) -> Vec<&str> {
        self.registry.names()
    }

    /// Number of registered backends.
    pub fn len(&self) -> usize {
        self.registry.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.registry.is_empty()
    }

    /// `(priority, id, available)` for every backend.
    pub fn list(&self) -> Vec<(i32, String, bool)> {
        self.registry
            .entries()
            .iter()
            .map(|entry| {
                let backend = entry.create();
                (
                    entry.priority(),
                    entry.name().to_string(),
                    backend.available(),
                )
            })
            .collect()
    }

    /// Select the best available backend, honouring an explicit override.
    pub fn select_with(
        &self,
        env_override: Option<&str>,
    ) -> Option<Selection<Arc<dyn RenderBackend>>> {
        self.registry
            .select(env_override, |backend| backend.available())
    }

    /// Select the best available backend, honouring [`ENV_BACKEND`].
    pub fn select(&self) -> Option<Selection<Arc<dyn RenderBackend>>> {
        self.select_with(std::env::var(ENV_BACKEND).ok().as_deref())
    }

    /// Capability report for one backend, by id.
    pub fn report(&self, id: &str) -> Option<CapabilityReport> {
        let backend = self.registry.get(id)?;
        let mut report = CapabilityReport::new(backend.id());
        for flag in Features::iter_flags() {
            report.push(flag, backend.probe(flag));
        }
        Some(report)
    }
}

/// Whether the crate that links the native engine has announced itself.
///
/// The contract crate is dependency-free and therefore cannot link a WebView
/// engine itself, nor can it detect whether one is linked. The crate that does
/// link one (today `auroraview`/wry, in future `auroraview-core`) calls
/// [`NativeWebviewBackend::set_linked`] at start-up.
///
/// Until then `available()` is `false` and `missing_requirement()` says who
/// should have announced it -- a backend must never claim to be present while
/// `create_surface()` cannot work.
static NATIVE_LINKED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// Serializes tests that flip [`NATIVE_LINKED`].
///
/// The flag is process-wide by design (that is what lets the linking crate
/// announce itself), but tests run in parallel, so any test that changes it
/// must hold this lock. Without it the suite is flaky: a test that asserts
/// "unannounced" can observe another test's "announced" value.
static TEST_LINK_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Guard returned by [`NativeWebviewBackend::test_lock`].
///
/// Restores the linkage flag to its default (`false`) on drop so a test that
/// announces the backend cannot leak that into the next test.
#[doc(hidden)]
pub struct LinkageTestGuard(
    // Held only for its RAII lifetime: the mutex serializes tests, and this
    // Drop impl restores the default. The value itself is never read.
    #[allow(dead_code)] std::sync::MutexGuard<'static, ()>,
);

impl Drop for LinkageTestGuard {
    fn drop(&mut self) {
        NativeWebviewBackend::set_linked(false);
    }
}

/// The platform webview backend: WebView2 / WKWebView / WebKitGTK.
///
/// Declared here so both families are visible in one place. This type is a
/// **descriptor**: it declares what the native path can do, and its
/// `create_surface()` always fails because the contract crate links no engine.
/// Availability is announced by the crate that does link one -- see
/// [`NativeWebviewBackend::set_linked`].
#[derive(Debug, Default, Clone, Copy)]
pub struct NativeWebviewBackend;

impl NativeWebviewBackend {
    /// Announce that the native webview engine is linked into this build.
    ///
    /// Called by the crate that links wry (or an equivalent), not by the
    /// contract. Until this is called the backend reports itself unavailable, so
    /// `BackendRegistry::select()` will not hand out a backend that cannot
    /// create surfaces.
    pub fn set_linked(linked: bool) {
        NATIVE_LINKED.store(linked, std::sync::atomic::Ordering::SeqCst);
    }

    /// Lock guarding tests that call [`Self::set_linked`].
    ///
    /// Tests run in parallel against one process-wide flag, so each test that
    /// flips it must hold this lock for its whole body. Returns a guard that
    /// also restores the default (`false`) on drop.
    #[doc(hidden)]
    pub fn test_lock() -> LinkageTestGuard {
        // A poisoned mutex still guards correctly here; the flag is a bool.
        let guard = TEST_LINK_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        LinkageTestGuard(guard)
    }

    /// Whether the native webview engine has been announced as linked.
    pub fn linked() -> bool {
        NATIVE_LINKED.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Capability answers for the native path, assuming it is linked.
    ///
    /// Split out from [`RenderBackend::probe`] so callers that already know the
    /// engine is linked (and tests that must not touch the global flag) can ask
    /// about capabilities without depending on the announcement state.
    pub fn probe_when_linked(&self, feature: Features) -> CapabilitySupport {
        match feature {
            Features::CDP => CapabilitySupport::unsupported(
                "the platform webview does not expose a Chrome DevTools Protocol endpoint",
                "select the 'chromium' backend (AURORAVIEW_BACKEND=chromium)",
            ),
            Features::TRANSPARENCY => CapabilitySupport::unknown(
                "transparency depends on the platform compositor; verify at runtime",
            ),
            other if self.capabilities().contains(other) => CapabilitySupport::Supported,
            other => CapabilitySupport::unsupported(
                format!("the native backend does not provide {}", other),
                "select a different backend via AURORAVIEW_BACKEND",
            ),
        }
    }
}

impl RenderBackend for NativeWebviewBackend {
    fn id(&self) -> &'static str {
        "native"
    }

    fn display_name(&self) -> &'static str {
        "Platform WebView (WebView2 / WKWebView / WebKitGTK)"
    }

    fn family(&self) -> BackendFamily {
        BackendFamily::Native
    }

    fn available(&self) -> bool {
        Self::linked()
    }

    fn missing_requirement(&self) -> Option<String> {
        if Self::linked() {
            return None;
        }
        Some(
            "no crate has linked the native webview (wry) and announced it; ".to_string()
                + "the crate that links the engine must call "
                + "NativeWebviewBackend::set_linked(true)",
        )
    }

    fn capabilities(&self) -> Features {
        Features::NATIVE_EMBEDDING
            | Features::OUT_OF_PROCESS
            | Features::DEVTOOLS
            | Features::JS_EVAL_RESULT
            | Features::COOKIES
            | Features::FILE_PROTOCOL
            | Features::MAIN_THREAD_DISPATCH
            | Features::MULTI_WINDOW
    }

    fn probe(&self, feature: Features) -> CapabilitySupport {
        if !self.available() {
            return CapabilitySupport::unsupported(
                format!(
                    concat!(
                        "the native backend is not linked into this build, ",
                        "so {} cannot be provided",
                    ),
                    feature
                ),
                self.missing_requirement()
                    .unwrap_or_else(|| "link the native backend".to_string()),
            );
        }
        self.probe_when_linked(feature)
    }

    fn create_surface(&self, _spec: &SurfaceSpec) -> BackendResult<Box<dyn RenderSurface>> {
        Err(BackendError::unsupported(
            "create_surface",
            "this descriptor declares the native path; it is wired by the crate that links wry",
            "call BackendRegistry::select() from a build that links the native backend",
        ))
    }
}

/// A bundled Chromium-class backend.
///
/// Present so the second path is a first-class citizen of the contract rather
/// than a TODO. It is **not linked** in any current build, which is exactly the
/// situation the capability contract exists to describe: `available()` is
/// `false`, and every probe returns a structured `Unsupported` carrying the
/// build flag that would enable it.
#[derive(Debug, Default, Clone, Copy)]
pub struct ChromiumBackend;

impl RenderBackend for ChromiumBackend {
    fn id(&self) -> &'static str {
        "chromium"
    }

    fn display_name(&self) -> &'static str {
        "Chromium (bundled engine, CDP-capable)"
    }

    fn family(&self) -> BackendFamily {
        BackendFamily::Chromium
    }

    fn available(&self) -> bool {
        false
    }

    fn missing_requirement(&self) -> Option<String> {
        Some(
            "the Chromium backend is not linked into this build; \
             enable the `chromium` feature"
                .to_string(),
        )
    }

    fn capabilities(&self) -> Features {
        Features::CDP
            | Features::DEVTOOLS
            | Features::JS_EVAL_RESULT
            | Features::COOKIES
            | Features::MULTI_WINDOW
            | Features::OUT_OF_PROCESS
    }

    fn probe(&self, feature: Features) -> CapabilitySupport {
        // An unlinked backend cannot answer anything -- not even "unknown".
        // Short-circuiting here is what keeps probing honest: every answer from
        // a backend that is not in the build is a structured "unsupported, and
        // here is the flag that would enable it".
        if !self.available() {
            return CapabilitySupport::unsupported(
                format!(
                    "the chromium backend is not linked into this build, so {} \
                     cannot be provided",
                    feature
                ),
                self.missing_requirement()
                    .unwrap_or_else(|| "enable the `chromium` feature".to_string()),
            );
        }

        match feature {
            Features::NATIVE_EMBEDDING => CapabilitySupport::unsupported(
                "Chromium surfaces are not parented to a host window in this build",
                "run out-of-process and pass --parent-hwnd",
            ),
            Features::FILE_PROTOCOL => CapabilitySupport::unknown(
                "depends on how the Chromium build registers custom schemes; verify at runtime",
            ),
            other if self.capabilities().contains(other) => CapabilitySupport::Supported,
            other => CapabilitySupport::unsupported(
                format!("the chromium backend does not provide {}", other),
                "select a different backend via AURORAVIEW_BACKEND",
            ),
        }
    }

    fn create_surface(&self, _spec: &SurfaceSpec) -> BackendResult<Box<dyn RenderSurface>> {
        Err(BackendError::unsupported(
            "create_surface",
            "the chromium backend is not linked into this build",
            self.missing_requirement()
                .unwrap_or_else(|| "enable the `chromium` feature".to_string()),
        ))
    }
}

/// A registry preloaded with both reference backends: native first, chromium second.
pub fn default_backend_registry() -> BackendRegistry {
    let mut registry = BackendRegistry::new();
    registry.register_default::<NativeWebviewBackend>(100);
    registry.register_default::<ChromiumBackend>(50);
    registry
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A native backend that is always available, for testing capability logic
    /// without touching the process-wide linkage flag.
    #[derive(Default)]
    struct _AvailableBackend;

    impl RenderBackend for _AvailableBackend {
        fn id(&self) -> &'static str {
            "native"
        }

        fn display_name(&self) -> &'static str {
            "Available native backend (test)"
        }

        fn family(&self) -> BackendFamily {
            BackendFamily::Native
        }

        fn available(&self) -> bool {
            true
        }

        fn missing_requirement(&self) -> Option<String> {
            None
        }

        fn capabilities(&self) -> Features {
            NativeWebviewBackend.capabilities()
        }

        fn probe(&self, feature: Features) -> CapabilitySupport {
            NativeWebviewBackend.probe_when_linked(feature)
        }

        fn create_surface(&self, _spec: &SurfaceSpec) -> BackendResult<Box<dyn RenderSurface>> {
            Err(BackendError::unsupported(
                "create_surface",
                "test backend",
                "not implemented",
            ))
        }
    }

    // Only these two tests touch the process-wide `NATIVE_LINKED` flag, and
    // each holds `test_lock()` for its whole body. Every other test goes
    // through `probe_when_linked()` or a local backend, so it never mutates
    // global state -- tests run in parallel, and two of them flipping one bool
    // race each other no matter how carefully each restores it.
    #[test]
    fn native_backend_availability_follows_the_linkage_announcement() {
        // Held for the whole body: the flag is process-wide and other tests
        // read it. Dropping the guard restores the default (`false`).
        let _guard = NativeWebviewBackend::test_lock();

        assert_eq!(NativeWebviewBackend.id(), "native");
        assert_eq!(NativeWebviewBackend.family(), BackendFamily::Native);

        // Unannounced: must not claim to be present, and must say who should
        // have announced it. A backend that is "here" but cannot create a
        // surface is the exact failure this prevents.
        NativeWebviewBackend::set_linked(false);
        assert!(!NativeWebviewBackend.available());
        let missing = NativeWebviewBackend
            .missing_requirement()
            .expect("unannounced backend must explain what is missing");
        assert!(missing.contains("set_linked"), "{}", missing);

        // Unannounced -> every probe is a structured "unsupported" with a hint.
        for flag in Features::iter_flags() {
            let support = NativeWebviewBackend.probe(flag);
            assert!(
                !support.is_supported(),
                "an unannounced backend must not claim {}",
                flag
            );
            assert!(
                support.how_to_enable().is_some(),
                "missing hint for {}",
                flag
            );
        }

        // Announced: capabilities are reported honestly again.
        NativeWebviewBackend::set_linked(true);
        assert!(NativeWebviewBackend.available());
        assert_eq!(NativeWebviewBackend.missing_requirement(), None);
        assert!(NativeWebviewBackend
            .probe(Features::NATIVE_EMBEDDING)
            .is_supported());
        // No explicit reset: the guard restores the default on drop.
    }

    #[test]
    fn native_backend_reports_cdp_as_unsupported_with_a_remediation() {
        // Routed through `probe_when_linked`, so this test never touches the
        // process-wide linkage flag: only the consolidated availability test
        // below mutates it.
        let support = NativeWebviewBackend.probe_when_linked(Features::CDP);
        assert!(!support.is_supported());
        assert_eq!(
            support.how_to_enable(),
            Some("select the 'chromium' backend (AURORAVIEW_BACKEND=chromium)")
        );
        assert!(support.reason().expect("reason").contains("DevTools"));
    }

    #[test]
    fn native_backend_reports_transparency_as_unknown_not_unsupported() {
        let support = NativeWebviewBackend.probe_when_linked(Features::TRANSPARENCY);
        assert!(support.is_unknown(), "must not guess: {}", support);
        assert_eq!(support.how_to_enable(), None);
    }

    #[test]
    fn native_backend_reports_declared_capabilities_as_supported() {
        assert!(NativeWebviewBackend
            .probe_when_linked(Features::NATIVE_EMBEDDING)
            .is_supported());
        assert!(NativeWebviewBackend
            .probe_when_linked(Features::COOKIES)
            .is_supported());
    }

    #[test]
    fn chromium_backend_is_not_available_and_says_how_to_enable_it() {
        let backend = ChromiumBackend;
        assert_eq!(backend.family(), BackendFamily::Chromium);
        assert!(!backend.available());

        let requirement = backend.missing_requirement().expect("requirement");
        assert!(requirement.contains("chromium"), "{}", requirement);
    }

    #[test]
    fn chromium_backend_probing_never_guesses_and_never_panics() {
        let backend = ChromiumBackend;
        for flag in Features::iter_flags() {
            let support = backend.probe(flag);
            assert!(
                !support.is_supported(),
                "an unlinked backend must not claim {} as supported",
                flag
            );
            assert!(
                support.how_to_enable().is_some(),
                "every unsupported answer must carry a remediation hint ({})",
                flag
            );
        }
    }

    #[test]
    fn chromium_backend_declares_cdp_but_it_stays_unsupported_until_linked() {
        assert!(ChromiumBackend.capabilities().contains(Features::CDP));
        let support = ChromiumBackend.probe(Features::CDP);
        assert!(!support.is_supported());
        assert!(support.reason().expect("reason").contains("not linked"));
    }

    #[test]
    fn unlinked_backends_fail_surface_creation_with_a_hint_instead_of_panicking() {
        for backend in [
            &NativeWebviewBackend as &dyn RenderBackend,
            &ChromiumBackend,
        ] {
            let err = backend
                .create_surface(&SurfaceSpec::with_url("about:blank"))
                .err()
                .expect("descriptors must not create surfaces");
            assert_eq!(err.operation, "create_surface");
            assert!(err.how_to_enable.is_some());
        }
    }

    #[test]
    fn surface_spec_builders() {
        let spec = SurfaceSpec::with_url("https://example.com").with_parent_handle(42);
        assert_eq!(spec.url.as_deref(), Some("https://example.com"));
        assert_eq!(spec.parent_handle, Some(42));
        assert!(spec.devtools);

        let spec = SurfaceSpec::with_html("<h1>hi</h1>");
        assert_eq!(spec.html.as_deref(), Some("<h1>hi</h1>"));
        assert_eq!(spec.width, 800);
        assert_eq!(spec.height, 600);
    }

    #[test]
    fn default_registry_lists_both_but_selects_nothing_until_announced() {
        let _guard = NativeWebviewBackend::test_lock();
        let registry = default_backend_registry();
        assert_eq!(registry.ids(), vec!["native", "chromium"]);

        // Nothing is linked into this crate, so nothing is selectable. Returning
        // `None` is the honest answer -- handing out a backend whose
        // `create_surface()` can only fail would be worse.
        assert_eq!(
            registry.list(),
            vec![
                (100, "native".to_string(), false),
                (50, "chromium".to_string(), false)
            ]
        );
        assert!(registry.select_with(None).is_none());

        // Once the linking crate announces itself, native wins by priority.
        NativeWebviewBackend::set_linked(true);
        let selection = registry
            .select_with(None)
            .expect("native must be available once announced");
        assert_eq!(selection.name, "native");
        assert!(!selection.has_warnings());

        // An override naming an unavailable backend degrades to native with a
        // warning rather than failing.
        let selection = registry
            .select_with(Some("chromium"))
            .expect("must fall back to native");
        assert_eq!(selection.name, "native");
        assert!(selection.has_warnings());
        assert!(selection.warnings[0].contains("not available"));
        // No explicit reset: the guard restores the default on drop.
    }

    /// Pins the deferred gap described in `docs/design/adapter-contract.md`:
    /// once surface creation is wired through the registry (step 3), a backend
    /// that `select()` hands out MUST be able to create a surface.
    ///
    /// Today `NativeWebviewBackend` is a descriptor whose `create_surface()`
    /// always fails, so announcing the engine as linked re-opens the very
    /// failure this contract forbids -- "selectable but unusable". This test
    /// asserts the CURRENT (known-incomplete) state so the gap is visible in
    /// test output and cannot be silently forgotten. When step 3 lands, flip
    /// the assertion to `is_ok()` and the guard becomes a real invariant.
    #[test]
    fn descriptor_still_cannot_create_surfaces_even_when_announced() {
        let _guard = NativeWebviewBackend::test_lock();

        NativeWebviewBackend::set_linked(true);
        let registry = default_backend_registry();
        let selection = registry
            .select_with(None)
            .expect("native is available once announced");

        // The documented gap: selectable, but not yet able to build a surface.
        let result = selection
            .value
            .create_surface(&SurfaceSpec::with_url("about:blank"));
        assert!(
            result.is_err(),
            "step 3 not done: expected the descriptor to \
             refuse; wire surface creation through the registry and flip this \
             assertion to is_ok()"
        );
        // No explicit reset: the guard restores the default on drop.
    }

    #[test]
    fn registry_reports_capabilities_per_backend() {
        // Built from a local "available" backend rather than the global linkage
        // flag: tests run in parallel, and flipping shared state from two tests
        // at once is a race regardless of how carefully each one restores it.
        let mut registry = BackendRegistry::new();
        registry.register("native", 100, || {
            Arc::new(_AvailableBackend) as Arc<dyn RenderBackend>
        });

        let report = registry.report("native").expect("native report");
        assert!(report.supported().contains(&"NATIVE_EMBEDDING"));
        assert!(report
            .unknown()
            .iter()
            .any(|entry| entry.feature == "TRANSPARENCY"));
        assert!(report
            .unsupported()
            .iter()
            .any(|entry| entry.feature == "CDP"));
    }

    #[test]
    fn unknown_backend_report_is_none() {
        assert!(default_backend_registry().report("nope").is_none());
    }
}
