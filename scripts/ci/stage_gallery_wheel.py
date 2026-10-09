"""Stage one native Gallery wheel beside matching checkout sources (Python 3.11+)."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath


def stage(wheel_dir):
    wheels = list(wheel_dir.glob("*.whl"))
    if len(wheels) != 1 or not wheels[0].is_file():
        raise ValueError("Exactly one wheel is required in the Gallery wheel directory")
    wheel = wheels[0].resolve()
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    filename_parts = wheel.stem.rsplit("-", 3)
    if len(filename_parts) != 4 or not filename_parts[0].startswith("auroraview-"):
        raise ValueError("The Gallery wheel must be an auroraview distribution")

    root = Path.cwd()
    target = (root / "python").resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("The Gallery Python target resolves outside the checkout")
    with zipfile.ZipFile(wheel) as archive:
        paths = set()
        files = {}
        for info in archive.infolist():
            name = info.orig_filename.rstrip("/")
            path = PurePosixPath(name)
            if (
                not name
                or "\\" in name
                or "\0" in name
                or ":" in name
                or path.is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))
                or stat.S_ISLNK(info.external_attr >> 16)
                or not (target / name).resolve().is_relative_to(target)
            ):
                raise ValueError(f"Unsafe wheel member path: {info.filename}")
            if name.casefold() in paths:
                raise ValueError(f"Duplicate wheel member path: {info.filename}")
            paths.add(name.casefold())
            if not info.is_dir():
                files[name] = archive.read(info)

        metadata_names = [name for name in files if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("Exactly one wheel distribution metadata file is required")
        metadata_name = metadata_names[0]
        metadata = BytesParser().parsebytes(files[metadata_name])
        if metadata.get("Name", "").lower() != "auroraview":
            raise ValueError("The Gallery wheel metadata must name auroraview")
        dist_info = metadata_name.split("/")[0]
        if any(
            PurePosixPath(name).parts[0] not in ("auroraview", "auroraview.libs", dist_info)
            for name in files
        ):
            raise ValueError("Unexpected package path in the Gallery wheel")
        wheel_metadata = BytesParser().parsebytes(files[f"{dist_info}/WHEEL"])
        tags = wheel_metadata.get_all("Tag", [])
        if not tags:
            raise ValueError("The Gallery wheel must declare compatibility tags")

        members = {
            name: data
            for name, data in files.items()
            if name.startswith(("auroraview/", "auroraview.libs/"))
        }
        native = {
            name: data
            for name, data in members.items()
            if name.endswith((".pyd", ".so", ".dll", ".dylib")) or ".so." in name
        }
        if not any(
            PurePosixPath(name).parent == PurePosixPath("auroraview")
            and PurePosixPath(name).name.startswith("_core")
            and name.endswith((".pyd", ".so"))
            for name in native
        ):
            raise ValueError("The Gallery wheel has no native auroraview/_core extension")
        python_sources = [
            name for name in members if name.startswith("auroraview/") and name.endswith(".py")
        ]
        for name in python_sources:
            source = target / name
            if not source.is_file() or source.read_bytes() != members[name]:
                raise ValueError(f"Wheel Python source differs from checkout: {name}")

    subprocess.run(
        [
            "vx",
            "uv",
            "pip",
            "install",
            "--python",
            "3.11",
            "--target",
            "python",
            "--no-deps",
            "--upgrade",
            str(wheel),
        ],
        cwd=root,
        check=True,
    )
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != wheel_sha256:
        raise ValueError("Gallery wheel changed during staging")
    for name, data in members.items():
        installed = target / name
        if not installed.is_file() or installed.read_bytes() != data:
            raise ValueError(f"Staged wheel member differs from archive: {name}")

    receipt = {
        "boundary": "Wheel staging only; collected packed payload is not verified",
        "provenance": {
            "source_head": os.environ.get("GALLERY_SOURCE_HEAD"),
            "checkout_sha": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "wheel_artifact": os.environ.get("GALLERY_WHEEL_ARTIFACT"),
            "binding": "Environment declarations; not remote attestation",
        },
        "wheel": {
            "filename": wheel.name,
            "sha256": wheel_sha256,
            "filename_tags": dict(
                zip(("python", "abi", "platform"), filename_parts[1:], strict=True)
            ),
            "tags": tags,
        },
        "python_sources_verified": len(python_sources),
        "package_files_verified": len(members),
        "native_members": [
            {"path": name, "length": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(native.items())
        ],
    }
    receipt_path = root / "test-results/gallery-wheel/receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Staged and verified Gallery wheel: {wheel.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel_dir", type=Path)
    stage(parser.parse_args().wheel_dir)
