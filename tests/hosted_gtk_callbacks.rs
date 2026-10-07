//! Python ownership/queue tests only: no GTK/WebKit/bpy/native acceptance.
#![cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]

use _core::ipc::{
    IpcHandler, IpcMessage, JsCallbackManager, MessageQueue, MessageQueueConfig, WebViewMessage,
};
use _core::webview::WebViewProxy;
use pyo3::prelude::*;
use pyo3::types::{PyList, PyModule};
use rstest::rstest;
use std::sync::Arc;

#[pyclass]
struct Reentry {
    manager: Arc<JsCallbackManager>,
    ipc: Arc<IpcHandler>,
}

#[pymethods]
impl Reentry {
    fn inspect(&self, py: Python<'_>) -> (usize, usize, bool) {
        let registered = self.manager.register_callback(999, py.None());
        self.ipc.register_python_callback("late", py.None());
        (
            self.manager.pending_count(),
            self.ipc.registered_event_count(),
            registered,
        )
    }
}

#[rstest]
#[case("manager")]
#[case("ipc")]
#[case("both")]
fn finalizer_reentry_observes_closed_admission_without_locks(#[case] owner: &str) {
    Python::attach(|py| {
        let manager = Arc::new(JsCallbackManager::new());
        let ipc = Arc::new(IpcHandler::new());
        let queue = Arc::new(MessageQueue::new());
        let proxy = Py::new(py, WebViewProxy::new(queue, manager.clone())).unwrap();
        let hook = Py::new(
            py,
            Reentry {
                manager: manager.clone(),
                ipc: ipc.clone(),
            },
        )
        .unwrap();
        let seen = PyList::empty(py);
        let module = PyModule::from_code(
            py,
            c"
def make(proxy, hook, seen):
    class Callback:
        def __call__(self, *args):
            pass
        def __del__(self):
            seen.append((repr(proxy), hook.inspect()))
    return Callback()
",
            c"finalizer.py",
            c"finalizer",
        )
        .unwrap();
        let callback = module
            .getattr("make")
            .unwrap()
            .call1((proxy, hook, &seen))
            .unwrap()
            .unbind();
        if owner != "manager" {
            ipc.register_python_callback("event", callback.clone_ref(py));
        }
        if owner != "ipc" {
            assert!(manager.register_callback(1, callback.clone_ref(py)));
        }
        drop(callback);
        // Close every gate before a finalizer can attempt to re-register.
        manager.close_admission();
        ipc.close_admission();
        manager.cancel_all_hosted();
        ipc.shutdown_hosted();
        assert_eq!(seen.len(), 1);
        let item: (String, (usize, usize, bool)) = seen.get_item(0).unwrap().extract().unwrap();
        assert!(item.0.contains("pending_callbacks=0"));
        assert_eq!(item.1, (0, 0, false));
    });
}

#[rstest]
fn rejected_async_admission_rolls_back_callback_ownership() {
    Python::attach(|py| {
        let manager = JsCallbackManager::new();
        let queue = MessageQueue::with_config(MessageQueueConfig {
            capacity: 1,
            ..Default::default()
        });
        queue.begin_hosted().unwrap();
        queue.push(WebViewMessage::EvalJs("fill".into()));
        assert!(manager
            .enqueue_callback(&queue, "2".into(), 1, py.None(), 5000)
            .is_err());
        assert_eq!(manager.pending_count(), 0);
        queue.finish_hosted();
        assert!(manager
            .enqueue_callback(&queue, "3".into(), 2, py.None(), 5000)
            .is_err());
        assert_eq!(manager.pending_count(), 0);
    });
}

#[rstest]
fn cached_proxy_rejects_after_shutdown_and_does_not_retain_callbacks() {
    Python::attach(|py| {
        let manager = Arc::new(JsCallbackManager::new());
        let queue = Arc::new(MessageQueue::new());
        queue.begin_hosted().unwrap();
        let proxy = Py::new(py, WebViewProxy::new(queue.clone(), manager.clone())).unwrap();
        queue.finish_hosted();
        manager.cancel_all_hosted();
        assert!(proxy
            .call_method1(py, "eval_js_async", ("1", py.None(), 1))
            .is_err());
        assert_eq!(manager.pending_count(), 0);
    });
}

