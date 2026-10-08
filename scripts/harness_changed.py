from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Dict, Iterable, List, Optional


def _run_name_only(args: List[str]) -> List[str]:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


IGNORED_PREFIXES = ()
IGNORED_FILES = {".gitcommitmsg"}

CI_FILES = {
    "Cargo.lock",
    "Cargo.toml",
    "justfile",
    "noxfile.py",
    "pyproject.toml",
    "vx.toml",
    ".config/nextest.toml",
    ".cargo/mutants.toml",
}


def _normalize_paths(paths: Iterable[str]) -> List[str]:
    unique_paths: List[str] = []
    for path in paths:
        if not path:
            continue
        if path in IGNORED_FILES:
            continue
        if any(path.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        if path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def list_changed_files(base: str) -> List[str]:
    committed = _run_name_only(["vx", "git", "diff", "--name-only", "{0}...HEAD".format(base)])
    worktree = _run_name_only(["vx", "git", "diff", "--name-only", "HEAD"])
    untracked = _run_name_only(["vx", "git", "ls-files", "--others", "--exclude-standard"])
    return _normalize_paths(committed + worktree + untracked)


def classify_changes(paths: Iterable[str]) -> Dict[str, bool]:
    flags = {
        "ci": False,
        "rust": False,
        "python_unit": False,
        "python_integration": False,
        "sdk": False,
        "assets": False,
        "gallery": False,
        "docs": False,
    }

    for path in paths:
        if path in CI_FILES or path.startswith(".github/"):
            flags["ci"] = True
        if (
            path.endswith(".rs")
            or path.startswith("src/")
            or path.startswith("crates/")
            or path.startswith("benches/")
            or path.startswith("tests/rust/")
            or path == ".config/nextest.toml"
        ):
            flags["rust"] = True
        if path.startswith("python/") or path.startswith("tests/python/unit/"):
            flags["python_unit"] = True
        if path.startswith("python/") or path.startswith("tests/python/integration/"):
            flags["python_integration"] = True
        if path.startswith("packages/auroraview-sdk/"):
            flags["sdk"] = True
        if path.startswith("crates/auroraview-assets/frontend/"):
            flags["assets"] = True
        if path.startswith("gallery/"):
            flags["gallery"] = True
        if path.startswith("docs/") or path.endswith(".md"):
            flags["docs"] = True

    return flags



def build_command_plan(paths: Iterable[str]) -> List[str]:
    path_list = list(paths)
    if not path_list:
        return ["vx just harness-quick"]

    flags = classify_changes(path_list)
    commands: List[str] = []

    if flags["ci"]:
        commands.append("vx just harness-verify")
    else:
        if flags["rust"]:
            commands.append("vx just test-rust-fast")
        if flags["python_unit"]:
            commands.append("vx just test-python-unit-fast")
        if flags["python_integration"]:
            commands.append("vx just test-python-integration")

    if flags["assets"]:
        commands.append("vx just assets-ci")
    if flags["sdk"]:
        commands.append("vx just sdk-ci")
    if flags["gallery"]:
        commands.append("vx just gallery-verify")
    if flags["docs"] and not commands:
        commands.append("vx just ci-docs-build")
    if not commands:
        commands.append("vx just harness-quick")

    unique_commands: List[str] = []
    for command in commands:
        if command not in unique_commands:
            unique_commands.append(command)
    return unique_commands



def run_plan(commands: Iterable[str]) -> int:
    for command in commands:
        print("==> {0}".format(command))
        result = subprocess.run(command, shell=True)
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the smallest useful AuroraView verification plan."
    )
    parser.add_argument(
        "--base", default="origin/main", help="Git base ref used for diff selection."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan without executing commands."
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="Print changed files before the command plan.",
    )
    args = parser.parse_args(argv)

    paths = list_changed_files(args.base)
    commands = build_command_plan(paths)

    if args.list_files:
        if paths:
            print("Changed files:")
            for path in paths:
                print("  - {0}".format(path))
        else:
            print("Changed files: <none>")

    print("Selected commands:")
    for command in commands:
        print("  - {0}".format(command))

    if args.dry_run:
        return 0
    return run_plan(commands)


if __name__ == "__main__":
    sys.exit(main())
