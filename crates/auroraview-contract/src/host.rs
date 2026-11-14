//! Host adapter contract.
//!
//! A *host adapter* is everything AuroraView needs to know about a host
//! application (Maya, Unreal, Unity, PowerPoint, a browser, plain desktop).
//! It answers three questions -- **how do I register myself**, **how am I
//! discovered**, and **how does a surface get embedded** -- and it is the only
//! place host-specific code is allowed to live.
//!
//! # Dependency direction
//!
//! ```text
//!   auroraview-contract   (this crate: traits only, zero dependencies)
//!        ^          ^
//!        |          |
//!   auroraview-core   auroraview-maya / -unreal / -unity / ...
//! ```
//!
//! Adapters depend on the contract; the contract never names a host. Core
//! depends on the contract and on nothing host-specific, so a new host is a new
//! crate that registers itself -- not an edit to a `DccType` enum in core.

use std::fmt;
use std::sync::Arc;

use crate::capability::{CapabilityProbe, CapabilitySupport, Features};
use crate::registry::{Registry, Selection};

/// Environment variable used to pin a host adapter.
pub const ENV_HOST: &str = "AURORAVIEW_HOST";

/// UI toolkit the host is built on.
///
/// This decides how a surface is parented, not how it is rendered.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
/// Adding a variant is a minor (additive) change; removing or renaming one
/// is breaking and requires a major bump coordinated across every host
/// repository. See the version policy in `Cargo.toml`.
#[non_exhaustive]
pub enum UiFramework {
    /// Qt widgets (Maya, Houdini, Nuke, 3ds Max).
    Qt,
    /// Unreal Slate.
    Slate,
    /// Raw Win32 / HWND.
    Win32,
    /// AppKit / NSView.
    Cocoa,
    /// GTK.
    Gtk,
    /// WPF / WinForms.
    Wpf,
    /// The host is itself a web surface (Office.js add-in, Electron).
    Html,
    /// Unknown or not applicable (plain desktop).
    Unknown,
}

impl UiFramework {
    /// Stable snake-case name.
    pub fn name(self) -> &'static str {
        match self {
            Self::Qt => "qt",
            Self::Slate => "slate",
            Self::Win32 => "win32",
            Self::Cocoa => "cocoa",
            Self::Gtk => "gtk",
            Self::Wpf => "wpf",
            Self::Html => "html",
            Self::Unknown => "unknown",
        }
    }

    /// Whether a native window handle can be obtained from the host.
    pub fn exposes_native_handle(self) -> bool {
        !matches!(self, Self::Html | Self::Unknown)
    }
}

/// Thread affinity the host imposes on UI work.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
/// Adding a variant is a minor (additive) change; removing or renaming one
/// is breaking and requires a major bump coordinated across every host
/// repository. See the version policy in `Cargo.toml`.
#[non_exhaustive]
pub enum ThreadModel {
    /// Host UI thread: the Qt main thread or a Win32 message thread.
    HostUiThread,
    /// Unreal Engine GameThread.
    GameThread,
    /// COM single-threaded apartment (Office / PowerPoint).
    StaApartment,
    /// No affinity -- any thread may create and drive the surface.
    Any,
}

impl ThreadModel {
    /// Stable snake-case name.
    pub fn name(self) -> &'static str {
        match self {
            Self::HostUiThread => "host_ui_thread",
            Self::GameThread => "game_thread",
            Self::StaApartment => "sta_apartment",
            Self::Any => "any",
        }
    }

    /// Whether blocking the host thread while waiting on a result is safe.
    ///
    /// On an STA thread (Office) blocking the message pump makes the host
    /// application report "not responding". On the Unreal GameThread it stalls
    /// the editor. Both must therefore use fire-and-forget dispatch and return
    /// results through an event.
    pub fn blocking_dispatch_is_safe(self) -> bool {
        !matches!(self, Self::StaApartment | Self::GameThread)
    }
}

/// How a surface is attached to the host window.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
/// Adding a variant is a minor (additive) change; removing or renaming one
/// is breaking and requires a major bump coordinated across every host
/// repository. See the version policy in `Cargo.toml`.
#[non_exhaustive]
pub enum EmbedMode {
    /// The surface is parented into a host-provided native window.
    NativeChild,
    /// The surface runs in a separate process positioned over the host window.
    ///
    /// This is the only mode that covers hosts with no in-process embedding
    /// path (Unity, Unreal C++, PowerPoint via COM).
    OutOfProcess,
    /// The surface is a top-level window owned by AuroraView.
    Floating,
}

