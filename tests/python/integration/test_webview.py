"""Unit tests for WebView class."""

import time

import pytest


@pytest.mark.unit
class TestWebViewCreation:
    """Test WebView creation and initialization."""

    def test_webview_import(self):
        """Test that WebView can be imported."""
        try:
            from auroraview import WebView

            assert WebView is not None
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_creation_default(self):
        """Test WebView creation with default parameters."""
        try:
            from auroraview import WebView

            webview = WebView()
            assert webview is not None
            assert webview._title == "AuroraView"
            assert webview._width == 800
            assert webview._height == 600
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_creation_custom(self):
        """Test WebView creation with custom parameters."""
        try:
            from auroraview import WebView

            webview = WebView(
                title="Custom Title",
                width=1024,
                height=768,
            )
            assert webview._title == "Custom Title"
            assert webview._width == 1024
            assert webview._height == 768
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_creation_with_url(self):
        """Test WebView creation with URL."""
        try:
            from auroraview import WebView

            webview = WebView(title="Test", url="https://example.com")
            assert webview is not None
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_load_file_helper(self, tmp_path):
        """Test WebView.load_file helper for local HTML files."""
        try:
            from auroraview import WebView

            html_path = tmp_path / "index.html"
            html_path.write_text("<html><body><h1>File Test</h1></body></html>", encoding="utf-8")

            webview = WebView(title="File Test")
            # Should not raise when loading a local HTML file via file:// URL
            webview.load_file(str(html_path))
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_creation_with_html(self):
        """Test WebView creation with HTML."""
        try:
            from auroraview import WebView

            webview = WebView(title="Test", html="<h1>Hello</h1>")
            assert webview is not None
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewMethods:
    """Test WebView methods."""

    def test_webview_repr(self):
        """Test WebView string representation."""
        try:
            from auroraview import WebView

            webview = WebView(title="Test", width=800, height=600)
            repr_str = repr(webview)
            assert "Test" in repr_str
            assert "800" in repr_str
            assert "600" in repr_str
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_title_property(self):
        """Test WebView title property."""
        try:
            from auroraview import WebView

            webview = WebView(title="Original Title")
            assert webview.title == "Original Title"
        except ImportError:
            pytest.skip("Package not built yet")

    def test_webview_context_manager(self):
        """Test WebView as context manager."""
        try:
            from auroraview import WebView

            with WebView(title="Test") as webview:
                assert webview is not None
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewEventHandling:
    """Test WebView event handling."""

    def test_event_handler_registration(self):
        """Test event handler registration."""
        try:
            from auroraview import WebView

            webview = WebView()
            received = []

            def handler(data):
                received.append(data)

            try:
                connection = webview.register_callback("test_event", handler)
                payload = {"value": 123}
                webview.signals.custom.emit("test_event", payload)
                assert received == [payload]

                assert webview.disconnect("test_event", connection)
                webview.signals.custom.emit("test_event", {"value": 456})
                assert received == [payload]
            finally:
                webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_event_decorator(self):
        """Test event decorator."""
        try:
            from auroraview import WebView

            webview = WebView()
            received = []

            @webview.on("test_event")
            def handler(data):
                received.append(data)

            try:
                payload = {"value": 123}
                webview.signals.custom.emit("test_event", payload)
                assert received == [payload]
            finally:
                webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_multiple_handlers_same_event(self):
        """Test multiple handlers for same event."""
        try:
            from auroraview import WebView

            webview = WebView()
            received = []

            def handler1(data):
                received.append(("first", data))

            def handler2(data):
                received.append(("second", data))

            try:
                first = webview.register_callback("test_event", handler1)
                webview.register_callback("test_event", handler2)
                payload = {"value": 123}
                webview.signals.custom.emit("test_event", payload)
                assert received == [("first", payload), ("second", payload)]

                assert webview.disconnect("test_event", first)
                next_payload = {"value": 456}
                webview.signals.custom.emit("test_event", next_payload)
                assert received == [
                    ("first", payload),
                    ("second", payload),
                    ("second", next_payload),
                ]
            finally:
                webview.close()
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewDataConversion:
    """Test WebView data conversion."""

    def test_emit_with_dict(self):
        """Test emit with dictionary data."""
        try:
            from auroraview import WebView

            webview = WebView()
            # Should not raise
            webview.emit("test_event", {"key": "value"})
        except ImportError:
            pytest.skip("Package not built yet")

    def test_emit_with_none(self):
        """Test emit with None data."""
        try:
            from auroraview import WebView

            webview = WebView()
            # Should not raise
            webview.emit("test_event", None)
        except ImportError:
            pytest.skip("Package not built yet")

    def test_emit_with_scalar(self):
        """Test emit with scalar data."""
        try:
            from auroraview import WebView

            webview = WebView()
            # Should not raise
            webview.emit("test_event", 42)
            webview.emit("test_event", "string")
            webview.emit("test_event", 3.14)
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewAsync:
    """Test WebView async/threading functionality."""

    def test_show_async_initialization(self):
        """Test that show_async() initializes threading attributes."""
        try:
            from auroraview import WebView

            webview = WebView()
            assert hasattr(webview, "_show_thread")
            assert hasattr(webview, "_is_running")
            assert webview._show_thread is None
            assert webview._is_running is False
        except ImportError:
            pytest.skip("Package not built yet")

    def test_show_async_not_running_initially(self):
        """Test that WebView is not running initially."""
        try:
            from auroraview import WebView

            webview = WebView()
            assert not webview._is_running
        except ImportError:
            pytest.skip("Package not built yet")

    def test_wait_returns_true_when_not_running(self):
        """Test that wait() returns True when WebView is not running."""
        try:
            from auroraview import WebView

            webview = WebView()
            result = webview.wait(timeout=0.1)
            assert result is True
        except ImportError:
            pytest.skip("Package not built yet")

    def test_wait_with_timeout(self):
        """Test that wait() respects timeout."""
        try:
            from auroraview import WebView

            webview = WebView()
            start_time = time.time()
            result = webview.wait(timeout=0.5)
            elapsed = time.time() - start_time

            # Should return True since no thread is running
            assert result is True
            # Should complete quickly
            assert elapsed < 1.0
        except ImportError:
            pytest.skip("Package not built yet")

    def test_close_with_no_thread(self):
        """Test that close() works when no thread is running."""
        try:
            from auroraview import WebView

            webview = WebView()
            # Should not raise
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_multiple_show_async_calls(self):
        """Test that multiple show_async() calls are handled correctly."""
        try:
            from auroraview import WebView

            webview = WebView()
            # First call should succeed (but won't actually show since no display)
            # We're just testing the logic, not the actual display

            # Mark as running to simulate a running WebView
            webview._is_running = True

            # Second call should be ignored
            webview.show_async()

            # Should still be marked as running
            assert webview._is_running is True
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewAutoShow:
    """Test WebView auto_show parameter behavior."""

    def test_create_default_auto_show_is_false(self):
        """Test that WebView.create() defaults to auto_show=False."""
        try:
            from auroraview import WebView

            # WebView.create() should default to auto_show=False
            webview = WebView.create(title="Test")
            # The _auto_show attribute should be False
            assert webview._auto_show is False
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_init_default_auto_show_is_true(self):
        """Test that WebView() constructor defaults to auto_show=True."""
        try:
            from auroraview import WebView

            # WebView() constructor should default to auto_show=True
            webview = WebView(title="Test")
            assert webview._auto_show is True
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_create_with_auto_show_true(self, monkeypatch):
        """Test that auto_show=True dispatches show once without entering its loop."""
        try:
            from auroraview import WebView

            show_calls = []
            monkeypatch.setattr(WebView, "show", lambda view: show_calls.append(view))
            webview = WebView.create(title="Test", auto_show=True)
            try:
                assert show_calls == [webview]
                assert webview._auto_show is True
            finally:
                webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_create_with_auto_show_false(self):
        """Test WebView.create() with explicit auto_show=False."""
        try:
            from auroraview import WebView

            webview = WebView.create(title="Test", auto_show=False)
            assert webview._auto_show is False
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_show_method_exists(self):
        """Test that show() method exists and is callable."""
        try:
            from auroraview import WebView

            webview = WebView.create(title="Test", auto_show=False)
            assert hasattr(webview, "show")
            assert callable(webview.show)
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_show_blocking_method_exists(self):
        """Test that show_blocking() method exists and is callable."""
        try:
            from auroraview import WebView

            webview = WebView.create(title="Test", auto_show=False)
            assert hasattr(webview, "show_blocking")
            assert callable(webview.show_blocking)
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")


