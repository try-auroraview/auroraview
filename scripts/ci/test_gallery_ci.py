"""Offline Gallery artifact and startup-diagnostic contracts; no browser launches."""

import fnmatch
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gallery_cdp", ROOT / "tests/test_gallery_cdp.py")
cdp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cdp
SPEC.loader.exec_module(cdp)


def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))


def step(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


class GalleryArtifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "gallery-artifacts").mkdir()
        (self.root / "release-artifacts").mkdir()
        self.wheel = self.root / "release-artifacts/auroraview-1.2.3-cp38-abi3-win_amd64.whl"
        self.wheel.write_bytes(b"selected PR wheel")
        jobs = workflow("release.yml")["jobs"]
        rename = next(
            step(job, "Rename artifacts with version")["run"]
            for job in jobs.values()
            if any(s.get("name") == "Rename artifacts with version" for s in job.get("steps", []))
        )
        self.rename = rename.replace("${{ steps.tag.outputs.VERSION }}", "1.2.3")

    def run_rename(self):
        bash = shutil.which("bash")
        if not bash:
            self.fail("bash is required to execute the release workflow contract")
        return subprocess.run(
            [bash, "--noprofile", "--norc", "-e", "-c", self.rename],
            cwd=self.root,
            capture_output=True,
            text=True,
            env=dict(os.environ, MSYS_NO_PATHCONV="1"),
        )

    def test_only_final_archives_reach_release_and_preserve_selected_wheel(self):
        jobs = workflow("build-gallery.yml")["jobs"]
        build = jobs["build"]
        upload = next(
            s["with"]["name"] for s in build["steps"] if "upload-artifact@" in s.get("uses", "")
        )
        artifacts = {
            upload.replace("${{ matrix.target }}", target["target"]): {
                target["archive"]: target["archive"].encode()
            }
            for target in build["strategy"]["matrix"]["include"]
        }
        artifacts.update(
            {
                "gallery-wheels-windows-x64": {self.wheel.name: b"internal Gallery wheel"},
                "gallery-sdk-assets-123": {"sdk.js": b"internal SDK"},
                "gallery-vite-assets-123": {"vite.js": b"internal Vite"},
                "gallery-frontend-dist-123": {"index.html": b"internal frontend"},
            }
        )
        combine = jobs["combine-artifacts"]
        pattern = step(combine, "Download all artifacts")["with"]["pattern"]
        selected = {
            name: files for name, files in artifacts.items() if fnmatch.fnmatchcase(name, pattern)
        }
        self.assertEqual(len(selected), len(build["strategy"]["matrix"]["include"]))
        for files in selected.values():
            for name, data in files.items():
                (self.root / "gallery-artifacts" / name).write_bytes(data)
        windows = step(jobs["e2e-test"], "Download Windows artifact")["with"]["name"]
        self.assertIn(windows, selected)
        self.assertEqual(
            step(combine, "Upload combined artifact")["with"]["name"], "gallery-all-platforms"
        )
        result = self.run_rename()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.wheel.read_bytes(), b"selected PR wheel")
        self.assertEqual(len(list((self.root / "release-artifacts").iterdir())), len(selected) + 1)
        self.assertFalse(list((self.root / "gallery-artifacts").iterdir()))

    def test_unexpected_assets_fail_without_overwriting_selected_wheel(self):
        for name in (self.wheel.name, "sdk.js", "index.html", "unknown.zip"):
            with self.subTest(name=name):
                asset = self.root / "gallery-artifacts" / name
                asset.write_bytes(b"unexpected payload")
                result = self.run_rename()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unexpected Gallery release asset", result.stderr)
                self.assertEqual(self.wheel.read_bytes(), b"selected PR wheel")
                self.assertEqual(asset.read_bytes(), b"unexpected payload")
                asset.unlink()