impl EmbedMode {
    /// Stable snake-case name.
    pub fn name(self) -> &'static str {
        match self {
            Self::NativeChild => "native_child",
            Self::OutOfProcess => "out_of_process",
            Self::Floating => "floating",
        }
    }
}

/// A host operation that could not be performed.
#[derive(Debug, Clone)]
pub struct HostError {
    /// Operation that failed.
    pub operation: &'static str,
    /// Why it failed.
    pub reason: String,
    /// What the integrator should do about it.
    pub how_to_enable: Option<String>,
}

impl HostError {
    /// Build an "unsupported by this host" error.
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

impl fmt::Display for HostError {
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

impl std::error::Error for HostError {}

/// Result alias for host operations.
pub type HostResult<T> = Result<T, HostError>;

/// A boxed job handed to the host's UI thread.
pub type HostJob = Box<dyn FnOnce() + Send>;

/// A snapshot of a host adapter, safe to log and to send across threads.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HostInfo {
    /// Stable machine-readable id (`"maya"`, `"unreal"`, ...).
    pub id: String,
    /// Human readable name.
    pub display_name: String,
    /// Host-reported version, when the host exposes one.
    pub version: Option<String>,
    /// UI toolkit.
    pub ui_framework: UiFramework,
    /// Thread affinity.
    pub thread_model: ThreadModel,
    /// Embedding strategy.
    pub embed_mode: EmbedMode,
    /// Parent window handle, when one could be discovered.
    pub parent_handle: Option<u64>,
}

/// The host adapter contract.
///
/// Implementations must be cheap to construct: construction happens during
/// discovery, before we know whether the host is present. Anything expensive
/// belongs in [`HostAdapter::detect`] or behind a lazy call.
///
/// # Registration
///
/// Adapters register themselves with a [`HostRegistry`]; nothing in core
/// enumerates host names. See the module docs.
pub trait HostAdapter: Send + Sync {
    /// Stable machine-readable id, e.g. `"maya"`, `"unreal"`, `"unity"`.
    fn id(&self) -> &'static str;

    /// Human readable name, e.g. `"Autodesk Maya"`.
    fn display_name(&self) -> &'static str;

    /// UI toolkit of the host.
    fn ui_framework(&self) -> UiFramework;

    /// Thread affinity imposed by the host.
    fn thread_model(&self) -> ThreadModel;

    /// How surfaces are attached to the host window.
    fn embed_mode(&self) -> EmbedMode;

    /// Whether this host is present in the current process.
    ///
    /// Must be cheap, must not panic, and must not import anything at
    /// module scope -- see the Python dispatcher backends for the pattern.
    fn detect(&self) -> bool;

    /// Host version, when the host exposes one.
    fn version(&self) -> Option<String> {
        None
    }

    /// Capabilities this host declares.
    fn capabilities(&self) -> Features {
        Features::empty()
    }

    /// Parent window handle, when the host can supply one directly.
    ///
    /// Returning `None` is normal: Qt hosts usually need a widget pointer from
    /// the caller rather than a top-level handle.
    /// The contract representation is `u64`; convert signed native values with
    /// `u64::try_from` before storing them in the adapter. Reject conversion
    /// failures rather than silently casting or reporting an absent handle.
    fn parent_handle(&self) -> Option<u64> {
        None
    }

    /// Run `job` on the host's UI thread without waiting for it.
    ///
    /// This is the only dispatch primitive the contract requires. It is safe on
    /// every thread model we support, including STA and GameThread.
    fn run_deferred(&self, job: HostJob) -> HostResult<()>;

    /// Run `job` on the host's UI thread and wait for it.
    ///
    /// Deliberately **not** required. The default implementation refuses,
    /// because blocking the host thread is exactly the failure mode that makes
    /// PowerPoint report "not responding" and stalls the Unreal editor.
    fn try_run_sync(&self, job: HostJob) -> HostResult<()> {
        drop(job);
        let model = self.thread_model();
        if model.blocking_dispatch_is_safe() {
            Err(HostError::unsupported(
                "try_run_sync",
                format!("host '{}' does not implement blocking dispatch", self.id()),
                format!(
                    "implement try_run_sync() on the '{}' adapter, or use run_deferred() \
                     and surface the result through an event",
                    self.id()
                ),
            ))
        } else {
            Err(HostError::unsupported(
                "try_run_sync",
                format!(
                    "host '{}' uses the {} thread model, where blocking dispatch would \
                     freeze the host",
                    self.id(),
                    model.name()
                ),
                "use run_deferred() and surface the result through an event",
            ))
        }
    }

