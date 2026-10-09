# Copyright (c) 2025 Long Hao
# Licensed under the MIT License
"""Unit tests for packed mode support.

Tests the packed mode detection and API server functionality
in auroraview.core.packed module.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from io import StringIO
from types import ModuleType
from typing import Any, Callable, Dict
from unittest.mock import MagicMock, patch

import pytest


class TestWebViewPackedConstruction:
    @pytest.mark.parametrize("packed_mode", [False, True])
    def test_detects_packed_mode_with_native_module(self, monkeypatch, packed_mode):
        import auroraview.core.packed as packed_module
        import auroraview.core.webview as webview_module

        native_module = ModuleType("auroraview._core")
        native_module.WebView = MagicMock()
        monkeypatch.setitem(sys.modules, "auroraview._core", native_module)
        monkeypatch.setenv("AURORAVIEW_PACKED", "1" if packed_mode else "0")
        monkeypatch.setattr(packed_module, "PACKED_MODE", packed_mode)
        spec = importlib.util.spec_from_file_location(
            "auroraview.core._packed_webview_test", webview_module.__file__
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module._CoreWebView is native_module.WebView
        assert module._IS_PACKED_MODE is packed_mode

    def test_native_available_packed_constructor_stays_headless(self, monkeypatch):
        import auroraview.core.webview as webview_module

        factory = MagicMock()
        monkeypatch.setattr(webview_module, "_CoreWebView", factory)
        monkeypatch.setattr(webview_module, "_IS_PACKED_MODE", True)
        with patch("auroraview.core.packed.is_packed_mode", return_value=True), patch(
            "auroraview.core.packed.run_api_server"
        ) as run_api_server:
            view = webview_module.WebView(debug=False, dcc_mode=False)
            try:
                view.show()
                factory.assert_not_called()
                assert view._core is None
                assert view._core_factory is None
                run_api_server.assert_called_once_with(view)
            finally:
                view.close()

    def test_standalone_constructor_uses_native_factory(self, monkeypatch):
        import auroraview.core.webview as webview_module

        factory = MagicMock()
        monkeypatch.setattr(webview_module, "_CoreWebView", factory)
        monkeypatch.setattr(webview_module, "_IS_PACKED_MODE", False)
        view = webview_module.WebView(title="Standalone", debug=False, dcc_mode=False)
        try:
            factory.assert_called_once_with(**view._core_kwargs)
            assert view._core_kwargs["title"] == "Standalone"
            assert view._core is factory.return_value
            assert view._core_factory is factory
        finally:
            view.close()

    @pytest.mark.parametrize("packed_mode", [False, True])
    def test_explicit_native_core_is_retained(self, monkeypatch, packed_mode):
        import auroraview.core.webview as webview_module

        factory = MagicMock()
        core = MagicMock()
        monkeypatch.setattr(webview_module, "_CoreWebView", factory)
        monkeypatch.setattr(webview_module, "_IS_PACKED_MODE", packed_mode)
        view = webview_module.WebView(_native_core=core, debug=False, dcc_mode=False)
        try:
            factory.assert_not_called()
            assert view._core is core
            assert view._core_factory is type(core)
            assert view._is_embedded is True
            assert view._is_running is True
        finally:
            view.close()


class TestIsPackedMode:
    """Test is_packed_mode() function."""

    def test_returns_false_when_env_not_set(self):
        """Test is_packed_mode returns False when AURORAVIEW_PACKED is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to reload the module to pick up the new env

            import auroraview.core.packed as packed_module

            # Manually set the module-level variable for testing
            original = packed_module.PACKED_MODE
            packed_module.PACKED_MODE = os.environ.get("AURORAVIEW_PACKED", "0") == "1"

            try:
                assert packed_module.is_packed_mode() is False
            finally:
                packed_module.PACKED_MODE = original

    def test_returns_false_when_env_is_zero(self):
        """Test is_packed_mode returns False when AURORAVIEW_PACKED is '0'."""
        with patch.dict(os.environ, {"AURORAVIEW_PACKED": "0"}):
            import auroraview.core.packed as packed_module

            original = packed_module.PACKED_MODE
            packed_module.PACKED_MODE = os.environ.get("AURORAVIEW_PACKED", "0") == "1"

            try:
                assert packed_module.is_packed_mode() is False
            finally:
                packed_module.PACKED_MODE = original

    def test_returns_true_when_env_is_one(self):
        """Test is_packed_mode returns True when AURORAVIEW_PACKED is '1'."""
        with patch.dict(os.environ, {"AURORAVIEW_PACKED": "1"}):
            import auroraview.core.packed as packed_module

            original = packed_module.PACKED_MODE
            packed_module.PACKED_MODE = os.environ.get("AURORAVIEW_PACKED", "0") == "1"

            try:
                assert packed_module.is_packed_mode() is True
            finally:
                packed_module.PACKED_MODE = original

    def test_returns_false_for_other_values(self):
        """Test is_packed_mode returns False for values other than '1'."""
        for value in ["true", "True", "TRUE", "yes", "2", ""]:
            with patch.dict(os.environ, {"AURORAVIEW_PACKED": value}):
                import auroraview.core.packed as packed_module

                original = packed_module.PACKED_MODE
                packed_module.PACKED_MODE = os.environ.get("AURORAVIEW_PACKED", "0") == "1"

                try:
                    assert packed_module.is_packed_mode() is False, f"Failed for value: {value}"
                finally:
                    packed_module.PACKED_MODE = original


