#!/usr/bin/env python3
"""Preflight guard for the prebuilt-wheel ``python-tests`` CI lanes (GH-528).

Why this exists
---------------
``tests/python/unit/test_run_desktop_icon.py`` pins the ``run_desktop(icon=...)``
contract at the PyO3 boundary. It opens with a module-level
``pytest.importorskip("auroraview._core")``. On Linux the ABI3 wheel's ``_core``
is dynamically linked against ``libxdo.so.3`` (active-win-pos-rs) and the
WebKit/GTK stack (wry/tao). If a required Linux runtime library is missing,
``import auroraview._core`` raises ``ImportError``. Under pytest >= 9 that
becomes a hard collection error; under pytest 8 it degrades to a warning and
the *whole module is silently skipped* -- the lane goes green while the icon
signature/documentation checks never run.

A green wheel lane is only meaningful if the native extension really imports
and the GH-528 icon checks are really collected. This guard runs inside the
wheel lanes and fails loudly (exit != 0) when either condition is not met, so a
missing runtime package can never masquerade as a passing lane again. It runs
in the lane's own interpreter (the one with the wheel installed), independent
of pytest's version-specific ``importorskip`` behaviour.

What it checks
--------------
1. ``import auroraview._core`` succeeds here (not swallowed by ``importorskip``).
2. ``pytest --collect-only`` collects the three GH-528 icon check functions
   (two parameterized + docstring + round-trip) from the icon test file, with
   no collection error and nothing skipped at module level.

The round-trip check legitimately self-skips at runtime on release wheels (the
``test-helpers`` feature gate); collection is what this guard requires, not a
pass. This is a deterministic, offline check. It does NOT launch a GUI window
and makes no claim about native window-icon rendering -- that remains covered
by the Rust tests in ``src/webview/desktop/icon.rs``.

Usage
-----
    python scripts/ci/check_wheel_native_import.py

Exit codes: 0 = verified, 1 = contract violated, 2 = could not run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_TEST = "tests/python/unit/test_run_desktop_icon.py"

# Test function names that must appear in the collected node IDs. Parameterized
# cases (test_runner_accepts_icon_kwarg[run_desktop|run_standalone]) collapse
# to this single name, so a substring match is sufficient and path-format
# independent (Windows vs POSIX separators).
EXPECTED_ICON_CHECKS = (
    "test_runner_accepts_icon_kwarg",
    "test_run_desktop_icon_is_documented",
    "test_run_desktop_icon_kwarg_round_trip",
)


def verify_native_import(import_result) -> list[str]:
    """Return problems for a native import attempt.

    ``import_result`` is ``(ok, detail)``: ``ok`` is True when the import
    succeeded, ``detail`` is the import error text on failure. A failed import
    is a hard problem -- the whole point is that it must not degrade into a
    silent skip.
    """
    ok, detail = import_result
    if ok:
        return []
    return [
        "auroraview._core could not be imported: {}. On Linux install the "
        "wheel runtime packages (libwebkit2gtk-4.1-0 libxdo3).".format(detail)
    ]


def verify_collection(collected_output: str, returncode: int) -> list[str]:
    """Return problems for a ``pytest --collect-only -q`` result."""
    problems: list[str] = []
    if returncode != 0:
        problems.append(
            "pytest --collect-only failed (exit {}): the icon checks may have "
            "hit a hard collection error.".format(returncode)
        )
    lines = [ln.strip() for ln in collected_output.splitlines() if ln.strip()]
    # Concrete collected tests are reported as node IDs containing '::'. A
    # module-level importorskip skip or an 'ERROR collecting' line has no
    # '::test_' node, so the expected names will be absent.
    node_lines = [ln for ln in lines if "::" in ln and "test_" in ln]
    collected = "\n".join(node_lines)
    for name in EXPECTED_ICON_CHECKS:
        if name not in collected:
            problems.append(
                "GH-528 icon check {!r} was not collected (module-level skip "
                "or collection error).".format(name)
            )
    return problems


def _import_core() -> tuple[bool, str]:
    try:
        import auroraview._core  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - any failure is a hard gate
        return False, "{}: {}".format(type(exc).__name__, exc)
    return True, ""


def _collect_icon_tests() -> tuple[int, str]:
    icon_test = REPO_ROOT / ICON_TEST
    if not icon_test.is_file():
        return 2, "icon test file not found: {}".format(icon_test)
    env = dict(os.environ)
    # Collection must be deterministic and offline: disable third-party plugin
    # autoload (e.g. pytest-qt, which errors without a Qt binding) and clear
    # addopts so no coverage/timeout plugin is needed just to collect nodes.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            ICON_TEST,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    problems: list[str] = []
    problems += verify_native_import(_import_core())
    returncode, output = _collect_icon_tests()
    problems += verify_collection(output, returncode)

    if problems:
        print(
            "FAIL: wheel native import / GH-528 icon collection contract violated:",
            file=sys.stderr,
        )
        for problem in problems:
            print("  - {}".format(problem), file=sys.stderr)
        return 1

    print(
        "OK: auroraview._core imports and all {} GH-528 icon check functions are collected.".format(
            len(EXPECTED_ICON_CHECKS)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
