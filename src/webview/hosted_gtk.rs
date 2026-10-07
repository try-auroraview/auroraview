//! Experimental GTK runtime driven by a non-GTK host's main-thread timer.
//!
//! No Tao event loop, worker-thread GTK, native Send/Sync wrapper, or sandbox
//! override is used. A single runtime owns all views and advances the default
//! GTK context in bounded, nonblocking slices. Native acceptance is outstanding.

use std::cell::{Cell, RefCell};
use std::collections::VecDeque;
use std::sync::Arc;
use std::time::{Duration, Instant};

use gtk::glib::{Propagation, SignalHandlerId};
use gtk::prelude::*;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use wry::{WebViewBuilderExtUnix, WebViewExtUnix};

use super::core::AuroraView;
use super::desktop::{configure_with_context, create_web_context};
use super::hosted_pump::{run_slice, PumpTarget};
use super::message_processor::process_message;
use crate::ipc::{IpcHandler, JsCallbackManager, MessageQueue, WebViewMessage};

const MAX_VIEWS: usize = 16;

thread_local! {
    static VIEWS: RefCell<VecDeque<HostedView>> = const { RefCell::new(VecDeque::new()) };
    static CLAIMED: Cell<bool> = const { Cell::new(false) };
    static BUSY: Cell<bool> = const { Cell::new(false) };
    static SHUTDOWN: Cell<bool> = const { Cell::new(false) };
}

/// Never hold a registry borrow across a GTK call or an application callback.
struct DispatchGuard;

impl DispatchGuard {
    fn enter() -> PyResult<Self> {
        if BUSY.with(|busy| busy.replace(true)) {
            return Err(PyRuntimeError::new_err(
                "Hosted GTK dispatch cannot be reentered",
            ));
        }
        Ok(Self)
    }
}

impl Drop for DispatchGuard {
    fn drop(&mut self) {
        BUSY.with(|busy| busy.set(false));
    }
}

/// Retain owner-thread native objects if Rust unwinds out of dispatch.
/// No native operation or Python finalizer runs while restoring the registry.
struct RegistryLease {
    views: VecDeque<HostedView>,
}

impl RegistryLease {
    fn take() -> Self {
        Self {
            views: VIEWS.with(|stored| std::mem::take(&mut *stored.borrow_mut())),
        }
    }
}

impl Drop for RegistryLease {
    fn drop(&mut self) {
        if std::thread::panicking() {
            // Only shutdown is supported after an unwind; do not resume work.
            SHUTDOWN.with(|shutdown| shutdown.set(true));
        }
        let views = std::mem::take(&mut self.views);
        let previous = VIEWS.with(|stored| std::mem::replace(&mut *stored.borrow_mut(), views));
        drop(previous); // Always outside the RefCell borrow.
    }
}

/// GTK top-level ownership also covers failed WebView construction.
struct WindowOwner {
    window: gtk::Window,
    delete_handler: Option<SignalHandlerId>,
}

impl Drop for WindowOwner {
    fn drop(&mut self) {
        if let Some(handler) = self.delete_handler.take() {
            self.window.disconnect(handler);
        }
        // SAFETY: this private top-level never escapes Core. The Wry view is
        // dropped first, dispatch has unwound, and its delete handler is gone.
        // Neither this code nor a callback queries the widget after destruction.
        unsafe { self.window.destroy() };
    }
}

struct HostedView {
    webview: Option<wry::WebView>,
    window: WindowOwner,
    // Must outlive the Wry view; the builder only borrows it during creation.
    _context: wry::WebContext,
    queue: Arc<MessageQueue>,
    ipc: Arc<IpcHandler>,
    callbacks: Arc<JsCallbackManager>,
}

impl HostedView {
    fn close(mut self) {
        self.queue.shutdown();
        self.callbacks.close_admission();
        self.ipc.close_admission();
        self.callbacks.cancel_all_hosted();
        self.ipc.shutdown_hosted();
        drop(self.webview.take());
        let queue = Arc::clone(&self.queue);
        drop(self); // Window and context release on this owner thread.
        queue.finish_hosted();
    }
}

