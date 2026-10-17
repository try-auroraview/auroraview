# -*- coding: utf-8 -*-
"""Isolated source contracts; fake adapters, no MCP server, GUI, or host runtime.

Loads only the pure routing modules so this suite cannot silently skip when
optional DCC-MCP/native dependencies are absent. Each test gets its own registry
and restores the temporary import environment before returning.
"""

from __future__ import annotations

import contextlib
import gc
import importlib.util
import io
import json
import os
import sys
import threading
import types
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAdapter:
    def __init__(self, name):
        self.name = name
        self.calls = []
        self.stop_calls = 0

    def execute(self, tool, params):
        self.calls.append((tool, params))
        return {"ok": True, "target": self.name}

    def stop(self):
        self.stop_calls += 1
        raise AssertionError("a view route must never stop its host service")


class ViewRoutingTests(unittest.TestCase):
    def setUp(self):
        self.registry = _load(
            "isolated_view_registry", ROOT / "python/auroraview/dcc_mcp/adapter_registry.py"
        )
        self.dispatch = _load(
            "isolated_view_dispatch", ROOT / "skills/auroraview-webview/scripts/_dispatch.py"
        )
        package = types.ModuleType("auroraview.dcc_mcp")
        package.adapter_registry = self.registry
        parent = types.ModuleType("auroraview")
        parent.dcc_mcp = package
        self.modules = {"auroraview": parent, "auroraview.dcc_mcp": package}
        self.a = FakeAdapter("A")
        self.b = FakeAdapter("B")

    def call(self, tool="load_html", params=None, factory=None):
        if params is None:
            params = {"html": "A's page"}
        output = io.StringIO()
        env = {} if factory is None else {"AURORAVIEW_ADAPTER": factory}
        with patch.dict(sys.modules, self.modules), patch.dict(os.environ, env, clear=True):
            with contextlib.redirect_stdout(output):
                result = self.dispatch.run_tool(tool, params)
        self.assertEqual(json.loads(output.getvalue()), result)
        return result

    @staticmethod
    def target(registration, **params):
        params.update(view_id=registration.view_id, generation=registration.generation)
        return params

    def test_legacy_zero_or_one_view(self):
        self.assertIsNone(self.registry.current())
        self.assertFalse(self.call()["ok"])
        registration = self.registry.register(self.a)
        self.assertIs(self.registry.current_adapter(), self.a)
        self.assertEqual(self.call()["target"], "A")
        self.assertTrue(registration.active)

    def test_two_views_without_target_reject_before_either_executes(self):
        self.registry.register(self.a)
        self.registry.register(self.b)
        result = self.call()
        self.assertFalse(result["ok"])
        self.assertIn("Multiple", result["error"])
        self.assertEqual(self.a.calls + self.b.calls, [])
        with self.assertRaises(self.registry.AmbiguousViewError):
            self.registry.current_adapter()

    def test_explicit_routes_are_independent_and_strip_routing_fields(self):
        a = self.registry.register(self.a, view_id="A")
        b = self.registry.register(self.b, view_id="B")
        payload = self.target(a, html="alpha")
        self.assertEqual(self.call(params=payload)["target"], "A")
        self.assertEqual(self.call(params=self.target(b, html="beta"))["target"], "B")
        self.assertEqual(self.a.calls, [("load_html", {"html": "alpha"})])
        self.assertEqual(self.b.calls, [("load_html", {"html": "beta"})])
        self.assertIn("view_id", payload)  # caller data was not mutated

    def test_closed_generation_cannot_target_same_id_replacement(self):
        old = self.registry.register(self.a, view_id="panel")
        self.assertTrue(old.close())
        new = self.registry.register(self.b, view_id="panel")
        self.assertNotEqual(old.generation, new.generation)
        self.assertFalse(self.call(params=self.target(old, html="stale"))["ok"])
        self.assertEqual(self.a.calls + self.b.calls, [])
        self.assertFalse(old.close())
        self.assertTrue(new.active)
        self.assertEqual(self.call(params=self.target(new, html="new"))["target"], "B")

    def test_close_only_own_registration_and_never_stops_service(self):
        a = self.registry.register(self.a)
        b = self.registry.register(self.b)
        self.registry.unregister(a)
        self.assertFalse(a.active)
        self.assertTrue(b.active)
        self.assertEqual(self.call()["target"], "B")
        b.close()
        self.assertEqual(self.a.stop_calls + self.b.stop_calls, 0)
        self.assertEqual(self.registry.list_views(), [])

    def test_resolved_handle_rechecks_close_at_execution(self):
        a = self.registry.register(self.a)
        queued = self.registry.resolve(a.view_id, a.generation)
        a.close()
        with self.assertRaises(self.registry.StaleViewError):
            queued.execute("load_html", {"html": "too late"})
        self.assertEqual(self.a.calls, [])

    def test_duplicate_registration_is_same_owner_not_independent_lease(self):
        a = self.registry.register(self.a, view_id="one")
        self.assertIs(self.registry.register(self.a), a)
        self.assertIs(self.registry.register(self.a, view_id="one"), a)
        with self.assertRaises(ValueError):
            self.registry.register(self.a, view_id="different")
        with self.assertRaises(ValueError):
            self.registry.register(self.b, view_id="one")
        self.assertEqual(len(self.registry.list_views()), 1)

    def test_same_id_concurrent_registration_has_exactly_one_owner(self):
        barrier = threading.Barrier(2)
        results = []
        failures = []

        def register(adapter):
            barrier.wait(timeout=5)
            try:
                results.append(self.registry.register(adapter, view_id="shared"))
            except ValueError as exc:
                failures.append(exc)

        workers = [threading.Thread(target=register, args=(adapter,)) for adapter in (self.a, self.b)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(len(self.registry.list_views()), 1)

    def test_weak_routes_do_not_retain_views(self):
        adapter = FakeAdapter("temporary")
        weak = weakref.ref(adapter)
        registration = self.registry.register(adapter, view_id="temporary")
        del adapter
        gc.collect()
        self.assertIsNone(weak())
        self.assertFalse(registration.active)
        self.assertEqual(self.registry.list_views(), [])
        with self.assertRaises(self.registry.StaleViewError):
            registration.execute("load_html", {})

    def test_clear_and_identity_unregister_revoke_routes(self):
        a = self.registry.register(self.a)
        b = self.registry.register(self.b)
        self.assertEqual(list(self.registry.iter_adapters()), [self.a, self.b])
        self.registry.unregister(self.a)
        self.assertFalse(a.active)
        self.assertTrue(b.active)
        self.registry.clear()
        self.assertFalse(b.active)
        self.assertIsNone(self.registry.current())

    def test_invalid_identity_never_changes_registry(self):
        for value in ("", " ", "x" * 129, "\x00", 42):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.registry.register(self.a, view_id=value)
        with self.assertRaises(ValueError):
            self.registry.register(None)
        with self.assertRaises(TypeError):
            self.registry.register(object())
        self.assertEqual(self.registry.list_views(), [])

    def test_incomplete_or_stale_route_rejects_without_fallback(self):
        a = self.registry.register(self.a)
        bad = [
            {"view_id": a.view_id},
            {"generation": a.generation},
            {"view_id": "missing", "generation": a.generation},
            {"view_id": a.view_id, "generation": "wrong"},
            {"view_id": None, "generation": None},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                payload["html"] = "must not execute"
                self.assertFalse(self.call(params=payload)["ok"])
        self.assertEqual(self.a.calls, [])

    def test_list_views_is_side_effect_free_and_closed_routes_disappear(self):
        a = self.registry.register(self.a, view_id="one")
        b = self.registry.register(self.b, view_id="two")
        result = self.call("list_views", {})
        self.assertEqual(result, {"ok": True, "views": [self.target(a), self.target(b)]})
        self.assertEqual(self.a.calls + self.b.calls, [])
        a.close()
        self.assertEqual(self.call("list_views", {})["views"], [self.target(b)])
        self.assertFalse(self.call("list_views", {"unexpected": True})["ok"])

    def test_environment_factory_only_used_when_registry_empty(self):
        factory = types.ModuleType("fake_view_factory")
        factory.get_adapter = lambda: self.b
        self.modules[factory.__name__] = factory
        env = "fake_view_factory.get_adapter"
        self.assertEqual(self.call(factory=env)["target"], "B")
        a = self.registry.register(self.a)
        self.assertEqual(self.call(factory=env)["target"], "A")
        self.registry.register(self.b)
        self.assertFalse(self.call(factory=env)["ok"])
        self.assertEqual(self.call(params=self.target(a, html="A"), factory=env)["target"], "A")
        a.close()
        self.assertFalse(self.call(params=self.target(a, html="old"), factory=env)["ok"])

    def test_non_object_params_and_adapter_errors_are_structured(self):
        self.registry.register(self.a)
        for payload in ([], "wrong", False):
            with self.subTest(payload=payload):
                self.assertFalse(self.call(params=payload)["ok"])
        self.assertEqual(self.a.calls, [])
        self.a.execute = lambda *args: (_ for _ in ()).throw(RuntimeError("host failure"))
        self.assertEqual(self.call()["error"], "host failure")


if __name__ == "__main__":
    unittest.main()