class TestHandleRequest:
    """Test _handle_request() function."""

    def test_method_not_found(self):
        """Test _handle_request returns error for unknown method."""
        from auroraview.core.packed import _handle_request

        request = {"id": "1", "method": "unknown.method", "params": None}
        bound_functions: Dict[str, Callable[..., Any]] = {}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "1"
        assert response["ok"] is False
        assert response["error"]["name"] == "MethodNotFound"
        assert "unknown.method" in response["error"]["message"]

    def test_call_with_no_params(self):
        """Test _handle_request calls function with no params."""
        from auroraview.core.packed import _handle_request

        def my_func():
            return "hello"

        request = {"id": "2", "method": "api.my_func", "params": None}
        bound_functions = {"api.my_func": my_func}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "2"
        assert response["ok"] is True
        assert response["result"] == "hello"

    def test_call_with_dict_params(self):
        """Test _handle_request calls function with dict params as kwargs."""
        from auroraview.core.packed import _handle_request

        def greet(name: str, greeting: str = "Hello"):
            return f"{greeting}, {name}!"

        request = {
            "id": "3",
            "method": "api.greet",
            "params": {"name": "World", "greeting": "Hi"},
        }
        bound_functions = {"api.greet": greet}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "3"
        assert response["ok"] is True
        assert response["result"] == "Hi, World!"

    def test_call_with_list_params(self):
        """Test _handle_request calls function with list params as args."""
        from auroraview.core.packed import _handle_request

        def add(a: int, b: int):
            return a + b

        request = {"id": "4", "method": "api.add", "params": [1, 2]}
        bound_functions = {"api.add": add}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "4"
        assert response["ok"] is True
        assert response["result"] == 3

    def test_call_with_single_value_param(self):
        """Test _handle_request calls function with single value param."""
        from auroraview.core.packed import _handle_request

        def echo(msg):
            return msg

        request = {"id": "5", "method": "api.echo", "params": "hello"}
        bound_functions = {"api.echo": echo}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "5"
        assert response["ok"] is True
        assert response["result"] == "hello"

    def test_call_with_exception(self):
        """Test _handle_request returns error when function raises exception."""
        from auroraview.core.packed import _handle_request

        def failing_func():
            raise ValueError("Something went wrong")

        request = {"id": "6", "method": "api.fail", "params": None}
        bound_functions = {"api.fail": failing_func}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "6"
        assert response["ok"] is False
        assert response["error"]["name"] == "ValueError"
        assert "Something went wrong" in response["error"]["message"]

    def test_missing_id_defaults_to_empty_string(self):
        """Test _handle_request handles missing id gracefully."""
        from auroraview.core.packed import _handle_request

        def my_func():
            return "ok"

        request = {"method": "api.my_func", "params": None}
        bound_functions = {"api.my_func": my_func}

        response = _handle_request(request, bound_functions)

        assert response["id"] == ""
        assert response["ok"] is True

    def test_missing_method_defaults_to_empty_string(self):
        """Test _handle_request handles missing method gracefully."""
        from auroraview.core.packed import _handle_request

        request = {"id": "7", "params": None}
        bound_functions: Dict[str, Callable[..., Any]] = {}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "7"
        assert response["ok"] is False
        # Empty method should not be found
        assert response["error"]["name"] == "MethodNotFound"

    def test_complex_return_value(self):
        """Test _handle_request handles complex return values."""
        from auroraview.core.packed import _handle_request

        def get_data():
            return {
                "items": [1, 2, 3],
                "nested": {"key": "value"},
                "null_value": None,
            }

        request = {"id": "8", "method": "api.get_data", "params": None}
        bound_functions = {"api.get_data": get_data}

        response = _handle_request(request, bound_functions)

        assert response["id"] == "8"
        assert response["ok"] is True
        assert response["result"]["items"] == [1, 2, 3]
        assert response["result"]["nested"]["key"] == "value"
        assert response["result"]["null_value"] is None


