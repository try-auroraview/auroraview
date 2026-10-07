# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""Unit tests for API binding mechanism.

Tests the duplicate binding detection and thread-safety features
of the WebViewApiMixin class.
"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock


class TestApiBindingMixin:
    """Test WebViewApiMixin binding mechanism."""

    def create_mock_webview_with_mixin(self):
        """Create a mock WebView object with the ApiMixin."""
        from auroraview.core.mixins.api import WebViewApiMixin

        class MockWebView(WebViewApiMixin):
            def __init__(self):
                self._core = MagicMock()
                self._core.on = MagicMock()
                self._core.eval_js = MagicMock()
                self._core.register_api_methods = MagicMock()

            def eval_js(self, script: str) -> None:
                self._core.eval_js(script)

            def emit(self, event: str, data: Any) -> None:
                pass

        return MockWebView()

    def test_init_api_registry(self):
        """Test that API registry is properly initialized."""
        webview = self.create_mock_webview_with_mixin()
        webview._init_api_registry()

        assert hasattr(webview, "_bound_functions")
        assert hasattr(webview, "_bind_lock")
        assert isinstance(webview._bound_functions, dict)
        assert len(webview._bound_functions) == 0

    def test_ensure_api_registry_lazy_init(self):
        """Test lazy initialization of API registry."""
        webview = self.create_mock_webview_with_mixin()

        # Should not have registry yet
        assert not hasattr(webview, "_bound_functions") or webview._bound_functions is None

        # Calling ensure should initialize
        webview._ensure_api_registry()

        assert hasattr(webview, "_bound_functions")
        assert hasattr(webview, "_bind_lock")

    def test_is_method_bound_returns_false_for_unbound(self):
        """Test is_method_bound returns False for unbound methods."""
        webview = self.create_mock_webview_with_mixin()

        assert webview.is_method_bound("api.unknown") is False

    def test_is_method_bound_returns_true_for_bound(self):
        """Test is_method_bound returns True for bound methods."""
        webview = self.create_mock_webview_with_mixin()

        def my_func():
            return "hello"

        webview.bind_call("api.my_func", my_func)

        assert webview.is_method_bound("api.my_func") is True

    def test_get_bound_methods_empty_initially(self):
        """Test get_bound_methods returns empty list initially."""
        webview = self.create_mock_webview_with_mixin()

        assert webview.get_bound_methods() == []

    def test_get_bound_methods_returns_bound(self):
        """Test get_bound_methods returns all bound method names."""
        webview = self.create_mock_webview_with_mixin()

        webview.bind_call("api.func1", lambda: 1)
        webview.bind_call("api.func2", lambda: 2)

        methods = webview.get_bound_methods()
        assert "api.func1" in methods
        assert "api.func2" in methods
        assert len(methods) == 2

    def test_bind_call_registers_function(self):
        """Test bind_call registers the function."""
        webview = self.create_mock_webview_with_mixin()

        def echo(msg: str) -> str:
            return msg

        webview.bind_call("api.echo", echo)

        assert webview.is_method_bound("api.echo")
        webview._core.on.assert_called_once()

    def test_bind_call_allows_rebind_by_default(self):
        """Test bind_call allows rebinding by default."""
        webview = self.create_mock_webview_with_mixin()

        def func_v1():
            return "v1"

        def func_v2():
            return "v2"

        webview.bind_call("api.func", func_v1)
        webview.bind_call("api.func", func_v2)  # Should work

        # Should have the latest function
        assert webview._bound_functions["api.func"] == func_v2
        # The existing native callback resolves the latest Python function.
        assert webview._core.on.call_count == 1

    def test_bind_call_skips_when_allow_rebind_false(self):
        """Test bind_call skips when allow_rebind=False and already bound."""
        webview = self.create_mock_webview_with_mixin()

        def func_v1():
            return "v1"

        def func_v2():
            return "v2"

        webview.bind_call("api.func", func_v1)
        webview.bind_call("api.func", func_v2, allow_rebind=False)

        # Should still have v1
        assert webview._bound_functions["api.func"] == func_v1
        # on() should be called only once
        assert webview._core.on.call_count == 1

    def test_bind_call_decorator_usage(self):
        """Test bind_call works as a decorator."""
        webview = self.create_mock_webview_with_mixin()

        @webview.bind_call("api.decorated")
        def my_decorated_func():
            return "decorated"

        assert webview.is_method_bound("api.decorated")
        # The decorator should return the original function
        assert my_decorated_func() == "decorated"


