"""Actual Python dispatch/reap contracts with an explicit fake native boundary.

No GTK, WebKit, browser IPC, native generation isolation or bpy proof is claimed.
The Rust queue/policy boundary has its own authored, not-run tests.
"""

import importlib.util
import sys
import threading
import types
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Package shells avoid importing a native extension; all mixin/signal code is real.
for package_name in ("auroraview", "auroraview.core"):
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
signals = load_module("auroraview.core.signals", ROOT / "python/auroraview/core/signals.py")
lifecycle = load_module("candidate_lifecycle", ROOT / "python/auroraview/core/mixins/lifecycle.py")
events = load_module("candidate_events", ROOT / "python/auroraview/core/mixins/events.py")
api = load_module("candidate_api", ROOT / "python/auroraview/core/mixins/api.py")
content = load_module("candidate_content", ROOT / "python/auroraview/core/mixins/content.py")
hosted = load_module("candidate_hosted", ROOT / "python/auroraview/hosted.py")


class FakeProxy:
    """Explicit atomic admission stand-in; no native Core method is queried."""

    def __init__(self, state, results):
        self.state = state
        self.results = results

    def callbacks_allowed(self):
        return self.state[0]

    def close(self):
        self.state[0] = False

    def emit(self, event, payload):
        if self.state[0]:
            self.results.append((event, payload))


class FakeCore:
    def __init__(self, results):
        self.state = [True]
        self.proxy = FakeProxy(self.state, results)
        self._lifecycle_state = "active"
        self.borrowed = False
        self.handlers = {}

    @property
    def lifecycle_state(self):
        if self.borrowed:
            raise AssertionError("Native Core read while already borrowed")
        return self._lifecycle_state

    @lifecycle_state.setter
    def lifecycle_state(self, state):
        self._lifecycle_state = state

    def get_proxy(self):
        if self.borrowed:
            raise AssertionError("Proxy reacquired during native callback release")
        return self.proxy

    def close(self):
        if self.borrowed:
            raise AssertionError("Native Core close while already borrowed")
        self.state[0] = False

    def on(self, name, callback):
        self.handlers[name] = callback


class View(
    lifecycle.WebViewLifecycleMixin,
    api.WebViewApiMixin,
    content.WebViewContentMixin,
    events.WebViewEventMixin,
):
    """Actual request_close, events/signals and API cancellation; no overrides."""

    def __init__(self):
        self._init_api_registry()
        self.results = []
        self.emit_attempts = []
        self._core = FakeCore(self.results)
        self._core_threads = {id(self._core): threading.get_ident()}
        self._core_proxies = {id(self._core): self._core.proxy}
        self._async_core_lock = threading.Lock()
        self._async_core = None
        self._lifecycle_lock = threading.RLock()
        self._event_handlers_lock = threading.Lock()
        self._event_handlers = {}
        self._event_connections = {}
        self._signals = signals.WebViewSignals()
        self._singleton_registry = {}
        self._close_requested = False
        self._is_running = True
        self._show_thread = None
        self._closed_event = threading.Event()
        self._host_runtime = None
        self._stored_url = "old-document"
        self._stored_html = None

    @property
    def closed(self):
        return self._close_requested

    @property
    def observed(self):
        return getattr(self, "_native_close_observed", False)

    def emit(self, event, payload):
        self.emit_attempts.append((event, payload))
        self._check_open()
        self.results.append((event, payload))

    def _teardown_telemetry(self):
        pass

    def _command_target(self):
        raise AssertionError("Rejected navigation must not touch any native owner or proxy")


class FakeNative:
    """Only retirement ordering is modeled; this is not WebKit/GTK execution."""

    def __init__(self, view):
        self.view = view
        self.js_callbacks = []
        self.ipc_callbacks = []

    def poll(self, *args):
        self.view.results.clear()
        core = self.view._core
        core.lifecycle_state = "close_requested"
        core.state[0] = False  # The real queue closes before either native registry drops.
        core.borrowed = True
        try:
            self.js_callbacks.clear()
            self.ipc_callbacks.clear()
        finally:
            core.borrowed = False
        core.lifecycle_state = "destroyed"
        return {"live_views": 0}


