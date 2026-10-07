"""Resolve the managed Python shared library for this Linux CI test lane only.

Relocatable Python distributions can retain a build-time sysconfig LIBDIR.
Keep PyO3's interpreter-derived ABI configuration, and add the verified runtime
library directory to the compiler and loader search paths after the wheel build.
"""

import argparse
import ctypes
import json
import os
import sys
import sysconfig
from pathlib import Path

RECEIPT = Path("hosted-gtk-evidence/python-embedding.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-environment", action="store_true")
    args = parser.parse_args()
    if sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This helper is restricted to the Linux GitHub Actions lane")
    if sys.implementation.name != "cpython" or sys.version_info[:3] != (3, 11, 15):
        raise RuntimeError("Expected the lane's managed CPython 3.11.15")
    if os.environ.get("RUSTUP_TOOLCHAIN") != "1.95.0":
        raise RuntimeError("Select the development compiler after building the wheel first")
    config = {
        key: sysconfig.get_config_var(key)
        for key in (
            "LIBDIR",
            "LIBPL",
            "LDLIBRARY",
            "INSTSONAME",
            "Py_ENABLE_SHARED",
            "SOABI",
            "MULTIARCH",
        )
    }
    executable = Path(sys.executable).resolve(strict=True)
    prefix = Path(sys.base_prefix).resolve(strict=True)
    print(
        json.dumps({"executable": str(executable), "base_prefix": str(prefix), **config}, indent=2)
    )
    name = config["LDLIBRARY"]
    if not config["Py_ENABLE_SHARED"] or not isinstance(name, str) or not name.endswith(".so"):
        raise RuntimeError("The selected Python must provide a Linux shared link library")
    if Path(name).name != name:
        raise RuntimeError("LDLIBRARY must be a library filename")
    library = prefix / "lib" / name
    resolved = library.resolve(strict=True)
    if not executable.is_file() or not resolved.is_file() or prefix not in resolved.parents:
        raise RuntimeError("Expected a regular Python library inside the managed interpreter")
    reported = Path(config["LIBDIR"]) / name if config["LIBDIR"] else None
    if reported is not None and reported.exists() and not reported.samefile(library):
        raise RuntimeError("sysconfig LIBDIR contains a different library with linker priority")
    runtime = ctypes.CDLL(str(resolved))
    runtime.Py_GetVersion.argtypes = []
    runtime.Py_GetVersion.restype = ctypes.c_char_p
    runtime_version = runtime.Py_GetVersion().decode("utf-8")
    if runtime_version != sys.version:
        raise RuntimeError("The shared library's Py_GetVersion does not match the interpreter")
    current = {
        "executable": str(executable),
        "base_prefix": str(prefix),
        "sysconfig": config,
        "link_library": str(library),
        "resolved_library": str(resolved),
        "runtime_version": runtime_version,
        "pointer_width": ctypes.sizeof(ctypes.c_void_p) * 8,
    }
    if args.verify_environment:
        saved = json.loads(RECEIPT.read_text(encoding="utf-8"))
        if saved["python"] != current:
            raise RuntimeError("Python no longer matches the embedding receipt")
        for key, value in saved["environment"].items():
            if os.environ.get(key) != value:
                raise RuntimeError("Embedding environment lost pinned " + key)
        print(json.dumps(saved, indent=2))
        print("Verified interpreter, shared-library identity, and embedding search paths")
        return
    environment = {"PYO3_PYTHON": str(executable)}
    for key in ("LIBRARY_PATH", "LD_LIBRARY_PATH"):
        previous = os.environ.get(key, "")
        environment[key] = str(library.parent) + (os.pathsep + previous if previous else "")
    for value in environment.values():
        if "\n" in value or "\r" in value:
            raise RuntimeError("Cannot write a multiline environment value")
    receipt = {"python": current, "environment": environment}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as handle:
        for key, value in environment.items():
            handle.write(key + "=" + value + "\n")
    print(json.dumps(receipt, indent=2))
    print("Prepared CI embedding paths; Rust linking and test execution remain separate checks")


if __name__ == "__main__":
    main()
