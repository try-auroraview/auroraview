"""Gallery CDP Integration Tests for CI Environment.

This module provides comprehensive testing of the AuroraView Gallery
through CDP (Chrome DevTools Protocol) connection.

Gallery is auto-started by the session fixture if not running.

Tests:
1. Gallery startup and initialization
2. All examples can be launched
3. Gallery UI interactions (search, filter, settings)
4. Process management (spawn, kill, list)
5. IPC communication (stdout/stderr streaming)

Usage in CI:
    pytest tests/test_gallery_cdp.py -v

Usage locally:
    # Connect to existing Gallery
    pytest tests/test_gallery_cdp.py -v

Requirements:
    - playwright: pip install playwright
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "python"))


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CDP_URL = os.environ.get("WEBVIEW2_CDP_URL", "http://127.0.0.1:9222")
CDP_PORT = int(os.environ.get("WEBVIEW2_CDP_PORT", "9222"))
GALLERY_EXE = PROJECT_ROOT / "gallery" / "pack-output" / "auroraview-gallery.exe"

# Timeouts
STARTUP_TIMEOUT = 120  # Gallery startup timeout (WebView2 cold-start on CI can be slow)
API_TIMEOUT = 60  # API call timeout (some DCC samples need more time)
EXAMPLE_RUN_TIMEOUT = 2  # Example run duration (reduced for faster tests)
LOADING_TIMEOUT = (
    50  # Loading screen timeout before force-navigate (must be < _wait_for_ready timeout)
)


@dataclass
class CDPTestResult:
    """Result of a test case."""

    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# CDP Connection Utilities
# ─────────────────────────────────────────────────────────────────────────────


def wait_for_cdp(url: str = CDP_URL, timeout: int = STARTUP_TIMEOUT) -> bool:
    """Wait for CDP endpoint to become available."""
    import urllib.error
    import urllib.request

    host_port = url.replace("http://", "").replace("https://", "")
    start = time.time()

    while time.time() - start < timeout:
        try:
            req = urllib.request.urlopen(f"http://{host_port}/json/version", timeout=2)
            req.close()
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def is_cdp_available() -> bool:
    """Check if CDP is available."""
    return wait_for_cdp(timeout=2)


# ─────────────────────────────────────────────────────────────────────────────
# Gallery Process Manager
# ─────────────────────────────────────────────────────────────────────────────


class GalleryManager:
    """Manage gallery process for testing."""

    def __init__(self, exe_path: Path = GALLERY_EXE):
        self.exe_path = exe_path
        self.process: Optional[subprocess.Popen] = None
        self._started_by_us = False

    def start(self, timeout: int = STARTUP_TIMEOUT) -> bool:
        """Start gallery if not already running."""
        if is_cdp_available():
            print("Gallery already running (CDP available)")
            return True

        if not self.exe_path.exists():
            print(f"Gallery exe not found: {self.exe_path}")
            return False

        print(f"Starting gallery: {self.exe_path}")

        self.process = subprocess.Popen(
            [str(self.exe_path)],
            cwd=str(self.exe_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._started_by_us = True

        print(f"Process started: PID {self.process.pid}")
        print("Waiting for CDP...")

        if not wait_for_cdp(timeout=timeout):
            self.stop()
            return False

        print("CDP is available!")
        return True

    def stop(self):
        """Stop gallery if we started it."""
        if self._started_by_us and self.process:
            print("Stopping gallery...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self._started_by_us = False


# ─────────────────────────────────────────────────────────────────────────────
# Gallery Test Client
# ─────────────────────────────────────────────────────────────────────────────


class GalleryTestClient:
    """Test client for Gallery via CDP."""

    def __init__(self, cdp_url: str = CDP_URL):
        self.cdp_url = cdp_url
        self._playwright = None
        self._browser = None
        self._page = None
        self._original_event_loop = None

    def _prepare_playwright_loop(self):
        """Prepare a compatible event loop for Playwright sync API.

        Playwright's sync API calls asyncio.get_running_loop() internally and
        raises an error if it detects a running loop. Some environments
        (including CI runners with pytest-asyncio's asyncio_mode=strict) have
        an asyncio loop already running in the main thread.

        The fix: save the current event loop, then set it to None so
        asyncio.get_running_loop() raises RuntimeError (the expected "no
        running loop" state for sync code). This is safe because the E2E tests
        use Playwright's sync API and do not need an active asyncio loop.

        We always save the loop (not just when there's a running one) so that
        _restore_playwright_loop() always has something to restore, even across
        multiple client connect/disconnect cycles.
        """
        try:
            self._original_event_loop = asyncio.get_event_loop()
        except RuntimeError:
            self._original_event_loop = None

        # Unset the event loop so asyncio.get_running_loop() raises RuntimeError
        asyncio.set_event_loop(None)

    def _restore_playwright_loop(self):
        """Restore the original event loop after Playwright operations.

        This is idempotent — safe to call multiple times (connect, disconnect,
        and teardown paths may all call it). We do NOT consume
        self._original_event_loop here so that disconnect() can still restore
        the loop even after connect() already called this method.
        """
        if self._original_event_loop is not None:
            try:
                asyncio.set_event_loop(self._original_event_loop)
            except Exception:
                pass

    def connect(self):
        """Connect to gallery via CDP."""
        from playwright.sync_api import sync_playwright

        self._prepare_playwright_loop()
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            self._restore_playwright_loop()
            raise

        # Restore the original event loop now that Playwright is initialized.
        # Playwright's sync API only needs the "no running loop" state during
        # sync_playwright().start() — after that it uses its own greenlets.
        self._restore_playwright_loop()

        try:
            # Find the correct page (not about:blank)
            self._page = self._find_gallery_page()
            if not self._page:
                raise RuntimeError("No valid Gallery page found")

            # Wait for gallery to be ready
            self._wait_for_ready()
        except Exception as error:
            # Ensure cleanup on partial connect failure
            self._save_diagnostics(error)
            self.disconnect()
            raise

    def _find_gallery_page(self):
        """Find the correct Gallery page from all available pages.

        WebView2 with CDP may expose multiple pages:
        - about:blank (empty initial page)
        - Loading screen page
        - Main application page

        This method finds the most appropriate page for testing.
        """
        all_pages = []
        for context in self._browser.contexts:
            for page in context.pages:
                url = page.url
                title = ""
                try:
                    title = page.title()
                except Exception:
                    pass
                all_pages.append(
                    {
                        "page": page,
                        "url": url,
                        "title": title,
                    }
                )

        print(f"[CDP] Found {len(all_pages)} page(s):")
        for i, p in enumerate(all_pages):
            print(f"  [{i}] URL: {p['url']}, Title: {p['title']}")

        if not all_pages:
            return None

        # Priority order for page selection:
        # 1. Page with auroraview API ready
        # 2. Page with loading screen (auroraLoading)
        # 3. Page with non-blank URL (not about:blank)
        # 4. First available page

        # Check for auroraview ready
        for p in all_pages:
            try:
                has_api = p["page"].evaluate("""
                    () => typeof window.auroraview !== 'undefined' &&
                          typeof window.auroraview.api !== 'undefined'
                """)
                if has_api:
                    print(f"[CDP] Selected page with auroraview API: {p['url']}")
                    return p["page"]
            except Exception:
                pass

        # Check for loading screen
        for p in all_pages:
            try:
                has_loading = p["page"].evaluate("""
                    () => typeof window.auroraLoading !== 'undefined' ||
                          document.querySelector('.loading-container') !== null
                """)
                if has_loading:
                    print(f"[CDP] Selected page with loading screen: {p['url']}")
                    return p["page"]
            except Exception:
                pass

        # Skip about:blank pages
        for p in all_pages:
            if p["url"] and p["url"] != "about:blank":
                print(f"[CDP] Selected non-blank page: {p['url']}")
                return p["page"]

        # Fallback to first page
        print(f"[CDP] Fallback to first page: {all_pages[0]['url']}")
        return all_pages[0]["page"]

    def _read_status(self):
        return self._page.evaluate("""
            () => ({
                title: document.title,
                url: location.href,
                error_info: window._errorInfo || null,
                is_loading: !!(window.auroraLoading || document.querySelector('.loading-container')),
                backend_ready: window.__backendReady || false,
                auroraview_ready: typeof window.auroraview !== 'undefined' &&
                                 typeof window.auroraview.api !== 'undefined' &&
                                 typeof window.auroraview.api.get_samples === 'function',
                diagnostics: window.auroraLoading && window.auroraLoading.getDiagnostics
                    ? window.auroraLoading.getDiagnostics() : null
            })
        """)

    def _save_diagnostics(self, error):
        """Capture the failure before disconnect closes the error page."""
        try:
            diagnostics = {"error": str(error)[:4096]}
            if self._page:
                diagnostics["url"] = self._page.url[:4096]
                try:
                    snapshot = json.dumps(self._read_status(), ensure_ascii=False)
                    diagnostics["page"] = (
                        json.loads(snapshot)
                        if len(snapshot) <= 65536
                        else {"truncated": snapshot[:65536]}
                    )
                except Exception as capture_error:
                    diagnostics["capture_error"] = str(capture_error)[:4096]
            directory = PROJECT_ROOT / "test-results" / "gallery"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "startup.json").write_text(
                json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as capture_error:
            print(f"Could not save Gallery diagnostics: {capture_error}")

    def _wait_for_ready(self, timeout: int = 60):
        """Wait for gallery to be fully loaded.

        This method handles both the loading screen and the main app.
        On Windows CI, WebView2 cold-start can take 30-60s, so we use a
        generous timeout.
        """
        start = time.time()

        # First, check if we're on loading screen
        while time.time() - start < timeout:
            try:
                loading_status = self._read_status()
            except Exception as e:
                print(f"Error checking status: {e}")
                time.sleep(0.5)
                continue

            if loading_status.get("error_info") or loading_status.get("title", "").startswith(
                "Error - AuroraView"
            ):
                raise RuntimeError(f"Gallery startup failed: {loading_status.get('error_info')}")

            if loading_status.get("auroraview_ready"):
                print("Gallery is ready!")
                return

            if loading_status.get("is_loading"):
                elapsed = time.time() - start
                if elapsed > LOADING_TIMEOUT:
                    print(f"Loading timeout after {elapsed:.1f}s, forcing navigation...")
                    self._force_navigate()
                    time.sleep(2)
                    continue

                if int(elapsed) % 5 == 0 and elapsed > 0:
                    diag = loading_status.get("diagnostics") or {}
                    print(
                        f"Loading... elapsed={diag.get('elapsed_ms', 0)}ms, "
                        f"backend_ready={loading_status.get('backend_ready')}"
                    )

            time.sleep(0.5)

        raise TimeoutError("Gallery not ready within timeout")

    def _force_navigate(self):
        """Force navigation from loading screen."""
        try:
            self._page.evaluate("""
                () => {
                    if (window.__forceNavigate) {
                        window.__forceNavigate();
                    } else if (window.auroraview && window.auroraview.send_event) {
                        window.auroraview.send_event('navigate_to_app', {});
                    }
                }
            """)
        except Exception as e:
            print(f"Force navigate failed: {e}")

    def disconnect(self):
        """Disconnect from CDP."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._restore_playwright_loop()

    @property
    def page(self):
        """Get Playwright page."""
        return self._page

    # ─────────────────────────────────────────────────────────────────────
    # Gallery API Methods
    # ─────────────────────────────────────────────────────────────────────

    def call_api(self, method: str, args: dict = None, timeout: int = API_TIMEOUT * 1000) -> Any:
        """Call a gallery API method with timeout."""
        args_json = json.dumps(args or {})
        try:
            # Use JS-level timeout since page.evaluate doesn't accept timeout parameter
            result = self._page.evaluate(
                f"""
                (async () => {{
                    const timeoutMs = {timeout};
                    const timeoutPromise = new Promise((_, reject) =>
                        setTimeout(() => reject(new Error('API call timeout')), timeoutMs)
                    );
                    const apiPromise = (async () => {{
                        try {{
                            return await auroraview.api.{method}({args_json});
                        }} catch (e) {{
                            return {{ __error__: e.message }};
                        }}
                    }})();
                    return Promise.race([apiPromise, timeoutPromise]);
                }})()
            """
            )

            if isinstance(result, dict) and "__error__" in result:
                raise RuntimeError(result["__error__"])
            return result
        except Exception as e:
            # Check if page is still connected
            if "Target" in str(e) and "closed" in str(e):
                raise RuntimeError(f"Gallery closed unexpectedly during {method} call") from e
            raise

    def get_samples(self) -> list:
        """Get all samples."""
        return self.call_api("get_samples")

    def get_categories(self) -> dict:
        """Get all categories."""
        return self.call_api("get_categories")

    def get_source(self, sample_id: str) -> str:
        """Get source code for a sample."""
        return self.call_api("get_source", {"sample_id": sample_id})

    def run_sample(self, sample_id: str, show_console: bool = False) -> dict:
        """Run a sample."""
        return self.call_api("run_sample", {"sample_id": sample_id, "show_console": show_console})

    def kill_process(self, pid: int) -> dict:
        """Kill a process."""
        return self.call_api("kill_process", {"pid": pid})

    def list_processes(self) -> dict:
        """List running processes."""
        return self.call_api("list_processes")

    def open_url(self, url: str) -> dict:
        """Open URL in browser."""
        return self.call_api("open_url", {"url": url})

    # ─────────────────────────────────────────────────────────────────────
    # UI Interaction Methods
    # ─────────────────────────────────────────────────────────────────────

    def search(self, query: str):
        """Search for samples."""
        # Find search input and type
        self._page.fill('input[placeholder*="Search"]', query)
        time.sleep(0.3)  # Wait for filter

    def clear_search(self):
        """Clear search."""
        self._page.fill('input[placeholder*="Search"]', "")
        time.sleep(0.3)

    def click_sample(self, sample_id: str):
        """Click on a sample card."""
        self._page.click(f'[data-sample-id="{sample_id}"]')
        time.sleep(0.3)

    def click_run_button(self):
        """Click the run button."""
        self._page.click('button:has-text("Run")')
        time.sleep(0.5)

    def click_stop_button(self):
        """Click the stop button."""
        self._page.click('button:has-text("Stop")')
        time.sleep(0.3)

    def get_visible_samples(self) -> list:
        """Get list of visible sample IDs."""
        return self._page.evaluate("""
            Array.from(document.querySelectorAll('[data-sample-id]'))
                .map(el => el.dataset.sampleId)
        """)

    def get_console_output(self) -> str:
        """Get console output text."""
        return self._page.evaluate("""
            document.querySelector('.console-output')?.textContent || ''
        """)

    def take_screenshot(self, path: str):
        """Take a screenshot."""
        self._page.screenshot(path=path)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestGalleryAPI:
    """Test Gallery API functionality."""

    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        if not is_cdp_available():
            pytest.skip("CDP not available - start gallery first")

        with GalleryTestClient() as client:
            yield client

    def test_get_samples(self, client):
        """Test getting samples list."""
        samples = client.get_samples()

        assert samples, "No samples returned"
        assert len(samples) > 10, f"Expected >10 samples, got {len(samples)}"

        # Check sample structure
        sample = samples[0]
        assert "id" in sample
        assert "title" in sample
        assert "category" in sample

        print(f"?Got {len(samples)} samples")

    def test_get_categories(self, client):
        """Test getting categories."""
        categories = client.get_categories()

        assert categories, "No categories returned"
        assert len(categories) >= 3, f"Expected >=3 categories, got {len(categories)}"

        print(f"?Got {len(categories)} categories: {list(categories.keys())}")

    def test_get_source(self, client):
        """Test getting source code."""
        source = client.get_source("simple_decorator")

        assert source, "No source returned"
        assert "def main" in source, "Source should contain main function"
        assert "WebView" in source, "Source should import WebView"

        print(f"?Got source code ({len(source)} chars)")

    def test_list_processes_empty(self, client):
        """Test listing processes when none running."""
        result = client.list_processes()

        assert result.get("ok"), f"list_processes failed: {result}"
        assert "processes" in result

        print(f"?Listed {len(result['processes'])} processes")


class TestGalleryExamples:
    """Test running examples through Gallery."""

    @pytest.fixture(scope="function")
    def client(self):
        """Create test client for each test (isolated)."""
        if not is_cdp_available():
            pytest.skip("CDP not available - start gallery first")

        with GalleryTestClient() as client:
            yield client

    # Examples to test (subset for CI speed)
    EXAMPLES_TO_TEST = [
        "simple_decorator",
        "window_events",
        "floating_panel",
        "system_tray",
        "native_menu",
    ]

    @pytest.mark.parametrize("sample_id", EXAMPLES_TO_TEST)
    def test_run_example(self, client, sample_id):
        """Test running an example."""
        # Run the sample
        result = client.run_sample(sample_id)

        assert result.get("ok"), f"Failed to run {sample_id}: {result.get('error')}"
        assert result.get("pid"), "No PID returned"

        pid = result["pid"]
        print(f"  Started {sample_id} with PID {pid}")

        # Let it run briefly
        time.sleep(EXAMPLE_RUN_TIMEOUT)

        # Kill the process (with error handling)
        try:
            kill_result = client.kill_process(pid)
            assert kill_result.get("ok") or kill_result.get("already_exited"), (
                f"Failed to kill process: {kill_result}"
            )
        except Exception as e:
            # Process might have exited on its own
            print(f"  Note: kill_process raised {e}")

        print(f"?{sample_id} ran successfully")

    def test_run_all_examples(self, client):
        """Test that all examples can be started (quick check)."""
        samples = client.get_samples()

        # Skip examples that require special environments
        skip_ids = {"maya_qt_echo", "qt_style_tool", "qt_custom_menu", "dcc_integration"}

        passed = 0
        failed = []

        for sample in samples:
            sample_id = sample["id"]

            if sample_id in skip_ids:
                continue

            try:
                result = client.run_sample(sample_id)

                if result.get("ok"):
                    pid = result.get("pid")
                    time.sleep(1)  # Brief run
                    try:
                        client.kill_process(pid)
                    except Exception:
                        pass  # Process might have exited
                    passed += 1
                else:
                    failed.append((sample_id, result.get("error")))
            except Exception as e:
                # Check if Gallery is still running
                if "Target" in str(e) and "closed" in str(e):
                    failed.append((sample_id, "Gallery closed unexpectedly"))
                    break  # Stop testing if Gallery crashed
                failed.append((sample_id, str(e)))

        print(f"\n?{passed} examples passed")
        if failed:
            print(f"?{len(failed)} examples failed:")
            for sid, err in failed:
                print(f"    - {sid}: {err}")

        # Allow some failures (Qt examples without Qt)
        assert passed > len(samples) * 0.5, f"Too many failures: {len(failed)}/{len(samples)}"


class TestGalleryUI:
    """Test Gallery UI interactions."""

    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        if not is_cdp_available():
            pytest.skip("CDP not available - start gallery first")

        with GalleryTestClient() as client:
            yield client

    def test_page_title(self, client):
        """Test page title."""
        title = client.page.title()
        assert "AuroraView" in title or "Gallery" in title
        print(f"?Page title: {title}")

    def test_page_url(self, client):
        """Test page URL."""
        url = client.page.url
        assert "auroraview" in url.lower() or "localhost" in url.lower()
        print(f"?Page URL: {url}")

    def test_search_filter(self, client):
        """Test search functionality."""
        # Get initial count
        initial = client.get_visible_samples()

        # Search for specific term
        client.search("window")
        filtered = client.get_visible_samples()

        # Should have fewer results
        assert len(filtered) <= len(initial), "Search should filter results"

        # Clear and verify
        client.clear_search()
        restored = client.get_visible_samples()

        assert len(restored) == len(initial), "Clear should restore all samples"

        print(f"?Search filter works: {len(initial)} -> {len(filtered)} -> {len(restored)}")

    def test_screenshot(self, client, tmp_path):
        """Test taking screenshot."""
        screenshot_path = tmp_path / "gallery_test.png"
        client.take_screenshot(str(screenshot_path))

        assert screenshot_path.exists(), "Screenshot not saved"
        assert screenshot_path.stat().st_size > 1000, "Screenshot too small"

        print(f"?Screenshot saved: {screenshot_path.stat().st_size} bytes")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone Test Runner
# ─────────────────────────────────────────────────────────────────────────────


def run_all_tests():
    """Run all gallery tests."""
    print("=" * 70)
    print("AuroraView Gallery CDP Integration Tests")
    print("=" * 70)

    # Check CDP
    if not is_cdp_available():
        print("\nCDP not available. Starting gallery...")
        manager = GalleryManager()
        if not manager.start():
            print("ERROR: Failed to start gallery")
            return 1
        own_gallery = True
    else:
        print("\nUsing existing gallery (CDP available)")
        manager = None
        own_gallery = False

    results: list[CDPTestResult] = []

    try:
        with GalleryTestClient() as client:
            # Test 1: Get samples
            print("\n" + "-" * 50)
            print("Test: API - Get Samples")
            start = time.time()
            try:
                samples = client.get_samples()
                results.append(
                    CDPTestResult(
                        name="get_samples",
                        passed=True,
                        duration_ms=(time.time() - start) * 1000,
                        details={"count": len(samples)},
                    )
                )
                print(f"  ?Got {len(samples)} samples")
            except Exception as e:
                results.append(
                    CDPTestResult(
                        name="get_samples",
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(e),
                    )
                )
                print(f"  ?Failed: {e}")

            # Test 2: Get categories
            print("\n" + "-" * 50)
            print("Test: API - Get Categories")
            start = time.time()
            try:
                categories = client.get_categories()
                results.append(
                    CDPTestResult(
                        name="get_categories",
                        passed=True,
                        duration_ms=(time.time() - start) * 1000,
                        details={"categories": list(categories.keys())},
                    )
                )
                print(f"  ?Got {len(categories)} categories")
            except Exception as e:
                results.append(
                    CDPTestResult(
                        name="get_categories",
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(e),
                    )
                )
                print(f"  ?Failed: {e}")

            # Test 3: Run examples
            print("\n" + "-" * 50)
            print("Test: Run Examples")

            skip_ids = {
                "maya_qt_echo_demo",
                "qt_style_tool",
                "qt_custom_menu_demo",
                "dcc_integration_example",
            }

            for sample in samples[:10]:  # Test first 10 for speed
                sample_id = sample["id"]
                if sample_id in skip_ids:
                    continue

                start = time.time()
                try:
                    result = client.run_sample(sample_id)
                    if result.get("ok"):
                        pid = result.get("pid")
                        time.sleep(1)
                        client.kill_process(pid)
                        results.append(
                            CDPTestResult(
                                name=f"run_{sample_id}",
                                passed=True,
                                duration_ms=(time.time() - start) * 1000,
                                details={"pid": pid},
                            )
                        )
                        print(f"  ?{sample_id}")
                    else:
                        results.append(
                            CDPTestResult(
                                name=f"run_{sample_id}",
                                passed=False,
                                duration_ms=(time.time() - start) * 1000,
                                error=result.get("error"),
                            )
                        )
                        print(f"  ?{sample_id}: {result.get('error')}")
                except Exception as e:
                    results.append(
                        CDPTestResult(
                            name=f"run_{sample_id}",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=str(e),
                        )
                    )
                    print(f"  ?{sample_id}: {e}")

            # Test 4: Screenshot
            print("\n" + "-" * 50)
            print("Test: Screenshot")
            start = time.time()
            try:
                screenshot_path = PROJECT_ROOT / "gallery" / "test_screenshot.png"
                client.take_screenshot(str(screenshot_path))
                results.append(
                    CDPTestResult(
                        name="screenshot",
                        passed=True,
                        duration_ms=(time.time() - start) * 1000,
                        details={"path": str(screenshot_path)},
                    )
                )
                print(f"  ?Saved to {screenshot_path}")
            except Exception as e:
                results.append(
                    CDPTestResult(
                        name="screenshot",
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(e),
                    )
                )
                print(f"  ?Failed: {e}")

    finally:
        if own_gallery and manager:
            manager.stop()

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total_time = sum(r.duration_ms for r in results)

    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Duration: {total_time:.0f}ms")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.error}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