#[rstest]
fn bounded_timeouts_rotate_past_unexpired_entries_on_owner_thread() {
    Python::attach(|py| {
        let manager = JsCallbackManager::new();
        let seen = PyList::empty(py);
        // Python callback accepts two arguments; record both and owner thread.
        let module = PyModule::from_code(py, c"import threading\ndef make(seen):\n    return lambda result, error: seen.append((result, error, threading.get_ident()))\n", c"timeout.py", c"timeout").unwrap();
        let callback = module
            .getattr("make")
            .unwrap()
            .call1((&seen,))
            .unwrap()
            .unbind();
        assert!(manager.register_callback_with_timeout(1, callback.clone_ref(py), u64::MAX));
        for id in 2..=5 {
            assert!(manager.register_callback_with_timeout(id, callback.clone_ref(py), 0));
        }
        assert_eq!(manager.cleanup_timed_out_bounded(1), 0);
        for _ in 0..4 {
            assert_eq!(manager.cleanup_timed_out_bounded(1), 1);
        }
        assert_eq!(seen.len(), 4);
        let owner: u64 = py
            .import("threading")
            .unwrap()
            .call_method0("get_ident")
            .unwrap()
            .extract()
            .unwrap();
        for item in seen.iter() {
            let (_, error, thread): (Py<PyAny>, String, u64) = item.extract().unwrap();
            assert!(error.contains("timed out"));
            assert_eq!(thread, owner);
        }
        manager.cancel_all_hosted();
    });
}

#[rstest]
fn rust_ipc_callback_may_clear_its_own_registration() {
    let ipc = Arc::new(IpcHandler::new());
    let weak = Arc::downgrade(&ipc);
    ipc.on("self-clear", move |_| {
        weak.upgrade().unwrap().clear();
        Ok(serde_json::json!(true))
    });
    assert!(ipc
        .handle_message(IpcMessage {
            event: "self-clear".into(),
            data: serde_json::Value::Null,
            id: None
        })
        .is_ok());
    assert_eq!(ipc.registered_event_count(), 0);
}

#[rstest]
fn existing_callback_wire_settles_the_shared_manager() {
    Python::attach(|py| {
        let manager = Arc::new(JsCallbackManager::new());
        let mut ipc = IpcHandler::new();
        ipc.set_js_callback_manager(manager.clone());
        let seen = PyList::empty(py);
        let module = PyModule::from_code(
            py,
            c"def make(seen):\n    return lambda value, error: seen.append((value, error))\n",
            c"wire.py",
            c"wire",
        )
        .unwrap();
        let callback = module
            .getattr("make")
            .unwrap()
            .call1((&seen,))
            .unwrap()
            .unbind();
        assert!(manager.register_callback(42, callback));
        let response = ipc.handle_message(IpcMessage {
            event: "__js_callback_result__".into(),
            data: serde_json::json!({ "callback_id": 42, "result": 42, "error": null }),
            id: None,
        });
        assert!(response.is_ok());
        assert_eq!(manager.pending_count(), 0);
        let result: (u64, Option<String>) = seen.get_item(0).unwrap().extract().unwrap();
        assert_eq!(result, (42, None));
    });
}

