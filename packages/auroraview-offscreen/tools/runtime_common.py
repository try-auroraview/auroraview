"""Standard-library helpers for maintainer-only Electron packaging."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "runtime-lock.json"
CHUNK_SIZE = 1024 * 1024
MAX_EXPANDED_SIZE = 2 * 1024 * 1024 * 1024
MAX_FILES = 10000


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_lock(path: Path) -> dict[str, Any]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or lock.get("publisher") != "electron/electron":
        raise ValueError("Unsupported runtime lock")
    version = lock.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or lock.get("platform") != "win32-x64":
        raise ValueError("Only pinned stable Electron Windows x64 releases are supported")
    base = f"https://github.com/electron/electron/releases/download/v{version}/"
    if lock.get("release_api") != (
        f"https://api.github.com/repos/electron/electron/releases/tags/v{version}"
    ):
        raise ValueError("Runtime metadata must come from the official publisher")
    for key, name in (
        ("archive", f"electron-v{version}-win32-x64.zip"),
        ("checksums", "SHASUMS256.txt"),
    ):
        asset = lock[key]
        if asset["name"] != name or asset["url"] != base + name:
            raise ValueError("Runtime assets must come from the official publisher")
        if not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            raise ValueError("Invalid pinned SHA256")
        if not isinstance(asset["size"], int) or not 0 < asset["size"] <= MAX_EXPANDED_SIZE:
            raise ValueError("Invalid pinned asset size")
    if lock.get("licenses") != ["LICENSE", "LICENSES.chromium.html"]:
        raise ValueError("Publisher license files must be preserved")
    return lock


def digest_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def verify_file(path: Path, asset: dict[str, Any]) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != asset["size"]:
        raise ValueError(f"Unexpected file size or type: {path.name}")
    with path.open("rb") as stream:
        digest, _ = digest_stream(stream)
    if digest != asset["sha256"]:
        raise ValueError(f"SHA256 mismatch: {path.name}")


def verify_checksums(path: Path, lock: dict[str, Any]) -> None:
    verify_file(path, lock["checksums"])
    entries = [line.split() for line in path.read_text(encoding="utf-8").splitlines()]
    matches = [
        parts[0]
        for parts in entries
        if len(parts) == 2 and parts[1].removeprefix("*") == lock["archive"]["name"]
    ]
    if matches != [lock["archive"]["sha256"]]:
        raise ValueError("Publisher checksum list does not match the pinned archive")


def verify_release(release: dict[str, Any], lock: dict[str, Any]) -> None:
    if (
        release.get("tag_name") != "v" + lock["version"]
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Publisher release is not the pinned stable release")
    for key in ("archive", "checksums"):
        expected = lock[key]
        matches = [
            asset for asset in release.get("assets", []) if asset.get("name") == expected["name"]
        ]
        if (
            len(matches) != 1
            or any(
                matches[0].get(field) != expected[value]
                for field, value in (("size", "size"), ("browser_download_url", "url"))
            )
            or matches[0].get("digest") != "sha256:" + expected["sha256"]
        ):
            raise ValueError(f"GitHub publisher metadata mismatch: {expected['name']}")


def archive_files(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    files = []
    seen: set[str] = set()
    expanded = 0
    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or ":" in name
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))
            or stat.S_ISLNK(info.external_attr >> 16)
            or info.flag_bits & 1
        ):
            raise ValueError(f"Unsafe archive member: {name}")
        if name.rstrip("/").casefold() in seen:
            raise ValueError(f"Duplicate archive member: {name}")
        seen.add(name.rstrip("/").casefold())
        if not info.is_dir():
            files.append(info)
            expanded += info.file_size
    if len(files) > MAX_FILES or expanded > MAX_EXPANDED_SIZE:
        raise ValueError("Runtime archive exceeds extraction limits")
    names = {info.filename for info in files}
    if not {"electron.exe", "LICENSE", "LICENSES.chromium.html"} <= names:
        raise ValueError("Runtime archive is missing its executable or publisher notices")
    return sorted(files, key=lambda info: info.filename)


def verify_extracted(archive: zipfile.ZipFile, target: Path) -> None:
    if target.is_symlink() or not target.is_dir():
        raise ValueError("Runtime directory must be a regular directory")
    paths = list(target.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("Runtime directory contains a symlink")
    files = archive_files(archive)
    if {path.relative_to(target).as_posix() for path in paths if path.is_file()} != {
        info.filename for info in files
    }:
        raise ValueError("Extracted runtime contents differ from the publisher archive")
    for info in files:
        with archive.open(info) as source, (target / info.filename).open("rb") as local:
            if digest_stream(source) != digest_stream(local):
                raise ValueError(f"Extracted runtime checksum mismatch: {info.filename}")


def provenance(lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "publisher": lock["publisher"],
        "version": lock["version"],
        "platform": lock["platform"],
        "release_api": lock["release_api"],
        "release_url": lock["release_url"],
        "archive": lock["archive"],
        "checksums": lock["checksums"],
        "sources": lock["sources"],
        "redistribution": lock["redistribution"],
        "verification": ["pinned_sha256", "publisher_shasums256", "github_asset_digest"],
    }