class HostedBoundaryTests(unittest.TestCase):
    def runtime(self, view):
        runtime = hosted.HostRuntime.__new__(hosted.HostRuntime)
        runtime._native = FakeNative(view)
        runtime._views = {id(view): view}
        runtime._closed = False
        view._host_runtime = runtime
        view._host_callback_gate = view._core.proxy.callbacks_allowed
        return runtime

    def test_requested_navigation_rejects_before_native_access_or_stored_url_change(self):
        view = View()
        self.runtime(view)
        for method, value in [("load_url", "new-document"), ("load_html", "<p>new</p>")]:
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "single-document"):
                    getattr(view, method)(value)
                self.assertEqual(view._stored_url, "old-document")
                self.assertIsNone(view._stored_html)
        self.assertFalse(view.closed)

    def test_foreign_thread_rejection_never_reaches_native_owner(self):
        view = View()
        self.runtime(view)
        failures = []

        def worker():
            try:
                view.load_url("new-document")
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], RuntimeError)
        self.assertIn("single-document", str(failures[0]))

    def test_running_callback_late_result_is_discarded_after_reap(self):
        view = View()
        runtime = self.runtime(view)
        queue = []
        view.set_call_dispatcher(queue.append)

        def operation():
            runtime.poll()
            return {"must_not_deliver": True}

        handler = view._create_ipc_handler("api.operation", operation)
        handler({"id": "old-call"})
        queue.pop()()
        self.assertTrue(view.closed)
        self.assertEqual(view.results, [])
        self.assertEqual(view._pending_calls, {})

    def test_runtime_poll_refuses_foreign_thread_before_native_access(self):
        view = View()
        runtime = self.runtime(view)
        failures = []

        def worker():
            try:
                runtime.poll()
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIn("main thread", str(failures[0]))
        self.assertEqual(view._core.lifecycle_state, "active")
        self.assertFalse(view.closed)

    def test_python_signal_finalizer_sees_all_gates_closed_and_no_locks(self):
        view = View()
        held = []
        effects = []
        observations = []
        view.set_call_dispatcher(held.append)
        view._create_ipc_handler("api.mutate", lambda: effects.append("api"))({"id": "old"})
        view.register_callback("event", lambda value: effects.append("event"))
        event = view._event_handlers["event"][0]

        class Finalizer:
            def __call__(self):
                pass

            def __del__(self):
                observations.append(
                    (
                        view.closed,
                        view._events_closed,
                        view._calls_closed_reason,
                        view._lifecycle_lock._is_owned(),
                        view._call_lock._is_owned(),
                        view._event_handlers_lock.locked(),
                        view.signals.closed._lock._is_owned(),
                    )
                )
                held[0]()
                event(None)
                view.request_close()  # Reentry must neither deadlock nor reopen admission.

        callback = Finalizer()
        reference = weakref.ref(callback)
        view.signals.closed.connect(callback)
        del callback
        view.request_close()
        self.assertEqual(effects, [])
        self.assertIsNone(reference())
        self.assertEqual(observations, [(True, True, "WebView closed", False, False, False, False)])
        self.assertEqual(
            view.emit_attempts, []
        )  # Cancellation uses captured proxy, not closed emit.
        self.assertEqual(len(view.results), 1)
        self.assertEqual(view.results[0][1]["error"]["name"], "CancelledError")

    def test_native_finalizers_reject_api_events_and_results_before_python_reap(self):
        def check_owner(owner):
            view = View()
            runtime = self.runtime(view)
            held = []
            effects = []
            observations = []
            errors = []
            view.set_call_dispatcher(held.append)
            view._create_ipc_handler("api.mutate", lambda: effects.append("api"))({"id": "old"})
            view.register_callback("event", lambda value: effects.append("event"))
            event = view._event_handlers["event"][0]

            class Finalizer:
                def __call__(self, *args):
                    pass

                def __del__(self):
                    try:
                        observations.append((view.closed, view._core.borrowed))
                        held[0]()
                        event(None)
                        view._dispatch_call_result({"id": "old", "ok": True})
                        view.request_close()  # Cached proxy while Core is borrowed.
                    except BaseException as error:
                        errors.append(repr(error))

            callback = Finalizer()
            reference = weakref.ref(callback)
            if owner != "ipc":
                runtime._native.js_callbacks.append(callback)
            if owner != "js":
                runtime._native.ipc_callbacks.append(callback)
            del callback
            runtime.poll()
            self.assertEqual(observations, [(False, True)])
            self.assertEqual(errors, [])
            self.assertEqual(effects, [])
            self.assertEqual(view.results, [])
            self.assertEqual(view.emit_attempts, [])
            self.assertIsNone(reference())
            self.assertTrue(view.closed)
            self.assertTrue(view.observed)

        for owner in ("js", "ipc", "both"):
            with self.subTest(owner=owner):
                check_owner(owner)

    def test_native_close_intent_rejects_a_new_incoming_call_before_reap(self):
        view = View()
        self.runtime(view)
        held = []
        view.set_call_dispatcher(held.append)
        handler = view._create_ipc_handler("api.mutate", lambda: self.fail("stale mutation"))
        view._core.state[0] = False
        handler({"id": "late"})
        self.assertEqual(held, [])
        self.assertEqual(view.results, [])

    def test_signal_release_allows_reentrant_registry_inspection(self):
        signal = signals.Signal()
        observed = []

        class Finalizer:
            def __call__(self):
                pass

            def __del__(self):
                observed.append((signal._lock._is_owned(), signal.handler_count))
                signal.connect(lambda: None)

        signal.connect(Finalizer())
        self.assertEqual(signal.disconnect_all(), 1)
        self.assertEqual(observed, [(False, 0)])
        self.assertEqual(signal.handler_count, 1)

    def test_show_captures_only_the_previously_cached_proxy_gate(self):
        view = View()
        view._is_running = False
        view.set_call_dispatcher(lambda callback: None)
        runtime = hosted.HostRuntime.__new__(hosted.HostRuntime)
        runtime._views = {}
        runtime._closed = False
        captured = []
        runtime._native = SimpleNamespace(
            show=lambda core: captured.append(view._host_callback_gate)
        )
        view._core.get_proxy = lambda: self.fail("Must use the cached owner-created proxy")
        runtime.show(view)
        self.assertEqual(captured, [view._core.proxy.callbacks_allowed])
        self.assertIs(view._host_runtime, runtime)

    def test_show_rejects_a_missing_native_admission_gate_before_construction(self):
        view = View()
        view._is_running = False
        view.set_call_dispatcher(lambda callback: None)
        view._core_proxies = {}
        runtime = hosted.HostRuntime.__new__(hosted.HostRuntime)
        runtime._views = {}
        runtime._closed = False
        runtime._native = SimpleNamespace(
            show=lambda core: self.fail("Must not construct native view")
        )
        with self.assertRaisesRegex(RuntimeError, "callback-admission gate"):
            runtime.show(view)
        self.assertIsNone(view._host_runtime)
        self.assertFalse(view._is_running)

    def test_result_hook_close_releases_callables_without_the_call_lock(self):
        view = View()
        held = []
        observed = []
        view.set_call_dispatcher(held.append)

        class Finalizer:
            def __call__(self):
                pass

            def __del__(self):
                observed.append(view._call_lock._is_owned())

        view.signals.closed.connect(Finalizer())
        view.emit = lambda event, payload: view.request_close()
        view._create_ipc_handler("api.result", lambda: 42)({"id": "result"})
        held.pop()()
        self.assertEqual(observed, [False])
        self.assertTrue(view.closed)

    def test_event_registry_finalizer_is_released_after_all_python_gates(self):
        view = View()
        held = []
        mutations = []
        observations = []
        view.set_call_dispatcher(held.append)
        view._create_ipc_handler("api.mutate", lambda: mutations.append(True))({"id": "old"})

        class Finalizer:
            def __call__(self, *args):
                pass

            def __del__(self):
                observations.append(
                    (
                        view.closed,
                        view._calls_closed_reason,
                        view._events_closed,
                        view._lifecycle_lock._is_owned(),
                        view._event_handlers_lock.locked(),
                    )
                )
                held[0]()

        callback = Finalizer()
        reference = weakref.ref(callback)
        view.register_callback("owned", callback)
        del callback
        view.request_close()
        self.assertIsNone(reference())
        self.assertEqual(mutations, [])
        self.assertEqual(observations, [(True, "WebView closed", True, False, False)])


if __name__ == "__main__":
    unittest.main()