fn close_requested(views: &mut VecDeque<HostedView>) -> usize {
    let mut closed = 0;
    for _ in 0..views.len() {
        if let Some(view) = views.pop_front() {
            if SHUTDOWN.with(Cell::get) || view.queue.hosted_state() == 2 {
                view.close();
                closed += 1;
            } else {
                views.push_back(view);
            }
        }
    }
    closed
}

struct NativePump<'a> {
    views: &'a mut VecDeque<HostedView>,
    closed: usize,
}

impl PumpTarget for NativePump<'_> {
    fn is_running(&self) -> bool {
        !SHUTDOWN.with(Cell::get) && !self.views.is_empty()
    }

    fn native_step(&mut self) -> bool {
        if !gtk::events_pending() {
            return false;
        }
        gtk::main_iteration_do(false);
        self.closed += close_requested(self.views);
        true
    }

    fn outbound_step(&mut self) -> bool {
        self.closed += close_requested(self.views);
        for _ in 0..self.views.len() {
            // The lease retains ownership across application/native calls and
            // restores it if Rust unwinds before this step returns.
            let Some(view) = self.views.front() else {
                break;
            };
            if SHUTDOWN.with(Cell::get) || view.queue.hosted_state() != 1 {
                break;
            }
            let message = view.queue.pop();
            if let (Some(message), Some(webview)) = (message, view.webview.as_ref()) {
                // Final owner-side firewall for commands admitted before
                // begin_hosted() or through an older producer path.
                if MessageQueue::is_navigation(&message) {
                    tracing::warn!("Hosted GTK rejected queued navigation; use a fresh view");
                    self.views.rotate_left(1);
                    return true;
                }
                match message {
                    WebViewMessage::SetVisible(true) => view.window.window.show_all(),
                    WebViewMessage::SetVisible(false) => view.window.window.hide(),
                    WebViewMessage::Close => view.queue.push(WebViewMessage::Close),
                    message => process_message(webview, message, "hosted-gtk"),
                }
                self.views.rotate_left(1);
                self.closed += close_requested(self.views);
                return true;
            }
            self.views.rotate_left(1);
        }
        false
    }
}

fn finish_shutdown() {
    SHUTDOWN.with(|shutdown| shutdown.set(false));
    CLAIMED.with(|claimed| claimed.set(false));
}

fn shutdown_views() -> bool {
    SHUTDOWN.with(|shutdown| shutdown.set(true));
    if BUSY.with(Cell::get) {
        // A callback may request shutdown; the outer dispatch owns destruction.
        return false;
    }
    let Ok(_guard) = DispatchGuard::enter() else {
        return false;
    };
    let mut lease = RegistryLease::take();
    close_requested(&mut lease.views);
    finish_shutdown();
    true
}

/// One process-wide, main-thread GTK pump. Available only in opt-in builds.
#[pyclass(name = "HostRuntime", unsendable)]
pub(crate) struct HostRuntime {
    closed: Cell<bool>,
}