#[rstest]
fn timeout_close_intent_preempts_later_notifications() {
    Python::attach(|py| {
        let manager = Arc::new(JsCallbackManager::new());
        let queue = Arc::new(MessageQueue::new());
        queue.begin_hosted().unwrap();
        let proxy = Py::new(py, WebViewProxy::new(queue.clone(), manager.clone())).unwrap();
        let seen = PyList::empty(py);
        let module = PyModule::from_code(py,
            c"def make(proxy, seen):\n    def callback(value, error):\n        seen.append(error)\n        proxy.close()\n    return callback\n",
            c"timeout_close.py", c"timeout_close").unwrap();
        let callback = module
            .getattr("make")
            .unwrap()
            .call1((proxy, &seen))
            .unwrap()
            .unbind();
        for id in 1..=5 {
            assert!(manager.register_callback_with_timeout(id, callback.clone_ref(py), 0));
        }
        manager.cleanup_timed_out_while(8, || queue.hosted_state() == 1);
        assert_eq!(seen.len(), 1);
        assert_eq!(queue.hosted_state(), 2);
        assert_eq!(manager.pending_count(), 0);
    });
}

#[rstest]
fn expired_old_callback_is_not_starved_by_eight_arrivals_per_poll() {
    Python::attach(|py| {
        let manager = JsCallbackManager::new();
        let seen = PyList::empty(py);
        let module = PyModule::from_code(
            py,
            c"
class Callback:
    def __init__(self, seen, label):
        self.seen = seen
        self.label = label
    def __call__(self, value, error):
        self.seen.append((self.label, error))
",
            c"timeout_arrivals.py",
            c"timeout_arrivals",
        )
        .unwrap();
        let callback = module
            .getattr("Callback")
            .unwrap()
            .call1((&seen, "old"))
            .unwrap();
        let weak = py
            .import("weakref")
            .unwrap()
            .getattr("ref")
            .unwrap()
            .call1((&callback,))
            .unwrap();
        let arrival = module
            .getattr("Callback")
            .unwrap()
            .call1((&seen, "new"))
            .unwrap()
            .unbind();
        assert!(manager.register_callback_with_timeout(1, callback.unbind(), 250));
        // The first inspection must see this exact callback while it is alive
        // and unexpired. It expires only after the cursor has passed its ID.
        assert_eq!(manager.cleanup_timed_out_bounded(8), 0);
        assert!(!weak.call0().unwrap().is_none());
        std::thread::sleep(std::time::Duration::from_millis(300));
        for poll in 0..16 {
            let first = 2 + poll * 8;
            for id in first..first + 8 {
                assert!(manager.register_callback_with_timeout(id, arrival.clone_ref(py), 0));
            }
            assert!(manager.cleanup_timed_out_bounded(8) <= 8);
            // Model short-lived arrivals, keeping the map bounded even with the
            // former moving-end algorithm, which never revisits callback 1.
            for id in first..first + 8 {
                manager.cancel_callback(id);
            }
            assert!(manager.pending_count() <= 1);
        }
        assert_eq!(manager.pending_count(), 0);
        assert!(weak.call0().unwrap().is_none());
        let entries: Vec<(String, String)> = seen.extract().unwrap();
        assert_eq!(
            entries.iter().filter(|(label, _)| label == "old").count(),
            1
        );
        assert!(entries.iter().all(|(_, error)| error.contains("timed out")));
    });
}

#[rstest]
fn bounded_timeout_sweep_handles_removed_high_water_and_zero_id() {
    Python::attach(|py| {
        let manager = JsCallbackManager::new();
        let module = PyModule::from_code(
            py,
            c"def callback(value, error): pass\n",
            c"timeout_boundary.py",
            c"timeout_boundary",
        )
        .unwrap();
        let callback = module.getattr("callback").unwrap().unbind();
        for id in 0..=3 {
            assert!(manager.register_callback_with_timeout(id, callback.clone_ref(py), 0));
        }
        assert_eq!(manager.cleanup_timed_out_bounded(0), 0);
        assert_eq!(manager.pending_count(), 4);
        assert_eq!(manager.cleanup_timed_out_bounded(1), 1); // Includes ID zero.
        manager.cancel_callback(3); // Remove this sweep's high-water entry.
        assert_eq!(manager.cleanup_timed_out_bounded(8), 2);
        assert!(manager.register_callback_with_timeout(4, callback, 0));
        assert_eq!(manager.cleanup_timed_out_bounded(1), 1);
        assert_eq!(manager.pending_count(), 0);
    });
}

