"""Tests for QtEventProcessor strategy pattern."""

import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("qtpy", reason="Qt backend requires qtpy and Qt bindings")

from auroraview import WebView  # noqa: E402, I001


# Mark all tests as Qt tests and skip in CI (requires display)
pytestmark = [
    pytest.mark.qt,
    pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Qt tests require display environment, skipped in CI",
    ),
]


class TestQtEventProcessor(unittest.TestCase):
    """Test QtEventProcessor strategy pattern."""

    def test_qt_event_processor_creation(self):
        """Test creating QtEventProcessor."""
        from auroraview.integration.qt import QtEventProcessor

        webview = WebView()
        processor = QtEventProcessor(webview)

        assert processor._webview is webview
        assert processor._process_count == 0

    def test_qt_event_processor_process(self):
        """Test QtEventProcessor.process() calls both Qt and WebView events."""
        from auroraview.integration.qt import QtEventProcessor

        webview = WebView()
        processor = QtEventProcessor(webview)

        # Mock Qt and WebView process_events
        with patch("auroraview.integration.qt.event_processor.QCoreApplication") as mock_qt:
            # Call process
            processor.process()

            # Verify Qt events were processed
            mock_qt.processEvents.assert_called_once()

            # Verify process count incremented
            assert processor._process_count == 1

    def test_webview_with_qt_processor(self):
        """Test WebView with QtEventProcessor set."""
        from auroraview.integration.qt import QtEventProcessor

        webview = WebView()
        processor = QtEventProcessor(webview)
        webview.set_event_processor(processor)

        # Mock the processor's process method
        processor.process = MagicMock()

        # Emit event
        webview.emit("test_event", {"data": 123})

        # Verify processor was called
        processor.process.assert_called_once()

    def test_webview_without_processor_uses_default(self):
        """Test WebView without processor uses default implementation."""
        webview = WebView()

        # Replace the native Rust core with a mock so we can observe the
        # default-path call. The real `_core` is a builtins.WebView whose
        # attributes can't be reassigned, so swap the whole object.
        original_core = webview._core
        try:
            webview._core = MagicMock()
            webview._track_core_thread(webview._core)

            # Emit event (should use default implementation via _auto_process_events)
            webview.emit("test_event", {"data": 123})

            # Verify default implementation was called
            webview._core.process_events.assert_called_once()
        finally:
            webview._core = original_core
            webview.close()

    def test_processor_can_be_changed(self):
        """Test that event processor can be changed."""
        webview = WebView()

        # Create two processors
        processor1 = MagicMock()
        processor1.process = MagicMock()

        processor2 = MagicMock()
        processor2.process = MagicMock()

        # Set first processor
        webview.set_event_processor(processor1)
        webview.emit("event1", {})
        processor1.process.assert_called_once()
        processor2.process.assert_not_called()

        # Change to second processor
        webview.set_event_processor(processor2)
        webview.emit("event2", {})
        processor1.process.assert_called_once()  # Still only once
        processor2.process.assert_called_once()  # Now called


if __name__ == "__main__":
    unittest.main()
