"""Regression guard for mutation report integrity (cancelled run 40773589794).

Authoritative evidence, read from the public run (check-run annotation on job
123116945607: "The job has exceeded the maximum execution time of 30m0s"):

* 21:39:13Z -- "Found 200 mutants to test"; ``mutants.json`` lists 200.
* 21:41:57Z -- "ok Unmutated baseline in 160s build + 3s test" (E0599 gone).
* 22:08:32Z -- "The operation was canceled." (30-minute job cap).
* The partial ``outcomes.json`` had ``total_mutants=129``, ``end_time=null``,
  130 outcome entries (1 baseline + 129 mutants), caught=19 / missed=109 /
  unviable=1 -- i.e. 129 of 200 planned mutants were evaluated.

The old parser kept ``""`` in ``_KNOWN_OK_CODES`` and had no completeness check,
so the ``always()`` Parse step (empty exit code) reported
``status=missed score=14`` as a VALID result and the gate accepted it -- even
though the job conclusion was ``cancelled``. That is a false "complete" result.

This module replays that exact artifact shape and pins the corrected contract:

* cancelled / timed_out step or job -> ``incomplete``, score ``N/A``, rejected;
* partial outcomes (``end_time=null`` or recorded < planned) -> ``incomplete``;
* missing exit code -> ``incomplete`` (empty is no longer a known-OK code);
* a *completed* run with exit code 0 or 2 keeps the original ``pass``/``missed``
  contract with a real numeric score (no quality-threshold change, no hiding);
* the completed 60-min run (200/200, caught=28, missed=169, unviable=3, exit 2)
  stays ``missed`` / score 14 with the workflow's real signals -- both when the
  step is ``success`` and when an exit-2 re-raise would have made it ``failure``;
* ``baseline_failed`` / ``no_results`` / ``no_mutants`` / ``timeout`` / ``error``
  all still fail;
* the workflow really binds the runner contexts to the parser (not just a
  hand-passed-argument unit test).

"Valid result" and "quality passed" are deliberately separate layers: the gate
only certifies that a report is complete and honest. Base 8edc987 had no
numeric mutation-score threshold and never re-raised ``PIPESTATUS``; a completed
``missed`` run with 169 survivors is a valid report, NOT a quality pass.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_PARSER = _ROOT / "scripts/ci/parse_mutation_results.py"
_WORKFLOW = _ROOT / ".github/workflows/mutation-testing.yml"


def load_parser():  # noqa: ANN201
    spec = importlib.util.spec_from_file_location("parse_mutation_results", _PARSER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mutant_entries(count: int) -> list[dict]:
    return [{"scenario": {"Mutant": {"name": f"m{i}"}}} for i in range(count)]


def write_cancelled_artifact(directory: Path) -> Path:
    """Reproduce the real cancelled ``mutants.out`` from run 40773589794."""
    directory.mkdir(parents=True, exist_ok=True)
    planned = 200
    recorded = 129
    (directory / "mutants.json").write_text(
        json.dumps([{"i": i} for i in range(planned)]), encoding="utf-8"
    )
    data = {
        "outcomes": [{"scenario": "Baseline", "summary": "Success"}] + _mutant_entries(recorded),
        "total_mutants": recorded,
        "caught": 19,
        "missed": 109,
        "timeout": 0,
        "unviable": 1,
        "success": 0,
        "start_time": "2026-10-28T21:39:12.973654898Z",
        "end_time": None,  # cargo-mutants never reached the end of the run
        "cargo_mutants_version": "27.1.0",
    }
    (directory / "outcomes.json").write_text(json.dumps(data), encoding="utf-8")
    (directory / "caught.txt").write_text("c\n" * 19, encoding="utf-8")
    (directory / "missed.txt").write_text("m\n" * 109, encoding="utf-8")
    (directory / "timeout.txt").write_text("", encoding="utf-8")
    (directory / "unviable.txt").write_text("u\n", encoding="utf-8")
    return directory


def write_complete_artifact(
    directory: Path,
    *,
    total: int = 200,
    caught: int = 200,
    missed: int = 0,
    unviable: int = 0,
) -> Path:
    """A finished run: end_time set and every planned mutant has an outcome."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "mutants.json").write_text(
        json.dumps([{"i": i} for i in range(total)]), encoding="utf-8"
    )
    data = {
        "outcomes": [{"scenario": "Baseline", "summary": "Success"}] + _mutant_entries(total),
        "total_mutants": total,
        "caught": caught,
        "missed": missed,
        "timeout": 0,
        "unviable": unviable,
        "success": 0,
        "start_time": "2026-10-28T22:17:42Z",
        "end_time": "2026-10-28T23:02:00Z",
        "cargo_mutants_version": "27.1.0",
    }
    (directory / "outcomes.json").write_text(json.dumps(data), encoding="utf-8")
    return directory


