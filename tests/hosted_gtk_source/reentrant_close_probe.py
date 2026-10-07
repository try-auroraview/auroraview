"""Compare close-order defects with actual Python lifecycle methods.

SOURCE-ONLY. No GTK, WebKit, Rust extension, Blender, rendering or native IPC is
loaded. Case 1 executes actual request_close/events/signals/API code. Case 2
also executes actual HostRuntime.poll/_reap, with an explicitly fake native
boundary reproducing the Rust source's callback-release ordering.

Run: python -B reentrant_close_probe.py [--source-root /path/to/candidate]
Exit 1 means a stale queued API callback executed; exit 0 means neither case
observed that failure. New native interfaces may require adapting the fake
boundary; this script never replaces native acceptance.
"""

import argparse
import importlib.util
import json
import sys
import threading
import traceback
import types
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--case", choices=("python_close", "native_retirement", "all"), default="all"
    )
    arguments = parser.parse_args()
    root = arguments.source_root.resolve()
    # Accept either a portable Core checkout or an old complete candidate root.
    if (root / "core/python/auroraview").is_dir():
        root = root / "core"
    pyroot = root / "python/auroraview"

    # Package shells prevent importing AuroraView's native package initializer.
    # All lifecycle, callback, signal and API implementations below are loaded
    # unchanged from the selected candidate's actual files.
    for name in ("auroraview", "auroraview.core"):
        package = types.ModuleType(name)
        package.__path__ = []
        sys.modules[name] = package
    signals = load("auroraview.core.signals", pyroot / "core/signals.py")
    api = load("review_api", pyroot / "core/mixins/api.py")
    events = load("review_events", pyroot / "core/mixins/events.py")
    lifecycle = load("review_lifecycle", pyroot / "core/mixins/lifecycle.py")
    hosted = load("review_hosted", pyroot / "hosted.py")

    class FakeProxy:
        """Only plain shared admission state, never native Core borrowing."""

        def __init__(self, admission):
            self.admission = admission

        def callbacks_allowed(self):
            return self.admission[0]

        def close(self):
            self.admission[0] = False

        def emit(self, *args):
            pass

    class FakeCore:
        """Only terminal-state observation and a harmless close-send target."""

        def __init__(self):
            self._state = "active"
            self.borrowed = False
            self.admission = [True]
            self.proxy = FakeProxy(self.admission)
            self.close_requests = 0

        @property
        def lifecycle_state(self):
            assert not self.borrowed, "Native Core accessed during callback retirement"
            return self._state

        @lifecycle_state.setter
        def lifecycle_state(self, state):
            self._state = state

        def get_proxy(self):
            assert not self.borrowed, "Native proxy reacquired during callback retirement"
            return self.proxy

        def close(self):
            assert not self.borrowed, "Native Core borrowed during callback retirement"
            self.close_requests += 1
            self.admission[0] = False

    class View(
        lifecycle.WebViewLifecycleMixin,
        api.WebViewApiMixin,
        events.WebViewEventMixin,
    ):
        # request_close, _cancel_event_callbacks, _cancel_pending_calls,
        # _create_ipc_handler and _observe_native_close are NOT overridden.
        def __init__(self, with_core=False):
            self._init_api_registry()
            self._event_handlers_lock = threading.Lock()
            self._event_handlers = {}
            self._event_connections = {}
            self._signals = signals.WebViewSignals()
            self._async_core_lock = threading.Lock()
            self._async_core = None
            self._core = FakeCore() if with_core else None
            self._core_threads = {id(self._core): threading.get_ident()} if with_core else {}
            self._core_proxies = {id(self._core): self._core.proxy} if with_core else {}
            if with_core:
                # Mirrors HostRuntime.show's new capture contract. This is a
                # fake atomic proxy only; actual Rust binding remains not_run.
                self._host_callback_gate = self._core.proxy.callbacks_allowed
            self._singleton_registry = {}
            self._is_running = with_core
            self._closed_event = threading.Event()
            self.results = []

        def emit(self, event, payload):
            # Record only. There is deliberately no native transport here.
            self.results.append((event, payload))

        def _teardown_telemetry(self):
            pass

    def prepare_case(name, with_core=False):
        view = View(with_core)
        held = []
        mutations = []
        observations = []
        view.set_call_dispatcher(held.append)
        handler = view._create_ipc_handler(
            "api.mutate", lambda: mutations.append("stale queued mutation")
        )
        handler({"id": name})
        assert len(held) == 1

        class Finalizer:
            def __call__(self, *args):
                pass

            def __del__(self):
                observation = {
                    "close_requested": getattr(view, "_close_requested", False),
                    "calls_closed_reason": view._calls_closed_reason,
                    "event_admission_closed": getattr(view, "_events_closed", False),
                    "core_state": getattr(view._core, "_state", None),
                    "native_core_borrowed": getattr(view._core, "borrowed", False),
                    "lifecycle_lock_held": getattr(
                        getattr(view, "_lifecycle_lock", None), "_is_owned", lambda: False
                    )(),
                    "call_lock_held": view._call_lock._is_owned(),
                    "event_lock_held": view._event_handlers_lock.locked(),
                    "signal_lock_held": view.signals.closed._lock._is_owned(),
                    "stack": [
                        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                        for frame in traceback.extract_stack()[-12:]
                    ],
                }
                try:
                    # This is the actual closure supplied by Core to the host
                    # dispatcher, not a hand-written replacement mutation gate.
                    held[0]()
                except BaseException as error:
                    observation["exception"] = repr(error)
                observations.append(observation)

        return view, mutations, observations, Finalizer

    results = []
    view, mutations, observations, finalizer = prepare_case("python_close")
    view.signals.closed.connect(finalizer())  # Signal is the only callable owner.
    view.request_close()
    results.append(
        {
            "case": "actual_request_close_signal_finalizer",
            "native_boundary": "none",
            "observations": observations,
            "mutations": mutations,
            "closed_afterward": view._close_requested,
        }
    )

    view, mutations, observations, finalizer = prepare_case("native_retirement", True)

    class NativeRetirementBoundary:
        """Model only the source's order, without pretending to run Rust/GTK.

        hosted_gtk.rs:105-114: queue shutdown -> callback/IPC gates -> callback
        decrefs -> native destruction -> finish_hosted. Python invalidation
        occurs later in hosted.py:63-80, after native.poll returns.
        """

        def __init__(self, callback):
            self.callback = callback

        def poll(self, *args):
            view._core.lifecycle_state = "close_requested"
            view._core.admission[0] = False  # Real queue closes before native decrefs.
            view._core.borrowed = True
            try:
                self.callback = None  # Native sole ownership release, before reap.
            finally:
                view._core.borrowed = False
            view._core.lifecycle_state = "destroyed"
            return {"live_views": 0}

    runtime = hosted.HostRuntime.__new__(hosted.HostRuntime)
    runtime._closed = False
    runtime._views = {id(view): view}
    runtime._native = NativeRetirementBoundary(finalizer())
    view._host_runtime = runtime
    runtime.poll()  # Actual HostRuntime.poll and actual _reap/request_close.
    results.append(
        {
            "case": "callback_release_before_python_reap",
            "native_boundary": "explicit fake matching reviewed Rust source ordering",
            "observations": observations,
            "mutations": mutations,
            "closed_afterward": view._close_requested,
        }
    )
    report = {
        "source_only": True,
        "native_validation": False,
        "candidate": str(root),
        "actual_modules": [
            str(Path(module.__file__))
            for module in (
                api,
                events,
                lifecycle,
                signals,
                hosted,
            )
        ],
        "cases": [
            case
            for case in results
            if arguments.case == "all"
            or case["case"]
            == {
                "python_close": "actual_request_close_signal_finalizer",
                "native_retirement": "callback_release_before_python_reap",
            }[arguments.case]
        ],
    }
    report["stale_mutation_cases"] = sum(bool(case["mutations"]) for case in report["cases"])
    report["finalizer_exceptions"] = [
        observation["exception"]
        for case in report["cases"]
        for observation in case["observations"]
        if "exception" in observation
    ]
    print(json.dumps(report, indent=2))
    return 1 if report["stale_mutation_cases"] or report["finalizer_exceptions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
