"""Regression tests for the Mutation Testing result parser (GH-537 follow-up).

The workflow's inline bash parser crashed on empty ``mutants.out/*.txt`` files
(``grep -c ... || echo "0"`` yields ``"0\\n0"``, which breaks ``$((...))``) and
reported failed/no-mutant runs as ``score=100`` plus "All mutations were
caught". These tests reproduce that failure and pin the corrected reporting:
invalid/no-baseline/zero-mutant runs must never look like a green pass.
"""

import importlib.util
import json
from pathlib import Path

import pytest


def load_parser():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "parse_mutation_results", root / "scripts/ci/parse_mutation_results.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_outcomes(directory: Path, **overrides) -> Path:
    data = {
        "outcomes": [{"scenario": "Baseline", "summary": "Success"}],
        "total_mutants": 0,
        "caught": 0,
        "missed": 0,
        "timeout": 0,
        "unviable": 0,
    }
    data.update(overrides)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "outcomes.json").write_text(json.dumps(data), encoding="utf-8")
    for name in ("caught.txt", "missed.txt", "timeout.txt", "unviable.txt"):
        (directory / name).write_text("", encoding="utf-8")
    return directory


# --- Reproduce the old failure ----------------------------------------------


def test_legacy_failure_multiline_value_breaks_arithmetic():
    """Reproduce the mechanism behind the old ``0\\n0`` arithmetic crash.

    ``grep -c`` prints ``0`` *and* exits 1 with no matches, so the old
    ``|| echo "0"`` branch appended a second ``0``. The two-line value is not
    a valid integer for shell arithmetic / int(), which is what crashed the
    "Parse mutation results" step under ``bash -e``.
    """
    legacy_value = "0\n" + "0"  # exactly what `grep -c ... || echo 0` yields
    with pytest.raises(ValueError):
        int(legacy_value)
    assert legacy_value.count("\n") == 1


def test_real_failing_artifact_is_not_a_pass(tmp_path):
    """The exact CI artifact shape: empty .txt + Baseline Failure + exit 4.

    Reproduces run 40720350821 / job 122929232241: cargo-mutants 27.1.0 wrote
    empty caught/missed/timeout/unviable .txt files and outcomes.json recording
    a failed unmutated baseline (rustc 1.90 vs a dependency needing 1.95). The
    new parser must report a clear failure, never a 100% pass.
    """
    out = write_outcomes(
        tmp_path / "mutants.out",
        outcomes=[
            {
                "scenario": "Baseline",
                "summary": "Failure",
                "phase_results": [{"phase": "Build", "process_status": {"Failure": 101}}],
            }
        ],
        total_mutants=0,
        caught=0,
        missed=0,
        timeout=0,
        unviable=0,
        success=0,
    )
    values = load_parser().derive(out, exit_code="4")
    assert values["status"] == "baseline_failed"
    assert values["score"] == "N/A"
    assert values["caught"] == "0" and values["missed"] == "0"
    assert all("\n" not in v for v in values.values())
    body = load_parser().render_comment(values)
    assert "All mutations were caught" not in body
    assert "NOT a passing result" in body
    assert "**Score** | **N/A**" in body


def test_count_nonempty_lines_missing_file_is_zero(tmp_path):
    assert load_parser().count_nonempty_lines(tmp_path / "missing.txt") == 0


def test_count_nonempty_lines_counts_content(tmp_path):
    f = tmp_path / "caught.txt"
    f.write_text("a\nb\n\n  \nc\n", encoding="utf-8")
    assert load_parser().count_nonempty_lines(f) == 3


# --- Corrected reporting: never a false pass --------------------------------


def test_failed_baseline_is_not_a_pass(tmp_path):
    out = write_outcomes(
        tmp_path / "mutants.out",
        outcomes=[{"scenario": "Baseline", "summary": "Failure"}],
        total_mutants=0,
    )
    values = load_parser().derive(out, exit_code="4")
    assert values["status"] == "baseline_failed"
    assert values["score"] == "N/A"
    assert "NOT a passing result" in values["summary"]
    assert values["status"] not in load_parser()._VALID_STATUSES


def test_no_results_dir_is_not_a_pass(tmp_path):
    values = load_parser().derive(tmp_path / "does-not-exist")
    assert values["status"] == "no_results"
    assert values["score"] == "N/A"
    assert "NOT a passing result" in values["summary"]


