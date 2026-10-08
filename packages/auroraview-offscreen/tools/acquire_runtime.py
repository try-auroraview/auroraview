"""Explicit maintainer command; never called by the Blender add-on or client.

python acquire_runtime.py --output /path/to/electron-44.7.0
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from runtime_common import (
    CHUNK_SIZE,
    DEFAULT_LOCK,
    archive_files,
    json_bytes,
    load_lock,
    provenance,
    verify_checksums,
    verify_extracted,
    verify_file,
    verify_release,
)


def request(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "auroraview-offscreen-maintainer"}),
        timeout=60,
    )


def download(asset: dict[str, Any], target: Path) -> None:
    if target.exists():
        verify_file(target, asset)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, request(asset["url"]) as response:
            remaining = asset["size"]
            while chunk := response.read(min(CHUNK_SIZE, remaining + 1)):
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError("Download exceeds the pinned publisher asset size")
                output.write(chunk)
        verify_file(Path(temporary), asset)
        Path(temporary).replace(target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def acquire(lock_path: Path, output: Path) -> Path:
    lock = load_lock(lock_path)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with request(lock["release_api"]) as response:
        release_bytes = response.read(2 * CHUNK_SIZE + 1)
    if len(release_bytes) > 2 * CHUNK_SIZE:
        raise ValueError("Publisher release metadata exceeds its size limit")
    release = json.loads(release_bytes)
    verify_release(release, lock)
    print("Verified GitHub publisher asset digests", flush=True)
    checksum_path = output / lock["checksums"]["name"]
    archive_path = output / lock["archive"]["name"]
    download(lock["checksums"], checksum_path)
    verify_checksums(checksum_path, lock)
    print("Verified publisher SHASUMS256; downloading runtime", flush=True)
    download(lock["archive"], archive_path)
    print("Verified runtime archive; extracting", flush=True)
    target = output / "electron"
    if target.exists():
        with zipfile.ZipFile(archive_path) as archive:
            verify_extracted(archive, target)
    else:
        with tempfile.TemporaryDirectory(prefix="electron-extract-", dir=output) as temporary:
            staging = Path(temporary) / "electron"
            staging.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive_files(archive):
                    destination = staging.joinpath(*info.filename.split("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("xb") as sink:
                        shutil.copyfileobj(source, sink, CHUNK_SIZE)
            staging.rename(target)
    (output / "runtime-lock.json").write_bytes(json_bytes(lock))
    (output / "provenance.json").write_bytes(json_bytes(provenance(lock)))
    # Keep the publisher response as acquisition evidence, outside distributable bundles.
    (output / "publisher-release.json").write_bytes(json_bytes(release))
    return target / "electron.exe"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(acquire(args.lock, args.output))


if __name__ == "__main__":
    main()