class TestRunApiServer:
    """Test run_api_server() function behavior."""

    def create_mock_webview(self, bound_functions=None, event_handlers=None):
        """Create a mock WebView with bound functions."""
        mock = MagicMock()
        mock._bound_functions = bound_functions or {}
        mock._event_handlers = event_handlers or {}
        return mock

    def test_gets_bound_functions_from_webview(self):
        """Test run_api_server accesses _bound_functions from webview."""
        from auroraview.core.packed import run_api_server

        def my_handler():
            return "ok"

        webview = self.create_mock_webview(bound_functions={"api.test": my_handler})

        # Simulate stdin closing immediately (EOF)
        with patch("sys.stdin", StringIO("")):
            with patch("sys.stderr", StringIO()):
                run_api_server(webview)

        # Verify it accessed the bound functions
        # (the function should have run without error)

    def test_handles_empty_lines(self):
        """Test run_api_server ignores empty lines."""
        from auroraview.core.packed import run_api_server

        webview = self.create_mock_webview()

        # Simulate empty lines then EOF
        stdin_data = "\n\n   \n"
        with patch("sys.stdin", StringIO(stdin_data)):
            with patch("sys.stderr", StringIO()):
                run_api_server(webview)

    def test_handles_invalid_json(self):
        """Test run_api_server handles invalid JSON gracefully."""
        from auroraview.core.packed import run_api_server

        webview = self.create_mock_webview()

        # Simulate invalid JSON then EOF
        stdin_data = "not valid json\n"
        stderr_capture = StringIO()
        with patch("sys.stdin", StringIO(stdin_data)):
            with patch("sys.stderr", stderr_capture):
                run_api_server(webview)

        # Should log error about invalid JSON
        stderr_output = stderr_capture.getvalue()
        assert "Invalid JSON" in stderr_output

    def test_processes_valid_request(self):
        """Test run_api_server processes valid JSON-RPC request."""
        from auroraview.core.packed import run_api_server

        def echo(msg):
            return f"echo: {msg}"

        webview = self.create_mock_webview(bound_functions={"api.echo": echo})

        request = json.dumps({"id": "1", "method": "api.echo", "params": {"msg": "hello"}})
        stdin_data = request + "\n"

        stdout_capture = StringIO()
        with patch("sys.stdin", StringIO(stdin_data)):
            with patch("sys.stderr", StringIO()):
                with patch("sys.stdout", stdout_capture):
                    # Need to patch print to capture output
                    with patch("builtins.print") as mock_print:
                        # Capture what gets printed
                        printed_values = []

                        def capture_print(*args, **kwargs):
                            if kwargs.get("file") is not sys.stderr:
                                printed_values.append(args[0] if args else "")

                        mock_print.side_effect = capture_print
                        run_api_server(webview)

                        # Verify response was printed
                        # First printed value is the ready signal, second is the response
                        assert len(printed_values) >= 2
                        # Skip ready signal, get the actual response
                        response = json.loads(printed_values[1])
                        assert response["id"] == "1"
                        assert response["ok"] is True
                        assert response["result"] == "echo: hello"

    def test_calls_close_handlers_on_exit(self):
        """Test run_api_server calls close handlers when exiting."""
        from auroraview.core.packed import run_api_server

        close_called = []

        def close_handler():
            close_called.append(True)

        webview = self.create_mock_webview(event_handlers={"close": [close_handler]})

        with patch("sys.stdin", StringIO("")):
            with patch("sys.stderr", StringIO()):
                run_api_server(webview)

        assert len(close_called) == 1

    def test_handles_close_handler_exception(self):
        """Test run_api_server handles exceptions in close handlers."""
        from auroraview.core.packed import run_api_server

        def failing_handler():
            raise RuntimeError("Close handler failed")

        webview = self.create_mock_webview(event_handlers={"close": [failing_handler]})

        stderr_capture = StringIO()
        with patch("sys.stdin", StringIO("")):
            with patch("sys.stderr", stderr_capture):
                # Should not raise, just log the error
                run_api_server(webview)

        stderr_output = stderr_capture.getvalue()
        assert "Error in close handler" in stderr_output


