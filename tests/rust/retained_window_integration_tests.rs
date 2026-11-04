use _core::ipc::js_callback::{JsCallbackManager, JsCallbackResult};
use _core::ipc::{IpcHandler, IpcMessage};
use _core::webview::window_control::{WindowCommand, WindowControl, WindowSnapshot, WindowState};
use pyo3::types::{PyAnyMethods, PyListMethods};
use rstest::rstest;
use std::sync::mpsc;
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc, Mutex,
};

#[rstest]
fn last_visibility_request_wins_without_inheriting_focus() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.show(true).unwrap();
    control.hide();
    control.show(false).unwrap();
    let intent = control.intent();
    assert!(intent.visible);
    assert!(!intent.focus);
    assert_eq!(control.state(), WindowState::Preparing);
}

#[rstest]
fn destroy_preempts_visibility_and_commands() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    control.enqueue(WindowCommand::ToggleMaximize).unwrap();
    control.close();
    assert!(control.show(true).is_err());
    assert!(control.enqueue(WindowCommand::Center).is_err());
    assert!(control.take_commands(2).is_empty());
    let cancelled = control.take_cancelled();
    assert_eq!(cancelled.len(), 1);
    assert_eq!(cancelled[0].operation.name(), "toggle_maximize");
    assert!(control.take_cancelled().is_empty());
    assert_eq!(control.state(), WindowState::Closing);
}

#[rstest]
fn bounded_commands_remain_fifo_and_reject_full_queue() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    control.enqueue(WindowCommand::ToggleMaximize).unwrap();
    control.enqueue(WindowCommand::Center).unwrap();
    assert!(control.enqueue(WindowCommand::ToggleMaximize).is_err());
    let commands = control.take_commands(2);
    assert_eq!(commands.len(), 2);
    assert!(matches!(
        commands[0].operation,
        WindowCommand::ToggleMaximize
    ));
    assert!(matches!(commands[1].operation, WindowCommand::Center));
}

#[rstest]
fn cancelled_commands_keep_original_sequence_across_dequeued_and_pending() {
    let control = WindowControl::new(3);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    let first = control.enqueue(WindowCommand::Center).unwrap();
    let second = control
        .enqueue(WindowCommand::SetTitle("later".into()))
        .unwrap();
    let dequeued = control.take_commands(1);
    control.close();
    control.cancel_dequeued(dequeued);
    let cancelled = control.take_cancelled();
    assert_eq!(
        cancelled
            .iter()
            .map(|command| command.seq)
            .collect::<Vec<_>>(),
        vec![first, second]
    );
    assert_eq!(cancelled[0].operation.name(), "center");
    assert_eq!(cancelled[1].operation.name(), "set_title");
}

#[rstest]
fn completion_requires_native_owner_and_host_cleanup() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    control.close();
    control.native_released();
    control.owner_returned();
    assert!(!control.wait(std::time::Duration::ZERO));
    control.host_cleaned();
    assert!(control.wait(std::time::Duration::ZERO));
    assert_eq!(control.state(), WindowState::Closed);
    assert_eq!(control.hwnd(), None);
}

#[rstest]
fn business_ipc_rejects_new_work_after_close() {
    let control = Arc::new(WindowControl::new(2));
    let handler = IpcHandler::new();
    handler.set_retained_control(control.clone()).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = calls.clone();
    handler.on("business", move |_| {
        observed.fetch_add(1, Ordering::SeqCst);
        Ok(serde_json::json!({"ok": true}))
    });
    let message = IpcMessage {
        event: "business".into(),
        data: serde_json::json!({}),
        id: None,
    };
    handler.handle_message(message.clone()).unwrap();
    control.close();
    assert!(handler
        .handle_message(message)
        .unwrap_err()
        .contains("closing"));
    assert_eq!(calls.load(Ordering::SeqCst), 1);
}

#[rstest]
fn closing_keeps_an_entered_callback_in_flight_until_it_returns() {
    let control = Arc::new(WindowControl::new(2));
    let handler = Arc::new(IpcHandler::new());
    handler.set_retained_control(control.clone()).unwrap();
    let (entered_tx, entered_rx) = mpsc::channel();
    let (release_tx, release_rx) = mpsc::channel();
    let release_rx = Mutex::new(release_rx);
    handler.on("business", move |_| {
        entered_tx.send(()).unwrap();
        release_rx.lock().unwrap().recv().unwrap();
        Ok(serde_json::json!({"ok": true}))
    });
    let message = IpcMessage {
        event: "business".into(),
        data: serde_json::json!({}),
        id: None,
    };
    let worker = std::thread::spawn({
        let handler = handler.clone();
        let message = message.clone();
        move || handler.handle_message(message)
    });
    entered_rx.recv().unwrap();
    assert_eq!(control.active_callbacks(), 1);
    control.close();
    assert!(handler
        .handle_message(message)
        .unwrap_err()
        .contains("closing"));
    assert_eq!(control.active_callbacks(), 1);
    control.native_released();
    control.owner_returned();
    control.host_cleaned();
    assert!(!control.wait(std::time::Duration::ZERO));
    release_tx.send(()).unwrap();
    worker.join().unwrap().unwrap();
    assert_eq!(control.active_callbacks(), 0);
    assert!(control.wait(std::time::Duration::ZERO));
}

#[rstest]
fn script_result_and_timeout_do_not_enter_python_after_close() {
    let control = Arc::new(WindowControl::new(2));
    let manager = JsCallbackManager::new();
    manager.set_retained_control(control.clone()).unwrap();
    pyo3::Python::attach(|py| {
        let calls = pyo3::types::PyList::empty(py);
        let append = calls.getattr("append").unwrap().unbind();
        manager.register_callback_with_timeout(1, append, 0);
        control.close();
        assert!(manager
            .complete_callback(
                1,
                JsCallbackResult {
                    value: None,
                    error: None
                }
            )
            .is_err());
        assert_eq!(manager.cleanup_timed_out(), 0);
        assert!(calls.is_empty());
        assert_eq!(manager.pending_count(), 0);
    });
}

#[rstest]
fn confirmed_visibility_transitions_are_not_lost_between_host_polls() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    let visible = WindowSnapshot {
        hwnd: Some(17),
        visible: true,
        ..WindowSnapshot::default()
    };
    let hidden = WindowSnapshot {
        hwnd: Some(17),
        visible: false,
        ..WindowSnapshot::default()
    };
    control.confirm(1, visible);
    assert_eq!(control.state(), WindowState::Visible);
    control.confirm(2, hidden);
    assert_eq!(control.state(), WindowState::Hidden);
    assert_eq!(control.take_visibility_transitions(), vec![true, false]);
}

#[rstest]
fn unsolicited_window_event_updates_actual_state_and_hook_transition() {
    let control = WindowControl::new(2);
    control.prepare().unwrap();
    control.ready(WindowSnapshot {
        hwnd: Some(17),
        ..WindowSnapshot::default()
    });
    control.update_snapshot(WindowSnapshot {
        hwnd: Some(17),
        visible: true,
        ..WindowSnapshot::default()
    });
    assert_eq!(control.state(), WindowState::Visible);
    assert_eq!(control.take_visibility_transitions(), vec![true]);
}
