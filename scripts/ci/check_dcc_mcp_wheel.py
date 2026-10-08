"""Run contracts against an installed wheel, outside the source checkout."""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", type=Path, required=True)
    args = parser.parse_args()

    import auroraview_dcc_mcp

    module = Path(auroraview_dcc_mcp.__file__).resolve()
    distribution = metadata.distribution("auroraview-dcc-mcp")
    origin = json.loads(distribution.read_text("direct_url.json") or "{}")
    if "archive_info" not in origin or not urlparse(origin.get("url", "")).path.endswith(".whl"):
        raise RuntimeError("Contract distribution was not installed from a wheel archive")
    member = next(
        (
            item
            for item in distribution.files or []
            if str(item).replace("\\", "/") == "auroraview_dcc_mcp/__init__.py"
        ),
        None,
    )
    if member is None or module != Path(distribution.locate_file(member)).resolve():
        raise RuntimeError(
            "Imported contract module is outside its wheel RECORD: {}".format(module)
        )
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(module.read_bytes()).digest()).rstrip(b"=").decode()
    )
    if member.hash is None or member.hash.mode != "sha256" or member.hash.value != digest:
        raise RuntimeError("Installed contract module does not match its wheel RECORD hash")
    forbidden = ("auroraview", "qtpy", "bpy", "unreal")
    if any(name in sys.modules for name in forbidden):
        raise RuntimeError("Importing contracts loaded a native renderer or host SDK")

    print(
        json.dumps(
            {
                "module": str(module),
                "version": distribution.version,
                "python": sys.version,
                "wheel_origin": origin,
                "installed_wheel": True,
            }
        )
    )
    with tempfile.TemporaryDirectory(prefix="auroraview-wheel-consumer-") as directory:
        tests = Path(directory) / "tests"
        shutil.copytree(
            str(args.tests.resolve()), str(tests), ignore=shutil.ignore_patterns("__pycache__")
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        return subprocess.call(
            [sys.executable, "-m", "pytest", "tests", "-v", "--timeout=60"],
            cwd=directory,
            env=environment,
        )


if __name__ == "__main__":
    sys.exit(main())