#[rstest]
fn cached_proxy_navigation_returns_an_error_without_changing_the_document() {
    Python::attach(|py| {
        let queue = Arc::new(MessageQueue::new());
        let manager = Arc::new(JsCallbackManager::new());
        let proxy = Py::new(py, WebViewProxy::new(queue.clone(), manager)).unwrap();
        queue.begin_hosted().unwrap();
        assert!(queue.hosted_document_started(true));
        for (method, argument) in [("load_url", "about:blank"), ("load_html", "<p>new</p>")] {
            let error = proxy.call_method1(py, method, (argument,)).unwrap_err();
            assert!(error.to_string().contains("single-document"));
        }
        assert!(proxy
            .call_method0(py, "reload")
            .unwrap_err()
            .to_string()
            .contains("single-document"));
        assert!(queue.is_empty());
        assert!(queue.hosted_ipc_allowed());
    });
}

#[rstest]
fn cached_callback_gate_covers_bootstrap_close_intent_and_shutdown() {
    Python::attach(|py| {
        let queue = Arc::new(MessageQueue::new());
        let manager = Arc::new(JsCallbackManager::new());
        let proxy = Py::new(py, WebViewProxy::new(queue.clone(), manager)).unwrap();
        let allowed = || {
            proxy
                .call_method0(py, "callbacks_allowed")
                .unwrap()
                .extract::<bool>(py)
                .unwrap()
        };
        assert!(allowed()); // Non-hosted open queue.
        queue.begin_hosted().unwrap();
        assert!(!allowed()); // No hosted document admission before initial commit.
        assert!(queue.hosted_document_started(true));
        assert!(allowed());
        queue.push(WebViewMessage::Close);
        assert!(!queue.is_shutdown()); // Close intent is earlier than shutdown.
        assert!(!allowed());
        queue.finish_hosted();
        assert!(!allowed());
    });
}

#[rstest]
#[case("manager")]
#[case("ipc")]
#[case("both")]
fn native_owned_finalizer_can_query_the_cached_gate_before_python_reap(#[case] owner: &str) {
    Python::attach(|py| {
        let queue = Arc::new(MessageQueue::new());
        let manager = Arc::new(JsCallbackManager::new());
        let ipc = Arc::new(IpcHandler::new());
        let proxy = Py::new(py, WebViewProxy::new(queue.clone(), manager.clone())).unwrap();
        queue.begin_hosted().unwrap();
        assert!(queue.hosted_document_started(true));
        let seen = PyList::empty(py);
        let module = PyModule::from_code(
            py,
            c"
def make(proxy, seen):
    class Callback:
        def __call__(self, *args):
            seen.append('unexpected invocation')
        def __del__(self):
            seen.append(proxy.callbacks_allowed())
    return Callback()
",
            c"admission_finalizer.py",
            c"admission_finalizer",
        )
        .unwrap();
        let callback = module
            .getattr("make")
            .unwrap()
            .call1((proxy, &seen))
            .unwrap();
        let weak = py
            .import("weakref")
            .unwrap()
            .getattr("ref")
            .unwrap()
            .call1((&callback,))
            .unwrap();
        let callback = callback.unbind();
        if owner != "ipc" {
            manager
                .enqueue_callback(&queue, "42".into(), 1, callback.clone_ref(py), 5000)
                .unwrap();
        }
        if owner != "manager" {
            ipc.register_python_callback("event", callback.clone_ref(py));
        }
        drop(callback);
        queue.push(WebViewMessage::Close);
        // Actual Rust ownership-release order, without GTK or Python HostRuntime.
        queue.shutdown();
        manager.close_admission();
        ipc.close_admission();
        manager.cancel_all_hosted();
        ipc.shutdown_hosted();
        queue.finish_hosted();
        assert!(weak.call0().unwrap().is_none());
        assert_eq!(seen.len(), 1);
        assert!(!seen.get_item(0).unwrap().extract::<bool>().unwrap());
        assert_eq!(manager.pending_count(), 0);
        assert!(queue.is_empty());
    });
}