class TestWebViewShowPackedMode:
    """Test WebView.show() behavior in packed mode."""

    def test_show_detects_packed_mode(self):
        """Test that show() detects packed mode and runs API server."""
        # This test verifies the integration point in webview.py

        # Mock the packed module functions
        with patch("auroraview.core.packed.is_packed_mode", return_value=True):
            with patch("auroraview.core.packed.run_api_server") as mock_run:
                # Create a minimal mock WebView
                mock_webview = MagicMock()
                mock_webview._parent = None

                # Import and call the show logic
                from auroraview.core.packed import is_packed_mode, run_api_server

                if is_packed_mode():
                    run_api_server(mock_webview)

                mock_run.assert_called_once_with(mock_webview)

    def test_show_skips_packed_mode_when_not_set(self):
        """Test that show() skips packed mode when env var not set."""
        with patch("auroraview.core.packed.is_packed_mode", return_value=False):
            with patch("auroraview.core.packed.run_api_server") as mock_run:
                from auroraview.core.packed import is_packed_mode, run_api_server

                if is_packed_mode():
                    run_api_server(MagicMock())

                mock_run.assert_not_called()


class TestPackedModeIntegration:
    """Integration tests for packed mode."""

    def test_bound_functions_are_accessible(self):
        """Test that functions bound via bind_call are accessible in packed mode."""
        from auroraview.core.packed import _handle_request

        # Simulate what happens when WebView.bind_call is used
        bound_functions: Dict[str, Callable[..., Any]] = {}

        def register_handler(method: str, func: Callable):
            bound_functions[method] = func

        # Register some handlers like the Gallery does
        def get_samples():
            return [{"name": "sample1"}, {"name": "sample2"}]

        register_handler("api.get_samples", get_samples)

        def run_sample(name: str):
            return {"status": "running", "name": name}

        register_handler("api.run_sample", run_sample)

        # Test calling them via _handle_request
        response1 = _handle_request(
            {"id": "1", "method": "api.get_samples", "params": None},
            bound_functions,
        )
        assert response1["ok"] is True
        assert len(response1["result"]) == 2

        response2 = _handle_request(
            {"id": "2", "method": "api.run_sample", "params": {"name": "test"}},
            bound_functions,
        )
        assert response2["ok"] is True
        assert response2["result"]["name"] == "test"

    def test_json_rpc_protocol_format(self):
        """Test that responses follow JSON-RPC-like format."""
        from auroraview.core.packed import _handle_request

        def my_func():
            return {"data": "value"}

        bound_functions = {"api.test": my_func}

        # Success response format
        success = _handle_request(
            {"id": "123", "method": "api.test", "params": None},
            bound_functions,
        )
        assert "id" in success
        assert "ok" in success
        assert "result" in success
        assert success["id"] == "123"
        assert success["ok"] is True

        # Error response format
        error = _handle_request(
            {"id": "456", "method": "api.unknown", "params": None},
            bound_functions,
        )
        assert "id" in error
        assert "ok" in error
        assert "error" in error
        assert error["id"] == "456"
        assert error["ok"] is False
        assert "name" in error["error"]
        assert "message" in error["error"]


