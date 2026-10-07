"""Pin the experimental CI lane to executables resolved by official rustup.

vx can select a cached stable rustc even after rustup default changes. Keep vx
and just as entry points, but use rustup's explicit toolchain for cargo recipes
and maturin's documented Cargo/compiler environment for the wheel build.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "1.90.0"
TOOLS = {"CARGO": "cargo", "RUSTC": "rustc", "RUSTDOC": "rustdoc", "RUSTFMT": "rustfmt"}


def output(arguments):
    return subprocess.check_output(arguments, text=True).strip()


def main():
    receipt = Path("hosted-gtk-evidence/rust-toolchain.json")
    if sys.argv[1:] == ["--verify-environment"]:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        for variable, expected in data["paths"].items():
            if os.environ.get(variable) != expected:
                raise RuntimeError("Build environment lost pinned " + variable)
        if os.environ.get("RUSTUP_TOOLCHAIN") != VERSION:
            raise RuntimeError("Build environment lost the pinned Rust toolchain")
        print("Verified exact Cargo/compiler paths in the wheel build environment")
        return
    if sys.argv[1:]:
        raise RuntimeError("Unsupported arguments")
    versions = {}
    for tool in ("cargo", "rustc"):
        value = output(["vx", "rustup", "run", VERSION, tool, "--version"])
        if not value.startswith(tool + " " + VERSION + " "):
            raise RuntimeError("Explicit rustup toolchain mismatch: " + value)
        versions[tool] = value
    paths = {}
    for variable, tool in TOOLS.items():
        value = output(["vx", "rustup", "which", "--toolchain", VERSION, tool])
        path = Path(value)
        if not path.is_absolute() or not path.is_file() or "\n" in value or "\r" in value:
            raise RuntimeError("rustup returned an invalid executable path for " + tool)
        paths[variable] = str(path.resolve())
    if len({str(Path(path).parent) for path in paths.values()}) != 1:
        raise RuntimeError("Resolved Rust tools do not share one toolchain bin directory")
    environment_file = Path(os.environ["GITHUB_ENV"])
    with environment_file.open("a", encoding="utf-8") as handle:
        for variable, path in paths.items():
            handle.write(variable + "=" + path + "\n")
        handle.write("RUSTUP_TOOLCHAIN=" + VERSION + "\n")
    data = {"toolchain": VERSION, "versions": versions, "paths": paths}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