    /// Probe a single capability.
    fn probe(&self, feature: Features) -> CapabilitySupport {
        if self.capabilities().contains(feature) {
            CapabilitySupport::Supported
        } else {
            CapabilitySupport::unsupported(
                format!("host '{}' does not declare {}", self.id(), feature),
                format!(
                    "implement the missing capability on the '{}' host adapter",
                    self.id()
                ),
            )
        }
    }

    /// Build a [`HostInfo`] snapshot.
    fn info(&self) -> HostInfo {
        HostInfo {
            id: self.id().to_string(),
            display_name: self.display_name().to_string(),
            version: self.version(),
            ui_framework: self.ui_framework(),
            thread_model: self.thread_model(),
            embed_mode: self.embed_mode(),
            parent_handle: self.parent_handle(),
        }
    }
}

impl CapabilityProbe for dyn HostAdapter {
    fn subject(&self) -> String {
        self.id().to_string()
    }

    fn capabilities(&self) -> Features {
        HostAdapter::capabilities(self)
    }

    fn probe(&self, feature: Features) -> CapabilitySupport {
        HostAdapter::probe(self, feature)
    }
}

/// Registry of host adapters.
pub struct HostRegistry {
    registry: Registry<Arc<dyn HostAdapter>>,
}

impl Default for HostRegistry {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Debug for HostRegistry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HostRegistry")
            .field("adapters", &self.registry.names())
            .finish()
    }
}