class GalleryDiagnostics(unittest.TestCase):
    def test_workflow_keeps_gallery_alive_through_tests_and_records_exit_state(self):
        job = workflow("build-gallery.yml")["jobs"]["e2e-test"]
        lifecycle = step(job, "Run Gallery CDP E2E tests")
        script = lifecycle["run"]
        self.assertEqual(lifecycle["shell"], "pwsh")
        self.assertEqual(lifecycle["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        launch = script.index("Start-Process")
        readiness = script.index("http://127.0.0.1:9222/json/version")
        tests = script.index("pytest tests/test_gallery_cdp.py")
        cleanup = script.index("} finally {")
        self.assertLess(launch, readiness)
        self.assertLess(readiness, tests)
        self.assertLess(tests, cleanup)
        self.assertIn("$process.HasExited", script[launch:readiness])
        self.assertIn("$state.exit_code = $process.ExitCode", script[cleanup:])
        self.assertIn("$process.Kill($true)", script[cleanup:])
        self.assertIn("$state.cleanup_error = $_.Exception.Message", script[cleanup:])
        self.assertIn("process.json", script[cleanup:])
        self.assertIn("if ($cleanupError -and -not $state.error)", script[cleanup:])
        self.assertFalse(any(s.get("name") == "Stop Gallery" for s in job["steps"]))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(cdp, "PROJECT_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = cdp.GalleryTestClient()
        self.page = Mock(url="https://gallery.invalid/")
        self.client._page = self.page
        self.path = self.root / "test-results/gallery/startup.json"

    def connect(self):
        browser = Mock()
        playwright = Mock()
        playwright.chromium.connect_over_cdp.return_value = browser
        sync_api = Mock()
        sync_api.sync_playwright.return_value.start.return_value = playwright
        with (
            patch.dict(sys.modules, {"playwright.sync_api": sync_api}),
            patch.object(self.client, "_prepare_playwright_loop"),
            patch.object(self.client, "_restore_playwright_loop"),
            patch.object(self.client, "_find_gallery_page", return_value=self.page),
        ):
            browser.close.side_effect = lambda: self.assertTrue(self.path.is_file())
            self.client.connect()

    def test_terminal_error_fails_immediately_and_is_saved_before_disconnect(self):
        info = {"code": "503", "title": "Backend Initialization Failed", "details": "ImportError"}
        self.page.evaluate.return_value = {
            "title": "Error - AuroraView",
            "url": self.page.url,
            "error_info": info,
            "diagnostics": {"elapsed_ms": 30000},
        }
        with patch.object(cdp.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "Gallery startup failed"):
                self.connect()
        sleep.assert_not_called()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["page"]["error_info"], info)
        self.assertEqual(saved["page"]["title"], "Error - AuroraView")
        self.assertEqual(saved["page"]["diagnostics"]["elapsed_ms"], 30000)

    def test_error_title_without_error_info_is_terminal(self):
        self.page.evaluate.return_value = {"title": "Error - AuroraView", "error_info": None}
        with self.assertRaisesRegex(RuntimeError, "Gallery startup failed"):
            self.client._wait_for_ready()

    def test_ready_page_still_connects(self):
        self.page.evaluate.return_value = {"title": "Gallery", "auroraview_ready": True}
        self.connect()
        self.assertFalse(self.path.exists())

    def test_timeout_diagnostics_are_saved(self):
        self.page.evaluate.return_value = {"title": "Loading", "diagnostics": {"elapsed_ms": 60000}}
        with patch.object(self.client, "_wait_for_ready", side_effect=TimeoutError("not ready")):
            with self.assertRaisesRegex(TimeoutError, "not ready"):
                self.connect()
        self.assertEqual(json.loads(self.path.read_text())["page"]["title"], "Loading")

    def test_capture_failure_preserves_original_error(self):
        self.page.evaluate.side_effect = RuntimeError("page closed")
        with patch.object(
            self.client, "_wait_for_ready", side_effect=TimeoutError("original failure")
        ):
            with self.assertRaisesRegex(TimeoutError, "original failure"):
                self.connect()
        self.assertEqual(json.loads(self.path.read_text())["capture_error"], "page closed")

    def test_large_diagnostics_are_bounded(self):
        self.page.evaluate.return_value = {"error_info": {"details": "x" * 1000000}}
        self.client._save_diagnostics(RuntimeError("backend failed"))
        saved = json.loads(self.path.read_text())
        self.assertEqual(len(saved["page"]["truncated"]), 65536)
        self.assertLess(self.path.stat().st_size, 70000)


if __name__ == "__main__":
    unittest.main()
