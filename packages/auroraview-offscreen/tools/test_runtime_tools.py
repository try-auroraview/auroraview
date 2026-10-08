"""Bounded publisher acquisition and portable artifact integrity regressions."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import acquire_runtime
import build_runtime
from runtime_common import (
    DEFAULT_LOCK,
    archive_files,
    json_bytes,
    load_lock,
    verify_checksums,
    verify_extracted,
    verify_release,
)


def asset_bytes(asset: dict, data: bytes) -> dict:
    return dict(asset, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def release_metadata(lock: dict) -> dict:
    return {
        "tag_name": "v" + lock["version"],
        "draft": False,
        "prerelease": False,
        "assets": [
            dict(
                name=lock[key]["name"],
                size=lock[key]["size"],
                browser_download_url=lock[key]["url"],
                digest="sha256:" + lock[key]["sha256"],
            )
            for key in ("archive", "checksums")
        ],
    }


class RuntimeToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lock = load_lock(DEFAULT_LOCK)

    def test_official_urls_only(self):
        self.lock["archive"]["url"] = "https://example.com/runtime.zip"
        path = self.root / "lock.json"
        path.write_bytes(json_bytes(self.lock))
        with self.assertRaisesRegex(ValueError, "official publisher"):
            load_lock(path)

    def test_release_requires_publisher_digest_and_exact_size(self):
        for field, value in (
            ("digest", None),
            ("size", 1),
            ("browser_download_url", "https://example.com"),
        ):
            with self.subTest(field=field):
                release = release_metadata(self.lock)
                release["assets"][0][field] = value
                with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                    verify_release(release, self.lock)

    def test_checksums_accept_binary_marker_and_refuse_duplicates(self):
        line = f"{self.lock['archive']['sha256']} *{self.lock['archive']['name']}\n".encode()
        path = self.root / "SHASUMS256.txt"
        for data, valid in ((line, True), (line + line, False)):
            path.write_bytes(data)
            self.lock["checksums"] = asset_bytes(self.lock["checksums"], data)
            if valid:
                verify_checksums(path, self.lock)
            else:
                with self.assertRaisesRegex(ValueError, "checksum list"):
                    verify_checksums(path, self.lock)

    def test_download_limit_and_digest_failure_remove_partial_files(self):
        asset = asset_bytes(self.lock["archive"], b"abc")
        for data in (b"abcd", b"bad"):
            with (
                self.subTest(data=data),
                patch.object(acquire_runtime, "request", return_value=io.BytesIO(data)),
            ):
                with self.assertRaises(ValueError):
                    acquire_runtime.download(asset, self.root / "asset.zip")
                self.assertEqual(list(self.root.iterdir()), [])

    def test_cached_download_is_verified_without_network(self):
        data = b"abc"
        target = self.root / "asset.zip"
        target.write_bytes(data)
        with patch.object(acquire_runtime, "request") as request:
            acquire_runtime.download(asset_bytes(self.lock["archive"], data), target)
        request.assert_not_called()

    def test_archive_refuses_traversal_duplicate_case_and_symlink(self):
        for name, attributes in (
            ("../outside", 0),
            ("C:/outside", 0),
            ("link", stat.S_IFLNK << 16),
            ("LICENSE", 0),
        ):
            with self.subTest(name=name):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr("license", b"notice")
                    info = zipfile.ZipInfo(name)
                    info.external_attr = attributes
                    archive.writestr(info, b"unsafe")
                with zipfile.ZipFile(buffer) as archive, self.assertRaises(ValueError):
                    archive_files(archive)

    def setup_build(self):
        acquired = self.root / "acquired"
        helper = self.root / "helper"
        acquired.mkdir()
        helper.mkdir()
        archive_path = acquired / self.lock["archive"]["name"]
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name in (
                "electron.exe",
                "LICENSE",
                "LICENSES.chromium.html",
                "resources/default_app.asar",
            ):
                archive.writestr(name, name.encode())
        self.lock["archive"] = asset_bytes(self.lock["archive"], archive_path.read_bytes())
        checksums = f"{self.lock['archive']['sha256']} *{archive_path.name}\n".encode()
        self.lock["checksums"] = asset_bytes(self.lock["checksums"], checksums)
        (acquired / "SHASUMS256.txt").write_bytes(checksums)
        (acquired / "publisher-release.json").write_bytes(json_bytes(release_metadata(self.lock)))
        lock_path = self.root / "lock.json"
        lock_path.write_bytes(json_bytes(self.lock))
        for name in build_runtime.HELPER_FILES:
            (helper / name).write_text(name, encoding="utf-8")
        (helper / "unwanted.log").write_text("exclude", encoding="utf-8")
        bridge = self.root / "event_bridge.js"
        bridge.write_text("window.auroraview = {};", encoding="utf-8")
        return lock_path, acquired, helper, bridge

    def test_build_is_reproducible_complete_and_excludes_undeclared_assets(self):
        args = self.setup_build()
        first, second = self.root / "first.zip", self.root / "second.zip"
        self.assertEqual(build_runtime.build(*args, first), build_runtime.build(*args, second))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertNotIn("helper/unwanted.log", archive.namelist())
            for name in (
                "electron/LICENSE",
                "electron/LICENSES.chromium.html",
                "helper/LICENSE",
                "helper/event_bridge.js",
                "provenance.json",
            ):
                self.assertIn(name, archive.namelist())
            self.assertEqual(
                json.loads(archive.read("bundle-manifest.json"))["launch"]["executable"],
                "electron/electron.exe",
            )

    def test_missing_bridge_or_helper_fails_before_output(self):
        args = self.setup_build()
        args[-1].unlink()
        with self.assertRaisesRegex(ValueError, "regular source file"):
            build_runtime.build(*args, self.root / "bundle.zip")
        self.assertFalse((self.root / "bundle.zip").exists())

    def test_verify_detects_tampered_members(self):
        args = self.setup_build()
        bundle = self.root / "bundle.zip"
        build_runtime.build(*args, bundle)
        corrupted = self.root / "corrupted.zip"
        with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(corrupted, "w") as target:
            for name in source.namelist():
                target.writestr(
                    name, b"tampered" if name == "helper/main.cjs" else source.read(name)
                )
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            build_runtime.verify(corrupted)

    def test_reused_extraction_refuses_added_or_changed_files(self):
        args = self.setup_build()
        archive_path = args[1] / self.lock["archive"]["name"]
        target = self.root / "electron"
        target.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(target)
            verify_extracted(archive, target)
            (target / "electron.exe").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify_extracted(archive, target)


if __name__ == "__main__":
    unittest.main()