impl HostRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            registry: Registry::new(),
        }
    }

    /// Register a [`Default`]-constructible adapter.
    pub fn register<A>(&mut self, priority: i32)
    where
        A: HostAdapter + Default + 'static,
    {
        let name = A::default().id().to_string();
        self.registry.register(name, priority, || {
            Arc::new(A::default()) as Arc<dyn HostAdapter>
        });
    }

    /// Register an adapter built by `factory`.
    pub fn register_adapter(
        &mut self,
        name: impl Into<String>,
        priority: i32,
        factory: impl Fn() -> Arc<dyn HostAdapter> + Send + Sync + 'static,
    ) {
        self.registry.register(name, priority, factory);
    }

    /// Remove an adapter by id.
    pub fn unregister(&mut self, id: &str) -> bool {
        self.registry.unregister(id)
    }

    /// Registered adapter ids in priority order.
    pub fn ids(&self) -> Vec<&str> {
        self.registry.names()
    }

    /// Number of registered adapters.
    pub fn len(&self) -> usize {
        self.registry.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.registry.is_empty()
    }

    /// `(priority, id, detected)` for every adapter, highest priority first.
    ///
    /// Mirrors `list_dispatcher_backends()` on the Python side so diagnostics
    /// output looks the same in both languages.
    pub fn list(&self) -> Vec<(i32, String, bool)> {
        self.registry
            .entries()
            .iter()
            .map(|entry| {
                let adapter = entry.create();
                (entry.priority(), entry.name().to_string(), adapter.detect())
            })
            .collect()
    }

    /// Detect the host, honouring an explicit override.
    pub fn detect_with(
        &self,
        env_override: Option<&str>,
    ) -> Option<Selection<Arc<dyn HostAdapter>>> {
        self.registry
            .select(env_override, |adapter| adapter.detect())
    }

    /// Detect the host, honouring [`ENV_HOST`].
    pub fn detect(&self) -> Option<Selection<Arc<dyn HostAdapter>>> {
        self.detect_with(std::env::var(ENV_HOST).ok().as_deref())
    }

    /// Snapshot of the detected host, or `None` when running standalone.
    pub fn current(&self) -> Option<HostInfo> {
        self.detect().map(|selection| selection.value.info())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn capabilities() -> Features {
        Features::NATIVE_EMBEDDING | Features::MAIN_THREAD_DISPATCH
    }

    /// Stand-in for a Qt-flavoured DCC host.
    #[derive(Default)]
    struct FakeQtHost {
        ran: std::sync::Mutex<Vec<&'static str>>,
    }

    impl HostAdapter for FakeQtHost {
        fn id(&self) -> &'static str {
            "fake_qt"
        }

        fn display_name(&self) -> &'static str {
            "Fake Qt Host"
        }

        fn ui_framework(&self) -> UiFramework {
            UiFramework::Qt
        }

        fn thread_model(&self) -> ThreadModel {
            ThreadModel::HostUiThread
        }

        fn embed_mode(&self) -> EmbedMode {
            EmbedMode::NativeChild
        }

        fn detect(&self) -> bool {
            true
        }

        fn version(&self) -> Option<String> {
            Some("2024.1".to_string())
        }

        fn capabilities(&self) -> Features {
            capabilities()
        }

        fn parent_handle(&self) -> Option<u64> {
            Some(0xDEAD)
        }

        fn run_deferred(&self, job: HostJob) -> HostResult<()> {
            job();
            self.ran.lock().expect("mutex").push("run_deferred");
            Ok(())
        }
    }

    /// Stand-in for an STA host (Office / PowerPoint).
    #[derive(Default)]
    struct FakeStaHost;

    impl HostAdapter for FakeStaHost {
        fn id(&self) -> &'static str {
            "powerpoint"
        }

        fn display_name(&self) -> &'static str {
            "Microsoft PowerPoint"
        }

        fn ui_framework(&self) -> UiFramework {
            UiFramework::Win32
        }

        fn thread_model(&self) -> ThreadModel {
            ThreadModel::StaApartment
        }

        fn embed_mode(&self) -> EmbedMode {
            EmbedMode::OutOfProcess
        }

        fn detect(&self) -> bool {
            false
        }

        fn capabilities(&self) -> Features {
            Features::OUT_OF_PROCESS
        }

        fn run_deferred(&self, job: HostJob) -> HostResult<()> {
            job();
            Ok(())
        }
    }

    #[test]
    fn thread_model_gates_blocking_dispatch() {
        assert!(ThreadModel::HostUiThread.blocking_dispatch_is_safe());
        assert!(ThreadModel::Any.blocking_dispatch_is_safe());
        assert!(!ThreadModel::StaApartment.blocking_dispatch_is_safe());
        assert!(!ThreadModel::GameThread.blocking_dispatch_is_safe());
    }

    #[test]
    fn sta_host_refuses_blocking_dispatch_with_remediation() {
        let host = FakeStaHost;
        let err = host
            .try_run_sync(Box::new(|| {}))
            .expect_err("STA must refuse blocking dispatch");
        assert_eq!(err.operation, "try_run_sync");
        assert!(err.reason.contains("sta_apartment"));
        assert_eq!(
            err.how_to_enable.as_deref(),
            Some("use run_deferred() and surface the result through an event")
        );
        assert!(err.to_string().contains("to enable: use run_deferred"));
    }

    #[test]
    fn adapter_without_sync_implementation_refuses_with_remediation() {
        let host = FakeQtHost::default();
        let err = host
            .try_run_sync(Box::new(|| {}))
            .expect_err("unimplemented sync must refuse");
        assert!(err.reason.contains("does not implement blocking dispatch"));
        assert!(err
            .how_to_enable
            .as_deref()
            .expect("hint")
            .contains("run_deferred"));
    }

    #[test]
    fn deferred_dispatch_runs_the_job() {
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::sync::Arc;

        let ran = Arc::new(AtomicBool::new(false));
        let flag = Arc::clone(&ran);
        let host = FakeQtHost::default();
        host.run_deferred(Box::new(move || flag.store(true, Ordering::SeqCst)))
            .expect("deferred dispatch must succeed");
        assert!(ran.load(Ordering::SeqCst));
    }

    #[test]
    fn probe_derives_from_declared_capabilities() {
        let host = FakeQtHost::default();
        assert!(host.probe(Features::NATIVE_EMBEDDING).is_supported());
        assert!(!host.probe(Features::CDP).is_supported());

        let missing = host
            .probe(Features::CDP)
            .how_to_enable()
            .expect("remediation hint")
            .to_string();
        assert!(missing.contains("fake_qt"));
    }

    #[test]
    fn info_snapshot_captures_the_contract() {
        let info = FakeQtHost::default().info();
        assert_eq!(info.id, "fake_qt");
        assert_eq!(info.display_name, "Fake Qt Host");
        assert_eq!(info.version.as_deref(), Some("2024.1"));
        assert_eq!(info.ui_framework, UiFramework::Qt);
        assert_eq!(info.thread_model, ThreadModel::HostUiThread);
        assert_eq!(info.embed_mode, EmbedMode::NativeChild);
        assert_eq!(info.parent_handle, Some(0xDEAD));
    }

    #[test]
    fn ui_framework_exposes_native_handle_except_for_html() {
        assert!(UiFramework::Qt.exposes_native_handle());
        assert!(UiFramework::Win32.exposes_native_handle());
        assert!(!UiFramework::Html.exposes_native_handle());
        assert!(!UiFramework::Unknown.exposes_native_handle());
    }

    fn registry() -> HostRegistry {
        let mut registry = HostRegistry::new();
        registry.register::<FakeQtHost>(200);
        registry.register::<FakeStaHost>(150);
        registry
    }

    /// A second *detectable* host, registered below the Qt one, used to prove
    /// that an override beats priority order.
    #[derive(Default)]
    struct FakeLowPriorityHost;

    impl HostAdapter for FakeLowPriorityHost {
        fn id(&self) -> &'static str {
            "fake_low"
        }

        fn display_name(&self) -> &'static str {
            "Fake Low Priority Host"
        }

        fn ui_framework(&self) -> UiFramework {
            UiFramework::Win32
        }

        fn thread_model(&self) -> ThreadModel {
            ThreadModel::Any
        }

        fn embed_mode(&self) -> EmbedMode {
            EmbedMode::Floating
        }

        fn detect(&self) -> bool {
            true
        }

        fn run_deferred(&self, job: HostJob) -> HostResult<()> {
            job();
            Ok(())
        }
    }

    #[test]
    fn registry_lists_adapters_in_priority_order_with_detection() {
        let registry = registry();
        assert_eq!(registry.ids(), vec!["fake_qt", "powerpoint"]);
        assert_eq!(registry.len(), 2);

        let listed: Vec<(i32, String, bool)> = registry.list();
        assert_eq!(listed[0], (200, "fake_qt".to_string(), true));
        assert_eq!(listed[1], (150, "powerpoint".to_string(), false));
    }

    #[test]
    fn detect_picks_the_first_available_adapter() {
        let selection = registry()
            .detect_with(None)
            .expect("fake_qt must be detected");
        assert_eq!(selection.name, "fake_qt");
        assert!(!selection.via_env_override);
        assert_eq!(selection.value.info().id, "fake_qt");
    }

    #[test]
    fn detect_returns_none_when_no_adapter_matches() {
        let mut registry = HostRegistry::new();
        registry.register::<FakeStaHost>(150);
        assert!(registry.detect_with(None).is_none());
    }

    #[test]
    fn host_override_beats_priority_order() {
        let mut registry = HostRegistry::new();
        registry.register::<FakeQtHost>(200);
        registry.register::<FakeLowPriorityHost>(10);

        let selection = registry
            .detect_with(Some("fake_low"))
            .expect("override must win");
        assert!(selection.via_env_override);
        assert_eq!(selection.name, "fake_low");
        assert!(!selection.has_warnings());
    }

    #[test]
    fn host_override_cannot_force_an_absent_host() {
        let selection = registry()
            .detect_with(Some("powerpoint"))
            .expect("must fall back");
        assert!(!selection.via_env_override);
        assert_eq!(selection.name, "fake_qt");
        assert!(selection.has_warnings());
    }

    #[test]
    fn host_override_falls_back_with_a_warning() {
        let selection = registry()
            .detect_with(Some("nonexistent"))
            .expect("must fall back to a detected host");
        assert_eq!(selection.name, "fake_qt");
        assert!(selection.has_warnings());
    }

    #[test]
    fn current_returns_a_host_snapshot() {
        let registry = registry();
        let info = registry.current().expect("fake_qt is detected");
        assert_eq!(info.id, "fake_qt");
    }

    #[test]
    fn unregister_removes_an_adapter() {
        let mut registry = registry();
        assert!(registry.unregister("powerpoint"));
        assert_eq!(registry.ids(), vec!["fake_qt"]);
    }
}
