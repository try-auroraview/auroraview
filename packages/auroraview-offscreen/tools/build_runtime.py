"""Build a portable runtime from previously acquired, verified publisher assets.

No network requests or Node installation are performed. --bridge accepts the SDK
build output, never a separately maintained copy of the bridge implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from runtime_common import (
    CHUNK_SIZE,
    DEFAULT_LOCK,
    archive_files,
    digest_stream,
    json_bytes,
    load_lock,
    provenance,
    verify_checksums,
    verify_file,
    verify_release,
)

HELPER_FILES = (
    "package.json",
    "main.cjs",
    "stdio.cjs",
    "input.cjs",
    "preload.cjs",
    "protocol.cjs",
    "pixels.cjs",
    "protocol.json",
)
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def member_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    # Stored members guarantee identical bytes across Python/zlib versions.
    info.compress_type = zipfile.ZIP_STORED
    return info


def regular_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular source file: {path}")
    return path


def build(lock_path: Path, acquired: Path, helper: Path, bridge: Path, output: Path) -> str:
    lock = load_lock(lock_path)
    archive_path = acquired / lock["archive"]["name"]
    verify_file(archive_path, lock["archive"])
    verify_checksums(acquired / lock["checksums"]["name"], lock)
    release = json.loads((acquired / "publisher-release.json").read_text(encoding="utf-8"))
    verify_release(release, lock)
    sources = {f"helper/{name}": regular_file(helper / name) for name in HELPER_FILES}
    sources["helper/event_bridge.js"] = regular_file(bridge)
    # Keep the project's license distinct from the publisher's electron/LICENSE.
    sources["helper/LICENSE"] = regular_file(Path(__file__).resolve().parents[3] / "LICENSE")
    for path in sources.values():
        if path.stat().st_size > 16 * CHUNK_SIZE:
            raise ValueError(f"Helper asset exceeds its size limit: {path.name}")
    output = output.resolve()
    inputs = {
        lock_path,
        archive_path,
        acquired / lock["checksums"]["name"],
        acquired / "publisher-release.json",
        *sources.values(),
    }
    if output.suffix.lower() != ".zip":
        raise ValueError("The portable output must be a ZIP archive")
    if output in {path.resolve() for path in inputs}:
        raise ValueError("The output must not overwrite an input asset")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
    os.close(descriptor)
    manifest = {
        "schema_version": 1,
        "runtime": {"version": lock["version"], "platform": lock["platform"]},
        "launch": {"executable": "electron/electron.exe", "helper": "helper"},
        "files": {},
    }
    try:
        with zipfile.ZipFile(archive_path) as publisher, zipfile.ZipFile(temporary, "w") as bundle:
            files = {"electron/" + info.filename: info for info in archive_files(publisher)}
            metadata = {
                "runtime-lock.json": json_bytes(lock),
                "provenance.json": json_bytes(provenance(lock)),
                "SHASUMS256.txt": (acquired / lock["checksums"]["name"]).read_bytes(),
            }
            for name in sorted(set(files) | set(sources) | set(metadata)):
                if name in files:
                    source = publisher.open(files[name])
                elif name in sources:
                    source = sources[name].open("rb")
                else:
                    source = io.BytesIO(metadata[name])
                digest = hashlib.sha256()
                size = 0
                with source, bundle.open(member_info(name), "w", force_zip64=True) as target:
                    while chunk := source.read(CHUNK_SIZE):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                manifest["files"][name] = {"sha256": digest.hexdigest(), "size": size}
            bundle.writestr(member_info("bundle-manifest.json"), json_bytes(manifest))
        verify(Path(temporary))
        Path(temporary).replace(output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    with output.open("rb") as stream:
        digest, _ = digest_stream(stream)
    return digest


def verify(path: Path) -> None:
    """Verify every portable member before publication; no runtime execution."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("Duplicate bundle member")
        for info in archive.infolist():
            if (
                not info.filename
                or "\\" in info.filename
                or ":" in info.filename
                or PurePosixPath(info.filename).is_absolute()
                or any(part in ("", ".", "..") for part in info.filename.split("/"))
                or info.is_dir()
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise ValueError(f"Unsafe bundle member: {info.filename}")
        manifest = json.loads(archive.read("bundle-manifest.json"))
        if manifest.get("schema_version") != 1 or manifest.get("launch") != {
            "executable": "electron/electron.exe",
            "helper": "helper",
        }:
            raise ValueError("Unsupported bundle manifest")
        if set(names) != set(manifest["files"]) | {"bundle-manifest.json"}:
            raise ValueError("Bundle contents do not match the manifest")
        required = {f"helper/{name}" for name in HELPER_FILES} | {
            "electron/electron.exe",
            "electron/LICENSE",
            "electron/LICENSES.chromium.html",
            "helper/event_bridge.js",
            "helper/LICENSE",
            "runtime-lock.json",
            "provenance.json",
            "SHASUMS256.txt",
        }
        if not required <= set(names):
            raise ValueError("Bundle is missing required runtime, helper or provenance files")
        lock = json.loads(archive.read("runtime-lock.json"))
        if manifest["runtime"] != {"version": lock["version"], "platform": lock["platform"]}:
            raise ValueError("Bundle runtime identity does not match its lock")
        if json.loads(archive.read("provenance.json")) != provenance(lock):
            raise ValueError("Bundle provenance does not match its lock")
        for name, expected in manifest["files"].items():
            with archive.open(name) as stream:
                digest, size = digest_stream(stream)
            if expected != {"sha256": digest, "size": size}:
                raise ValueError(f"Bundle member checksum mismatch: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--acquired", type=Path)
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path, help="Verify an existing bundle without rebuilding")
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
        print("Verified every portable bundle member")
    else:
        if any(value is None for value in (args.acquired, args.helper, args.bridge, args.output)):
            parser.error("--acquired, --helper, --bridge and --output are required for building")
        print(build(args.lock, args.acquired, args.helper, args.bridge, args.output))


if __name__ == "__main__":
    main()