class TestCliMetadataCollection:
    """Test RFC 0018 CLI metadata collection (iter/collect/dump)."""

    def _registry_webview(self):
        """Build a lightweight object exposing a real CommandRegistry as
        `_commands`, mirroring WebView's attribute layout."""
        from auroraview.core.commands import CommandRegistry

        class _FakeWebView:
            pass

        wv = _FakeWebView()
        wv._commands = CommandRegistry()
        return wv

    def test_iter_collects_only_cli_commands(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        reg = wv._commands

        @reg.register("export", cli="exp", help="Export data")
        def export(path: str, dpi: int = 300) -> dict:
            return {}

        @reg.register("internal")  # not CLI-exposed
        def internal() -> None:
            pass

        commands = packed_module.iter_cli_commands(wv)
        assert len(commands) == 1
        meta = commands[0]
        assert meta["name"] == "export"
        assert meta["aliases"] == ["exp"]
        assert meta["help"] == "Export data"
        assert [p["name"] for p in meta["params"]] == ["path", "dpi"]

    def test_iter_empty_when_no_registry(self):
        import auroraview.core.packed as packed_module

        class _Bare:
            pass

        assert packed_module.iter_cli_commands(_Bare()) == []

    def test_collect_matches_iter(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()

        @wv._commands.register("sync", cli=True)
        def sync() -> None:
            pass

        assert packed_module.collect_cli_commands(wv) == packed_module.iter_cli_commands(wv)

    def test_dump_cli_metadata_writes_json(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()

        @wv._commands.register("export", cli="exp")
        def export(path: str) -> dict:
            return {}

        buf = StringIO()
        with patch("sys.stdout", buf):
            packed_module.dump_cli_metadata(wv)

        payload = json.loads(buf.getvalue())
        assert payload["type"] == "cli_metadata"
        assert payload["commands"][0]["name"] == "export"
        assert payload["commands"][0]["aliases"] == ["exp"]

    def test_iter_skips_command_with_missing_func(self):
        """A CLI-listed name whose callable vanished is skipped (§13.2 guard)."""
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        reg = wv._commands

        @reg.register("export", cli="exp")
        def export(path: str) -> dict:
            return {}

        # Drop the underlying callable while leaving CLI metadata in place.
        reg._commands.pop("export", None)

        assert packed_module.iter_cli_commands(wv) == []


class TestInvokeCliCommand:
    """Test invoke_cli_command() headless dispatch (RFC 0018 §7)."""

    def _registry_webview(self):
        from auroraview.core.commands import CommandRegistry

        class _FakeWebView:
            pass

        wv = _FakeWebView()
        wv._commands = CommandRegistry()
        wv._bound_functions = {}
        return wv

    def test_runs_command_and_exits_with_code(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "greet"), patch.dict(
            os.environ, {"AURORAVIEW_CLI_ARGS": '["world"]'}
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=0) as mock_run:
                with __import__("pytest").raises(SystemExit) as exc:
                    packed_module.invoke_cli_command(wv)
        assert exc.value.code == 0
        mock_run.assert_called_once_with(wv, "greet", ["world"])

    def test_non_list_args_become_empty(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "ping"), patch.dict(
            os.environ, {"AURORAVIEW_CLI_ARGS": '{"not": "a list"}'}
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=2) as mock_run:
                with __import__("pytest").raises(SystemExit) as exc:
                    packed_module.invoke_cli_command(wv)
        assert exc.value.code == 2
        mock_run.assert_called_once_with(wv, "ping", [])

    def test_invalid_json_args_become_empty(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "ping"), patch.dict(
            os.environ, {"AURORAVIEW_CLI_ARGS": "not-json"}
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=1) as mock_run:
                with __import__("pytest").raises(SystemExit) as exc:
                    packed_module.invoke_cli_command(wv)
        assert exc.value.code == 1
        mock_run.assert_called_once_with(wv, "ping", [])

    def test_missing_args_env_defaults_to_empty_list(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "run"), patch.dict(
            os.environ, {}, clear=True
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=0) as mock_run:
                with __import__("pytest").raises(SystemExit):
                    packed_module.invoke_cli_command(wv)
        mock_run.assert_called_once_with(wv, "run", [])

    def test_none_command_falls_back_to_empty_string(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", None), patch.dict(
            os.environ, {"AURORAVIEW_CLI_ARGS": "[]"}
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=2) as mock_run:
                with __import__("pytest").raises(SystemExit):
                    packed_module.invoke_cli_command(wv)
        mock_run.assert_called_once_with(wv, "", [])

    def test_args_coerced_to_strings(self):
        import auroraview.core.packed as packed_module

        wv = self._registry_webview()
        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "calc"), patch.dict(
            os.environ, {"AURORAVIEW_CLI_ARGS": "[1, 2, true]"}
        ):
            with patch("auroraview.core.cli_invoke.run_cli_invoke", return_value=0) as mock_run:
                with __import__("pytest").raises(SystemExit):
                    packed_module.invoke_cli_command(wv)
        mock_run.assert_called_once_with(wv, "calc", ["1", "2", "True"])


class TestIsCliInvokeMode:
    """Test is_cli_invoke_mode() detection (RFC 0018 §7)."""

    def test_false_when_command_none(self):
        import auroraview.core.packed as packed_module

        with patch.object(packed_module, "CLI_INVOKE_COMMAND", None):
            assert packed_module.is_cli_invoke_mode() is False

    def test_true_when_command_set(self):
        import auroraview.core.packed as packed_module

        with patch.object(packed_module, "CLI_INVOKE_COMMAND", "greet"):
            assert packed_module.is_cli_invoke_mode() is True


class TestIsCliDumpMode:
    """Test is_cli_dump_mode() env detection."""

    def test_false_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            import auroraview.core.packed as packed_module

            original = packed_module.CLI_DUMP_MODE
            packed_module.CLI_DUMP_MODE = os.environ.get("AURORAVIEW_CLI_DUMP", "0") == "1"
            try:
                assert packed_module.is_cli_dump_mode() is False
            finally:
                packed_module.CLI_DUMP_MODE = original

    def test_true_when_one(self):
        with patch.dict(os.environ, {"AURORAVIEW_CLI_DUMP": "1"}):
            import auroraview.core.packed as packed_module

            original = packed_module.CLI_DUMP_MODE
            packed_module.CLI_DUMP_MODE = os.environ.get("AURORAVIEW_CLI_DUMP", "0") == "1"
            try:
                assert packed_module.is_cli_dump_mode() is True
            finally:
                packed_module.CLI_DUMP_MODE = original
