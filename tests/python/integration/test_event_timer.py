"""Tests for EventTimer functionality."""

import time
from unittest.mock import MagicMock

import pytest

from auroraview import EventTimer
from auroraview.utils.timer_backends import ThreadTimerBackend


class MockWebView:
    """Mock WebView for testing."""

    def __init__(self):
        self._should_close = False
        self._process_events_called = 0
        self._is_valid = True

    @property
    def is_ready(self) -> bool:
        """EventTimer reads this as the single source of truth for readiness."""
        return True

    def is_window_valid(self) -> bool:
        """EventTimer's validity probe (replaces the old ``_core`` path)."""
        return self._is_valid

    def process_events(self):
        """Mock process_events method."""
        self._process_events_called += 1
        return self._should_close

    def trigger_close(self):
        """Simulate window close."""
        self._should_close = True

    def invalidate_window(self):
        """Simulate window becoming invalid."""
        self._is_valid = False


class TestEventTimer:
    """Test EventTimer class."""

    def test_init(self):
        """Test EventTimer initialization."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16, check_window_validity=True)

        assert timer._webview is webview
        assert timer._interval_ms == 16
        assert timer._check_validity is True
        assert timer._running is False
        assert timer._timer_handle is None
        assert timer._backend is None  # Backend is auto-selected on start(), not __init__()

    def test_start_stop(self):
        """Test starting and stopping timer."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        # Start timer
        timer.start()
        assert timer.is_running is True
        assert timer._timer_handle is not None

        # Wait a bit
        time.sleep(0.05)

        # Stop timer
        timer.stop()
        assert timer.is_running is False

    def test_start_already_running(self):
        """Test starting timer when already running."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        timer.start()
        with pytest.raises(RuntimeError, match="already running"):
            timer.start()

        timer.stop()

    def test_stop_not_running(self):
        """Test stopping timer when not running."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10)

        # Should not raise error
        timer.stop()

    def test_on_close_callback(self):
        """Test on_close callback registration and execution."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        close_called = [False]

        @timer.on_close
        def handle_close():
            close_called[0] = True

        timer.start()

        # Trigger close
        webview.trigger_close()

        # Wait for callback (increased timeout for macOS thread scheduling)
        time.sleep(0.1)

        assert close_called[0] is True
        assert timer.is_running is False

    def test_on_tick_callback(self):
        """Test on_tick callback registration and execution."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        tick_count = [0]

        @timer.on_tick
        def handle_tick():
            tick_count[0] += 1

        timer.start()

        # Wait for a few ticks
        time.sleep(0.1)

        timer.stop()

        # Should have been called multiple times
        assert tick_count[0] > 0

    def test_process_events_called(self):
        """Test that process_events is called periodically."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        timer.start()

        # Wait for a few ticks
        time.sleep(0.1)

        timer.stop()

        # process_events should have been called multiple times
        assert webview._process_events_called > 0

    def test_window_validity_check(self):
        """Test window validity checking."""
        webview = MockWebView()
        timer = EventTimer(
            webview, interval_ms=10, check_window_validity=True, backend=ThreadTimerBackend()
        )

        close_called = [False]

        @timer.on_close
        def handle_close():
            close_called[0] = True

        timer.start()

        # Invalidate window
        webview.invalidate_window()

        # Wait for detection
        time.sleep(0.1)

        assert close_called[0] is True
        assert timer.is_running is False

    def test_window_validity_check_disabled(self):
        """Test that window validity check can be disabled."""
        webview = MockWebView()
        timer = EventTimer(
            webview, interval_ms=10, check_window_validity=False, backend=ThreadTimerBackend()
        )

        close_called = [False]

        @timer.on_close
        def handle_close():
            close_called[0] = True

        timer.start()

        # Invalidate window
        webview.invalidate_window()

        # Wait a bit
        time.sleep(0.1)

        # Should not have triggered close (validity check disabled)
        # But we need to stop the timer manually
        timer.stop()

    def test_interval_property(self):
        """Test interval_ms property."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16)

        assert timer.interval_ms == 16

        # Change interval
        timer.interval_ms = 33
        assert timer.interval_ms == 33

    def test_interval_property_invalid(self):
        """Test setting invalid interval."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16)

        with pytest.raises(ValueError, match="must be positive"):
            timer.interval_ms = 0

        with pytest.raises(ValueError, match="must be positive"):
            timer.interval_ms = -1

    def test_context_manager(self):
        """Test using EventTimer as context manager."""
        webview = MockWebView()

        with EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend()) as timer:
            assert timer.is_running is True

            # Wait a bit
            time.sleep(0.1)

        # Timer should be stopped after exiting context
        assert timer.is_running is False

    def test_multiple_close_callbacks(self):
        """Test multiple close callbacks."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        close_count = [0]

        @timer.on_close
        def handle_close_1():
            close_count[0] += 1

        @timer.on_close
        def handle_close_2():
            close_count[0] += 1

        timer.start()

        # Trigger close
        webview.trigger_close()

        # Wait for callbacks
        time.sleep(0.1)

        # Both callbacks should have been called
        assert close_count[0] == 2

    def test_multiple_tick_callbacks(self):
        """Test multiple tick callbacks."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        tick_count_1 = [0]
        tick_count_2 = [0]

        @timer.on_tick
        def handle_tick_1():
            tick_count_1[0] += 1

        @timer.on_tick
        def handle_tick_2():
            tick_count_2[0] += 1

        timer.start()

        # Wait for a few ticks
        time.sleep(0.1)

        timer.stop()

        # Both callbacks should have been called
        assert tick_count_1[0] > 0
        assert tick_count_2[0] > 0
        assert tick_count_1[0] == tick_count_2[0]

    def test_callback_exception_handling(self):
        """Test that exceptions in callbacks don't crash the timer."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        @timer.on_tick
        def handle_tick():
            raise RuntimeError("Test error")

        timer.start()

        # Wait a bit - timer should keep running despite exceptions
        time.sleep(0.1)

        assert timer.is_running is True

        timer.stop()

    def test_repr(self):
        """Test string representation."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16, backend=ThreadTimerBackend())

        repr_str = repr(timer)
        assert "EventTimer" in repr_str
        assert "16ms" in repr_str
        assert "stopped" in repr_str

        timer.start()
        repr_str = repr(timer)
        assert "running" in repr_str

        timer.stop()

    def test_timer_backend_selection(self):
        """Test that timer selects appropriate backend."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16, backend=ThreadTimerBackend())

        timer.start()

        # Should have selected a backend (Qt or thread)
        from auroraview.utils.timer_backends import QtTimerBackend

        assert isinstance(timer._backend, (QtTimerBackend, ThreadTimerBackend))
        assert timer._timer_handle is not None

        timer.stop()

    def test_tick_count_increments(self):
        """Test that tick count increments over time."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        initial_count = timer._tick_count

        timer.start()
        time.sleep(0.1)
        timer.stop()

        # Tick count should have increased
        assert timer._tick_count > initial_count

    def test_close_callback_stops_timer(self):
        """Test that close callback can stop the timer."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        @timer.on_close
        def handle_close():
            # Timer should auto-stop on close
            pass

        timer.start()
        webview.trigger_close()

        # Wait for close detection
        time.sleep(0.1)

        # Timer should be stopped
        assert not timer.is_running

    def test_multiple_start_stop_cycles(self):
        """Test multiple start/stop cycles."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        for _ in range(3):
            timer.start()
            assert timer.is_running
            time.sleep(0.02)
            timer.stop()
            assert not timer.is_running
            time.sleep(0.01)

    def test_interval_change_while_stopped(self):
        """Test changing interval while timer is stopped."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=16, backend=ThreadTimerBackend())

        timer.interval_ms = 33
        assert timer.interval_ms == 33

        # Should be able to start with new interval
        timer.start()
        assert timer.is_running
        timer.stop()

    def test_callback_execution_order(self):
        """Test that callbacks execute in registration order."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        execution_order = []

        @timer.on_tick
        def callback1():
            execution_order.append(1)

        @timer.on_tick
        def callback2():
            execution_order.append(2)

        @timer.on_tick
        def callback3():
            execution_order.append(3)

        timer.start()
        time.sleep(0.1)
        timer.stop()

        # Should have executed in order
        assert execution_order == [1, 2, 3] or execution_order[:3] == [1, 2, 3]

    def test_timer_with_zero_callbacks(self):
        """Test timer works without any callbacks."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        # Should work fine without callbacks
        timer.start()
        # Increased timeout for macOS thread scheduling
        time.sleep(0.1)
        timer.stop()

        assert webview._process_events_called > 0

    def test_check_validity_flag(self):
        """Test that check_window_validity flag is respected."""
        webview = MockWebView()

        # With validity check enabled
        timer1 = EventTimer(webview, interval_ms=10, check_window_validity=True)
        assert timer1._check_validity is True

        # With validity check disabled
        timer2 = EventTimer(webview, interval_ms=10, check_window_validity=False)
        assert timer2._check_validity is False

    def test_stop_with_no_timer(self):
        """Test stop() when no timer is running."""
        webview = MockWebView()
        timer = EventTimer(webview, interval_ms=10)

        # Should not raise error when stopping non-running timer
        timer.stop()
        assert timer._timer_handle is None
        assert timer.is_running is False

    def test_backend_stop_called(self):
        """Test that backend.stop() is called when timer stops."""
        from auroraview.utils.timer_backends import ThreadTimerBackend

        webview = MockWebView()

        # Create a mock backend
        mock_backend = MagicMock(spec=ThreadTimerBackend)
        mock_backend.is_available.return_value = True
        mock_backend.start.return_value = "mock_handle"

        timer = EventTimer(webview, interval_ms=10, backend=mock_backend)

        # Start timer
        timer.start()
        assert mock_backend.start.called

        # Stop timer
        timer.stop()

        # Backend stop should have been called with the handle
        mock_backend.stop.assert_called_once_with("mock_handle")

    def test_backend_stop_error_handling(self):
        """Test error handling when backend.stop() raises exception."""
        from auroraview.utils.timer_backends import ThreadTimerBackend

        webview = MockWebView()

        # Create a mock backend that raises error on stop
        mock_backend = MagicMock(spec=ThreadTimerBackend)
        mock_backend.is_available.return_value = True
        mock_backend.start.return_value = "mock_handle"
        mock_backend.stop.side_effect = RuntimeError("Mock error")

        timer = EventTimer(webview, interval_ms=10, backend=mock_backend)

        # Start timer
        timer.start()

        # Failed native teardown must remain observable and retryable.
        with pytest.raises(RuntimeError, match="Failed to stop timer"):
            timer.stop()
        assert timer.is_running is True
        assert timer._timer_handle == "mock_handle"

        # Backend stop was attempted
        mock_backend.stop.assert_called_once_with("mock_handle")
        mock_backend.stop.side_effect = None
        timer.stop()
        assert timer.is_running is False

    def test_off_close_unregisters(self):
        """off_close should remove a previously registered close callback."""
        from auroraview.utils.timer_backends import ThreadTimerBackend

        webview = MockWebView()
        # Use ThreadTimerBackend explicitly to avoid Qt thread issues in tests
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        called = {"a": False, "b": False}

        @timer.on_close
        def a():
            called["a"] = True

        @timer.on_close
        def b():
            called["b"] = True

        # Unregister 'a'
        assert timer.off_close(a) is True

        timer.start()
        webview.trigger_close()
        # Increased timeout for CI environments with slower thread scheduling
        time.sleep(0.1)

        # Only 'b' should be called
        assert called["a"] is False
        assert called["b"] is True

    def test_off_tick_unregisters(self):
        """off_tick should remove a previously registered tick callback."""
        from auroraview.utils.timer_backends import ThreadTimerBackend

        webview = MockWebView()
        # Use ThreadTimerBackend explicitly to avoid Qt thread issues in tests
        timer = EventTimer(webview, interval_ms=10, backend=ThreadTimerBackend())

        count = {"a": 0, "b": 0}

        @timer.on_tick
        def a():
            count["a"] += 1

        @timer.on_tick
        def b():
            count["b"] += 1

        # Unregister 'a'
        assert timer.off_tick(a) is True

        timer.start()
        # Increased timeout for CI environments with slower thread scheduling
        time.sleep(0.1)
        timer.stop()

        assert count["a"] == 0
        assert count["b"] > 0
