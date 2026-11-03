"""Regression guards for the merged #540 changed-line mutation selector.

The head of PR #537 originally resolved a conflict with ``--ours`` and kept the
old ``--file`` selector. That dropped main #540's ``--workspace --in-diff``
wiring and the Windows-only classifier entirely, so the PR no longer mutated
only the lines it changed (and no longer deferred Windows-gated code to the
native Windows runner). These tests exercise the real selector functions plus
the workflow wiring that calls them, so a future conflict resolution cannot
silently revert the accepted behaviour again.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW = _ROOT / ".github/workflows/mutation-testing.yml"
_PR_CHECKS = _ROOT / ".github/workflows/pr-checks.yml"
_JUSTFILE = _ROOT / "justfile"
_SELECTOR = _ROOT / "scripts/ci/mutation_changed_files.py"


def _load_selector():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location("mutation_changed_files_under_test", _SELECTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_source(root: Path, name: str, source: str) -> None:
    (root / name).write_text(source, encoding="utf-8")


def _gated_diff() -> str:
    return (
        "diff --git a/win.rs b/win.rs\n"
        "--- a/win.rs\n"
        "+++ b/win.rs\n"
        "@@ -1,3 +1,3 @@ fn f() {\n"
        " fn portable() -> u32 { 1 }\n"
        ' #[cfg(target_os = "windows")]\n'
        "-fn paint() -> u32 { 3 }\n"
        "+fn paint() -> u32 { 2 }\n"
    )


def _mixed_diff() -> str:
    return (
        "diff --git a/mix.rs b/mix.rs\n"
        "--- a/mix.rs\n"
        "+++ b/mix.rs\n"
        "@@ -1,2 +1,2 @@\n"
        "-fn portable() -> u32 { 0 }\n"
        "+fn portable() -> u32 { 1 }\n"
        " fn other() -> u32 { 2 }\n"
    )


# ---------------------------------------------------------------------------
# Direct selector contracts: positive and negative cases
# ---------------------------------------------------------------------------


def test_added_lines_maps_new_side_line_numbers():
    diff = (
        "diff --git a/x.rs b/x.rs\n"
        "--- a/x.rs\n"
        "+++ b/x.rs\n"
        "@@ -10,2 +10,3 @@ fn f() {\n"
        " context\n"
        "-removed\n"
        "+added at 11\n"
        "+added at 12\n"
    )
    assert _load_selector().added_lines(diff) == {"x.rs": {11, 12}}


def test_selector_accepts_a_fully_windows_gated_diff(tmp_path):
    selector = _load_selector()
    _write_source(
        tmp_path,
        "win.rs",
        'fn portable() -> u32 { 1 }\n#[cfg(target_os = "windows")]\nfn paint() -> u32 { 2 }\n',
    )
    assert selector.is_windows_only(tmp_path, _gated_diff(), ["win.rs"])


def test_selector_rejects_a_mixed_diff(tmp_path):
    selector = _load_selector()
    _write_source(tmp_path, "mix.rs", "fn portable() -> u32 { 1 }\nfn other() -> u32 { 2 }\n")
    assert not selector.is_windows_only(tmp_path, _mixed_diff(), ["mix.rs"])


def test_selector_rejects_an_unreadable_source(tmp_path):
    """A false positive would silently skip mutation testing; stay conservative."""
    selector = _load_selector()
    missing = (
        "diff --git a/gone.rs b/gone.rs\n"
        "--- a/gone.rs\n"
        "+++ b/gone.rs\n"
        "@@ -0,0 +1 @@\n"
        "+fn new() -> u32 { 1 }\n"
    )
    assert not selector.is_windows_only(tmp_path, missing, ["gone.rs"])


def test_selector_rejects_a_diff_without_attributable_added_lines(tmp_path):
    selector = _load_selector()
    _write_source(tmp_path, "win.rs", '#![cfg(target_os = "windows")]\nfn a() -> u32 { 1 }\n')
    assert not selector.is_windows_only(tmp_path, "", ["win.rs"])


def test_selector_main_writes_true_for_a_gated_diff(tmp_path):
    selector = _load_selector()
    _write_source(tmp_path, "win.rs", '#![cfg(target_os = "windows")]\nfn paint() -> u32 { 1 }\n')
    (tmp_path / "mutation.diff").write_text(
        "diff --git a/win.rs b/win.rs\n"
        "--- a/win.rs\n"
        "+++ b/win.rs\n"
        "@@ -1,2 +1,2 @@\n"
        ' #![cfg(target_os = "windows")]\n'
        "+fn paint() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    (tmp_path / "changed-files.txt").write_text("win.rs\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    assert (
        selector.main(
            [
                "--diff",
                str(tmp_path / "mutation.diff"),
                "--files",
                str(tmp_path / "changed-files.txt"),
                "--root",
                str(tmp_path),
                "--output",
                str(out),
            ]
        )
        == 0
    )
    assert out.read_text(encoding="utf-8") == "windows_only=true\n"


def test_selector_main_writes_false_for_a_mixed_diff(tmp_path):
    selector = _load_selector()
    _write_source(tmp_path, "mix.rs", "fn portable() -> u32 { 1 }\nfn other() -> u32 { 2 }\n")
    (tmp_path / "mutation.diff").write_text(_mixed_diff(), encoding="utf-8")
    (tmp_path / "changed-files.txt").write_text("mix.rs\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    assert (
        selector.main(
            [
                "--diff",
                str(tmp_path / "mutation.diff"),
                "--files",
                str(tmp_path / "changed-files.txt"),
                "--root",
                str(tmp_path),
                "--output",
                str(out),
            ]
        )
        == 0
    )
    assert out.read_text(encoding="utf-8") == "windows_only=false\n"


# ---------------------------------------------------------------------------
# Workflow wiring: the selector must really be called and its output honoured
# ---------------------------------------------------------------------------


def _steps() -> dict[str, dict]:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return {
        step["name"]: step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step, dict) and "name" in step
    }


def _triggers() -> dict:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the bare `on:` key as boolean True.
    return workflow.get("on", workflow.get(True))


def test_changed_files_step_generates_the_diff_and_calls_the_classifier():
    run = _steps()["Get changed Rust files"]["run"]
    assert "> mutation.diff" in run
    assert "scripts/ci/mutation_changed_files.py" in run
    assert "--diff mutation.diff" in run
    assert "--files changed-files.txt" in run
    assert "--root ." in run
    assert '--output "$GITHUB_OUTPUT"' in run
    assert "changed-files.txt" in run
    # The old --file union selector silently capped and truncated the diff.
    assert "file_args" not in run
    assert "--file " not in run
    assert "head -20" not in run
    assert "windows_only=false" in run


def test_mutants_step_scopes_all_crates_to_changed_lines():
    step = _steps()["Run incremental mutation testing"]
    command = next(line.strip() for line in step["run"].splitlines() if "cargo mutants " in line)
    assert "--workspace" in command
    assert "--in-diff mutation.diff" in command
    assert "--shard ${{ matrix.shard }}/2" in command
    assert "--sharding round-robin" in command
    assert "--file " not in command
    assert "file_args" not in command
    assert " -p " not in f" {command} "
    # --features must reach the baseline build, i.e. precede the `--` separator.
    feature_index = command.index('"${feature_args[@]}"')
    assert feature_index < command.index(" -- ")
    assert "windows_only != 'true'" in step["if"]


def test_windows_only_skip_is_explained_and_handed_to_the_native_runner():
    steps = _steps()
    explain = steps["Explain Windows-only mutation skip"]
    assert "windows_only == 'true'" in explain["if"]
    assert "pr-checks.yml" in explain["run"]
    assert "test-window-background" in explain["run"]
    pr_checks = _PR_CHECKS.read_text(encoding="utf-8")
    assert "runner.os == 'Windows'" in pr_checks
    assert "Test native Windows background color" in pr_checks


def test_windows_only_skip_reaches_both_shard_contexts():
    run = _steps()["Record shard context"]["run"]
    assert "${{ steps.changed.outputs.windows_only }}" in _WORKFLOW.read_text(encoding="utf-8")
    assert "CHANGED_WINDOWS_ONLY" in run
    assert "effective_skip" in run
    # Both legs must report skip=true for the aggregator to suppress the gate.
    assert "skip" in run and '"windows_only"' in run


def test_selector_scripts_are_exercised_by_the_mutation_job():
    run = _steps()["Test mutation selector contracts"]["run"]
    assert "-m unittest discover -s scripts/ci" in run
    assert "-p test_mutation_workflow.py" in run
    assert "-k MutationChangedFiles" in run


def test_pr_trigger_watches_the_classifier_and_its_tests():
    paths = _triggers()["pull_request"]["paths"]
    for expected in (
        "crates/**/*.rs",
        "src/**/*.rs",
        ".github/workflows/mutation-testing.yml",
        "scripts/ci/mutation_changed_files.py",
        "scripts/ci/test_mutation_workflow.py",
        "justfile",
    ):
        assert expected in paths


def test_all_mutation_jobs_pin_one_msrv_compliant_toolchain():
    text = _WORKFLOW.read_text(encoding="utf-8")
    refs = re.findall(r"dtolnay/rust-toolchain@([0-9]+\.[0-9]+\.[0-9]+)", text)
    assert len(refs) == 3, "incremental, full and single-crate each need a fixed pin"
    assert len(set(refs)) == 1, "dev-dependency MSRV requires one consistent toolchain"
    major, minor, patch = (int(part) for part in refs[0].split("."))
    assert (major, minor, patch) >= (1, 95, 0)


def test_justfile_keeps_the_mutation_workflow_recipe():
    justfile = _JUSTFILE.read_text(encoding="utf-8")
    assert "test-mutation-workflow:" in justfile
    assert "test_mutation_workflow.py" in justfile
    assert "mutation_changed_files.py" in justfile
