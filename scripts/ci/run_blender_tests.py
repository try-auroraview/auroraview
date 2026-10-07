"""Run required pytest cases inside Blender, rejecting skipped host coverage."""

import argparse
import sys
from pathlib import Path


class RequiredHostTests:
    """A green dedicated host job requires every collected test to execute."""

    def __init__(self):
        self.collected = 0
        self.passed = set()
        self.skipped = set()

    def pytest_collection_finish(self, session):
        self.collected = len(session.items)

    def pytest_runtest_logreport(self, report):
        if report.skipped:
            self.skipped.add(report.nodeid)
        if report.when == "call" and report.passed:
            self.passed.add(report.nodeid)

    def pytest_sessionfinish(self, session, exitstatus):
        complete = self.collected > 0 and len(self.passed) == self.collected and not self.skipped
        print(
            "Required Blender host tests: collected={}, passed={}, skipped={}".format(
                self.collected, len(self.passed), len(self.skipped)
            )
        )
        if not complete and not exitstatus:
            session.exitstatus = 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-site", type=Path)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.test_site:
        site = args.test_site.resolve(strict=True)
        if not site.is_dir():
            raise ValueError("--test-site must identify a directory")
        sys.path.insert(0, str(site))

    # Import in this process. Spawning sys.executable would lose the bpy host.
    import bpy
    import pytest

    print("Blender host:", bpy.app.version_string, "Python:", sys.version)
    print("Background:", bpy.app.background, "Renderer validation: not_run")
    test_args = args.pytest_args
    if test_args and test_args[0] == "--":
        test_args = test_args[1:]
    if not test_args:
        test_args = ["tests/python/integration/test_blender_integration.py", "-v"]
    return int(pytest.main(test_args, plugins=[RequiredHostTests()]))


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    result = main(arguments)
    if result:
        # Blender's --python-exit-code makes test failures fail the outer job.
        raise RuntimeError("Required Blender host tests failed (pytest exit {})".format(result))