def test_zero_mutants_with_good_baseline_is_not_a_pass(tmp_path):
    out = write_outcomes(tmp_path / "mutants.out", total_mutants=0)
    values = load_parser().derive(out, exit_code="0")
    assert values["status"] == "no_mutants"
    assert values["score"] == "N/A"  # must NOT be 100
    assert "NOT a passing result" in values["summary"]


def test_error_and_timeout_exit_codes_are_not_passes(tmp_path):
    out = write_outcomes(tmp_path / "mutants.out", total_mutants=5, caught=5)
    assert load_parser().derive(out, exit_code="1")["status"] == "error"
    assert load_parser().derive(out, exit_code="3")["status"] == "timeout"
    assert load_parser().derive(out, exit_code="1")["score"] == "N/A"


# --- Corrected reporting: real results still scored correctly ---------------


@pytest.mark.parametrize(
    "caught,missed,expected_score,expected_status",
    [
        (10, 0, "100", "pass"),
        (7, 3, "70", "missed"),
        (1, 2, "33", "missed"),
        (0, 4, "0", "missed"),
    ],
)
def test_real_score_uses_caught_over_caught_plus_missed(
    tmp_path, caught, missed, expected_score, expected_status
):
    out = write_outcomes(
        tmp_path / "mutants.out",
        total_mutants=caught + missed,
        caught=caught,
        missed=missed,
    )
    values = load_parser().derive(out, exit_code="0")
    assert values["status"] == expected_status
    assert values["score"] == expected_score
    assert values["status"] in load_parser()._VALID_STATUSES


def test_falls_back_to_txt_files_when_outcomes_json_missing(tmp_path):
    out = tmp_path / "mutants.out"
    out.mkdir()
    (out / "caught.txt").write_text("m1\nm2\nm3\n", encoding="utf-8")
    (out / "missed.txt").write_text("m4\n", encoding="utf-8")
    (out / "timeout.txt").write_text("", encoding="utf-8")
    (out / "unviable.txt").write_text("", encoding="utf-8")
    values = load_parser().derive(out, exit_code="0")
    assert values["caught"] == "3"
    assert values["missed"] == "1"
    assert values["total"] == "4"
    assert values["score"] == "75"
    assert values["status"] == "missed"


# --- Output writing ---------------------------------------------------------


def test_all_outputs_are_single_line(tmp_path):
    out = write_outcomes(
        tmp_path / "mutants.out",
        outcomes=[{"scenario": "Baseline", "summary": "Failure"}],
    )
    values = load_parser().derive(out, exit_code="4")
    output_file = tmp_path / "gh_output.txt"
    load_parser().write_outputs(values, output_file)
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert all("=" in line for line in lines)
    assert "status=baseline_failed" in lines
    assert "score=N/A" in lines
    # No multi-line value can corrupt $GITHUB_OUTPUT.
    assert all("\n" not in line for line in lines)


# --- The PR comment must never claim a false pass ---------------------------


def test_comment_never_claims_all_caught_for_invalid_runs(tmp_path):
    for status_setup in (
        {"outcomes": [{"scenario": "Baseline", "summary": "Failure"}], "exit_code": "4"},
        {"total_mutants": 0, "exit_code": "0"},
        {"total_mutants": 5, "caught": 5, "exit_code": "1"},
    ):
        setup = dict(status_setup)
        code = setup.pop("exit_code")
        out = write_outcomes(tmp_path / "mutants.out", **setup)
        values = load_parser().derive(out, exit_code=code)
        body = load_parser().render_comment(values)
        assert "All mutations were caught" not in body
        assert "NOT a passing result" in body
        assert "**Score** | **N/A**" in body


def test_comment_for_genuine_pass_says_caught(tmp_path):
    out = write_outcomes(tmp_path / "mutants.out", total_mutants=5, caught=5)
    values = load_parser().derive(out, exit_code="0")
    body = load_parser().render_comment(values)
    assert "All 5 mutants were caught" in body
    assert "**Score** | **100**" in body


def test_comment_includes_missed_details_only_when_missed(tmp_path):
    out = write_outcomes(tmp_path / "mutants.out", total_mutants=2, caught=1, missed=1)
    values = load_parser().derive(out, exit_code="2")
    body = load_parser().render_comment(values, "src/foo.rs:1: replace x\n")
    assert "<details>" in body
    assert "src/foo.rs:1" in body
