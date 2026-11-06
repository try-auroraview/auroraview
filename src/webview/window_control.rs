//! Send-safe lifecycle and window command state for a retained window.

use std::collections::VecDeque;
#[cfg(feature = "python-bindings")]
use std::sync::Arc;
use std::sync::{Condvar, Mutex};
use std::time::Duration;

#[cfg(feature = "python-bindings")]
use crate::webview::event_loop::UserEvent;
#[cfg(feature = "python-bindings")]
use pyo3::prelude::*;
#[cfg(feature = "python-bindings")]
use tao::event_loop::EventLoopProxy;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WindowState {
    New,
    Preparing,
    Hidden,
    Visible,
    Closing,
    Closed,
    Failed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Intent {
    pub seq: u64,
    pub visible: bool,
    pub focus: bool,
    pub close: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum WindowCommand {
    Center,
    Move(i32, i32),
    Resize(u32, u32),
    Minimize,
    Maximize,
    Unmaximize,
    ToggleMaximize,
    Restore,
    SetFullscreen(bool),
    ToggleFullscreen,
    SetTitle(String),
    SetAlwaysOnTop(bool),
    SetResizable(bool),
    SetDecorations(bool),
    SetMinSize(u32, u32),
    SetMaxSize(u32, u32),
    Focus,
}

impl WindowCommand {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Center => "center",
            Self::Move(..) => "set_position",
            Self::Resize(..) => "set_size",
            Self::Minimize => "minimize",
            Self::Maximize => "maximize",
            Self::Unmaximize => "unmaximize",
            Self::ToggleMaximize => "toggle_maximize",
            Self::Restore => "restore",
            Self::SetFullscreen(..) => "set_fullscreen",
            Self::ToggleFullscreen => "toggle_fullscreen",
            Self::SetTitle(..) => "set_title",
            Self::SetAlwaysOnTop(..) => "set_always_on_top",
            Self::SetResizable(..) => "set_resizable",
            Self::SetDecorations(..) => "set_decorations",
            Self::SetMinSize(..) => "set_min_size",
            Self::SetMaxSize(..) => "set_max_size",
            Self::Focus => "focus",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct QueuedCommand {
    pub seq: u64,
    pub operation: WindowCommand,
}

#[derive(Clone, Debug, Default)]
pub struct WindowSnapshot {
    pub version: u64,
    pub hwnd: Option<u64>,
    pub title: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub outer_width: u32,
    pub outer_height: u32,
    pub visible: bool,
    pub focused: bool,
    pub minimized: bool,
    pub maximized: bool,
    pub fullscreen: bool,
}

struct Data {
    state: WindowState,
    next_seq: u64,
    intent: Intent,
    applied_seq: u64,
    queue: VecDeque<QueuedCommand>,
    cancelled: VecDeque<QueuedCommand>,
    visibility_transitions: VecDeque<bool>,
    snapshot: Option<WindowSnapshot>,
    startup_error: Option<String>,
    native_released: bool,
    owner_returned: bool,
    host_cleaned: bool,
    active_callbacks: usize,
}

pub struct WindowControl {
    data: Mutex<Data>,
    completed: Condvar,
    capacity: usize,
}

/// An admitted business callback. Closing prevents new guards but does not
/// invalidate a callback which has already entered user code.
#[cfg(feature = "python-bindings")]
pub(crate) struct CallbackFlight(Arc<WindowControl>);

#[cfg(feature = "python-bindings")]
impl Drop for CallbackFlight {
    fn drop(&mut self) {
        let mut data = self.0.data.lock().unwrap();
        data.active_callbacks -= 1;
        self.0.finish(&mut data);
        self.0.completed.notify_all();
    }
}

#[cfg(feature = "python-bindings")]
#[pyclass(name = "RetainedCallbackGuard")]
pub struct RetainedCallbackGuard {
    flight: Option<CallbackFlight>,
}

#[cfg(feature = "python-bindings")]
#[pymethods]
impl RetainedCallbackGuard {
    fn finish(&mut self) {
        self.flight.take();
    }
}

/// Python-facing handle containing only state safe to access from host threads.
#[cfg(feature = "python-bindings")]
pub(crate) struct RetainedShared {
    pub control: std::sync::Arc<WindowControl>,
    wake: Mutex<Option<EventLoopProxy<UserEvent>>>,
    native_events: Mutex<Vec<&'static str>>,
    window_id: Mutex<String>,
    last_created_hwnd: Mutex<Option<u64>>,
    #[cfg(debug_assertions)]
    pub fail_adapter_install: std::sync::atomic::AtomicBool,
    #[cfg(debug_assertions)]
    pub create_delay_ms: std::sync::atomic::AtomicU64,
}

#[cfg(feature = "python-bindings")]
impl RetainedShared {
    #[cfg(target_os = "windows")]
    pub fn note_created_hwnd(&self, hwnd: u64) {
        *self.last_created_hwnd.lock().unwrap() = Some(hwnd);
    }

    #[cfg(target_os = "windows")]
    pub fn note_native_event(&self, event: &'static str) {
        let mut events = self.native_events.lock().unwrap();
        if events.len() == 32 {
            events.remove(0);
        }
        events.push(event);
    }

    pub fn native_events(&self) -> Vec<&'static str> {
        self.native_events.lock().unwrap().clone()
    }

    pub fn window_id(&self) -> String {
        self.window_id.lock().unwrap().clone()
    }

    pub fn install_wake(&self, proxy: EventLoopProxy<UserEvent>) {
        *self.wake.lock().unwrap() = Some(proxy);
    }

    #[cfg(target_os = "windows")]
    pub fn clear_wake(&self) {
        *self.wake.lock().unwrap() = None;
    }

    pub fn signal(&self) -> Result<(), String> {
        let proxy = self.wake.lock().unwrap().clone();
        if let Some(proxy) = proxy {
            proxy
                .send_event(UserEvent::ProcessMessages)
                .map_err(|_| "retained window owner is unavailable".to_string())?;
        }
        Ok(())
    }
}

#[cfg(feature = "python-bindings")]
#[pyclass(name = "RetainedControl")]
pub struct RetainedControl {
    pub(crate) shared: std::sync::Arc<RetainedShared>,
}

#[cfg(feature = "python-bindings")]
#[pymethods]
impl RetainedControl {
    #[new]
    fn new() -> Self {
        Self {
            shared: std::sync::Arc::new(RetainedShared {
                control: std::sync::Arc::new(WindowControl::new(10_000)),
                wake: Mutex::new(None),
                native_events: Mutex::new(Vec::new()),
                window_id: Mutex::new(String::new()),
                last_created_hwnd: Mutex::new(None),
                #[cfg(debug_assertions)]
                fail_adapter_install: std::sync::atomic::AtomicBool::new(false),
                #[cfg(debug_assertions)]
                create_delay_ms: std::sync::atomic::AtomicU64::new(0),
            }),
        }
    }

    fn prepare(&self) -> PyResult<()> {
        self.shared
            .control
            .prepare()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    #[pyo3(signature = (focus=true))]
    fn show(&self, focus: bool) -> PyResult<()> {
        self.shared
            .control
            .show(focus)
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        self.shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn hide(&self) -> PyResult<()> {
        self.shared.control.hide();
        self.shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn close(&self) -> PyResult<()> {
        self.shared.control.close();
        self.shared
            .signal()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)
    }

    fn host_cleaned(&self) {
        self.shared.control.host_cleaned();
    }

    fn fail(&self, message: String) {
        self.shared.control.fail(message);
    }

    fn native_skipped(&self) {
        self.shared.control.native_released();
    }

    fn owner_returned(&self) {
        self.shared.control.owner_returned();
    }

    fn native_done(&self, py: Python<'_>, timeout: f64) -> PyResult<bool> {
        if !timeout.is_finite() || timeout < 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "timeout must be finite and non-negative",
            ));
        }
        let control = self.shared.control.clone();
        Ok(py.detach(move || control.wait_native(Duration::from_secs_f64(timeout))))
    }

    fn wait(&self, py: Python<'_>, timeout: f64) -> PyResult<bool> {
        if !timeout.is_finite() || timeout < 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "timeout must be finite and non-negative",
            ));
        }
        let control = self.shared.control.clone();
        Ok(py.detach(move || control.wait(Duration::from_secs_f64(timeout))))
    }

    #[getter]
    fn state(&self) -> &'static str {
        match self.shared.control.state() {
            WindowState::New => "new",
            WindowState::Preparing => "preparing",
            WindowState::Hidden => "hidden",
            WindowState::Visible => "visible",
            WindowState::Closing => "closing",
            WindowState::Closed => "closed",
            WindowState::Failed => "failed",
        }
    }

    #[getter]
    fn startup_error(&self) -> Option<String> {
        self.shared.control.startup_error()
    }

    fn get_hwnd(&self) -> Option<u64> {
        self.shared.control.hwnd()
    }

    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        use pyo3::types::PyDict;
        let value = self
            .shared
            .control
            .snapshot()
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        let result = PyDict::new(py);
        result.set_item("version", value.version)?;
        result.set_item("hwnd", value.hwnd)?;
        result.set_item("title", value.title)?;
        result.set_item("x", value.x)?;
        result.set_item("y", value.y)?;
        result.set_item("width", value.width)?;
        result.set_item("height", value.height)?;
        result.set_item("outer_width", value.outer_width)?;
        result.set_item("outer_height", value.outer_height)?;
        result.set_item("visible", value.visible)?;
        result.set_item("focused", value.focused)?;
        result.set_item("minimized", value.minimized)?;
        result.set_item("maximized", value.maximized)?;
        result.set_item("fullscreen", value.fullscreen)?;
        Ok(result.into_any().unbind())
    }

    fn take_visibility_transitions(&self) -> Vec<bool> {
        self.shared.control.take_visibility_transitions()
    }

    fn completion_status(&self) -> (bool, bool, bool) {
        self.shared.control.completion_status()
    }

    fn active_callbacks(&self) -> usize {
        self.shared.control.active_callbacks()
    }

    fn take_cancelled(&self) -> Vec<(u64, &'static str)> {
        self.shared
            .control
            .take_cancelled()
            .into_iter()
            .map(|command| (command.seq, command.operation.name()))
            .collect()
    }

    fn begin_callback(&self) -> Option<RetainedCallbackGuard> {
        self.shared
            .control
            .begin_callback()
            .map(|flight| RetainedCallbackGuard {
                flight: Some(flight),
            })
    }

    fn native_events(&self) -> Vec<&'static str> {
        self.shared.native_events()
    }

    fn set_window_id(&self, window_id: String) {
        *self.shared.window_id.lock().unwrap() = window_id;
    }

    fn last_created_hwnd(&self) -> Option<u64> {
        *self.shared.last_created_hwnd.lock().unwrap()
    }

    #[cfg(debug_assertions)]
    fn fail_adapter_install_once(&self) {
        self.shared
            .fail_adapter_install
            .store(true, std::sync::atomic::Ordering::SeqCst);
    }

    #[cfg(debug_assertions)]
    fn delay_native_create_once(&self, milliseconds: u64) {
        self.shared
            .create_delay_ms
            .store(milliseconds, std::sync::atomic::Ordering::SeqCst);
    }
}