@pytest.mark.unit
class TestWebViewCreateFactory:
    """Test WebView.create() factory method behavior."""

    def test_create_with_asset_root(self, tmp_path):
        """Test WebView.create() with asset_root parameter."""
        try:
            from auroraview import WebView

            # Create a test HTML file
            html_file = tmp_path / "index.html"
            html_file.write_text("<h1>Test</h1>", encoding="utf-8")

            webview = WebView.create(
                title="Asset Root Test",
                asset_root=str(tmp_path),
            )
            assert webview is not None
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_create_standalone_mode(self):
        """Test WebView.create() in standalone mode (no parent)."""
        try:
            from auroraview import WebView

            webview = WebView.create(title="Standalone Test")
            # Standalone mode: parent should be None
            assert webview._parent is None
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_create_with_bind_call(self):
        """Test WebView.create() with bind_call decorator."""
        try:
            from auroraview import WebView

            webview = WebView.create(title="Bind Call Test")

            @webview.bind_call("test.method")
            def test_handler(**kwargs):
                return {"success": True}

            # Verify handler is registered
            assert webview.is_method_bound("test.method")
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")

    def test_create_load_url_then_show(self, tmp_path):
        """Test the recommended workflow: create -> bind_call -> load_url -> show."""
        try:
            from auroraview import WebView

            # Create HTML file
            html_file = tmp_path / "index.html"
            html_file.write_text("<h1>Test</h1>", encoding="utf-8")

            # 1. Create WebView with asset_root
            webview = WebView.create(
                title="Workflow Test",
                asset_root=str(tmp_path),
            )

            # 2. Register handlers BEFORE load_url
            @webview.bind_call("api.test")
            def handler(**kwargs):
                return {"ok": True}

            # 3. Load URL
            webview.load_url("https://auroraview.localhost/index.html")

            # Verify state
            assert webview.is_method_bound("api.test")
            assert webview._stored_url == "https://auroraview.localhost/index.html"

            # 4. Close without showing (for unit test)
            webview.close()
        except ImportError:
            pytest.skip("Package not built yet")
