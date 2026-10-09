"""Offline Gallery artifact and startup-diagnostic contracts; no browser launches."""

import fnmatch
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("gallery_cdp", ROOT / "tests/test_gallery_cdp.py")
cdp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cdp
SPEC.loader.exec_module(cdp)
STAGE_SPEC = importlib.util.spec_from_file_location(
    "stage_gallery_wheel", ROOT / "scripts/ci/stage_gallery_wheel.py"
)
wheel_stage = importlib.util.module_from_spec(STAGE_SPEC)
STAGE_SPEC.loader.exec_module(wheel_stage)


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

    def test_prebuilt_wheel_reaches_collected_python_input(self):
        for name, job_name in (("build-gallery.yml", "build"), ("pr-checks.yml", "gallery-pack")):
            install = step(workflow(name)["jobs"][job_name], "Install auroraview wheel")
            self.assertEqual(install["run"].strip(), "vx just gallery-ci-stage-wheel dist")
            self.assertIn("GALLERY_SOURCE_HEAD", install["env"])
            self.assertEqual(
                install["env"]["GALLERY_WHEEL_ARTIFACT"], "${{ matrix.wheel-artifact }}"
            )
        config = tomllib.loads((ROOT / "gallery/auroraview.pack.toml").read_text(encoding="utf-8"))
        includes = config["backend"]["python"]["include_paths"]
        self.assertIn(
            (ROOT / "python").resolve(), [(ROOT / "gallery" / p).resolve() for p in includes]
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


class GalleryWheelStaging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        self.payloads = {
            "auroraview/__init__.py": b"# exact-head Python source\n",
            "auroraview/core/webview.py": b"# exact-head headless fix\n",
            "auroraview/_core.pyd": b"native extension fixture; never imported",
            "auroraview.libs/dependency.dll": b"native dependency fixture; never loaded",
            "auroraview-1.2.3.dist-info/METADATA": b"Metadata-Version: 2.1\nName: auroraview\nVersion: 1.2.3\n",
            "auroraview-1.2.3.dist-info/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-any\n",
        }
        for name, data in self.payloads.items():
            if name.endswith(".py"):
                path = self.root / "python" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        self.source_only = self.root / "python/auroraview/source_only.py"
        self.source_only.write_bytes(b"# retain source-only files\n")
        self.wheel = self.dist / "auroraview-1.2.3-py3-none-any.whl"
        self.receipt = self.root / "test-results/gallery-wheel/receipt.json"
        self.write_wheel()

    def write_wheel(self, extra=()):
        with warnings.catch_warnings(), zipfile.ZipFile(self.wheel, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name, data in list(self.payloads.items()) + list(extra):
                info = zipfile.ZipInfo(name)
                info.filename = name  # Preserve hostile separators on Windows for path tests.
                archive.writestr(info, data)
            archive.writestr(
                "auroraview-1.2.3.dist-info/RECORD",
                "\n".join(name + ",," for name in self.payloads)
                + "\nauroraview-1.2.3.dist-info/RECORD,,\n",
            )

    def assert_rejected_before_install(self, reason):
        with (
            patch.object(wheel_stage.Path, "cwd", return_value=self.root),
            patch.object(wheel_stage.subprocess, "run") as install,
        ):
            with self.assertRaisesRegex(ValueError, reason):
                wheel_stage.stage(self.dist)
            install.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_real_uv_install_verifies_package_and_records_native_members(self):
        # Synthetic wheel checks staging only; it cannot attest a GitHub build or native load.
        result = subprocess.run(
            [
                "vx",
                "just",
                "--justfile",
                str(ROOT / "justfile"),
                "--working-directory",
                str(self.root),
                "gallery-ci-stage-wheel",
                str(self.dist),
            ],
            capture_output=True,
            text=True,
            env=dict(
                os.environ,
                UV_NO_INDEX="1",
                UV_OFFLINE="1",
                UV_PYTHON_DOWNLOADS="never",
                GALLERY_SOURCE_HEAD="fixture-source-head",
                GITHUB_SHA="fixture-checkout-sha",
                GITHUB_RUN_ID="fixture-run-id",
                GITHUB_RUN_ATTEMPT="fixture-run-attempt",
                GALLERY_WHEEL_ARTIFACT="fixture-wheel-artifact",
            ),
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, data in self.payloads.items():
            if name.startswith(("auroraview/", "auroraview.libs/")):
                self.assertEqual(self.root.joinpath("python", name).read_bytes(), data)
        self.assertEqual(self.source_only.read_bytes(), b"# retain source-only files\n")
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(receipt["wheel"]["filename"], self.wheel.name)
        self.assertEqual(
            receipt["wheel"]["sha256"], hashlib.sha256(self.wheel.read_bytes()).hexdigest()
        )
        self.assertEqual(receipt["wheel"]["tags"], ["py3-none-any"])
        self.assertEqual(
            receipt["wheel"]["filename_tags"], {"python": "py3", "abi": "none", "platform": "any"}
        )
        self.assertEqual(receipt["python_sources_verified"], 2)
        self.assertEqual(receipt["package_files_verified"], 4)
        self.assertEqual(
            receipt["native_members"],
            [
                {"path": name, "length": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in sorted(self.payloads.items())
                if name.endswith((".pyd", ".dll"))
            ],
        )
        for key, expected in (
            ("source_head", "fixture-source-head"),
            ("checkout_sha", "fixture-checkout-sha"),
            ("run_id", "fixture-run-id"),
            ("run_attempt", "fixture-run-attempt"),
            ("wheel_artifact", "fixture-wheel-artifact"),
        ):
            self.assertEqual(receipt["provenance"][key], expected)
        self.assertIn("not remote attestation", receipt["provenance"]["binding"])
        self.assertIn("collected packed payload is not verified", receipt["boundary"])

    def test_ambiguous_wheel_directory_rejected(self):
        self.wheel.unlink()
        self.assert_rejected_before_install("Exactly one wheel")
        self.write_wheel()
        shutil.copyfile(self.wheel, self.dist / "other-1.2.3-py3-none-any.whl")
        self.assert_rejected_before_install("Exactly one wheel")

    def test_mismatched_checkout_source_rejected(self):
        source = self.root / "python/auroraview/core/webview.py"
        source.write_bytes(b"# newer headless fix must not be overwritten\n")
        self.assert_rejected_before_install("Python source differs from checkout")
        self.assertEqual(source.read_bytes(), b"# newer headless fix must not be overwritten\n")

    def test_missing_native_extension_rejected(self):
        del self.payloads["auroraview/_core.pyd"]
        self.write_wheel()
        self.assert_rejected_before_install("no native auroraview/_core extension")

    def test_foreign_distribution_rejected(self):
        self.payloads["auroraview-1.2.3.dist-info/METADATA"] = b"Name: another-package\n"
        self.write_wheel()
        self.assert_rejected_before_install("metadata must name auroraview")

    def test_duplicate_and_unsafe_member_paths_rejected(self):
        for name in (
            "auroraview/__init__.py",
            "AuroraView/__init__.py",
            "auroraview/../outside.py",
            "auroraview/./outside.py",
            "auroraview//outside.py",
            "auroraview\\outside.py",
            "auroraview/C:outside.py",
            "/outside.py",
        ):
            with self.subTest(name=name):
                self.write_wheel([(name, b"invalid member")])
                self.assert_rejected_before_install("Duplicate|Unsafe")

    def test_install_readback_rejects_missing_or_changed_payload(self):
        for native_bytes in (None, b"changed native extension"):
            with self.subTest(native_bytes=native_bytes):
                if native_bytes is not None:
                    (self.root / "python/auroraview/_core.pyd").write_bytes(native_bytes)
                with (
                    patch.object(wheel_stage.Path, "cwd", return_value=self.root),
                    patch.object(wheel_stage.subprocess, "run"),
                ):
                    with self.assertRaisesRegex(
                        ValueError, "Staged wheel member differs from archive"
                    ):
                        wheel_stage.stage(self.dist)
                self.assertFalse(self.receipt.exists())

    def test_wheel_changed_during_install_cannot_produce_receipt(self):
        with (
            patch.object(wheel_stage.Path, "cwd", return_value=self.root),
            patch.object(
                wheel_stage.subprocess,
                "run",
                side_effect=lambda *args, **kwargs: self.wheel.write_bytes(b"changed wheel"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "wheel changed during staging"):
                wheel_stage.stage(self.dist)
        self.assertFalse(self.receipt.exists())


class GalleryDiagnostics(unittest.TestCase):
    def test_workflow_lifecycle_failures_and_cleanup_state(self):
        script = step(
            workflow("build-gallery.yml")["jobs"]["e2e-test"], "Run Gallery CDP E2E tests"
        )["run"]
        path = self.root / "workflow.ps1"
        path.write_text(script, encoding="utf-8")
        pwsh = shutil.which("pwsh")
        self.assertIsNotNone(pwsh, "PowerShell is required to check the Windows workflow lifecycle")
        result = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-File",
                str(ROOT / "scripts/ci/test_gallery_lifecycle.ps1"),
                str(path),
                str(self.root / "cases"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("Passed offline lifecycle scenario:"), 14)

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
