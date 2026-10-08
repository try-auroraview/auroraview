import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HARNESS_PATH = PROJECT_ROOT / "scripts" / "harness_changed.py"
HARNESS_SPEC = importlib.util.spec_from_file_location("harness_changed", HARNESS_PATH)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS_MODULE = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(HARNESS_MODULE)

build_command_plan = HARNESS_MODULE.build_command_plan
classify_changes = HARNESS_MODULE.classify_changes
list_changed_files = HARNESS_MODULE.list_changed_files


def test_build_command_plan_uses_quick_checks_for_no_changes():
    assert build_command_plan([]) == ["vx just harness-quick"]


def test_build_command_plan_uses_rust_fast_path_for_rust_changes():
    assert build_command_plan(["src/webview/backend/mod.rs"]) == ["vx just test-rust-fast"]


def test_build_command_plan_runs_python_unit_fast_for_unit_changes():
    assert build_command_plan(["tests/python/unit/test_backend.py"]) == [
        "vx just test-python-unit-fast"
    ]


def test_build_command_plan_runs_python_source_checks_for_python_module_changes():
    assert build_command_plan(["python/auroraview/core.py"]) == [
        "vx just test-python-unit-fast",
        "vx just test-python-integration",
    ]


def test_build_command_plan_runs_integration_only_for_integration_test_changes():
    assert build_command_plan(["tests/python/integration/test_qt_backend.py"]) == [
        "vx just test-python-integration"
    ]


def test_build_command_plan_escalates_ci_changes_to_verify():
    assert build_command_plan([".github/workflows/pr-checks.yml"]) == ["vx just harness-verify"]


def test_build_command_plan_runs_assets_ci_for_assets_changes():
    assert build_command_plan(["crates/auroraview-assets/frontend/src/main.tsx"]) == [
        "vx just test-rust-fast",
        "vx just assets-ci",
    ]


def test_build_command_plan_combines_sdk_and_gallery_checks():
    assert build_command_plan(
        [
            "packages/auroraview-sdk/src/core/bridge.ts",
            "gallery/src/main.ts",
        ]
    ) == ["vx just sdk-ci", "vx just gallery-verify"]


def test_classify_changes_marks_docs_for_markdown_files():
    flags = classify_changes(["README.md"])
    assert flags["docs"] is True
    assert flags["ci"] is False


def test_classify_changes_marks_cargo_mutants_as_ci():
    flags = classify_changes([".cargo/mutants.toml"])
    assert flags["ci"] is True


def test_list_changed_files_includes_worktree_and_filters_internal_files(monkeypatch):
    outputs = {
        ("vx", "git", "diff", "--name-only", "origin/main...HEAD"): ["justfile"],
        ("vx", "git", "diff", "--name-only", "HEAD"): [
            "scripts/harness_changed.py",
            "justfile",
        ],
        ("vx", "git", "ls-files", "--others", "--exclude-standard"): [
            "tests/python/unit/test_harness_changed.py",
            ".gitcommitmsg",
        ],
    }

    def fake_run_name_only(args):
        return outputs[tuple(args)]

    monkeypatch.setattr(HARNESS_MODULE, "_run_name_only", fake_run_name_only)

    assert list_changed_files("origin/main") == [
        "justfile",
        "scripts/harness_changed.py",
        "tests/python/unit/test_harness_changed.py",
    ]
