"""Focused unit tests for the strict Blender job result guard."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_runner():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "blender_test_runner", root / "scripts/ci/run_blender_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "collected,passed,skipped,initial,expected",
    [
        (4, 4, 0, 0, 0),
        (4, 0, 4, 0, 1),
        (4, 3, 1, 0, 1),
        (0, 0, 0, 0, 1),
        (4, 3, 0, 1, 1),
        (4, 0, 0, 2, 2),
    ],
)
def test_required_host_results(collected, passed, skipped, initial, expected):
    guard = load_runner().RequiredHostTests()
    session = SimpleNamespace(items=list(range(collected)), exitstatus=initial)
    guard.pytest_collection_finish(session)
    for index in range(passed):
        guard.pytest_runtest_logreport(
            SimpleNamespace(nodeid="pass_{}".format(index), when="call", passed=True, skipped=False)
        )
    for index in range(skipped):
        guard.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="skip_{}".format(index), when="setup", passed=False, skipped=True
            )
        )
    guard.pytest_sessionfinish(session, initial)
    assert session.exitstatus == expected


def test_missing_test_site_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_runner().main(["--test-site", str(tmp_path / "missing")])