def _legacy_derive(artifact: Path, exit_code: str = "") -> tuple[str, str]:
    """Replica of the PRE-FIX decision logic, to demonstrate the red side.

    Kept deliberately literal: ``_KNOWN_OK_CODES`` included the empty string and
    there was no step/artifact completeness check. Feeding it the real cancelled
    artifact with an empty exit code reproduces the published false pass
    ``status=missed score=14`` from the job log.
    """
    known_ok = {"", "0", "2"}
    status_by_code = {"1": "error", "3": "timeout", "4": "baseline_failed"}
    data = json.loads((artifact / "outcomes.json").read_text(encoding="utf-8"))
    total = int(data.get("total_mutants", 0))
    caught = int(data.get("caught", 0))
    missed = int(data.get("missed", 0))
    code = (exit_code or "").strip()
    baseline_failed = any(
        isinstance(e, dict) and e.get("scenario") == "Baseline" and e.get("summary") != "Success"
        for e in data.get("outcomes", [])
    )
    if not artifact.is_dir():
        status = "no_results"
    elif baseline_failed or code == "4":
        status = "baseline_failed"
    elif code in status_by_code:
        status = status_by_code[code]
    elif code and code not in known_ok:
        status = "error"
    elif total <= 0:
        status = "no_mutants"
    elif missed > 0:
        status = "missed"
    elif caught > 0:
        status = "pass"
    else:
        status = "no_results"
    denominator = caught + missed
    valid = status in {"pass", "missed"}
    score = str(caught * 100 // denominator) if valid and denominator > 0 else "N/A"
    return status, score


# --- Red -> green: the real cancelled artifact ------------------------------


def test_legacy_parser_published_a_false_complete_result(tmp_path):
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    status, score = _legacy_derive(artifact, exit_code="")
    # Exactly what the job log printed for the cancelled run.
    assert (status, score) == ("missed", "14")
    assert status in load_parser()._VALID_STATUSES  # gate would have ACCEPTED it


def test_cancelled_artifact_is_now_incomplete_and_rejected(tmp_path):
    parser = load_parser()
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    values = parser.derive(
        artifact,
        exit_code="",  # never persisted: step was killed at the 30m cap
        step_outcome="cancelled",
        step_conclusion="cancelled",
        job_status="cancelled",
    )
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"
    assert values["status"] not in parser._VALID_STATUSES
    # Counters are still reported honestly -- nothing is hidden.
    assert values["total"] == "129"
    assert values["caught"] == "19"
    assert values["missed"] == "109"
    body = parser.render_comment(values)
    assert "**Status:** `incomplete`" in body
    assert "**Score** | **N/A**" in body
    assert "NOT a passing result" in body
    assert "All 129 mutants were caught" not in body


def test_empty_exit_code_is_no_longer_a_known_ok_code():
    parser = load_parser()
    assert "" not in parser._KNOWN_OK_CODES
    assert parser._KNOWN_OK_CODES == {"0", "2"}
    assert "incomplete" not in parser._VALID_STATUSES
    assert "incomplete" in parser._SUMMARY


# --- Each independent incompleteness signal ---------------------------------


@pytest.mark.parametrize(
    "signals",
    [
        {"step_outcome": "cancelled"},
        {"step_conclusion": "cancelled"},
        {"job_status": "cancelled"},
        {"step_outcome": "timed_out"},
        {"job_status": "skipped"},
    ],
)
def test_cancellation_signals_force_incomplete_even_on_a_complete_artifact(tmp_path, signals):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out")
    kwargs = {
        "step_outcome": "success",
        "step_conclusion": "success",
        "job_status": "success",
    }
    kwargs.update(signals)
    values = parser.derive(artifact, exit_code="0", **kwargs)
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


def test_partial_outcomes_end_time_null_forces_incomplete(tmp_path):
    parser = load_parser()
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    # Even without any runner signal and with a plausible exit code, the
    # artifact itself proves the run was truncated.
    values = parser.derive(artifact, exit_code="2")
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


def test_manifest_planned_greater_than_recorded_forces_incomplete(tmp_path):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out", total=200)
    data = json.loads((artifact / "outcomes.json").read_text(encoding="utf-8"))
    data["end_time"] = "2026-10-28T23:02:00Z"  # pretend it finished
    data["outcomes"] = [{"scenario": "Baseline", "summary": "Success"}] + _mutant_entries(129)
    data["total_mutants"] = 129
    (artifact / "outcomes.json").write_text(json.dumps(data), encoding="utf-8")
    values = parser.derive(artifact, exit_code="2")
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


def test_missing_exit_code_forces_incomplete_even_on_complete_artifact(tmp_path):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out")
    values = parser.derive(artifact, exit_code="")
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


def test_failure_outcome_is_not_treated_as_interruption(tmp_path):
    """exit 2 (missed mutants) completes with a failing step: still a result."""
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out", total=10, caught=7, missed=3)
    values = parser.derive(
        artifact,
        exit_code="2",
        step_outcome="failure",
        step_conclusion="failure",
        job_status="failure",
    )
    assert values["status"] == "missed"
    assert values["score"] == "70"


# --- The completed 60-min run, exactly as the workflow drives the CLI ---------
#
# Reproduces the real artifact shape of run 40778843830 (200 planned / 200
# recorded, end_time set, caught=28, missed=169, unviable=3). Both signal sets
# are required: the corrected workflow leaves the step successful, while the
# earlier WIP that re-raised exit 2 produced failure outcomes. Neither may
# erase a complete result or be mistaken for a cancellation. These go through
# main() with the very flags the workflow passes -- not bare derive() calls
# that silently omit the signals.


def _real_full_run_artifact(tmp_path: Path) -> Path:
    return write_complete_artifact(
        tmp_path / "mutants.out", total=200, caught=28, missed=169, unviable=3
    )


def _cli_outputs(parser, artifact: Path, tmp_path: Path, **signals) -> dict[str, str]:
    output_file = tmp_path / "gh_output.txt"
    comment_file = tmp_path / "comment.md"
    argv = [
        "--mutants-out",
        str(artifact),
        "--output",
        str(output_file),
        "--comment-file",
        str(comment_file),
        "--exit-code",
        signals.pop("exit_code", ""),
        "--step-outcome",
        signals.pop("step_outcome", ""),
        "--step-conclusion",
        signals.pop("step_conclusion", ""),
        "--job-status",
        signals.pop("job_status", ""),
    ]
    assert not signals, f"unexpected signals: {signals}"
    assert parser.main(argv) == 0
    values = dict(
        line.split("=", 1) for line in output_file.read_text(encoding="utf-8").splitlines()
    )
    values["_comment"] = comment_file.read_text(encoding="utf-8")
    return values


@pytest.mark.parametrize(
    "signals",
    [
        {
            "step_outcome": "success",
            "step_conclusion": "success",
            "job_status": "success",
        },
        {
            "step_outcome": "failure",
            "step_conclusion": "failure",
            "job_status": "failure",
        },
    ],
    ids=["step-succeeded", "step-failed-on-exit-2"],
)
def test_cli_real_full_run_exit_2_keeps_missed_with_real_score(tmp_path, signals):
    parser = load_parser()
    values = _cli_outputs(
        parser, _real_full_run_artifact(tmp_path), tmp_path, exit_code="2", **signals
    )
    assert values["status"] == "missed"
    assert values["score"] == "14"
    assert values["total"] == "200"
    assert values["caught"] == "28"
    assert values["missed"] == "169"
    assert values["unviable"] == "3"
    assert "**Status:** `missed`" in values["_comment"]
    assert "**Score** | **14**" in values["_comment"]
    assert "NOT a passing result" not in values["_comment"]


def test_cli_real_cancelled_run_is_incomplete_and_rejected(tmp_path):
    parser = load_parser()
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    values = _cli_outputs(
        parser,
        artifact,
        tmp_path,
        exit_code="",
        step_outcome="cancelled",
        step_conclusion="cancelled",
        job_status="cancelled",
    )
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"
    assert values["total"] == "129"
    assert "**Status:** `incomplete`" in values["_comment"]
    assert "NOT a passing result" in values["_comment"]


# --- Original contract preserved --------------------------------------------


def test_completed_exit_0_is_pass_with_real_score(tmp_path):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out")
    values = parser.derive(artifact, exit_code="0")
    assert values["status"] == "pass"
    assert values["score"] == "100"
    assert values["status"] in parser._VALID_STATUSES


def test_completed_exit_2_is_missed_with_real_score(tmp_path):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out", total=10, caught=7, missed=3)
    values = parser.derive(artifact, exit_code="2")
    assert values["status"] == "missed"
    assert values["score"] == "70"
    assert values["status"] in parser._VALID_STATUSES


@pytest.mark.parametrize(
    "code,expected",
    [("1", "error"), ("3", "timeout"), ("4", "baseline_failed")],
)
def test_original_failure_codes_still_fail(tmp_path, code, expected):
    parser = load_parser()
    artifact = write_complete_artifact(tmp_path / "mutants.out")
    values = parser.derive(artifact, exit_code=code)
    assert values["status"] == expected
    assert values["score"] == "N/A"
    assert values["status"] not in parser._VALID_STATUSES


def test_no_results_and_no_mutants_still_fail(tmp_path):
    parser = load_parser()
    values = parser.derive(tmp_path / "missing")
    assert values["status"] == "no_results"
    values = parser.derive(
        write_complete_artifact(tmp_path / "zero", total=0, caught=0), exit_code="0"
    )
    assert values["status"] == "no_mutants"
    assert values["score"] == "N/A"


def test_comment_never_claims_a_pass_for_incomplete(tmp_path):
    parser = load_parser()
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    values = parser.derive(artifact, exit_code="", step_outcome="cancelled")
    body = parser.render_comment(values, "src/foo.rs:1: replace x\n")
    assert "were caught by the test suite" not in body
    assert "<details>" not in body  # incomplete must not publish missed details
    assert "NOT a passing result" in body


def test_incomplete_outputs_are_single_line(tmp_path):
    parser = load_parser()
    artifact = write_cancelled_artifact(tmp_path / "mutants.out")
    values = parser.derive(artifact, exit_code="", job_status="cancelled")
    output_file = tmp_path / "gh_output.txt"
    parser.write_outputs(values, output_file)
    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert "status=incomplete" in lines
    assert "score=N/A" in lines


# --- The workflow must really bind the runner contexts -----------------------


def _parse_step_block(text: str) -> str:
    match = re.search(
        r"- name: Parse mutation results\n(?P<body>.*?)(?=\n      - name: |\Z)",
        text,
        re.DOTALL,
    )
    assert match, "Parse mutation results step not found"
    return match.group("body")


def test_workflow_binds_real_step_signals_to_parser():
    text = _WORKFLOW.read_text(encoding="utf-8")
    parse_step = _parse_step_block(text)
    # The mutants step must be addressable via `steps.mutants`.
    assert re.search(r"- name: Run incremental mutation testing\n\s+id: mutants", text)
    # Runner contexts are bound into env (avoids interpolating into shell).
    for env_name, expression in (
        ("MUTANTS_EXIT_CODE", "${{ steps.mutants.outputs.exit_code }}"),
        ("MUTANTS_STEP_OUTCOME", "${{ steps.mutants.outcome }}"),
        ("MUTANTS_STEP_CONCLUSION", "${{ steps.mutants.conclusion }}"),
        ("JOB_STATUS", "${{ job.status }}"),
    ):
        assert re.search(rf"{env_name}:\s*{re.escape(expression)}", parse_step), (
            f"{env_name} must be bound to {expression}"
        )
    # ...and those bound values are actually passed to the parser.
    for flag, env_name in (
        ("--exit-code", "MUTANTS_EXIT_CODE"),
        ("--step-outcome", "MUTANTS_STEP_OUTCOME"),
        ("--step-conclusion", "MUTANTS_STEP_CONCLUSION"),
        ("--job-status", "JOB_STATUS"),
    ):
        assert re.search(rf"{flag} \"\${env_name}\"", parse_step), (
            f"{flag} must consume ${env_name}"
        )


def test_workflow_records_exit_code_without_changing_the_step_result():
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "exit_code=${PIPESTATUS[0]}" in text
    assert 'echo "exit_code=$exit_code" >> "$GITHUB_OUTPUT"' in text
    # The step must NOT re-raise the exit code: exit 2 is a *completed* missed
    # run whose result the gate legitimately accepts. Re-raising it would turn
    # every missed run into a red step and silently ADD a quality threshold that
    # base 8edc987 never had. Anchor on a standalone shell command; the
    # explanatory comment also quotes the same text and must not be mistaken
    # for the command itself.
    assert not re.search(r'^\s*exit "\$exit_code"\s*$', text, re.MULTILINE)
    assert "set +e" not in text
    # The PR-introduced claim of a hard "missed fails CI" policy was false; the
    # gate is about report validity, not a numeric quality threshold.
    assert "still fail via cargo-mutants' own exit code" not in text


def test_gate_still_accepts_only_pass_or_missed():
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"pass\|missed\)\s+echo \"Valid mutation result", text)
    assert "::error::No valid mutation result" in text


def test_incremental_timeout_not_expanded_beyond_60_minutes():
    text = _WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"^  incremental:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match
    timeout = re.search(r"timeout-minutes:\s*(\d+)", match.group("body"))
    assert timeout and int(timeout.group(1)) == 60