class TestBindApiDuplicateDetection:
    """Test bind_api duplicate detection."""

    def create_mock_webview_with_mixin(self):
        """Create a mock WebView object with the ApiMixin."""
        from auroraview.core.mixins.api import WebViewApiMixin

        class MockWebView(WebViewApiMixin):
            def __init__(self):
                self._core = MagicMock()
                self._core.on = MagicMock()
                self._core.eval_js = MagicMock()
                self._core.register_api_methods = MagicMock()

            def eval_js(self, script: str) -> None:
                self._core.eval_js(script)

            def emit(self, event: str, data: Any) -> None:
                pass

        return MockWebView()

    def test_bind_api_binds_all_public_methods(self):
        """Test bind_api binds all public methods."""
        webview = self.create_mock_webview_with_mixin()

        class MyAPI:
            def method1(self):
                return 1

            def method2(self):
                return 2

            def _private(self):
                return "private"

        api = MyAPI()
        webview.bind_api(api, namespace="myapi")

        assert webview.is_method_bound("myapi.method1")
        assert webview.is_method_bound("myapi.method2")
        assert not webview.is_method_bound("myapi._private")

    def test_bind_api_is_idempotent_by_default(self):
        """Test bind_api is idempotent by default (skips already bound namespace)."""
        webview = self.create_mock_webview_with_mixin()

        class APIV1:
            def method(self):
                return "v1"

        class APIV2:
            def method(self):
                return "v2"

        v1 = APIV1()
        webview.bind_api(v1, namespace="api")
        original_func = webview._bound_functions["api.method"]

        # Second call with same namespace is silently skipped (idempotent)
        webview.bind_api(APIV2(), namespace="api")

        # Should still have V1's method (second call was skipped)
        assert webview._bound_functions["api.method"] == original_func

    def test_bind_api_skips_entire_namespace_when_already_bound(self):
        """Test bind_api skips entire namespace when already bound (idempotent).

        With namespace-level idempotency (default allow_rebind=False), once a
        namespace is bound, subsequent bind_api calls for the same namespace
        are silently skipped. This prevents accidental duplicate bindings.
        """
        webview = self.create_mock_webview_with_mixin()

        class APIV1:
            def method(self):
                return "v1"

        class APIV2:
            def method(self):
                return "v2"

            def new_method(self):
                return "new"

        v1 = APIV1()
        v2 = APIV2()

        # First binding
        webview.bind_api(v1, namespace="api")
        original_func = webview._bound_functions["api.method"]
        assert webview.is_namespace_bound("api")

        # Second binding with same namespace - should be skipped entirely
        webview.bind_api(v2, namespace="api")  # allow_rebind=False by default

        # method should still be v1's (namespace was skipped)
        assert webview._bound_functions["api.method"] == original_func
        # new_method should NOT be bound (entire namespace skipped)
        assert not webview.is_method_bound("api.new_method")

    def test_bind_api_rebinds_when_allow_rebind_true(self):
        """Test bind_api rebinds when allow_rebind=True is explicit."""
        webview = self.create_mock_webview_with_mixin()

        class APIV1:
            def method(self):
                return "v1"

        class APIV2:
            def method(self):
                return "v2"

            def new_method(self):
                return "new"

        v1 = APIV1()
        v2 = APIV2()

        webview.bind_api(v1, namespace="api")
        original_func = webview._bound_functions["api.method"]

        # Explicitly allow rebinding
        webview.bind_api(v2, namespace="api", allow_rebind=True)

        # method should now be v2's
        assert webview._bound_functions["api.method"] != original_func
        # new_method should be bound
        assert webview.is_method_bound("api.new_method")


class TestThreadSafety:
    """Test thread safety of API binding."""

    def create_mock_webview_with_mixin(self):
        """Create a mock WebView object with the ApiMixin."""
        from auroraview.core.mixins.api import WebViewApiMixin

        class MockWebView(WebViewApiMixin):
            def __init__(self):
                self._core = MagicMock()
                self._core.on = MagicMock()
                self._core.eval_js = MagicMock()
                self._core.register_api_methods = MagicMock()

            def eval_js(self, script: str) -> None:
                self._core.eval_js(script)

            def emit(self, event: str, data: Any) -> None:
                pass

        return MockWebView()

    def test_concurrent_bind_call(self):
        """Test concurrent bind_call operations are thread-safe."""
        webview = self.create_mock_webview_with_mixin()
        errors = []

        def bind_func(thread_id):
            try:
                for i in range(10):
                    method = f"api.thread{thread_id}_func{i}"
                    webview.bind_call(method, lambda: thread_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=bind_func, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Should have 50 methods bound (5 threads * 10 methods each)
        assert len(webview.get_bound_methods()) == 50


class TestPageLoadedState:
    """Test _is_loaded state management for event-driven API registration."""

    def create_mock_webview_with_mixin(self):
        """Create a mock WebView object with the ApiMixin."""
        from auroraview.core.mixins.api import WebViewApiMixin

        class MockWebView(WebViewApiMixin):
            def __init__(self):
                self._core = MagicMock()
                self._core.on = MagicMock()
                self._core.eval_js = MagicMock()
                self._core.register_api_methods = MagicMock()

            def eval_js(self, script: str) -> None:
                self._core.eval_js(script)

            def emit(self, event: str, data: Any) -> None:
                pass

        return MockWebView()

    def test_is_loaded_initially_false(self):
        """Test that _is_loaded is False initially."""
        webview = self.create_mock_webview_with_mixin()
        webview._init_api_registry()

        assert webview.is_loaded() is False

    def test_set_loaded_updates_state(self):
        """Test that _set_loaded updates the loaded state."""
        webview = self.create_mock_webview_with_mixin()
        webview._init_api_registry()

        webview._set_loaded(True)
        assert webview.is_loaded() is True

        webview._set_loaded(False)
        assert webview.is_loaded() is False

    def test_bind_api_uses_rust_register_api_methods(self):
        """Test that bind_api uses Rust register_api_methods directly."""
        webview = self.create_mock_webview_with_mixin()
        webview._init_api_registry()

        class TestApi:
            def hello(self):
                return "world"

        webview.bind_api(TestApi())

        # Should call register_api_methods directly
        webview._core.register_api_methods.assert_called_once()
        call_args = webview._core.register_api_methods.call_args
        assert call_args[0][0] == "api"  # namespace
        assert "hello" in call_args[0][1]  # method names