impl WindowControl {
    pub fn new(capacity: usize) -> Self {
        Self {
            data: Mutex::new(Data {
                state: WindowState::New,
                next_seq: 0,
                intent: Intent {
                    seq: 0,
                    visible: false,
                    focus: false,
                    close: false,
                },
                applied_seq: 0,
                queue: VecDeque::new(),
                cancelled: VecDeque::new(),
                visibility_transitions: VecDeque::new(),
                snapshot: None,
                startup_error: None,
                native_released: false,
                owner_returned: false,
                host_cleaned: false,
                active_callbacks: 0,
            }),
            completed: Condvar::new(),
            capacity,
        }
    }

    pub fn prepare(&self) -> Result<(), String> {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return Err("retained window is closing".into());
        }
        if data.state == WindowState::New {
            data.state = WindowState::Preparing;
        }
        Ok(())
    }

    pub fn show(&self, focus: bool) -> Result<u64, String> {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return Err("retained window is closing".into());
        }
        if data.state == WindowState::New {
            data.state = WindowState::Preparing;
        }
        data.next_seq += 1;
        data.intent.seq = data.next_seq;
        data.intent.visible = true;
        data.intent.focus = focus;
        Ok(data.intent.seq)
    }

    pub fn hide(&self) -> u64 {
        let mut data = self.data.lock().unwrap();
        if data.intent.close || data.state == WindowState::New {
            return data.intent.seq;
        }
        data.next_seq += 1;
        data.intent.seq = data.next_seq;
        data.intent.visible = false;
        data.intent.focus = false;
        data.intent.seq
    }

    pub fn close(&self) -> u64 {
        let mut data = self.data.lock().unwrap();
        if !data.intent.close {
            data.next_seq += 1;
            data.intent.seq = data.next_seq;
            data.intent.close = true;
            data.intent.visible = false;
            data.intent.focus = false;
            data.state = WindowState::Closing;
            let pending = std::mem::take(&mut data.queue);
            data.cancelled.extend(pending);
        }
        data.intent.seq
    }

    #[cfg(feature = "python-bindings")]
    pub(crate) fn begin_callback(self: &Arc<Self>) -> Option<CallbackFlight> {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return None;
        }
        data.active_callbacks += 1;
        Some(CallbackFlight(self.clone()))
    }

    pub fn active_callbacks(&self) -> usize {
        self.data.lock().unwrap().active_callbacks
    }

    pub fn enqueue(&self, operation: WindowCommand) -> Result<u64, String> {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return Err("retained window is closing".into());
        }
        if data.snapshot.is_none() {
            return Err("retained window is not ready".into());
        }
        if data.queue.len() >= self.capacity {
            return Err("retained window command queue is full".into());
        }
        data.next_seq += 1;
        let seq = data.next_seq;
        data.queue.push_back(QueuedCommand { seq, operation });
        Ok(seq)
    }

    pub fn take_commands(&self, limit: usize) -> Vec<QueuedCommand> {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return Vec::new();
        }
        (0..limit).filter_map(|_| data.queue.pop_front()).collect()
    }

    pub fn cancel_dequeued(&self, commands: impl IntoIterator<Item = QueuedCommand>) {
        self.data.lock().unwrap().cancelled.extend(commands);
    }

    pub fn take_cancelled(&self) -> Vec<QueuedCommand> {
        let mut commands: Vec<_> = self.data.lock().unwrap().cancelled.drain(..).collect();
        commands.sort_by_key(|command| command.seq);
        commands
    }

    pub fn intent(&self) -> Intent {
        self.data.lock().unwrap().intent
    }

    pub fn applied_seq(&self) -> u64 {
        self.data.lock().unwrap().applied_seq
    }

    pub fn ready(&self, snapshot: WindowSnapshot) -> bool {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return false;
        }
        data.state = if snapshot.visible {
            WindowState::Visible
        } else {
            WindowState::Hidden
        };
        data.snapshot = Some(snapshot);
        true
    }

    pub fn confirm(&self, seq: u64, snapshot: WindowSnapshot) {
        let mut data = self.data.lock().unwrap();
        if data.intent.close {
            return;
        }
        if data
            .snapshot
            .as_ref()
            .is_some_and(|old| old.visible != snapshot.visible)
        {
            data.visibility_transitions.push_back(snapshot.visible);
        }
        data.applied_seq = seq;
        data.state = if snapshot.visible {
            WindowState::Visible
        } else {
            WindowState::Hidden
        };
        data.snapshot = Some(snapshot);
    }

    pub fn update_snapshot(&self, snapshot: WindowSnapshot) {
        let mut data = self.data.lock().unwrap();
        if !data.intent.close {
            if data
                .snapshot
                .as_ref()
                .is_some_and(|old| old.visible != snapshot.visible)
            {
                data.visibility_transitions.push_back(snapshot.visible);
            }
            data.state = if snapshot.visible {
                WindowState::Visible
            } else {
                WindowState::Hidden
            };
            data.snapshot = Some(snapshot);
        }
    }

    pub fn take_visibility_transitions(&self) -> Vec<bool> {
        self.data
            .lock()
            .unwrap()
            .visibility_transitions
            .drain(..)
            .collect()
    }

    pub fn snapshot(&self) -> Result<WindowSnapshot, String> {
        self.data
            .lock()
            .unwrap()
            .snapshot
            .clone()
            .ok_or_else(|| "retained window is not ready".into())
    }

    pub fn hwnd(&self) -> Option<u64> {
        self.data
            .lock()
            .unwrap()
            .snapshot
            .as_ref()
            .and_then(|s| s.hwnd)
    }

    pub fn state(&self) -> WindowState {
        self.data.lock().unwrap().state
    }

    pub fn fail(&self, error: String) {
        let mut data = self.data.lock().unwrap();
        data.startup_error = Some(error);
        data.intent.close = true;
        data.state = WindowState::Closing;
    }

    pub fn startup_error(&self) -> Option<String> {
        self.data.lock().unwrap().startup_error.clone()
    }

    pub fn native_released(&self) {
        let mut data = self.data.lock().unwrap();
        data.native_released = true;
        data.snapshot = None;
        self.completed.notify_all();
        self.finish(&mut data);
    }

    pub fn owner_returned(&self) {
        let mut data = self.data.lock().unwrap();
        data.owner_returned = true;
        self.completed.notify_all();
        self.finish(&mut data);
    }

    pub fn host_cleaned(&self) {
        let mut data = self.data.lock().unwrap();
        data.host_cleaned = true;
        self.finish(&mut data);
    }

    fn finish(&self, data: &mut Data) {
        if data.native_released
            && data.owner_returned
            && data.host_cleaned
            && data.active_callbacks == 0
        {
            data.state = if data.startup_error.is_some() {
                WindowState::Failed
            } else {
                WindowState::Closed
            };
            self.completed.notify_all();
        }
    }

    pub fn wait(&self, timeout: Duration) -> bool {
        let data = self.data.lock().unwrap();
        let (data, _) = self
            .completed
            .wait_timeout_while(data, timeout, |data| {
                !matches!(data.state, WindowState::Closed | WindowState::Failed)
            })
            .unwrap();
        matches!(data.state, WindowState::Closed | WindowState::Failed)
    }

    pub fn wait_native(&self, timeout: Duration) -> bool {
        let data = self.data.lock().unwrap();
        let (data, _) = self
            .completed
            .wait_timeout_while(data, timeout, |data| {
                !data.native_released || !data.owner_returned
            })
            .unwrap();
        data.native_released && data.owner_returned
    }

    pub fn completion_status(&self) -> (bool, bool, bool) {
        let data = self.data.lock().unwrap();
        (data.native_released, data.owner_returned, data.host_cleaned)
    }
}