#[pymethods]
impl HostRuntime {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        let threading = py.import("threading")?;
        let current = threading.call_method0("current_thread")?;
        let main = threading.call_method0("main_thread")?;
        if !current.is(&main) {
            return Err(PyRuntimeError::new_err(
                "Hosted GTK must be created on the host main thread",
            ));
        }
        if gtk::is_initialized() && !gtk::is_initialized_main_thread() {
            return Err(PyRuntimeError::new_err(
                "GTK is already owned by another thread",
            ));
        }
        if CLAIMED.with(Cell::get) {
            return Err(PyRuntimeError::new_err(
                "A HostRuntime already owns this process",
            ));
        }
        gtk::init().map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        CLAIMED.with(|claimed| claimed.set(true));
        Ok(Self {
            closed: Cell::new(false),
        })
    }

    /// Construct without entering an outer loop. The host must call poll().
    pub(crate) fn show(&self, view: PyRef<'_, AuroraView>) -> PyResult<()> {
        if self.closed.get() || SHUTDOWN.with(Cell::get) {
            return Err(PyRuntimeError::new_err("HostRuntime requires shutdown"));
        }
        let _guard = DispatchGuard::enter()?;
        if VIEWS.with(|views| views.borrow().len()) >= MAX_VIEWS {
            return Err(PyRuntimeError::new_err("Hosted view limit reached (16)"));
        }
        if view.inner.borrow().is_some() || view.message_queue.hosted_state() != 0 {
            return Err(PyRuntimeError::new_err(
                "Use a fresh WebView for hosted creation",
            ));
        }
        let config = view.config.borrow().clone();
        if config.parent_hwnd.is_some()
            || config.headless
            || config.download_prompt
            || matches!(
                config.new_window_mode,
                super::config::NewWindowMode::ChildWebView
            )
        {
            return Err(PyValueError::new_err(
                "Hosted GTK supports floating GUI views without modal downloads or child popups",
            ));
        }
        // Inline HTML has no initial network redirect to classify. Wry's GTK
        // Started event arrives at commit, too late to police such redirects.
        if config.url.is_some() {
            return Err(PyValueError::new_err(
                "Hosted GTK single-document mode requires initial inline HTML, not a URL",
            ));
        }
        let width = i32::try_from(config.width)
            .ok()
            .filter(|value| *value > 0)
            .ok_or_else(|| PyValueError::new_err("Invalid hosted width"))?;
        let height = i32::try_from(config.height)
            .ok()
            .filter(|value| *value > 0)
            .ok_or_else(|| PyValueError::new_err("Invalid hosted height"))?;
        view.message_queue
            .begin_hosted()
            .map_err(PyRuntimeError::new_err)?;
        let result = (|| -> Result<HostedView, Box<dyn std::error::Error>> {
            let window = gtk::Window::new(gtk::WindowType::Toplevel);
            let mut owner = WindowOwner {
                window,
                delete_handler: None,
            };
            owner.window.set_title(&config.title);
            owner.window.set_default_size(width, height);
            owner.window.set_resizable(config.resizable);
            owner.window.set_decorated(config.decorations);
            owner.window.set_keep_above(config.always_on_top);
            let queue = Arc::clone(&view.message_queue);
            owner.delete_handler = Some(owner.window.connect_delete_event(move |_, _| {
                queue.push(WebViewMessage::Close);
                Propagation::Stop
            }));
            let container = gtk::Box::new(gtk::Orientation::Vertical, 0);
            owner.window.add(&container);
            let mut context = create_web_context(&config)?;
            let builder = configure_with_context(
                &config,
                Arc::clone(&view.ipc_handler),
                Arc::clone(&view.message_queue),
                &mut context,
            )?;
            let webview = builder.build_gtk(&container)?;
            // Wry's window.close() handler destroys the WebKit child directly,
            // bypassing top-level delete-event. Widget destruction is synchronous:
            // publish priority close intent before GTK returns to this pump.
            // Keep only queue state in this handler, never a native cross-thread handle.
            let queue = Arc::clone(&view.message_queue);
            webview.webview().connect_destroy(move |_| {
                queue.push(WebViewMessage::Close);
            });
            if config.auto_show {
                owner.window.show_all();
            }
            Ok(HostedView {
                webview: Some(webview),
                window: owner,
                _context: context,
                queue: Arc::clone(&view.message_queue),
                ipc: Arc::clone(&view.ipc_handler),
                callbacks: Arc::clone(&view.js_callback_manager),
            })
        })();
        let result = match result {
            Ok(native) => {
                VIEWS.with(|views| views.borrow_mut().push_back(native));
                Ok(())
            }
            Err(error) => {
                view.message_queue.shutdown();
                view.js_callback_manager.close_admission();
                view.ipc_handler.close_admission();
                view.js_callback_manager.cancel_all_hosted();
                view.ipc_handler.shutdown_hosted();
                view.message_queue.finish_hosted();
                Err(PyRuntimeError::new_err(error.to_string()))
            }
        };
        if SHUTDOWN.with(Cell::get) {
            let mut lease = RegistryLease::take();
            close_requested(&mut lease.views);
            finish_shutdown();
            return Err(PyRuntimeError::new_err(
                "HostRuntime shut down during creation",
            ));
        }
        result
    }

    /// Advance native events and outbound queues with shared count/time limits.
    /// A single GTK callback can exceed the soft elapsed-time budget.
    #[pyo3(signature = (max_iterations=64, max_messages=64, budget_ms=2.0))]
    fn poll<'py>(
        &self,
        py: Python<'py>,
        max_iterations: usize,
        max_messages: usize,
        budget_ms: f64,
    ) -> PyResult<Bound<'py, PyDict>> {
        if max_iterations == 0
            || max_iterations > 64
            || max_messages == 0
            || max_messages > 256
            || !budget_ms.is_finite()
            || budget_ms <= 0.0
            || budget_ms > 16.0
        {
            return Err(PyValueError::new_err("Invalid hosted pump budget"));
        }
        if self.closed.get() {
            return Err(PyRuntimeError::new_err("HostRuntime is shut down"));
        }
        let _guard = DispatchGuard::enter()?;
        let started = Instant::now();
        let budget = Duration::from_secs_f64(budget_ms / 1000.0);
        let mut lease = RegistryLease::take();
        let views = &mut lease.views;
        let mut closed = close_requested(views);
        let mut timed_out_callbacks = 0;

        // Reserve bounded timeout inspection for every live view on the owner
        // thread. This opportunity is guaranteed even if GTK consumes the soft
        // budget every time. A callback itself cannot be preempted.
        for view in views.iter() {
            if SHUTDOWN.with(Cell::get) {
                break;
            }
            if view.queue.hosted_state() == 1 {
                timed_out_callbacks += view.callbacks.cleanup_timed_out_while(8, || {
                    !SHUTDOWN.with(Cell::get) && view.queue.hosted_state() == 1
                });
            }
        }
        closed += close_requested(views);
        let work = {
            let mut target = NativePump {
                views: &mut *views,
                closed: 0,
            };
            let work = run_slice(
                &mut target,
                || started.elapsed(),
                budget,
                max_iterations,
                max_messages,
            );
            closed += target.closed;
            work
        };
        closed += close_requested(views);
        let live = views.len();
        let pending_messages: usize = views.iter().map(|view| view.queue.len()).sum();
        let dropped_messages: u64 = views
            .iter()
            .map(|view| view.queue.get_metrics_snapshot().messages_dropped)
            .sum();
        let pending_native = gtk::events_pending();
        if SHUTDOWN.with(Cell::get) {
            self.closed.set(true);
            finish_shutdown();
        }
        drop(lease); // Restore ownership before publishing a report.
        let report = PyDict::new(py);
        report.set_item("live_views", live)?;
        report.set_item("closed_views", closed)?;
        report.set_item("native_iterations", work.native_iterations)?;
        report.set_item("messages", work.messages)?;
        report.set_item("timed_out_callbacks", timed_out_callbacks)?;
        report.set_item("pending_messages", pending_messages)?;
        report.set_item("dropped_messages", dropped_messages)?;
        report.set_item("pending_native", pending_native)?;
        report.set_item("elapsed_ms", started.elapsed().as_secs_f64() * 1000.0)?;
        Ok(report)
    }

    /// Release every native view before the host unregisters its timer.
    /// False means a current dispatch will finish the deferred destruction.
    fn shutdown(&self) -> bool {
        if self.closed.replace(true) {
            return !SHUTDOWN.with(Cell::get);
        }
        shutdown_views()
    }
}

impl Drop for HostRuntime {
    fn drop(&mut self) {
        if !self.closed.replace(true) {
            shutdown_views();
        }
    }
}
