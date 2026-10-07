"""Pin each experimental CI lane to executables resolved by official rustup.

vx can select a cached stable rustc even after rustup default changes. Keep vx
and just as entry points, but use rustup's explicit toolchain for cargo recipes
and maturin's documented Cargo/compiler environment for the wheel build.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

TOOLCHAINS = {"production": "1.90.0", "development": "1.95.0"}
TOOLS = {"CARGO": "cargo", "RUSTC": "rustc", "RUSTDOC": "rustdoc", "RUSTFMT": "rustfmt"}


def output(arguments):
    return subprocess.check_output(arguments, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=TOOLCHAINS)
    parser.add_argument("--verify-environment", action="store_true")
    args = parser.parse_args()
    version = TOOLCHAINS[args.lane]
    receipt = Path("hosted-gtk-evidence/rust-toolchain-" + args.lane + ".json")
    if args.verify_environment:
        data = json.loads(receipt.read_text(encoding="utf-8"))
        if data["lane"] != args.lane or data["toolchain"] != version:
            raise RuntimeError("Receipt does not match the requested Rust lane")
        if set(data["paths"]) != set(TOOLS):
            raise RuntimeError("Receipt does not contain every pinned Rust tool")
        for variable, expected in data["paths"].items():
            if os.environ.get(variable) != expected:
                raise RuntimeError("Build environment lost pinned " + variable)
        if os.environ.get("RUSTUP_TOOLCHAIN") != version:
            raise RuntimeError("Build environment lost the pinned Rust toolchain")
    paths = {}
    for variable, tool in TOOLS.items():
        value = output(["vx", "rustup", "which", "--toolchain", version, tool])
        path = Path(value)
        if not path.is_absolute() or not path.is_file() or "\n" in value or "\r" in value:
            raise RuntimeError("rustup returned an invalid executable path for " + tool)
        paths[variable] = str(path.resolve())
    if len({str(Path(path).parent) for path in paths.values()}) != 1:
        raise RuntimeError("Resolved Rust tools do not share one toolchain bin directory")
    versions = {}
    for variable in ("CARGO", "RUSTC"):
        tool = TOOLS[variable]
        value = output(["vx", "rustup", "run", version, paths[variable], "--version"])
        if not value.startswith(tool + " " + version + " "):
            raise RuntimeError("Explicit rustup toolchain mismatch: " + value)
        versions[tool] = value
    current = {"lane": args.lane, "toolchain": version, "versions": versions, "paths": paths}
    if args.verify_environment:
        if data != current:
            raise RuntimeError("Rust toolchain no longer matches the lane receipt")
        print(json.dumps(current, indent=2))
        print("Verified exact Cargo/compiler paths and versions for " + args.lane)
        return
    environment_file = Path(os.environ["GITHUB_ENV"])
    with environment_file.open("a", encoding="utf-8") as handle:
        for variable, path in paths.items():
            handle.write(variable + "=" + path + "\n")
        handle.write("RUSTUP_TOOLCHAIN=" + version + "\n")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(current, indent=2))


if __name__ == "__main__":
    main()
