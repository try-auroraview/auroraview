"""Red/green unit tests for the wheel native-import preflight guard.

Pure and offline: it feeds synthetic ``pytest --collect-only`` output and
synthetic import results to the guard's verifiers. It never imports
``auroraview._core`` and never launches a GUI. This is what proves the guard
itself fails loudly on the exact regression that turned the Ubuntu wheel lanes
red (a missing native runtime library) and on a silently skipped icon module.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_wheel_native_import",
    ROOT / "scripts" / "ci" / "check_wheel_native_import.py",
)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


# Realistic `pytest --collect-only -q` output for a healthy wheel lane: the
# four concrete node IDs plus a summary line.
COLLECTED_OK = "\n".join(
    [
        "tests/python/unit/test_run_desktop_icon.py::test_runner_accepts_icon_kwarg[run_desktop]",
        "tests/python/unit/test_run_desktop_icon.py::test_runner_accepts_icon_kwarg[run_standalone]",
        "tests/python/unit/test_run_desktop_icon.py::test_run_desktop_icon_is_documented",
        "tests/python/unit/test_run_desktop_icon.py::test_run_desktop_icon_kwarg_round_trip",
        "",
        "4 tests collected in 0.02s",
    ]
)


class NativeImportVerifierTests(unittest.TestCase):
    def test_green_when_core_imports(self):
        self.assertEqual(guard.verify_native_import((True, "")), [])

    def test_red_when_core_import_fails_names_libxdo(self):
        problems = guard.verify_native_import(
            (False, "ImportError: libxdo.so.3: cannot open shared object file")
        )
        self.assertTrue(problems)
        self.assertIn("_core", problems[0])
        self.assertIn("libxdo", problems[0])
        self.assertIn("libwebkit2gtk-4.1-0 libxdo3", problems[0])


class CollectionVerifierTests(unittest.TestCase):
    def test_green_when_all_icon_checks_collected(self):
        self.assertEqual(guard.verify_collection(COLLECTED_OK, 0), [])

    def test_red_on_hard_collection_error(self):
        # pytest 9: importorskip ImportError becomes exit-2 collection error.
        problems = guard.verify_collection("ERROR collecting ...\n", 2)
        self.assertTrue(any("collection" in p.lower() for p in problems))

    def test_red_when_module_silently_skipped(self):
        # pytest 8: module-level importorskip skip yields at most one skipped
        # marker and no concrete node IDs.
        problems = guard.verify_collection("1 skipped in 0.01s\n", 0)
        self.assertEqual(len(problems), len(guard.EXPECTED_ICON_CHECKS))

    def test_red_when_one_check_missing(self):
        lines = [
            ln
            for ln in COLLECTED_OK.splitlines()
            if "test_run_desktop_icon_is_documented" not in ln
        ]
        problems = guard.verify_collection("\n".join(lines), 0)
        self.assertTrue(any("test_run_desktop_icon_is_documented" in p for p in problems))

    def test_hard_error_and_missing_checks_both_reported(self):
        # A broken wheel: the import failed AND collection produced nothing.
        combined = guard.verify_native_import((False, "ImportError: libxdo.so.3"))
        combined += guard.verify_collection("1 error in 0.01s\n", 2)
        self.assertGreaterEqual(len(combined), 2)


class ExpectedContractTests(unittest.TestCase):
    def test_expected_icon_checks_are_stable(self):
        self.assertEqual(
            guard.EXPECTED_ICON_CHECKS,
            (
                "test_runner_accepts_icon_kwarg",
                "test_run_desktop_icon_is_documented",
                "test_run_desktop_icon_kwarg_round_trip",
            ),
        )

    def test_icon_test_file_exists(self):
        self.assertTrue((ROOT / guard.ICON_TEST).is_file())


if __name__ == "__main__":
    unittest.main()
