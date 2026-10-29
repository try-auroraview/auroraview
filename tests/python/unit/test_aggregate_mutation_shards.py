"""Regression guards for deterministic mutation sharding and honest aggregation.

Run 40790621664 (head afbac389) hit the 60-minute cap at 195/200 mutants even
though the same inputs finished 200/200 in 48m34s on run 40778843830. Runner
variance (13.4s -> 17.0s per mutant, 154s -> 227s baseline) makes a single
60-minute job non-deterministic. The fix keeps ALL 200 planned mutants but
runs them as two deterministic round-robin shards, then merges them back into
one result set judged by ``parse_mutation_results.py``.

These tests pin the contract:

* a complete 2-shard round reproduces the original ``missed / 14 / 200``;
* a truncated/cancelled leg yields ``incomplete / N/A`` and is rejected;
* completeness is checked by mutant NAME (missing, duplicate, extra, missing
  leg, denominator mismatch), never by a rounded-up counter;
* the workflow really wires the shard matrix, the aggregate step's runner
  contexts and the parser flags, and never raises the timeout or drops work.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_AGG = _ROOT / "scripts/ci/aggregate_mutation_shards.py"
_PARSER = _ROOT / "scripts/ci/parse_mutation_results.py"
_WORKFLOW = _ROOT / ".github/workflows/mutation-testing.yml"


def _load(name: str, path: Path):  # noqa: ANN201
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mutant(index: int) -> dict:
    return {
        "name": f"src/ipc/mod.rs:{index + 1}:5: replace f{index} with Default::default()",
        "file": "src/ipc/mod.rs",
        "genre": "FnValue",
        "replacement": "Default::default()",
    }


def _outcome(index: int, summary: str) -> dict:
    return {
        "scenario": {"Mutant": {"name": _mutant(index)["name"], "file": "src/ipc/mod.rs"}},
        "summary": summary,
        "log_path": f"log/m{index}.log",
        "diff_path": f"diff/m{index}.diff",
        "phase_results": [
            {"phase": "Build", "duration": 13.0, "process_status": "Success"},
            {"phase": "Test", "duration": 3.0, "process_status": "Success"},
        ],
    }


def _summaries(total: int = 200, caught: int = 28, unviable: int = 3) -> list[str]:
    return (
        ["CaughtMutant"] * caught
        + ["Unviable"] * unviable
        + ["MissedMutant"] * (total - caught - unviable)
    )


_COUNTER_BY_SUMMARY = {
    "CaughtMutant": "caught",
    "MissedMutant": "missed",
    "Unviable": "unviable",
    "Timeout": "timeout",
    "Success": "success",
}


def _counters(entries: list[dict]) -> dict[str, int]:
    counters = dict.fromkeys(("caught", "missed", "timeout", "unviable", "success"), 0)
    for entry in entries:
        key = _COUNTER_BY_SUMMARY.get(entry.get("summary"))
        if key:
            counters[key] += 1
    return {**counters, "total_mutants": len(entries)}


def build_shards(
    shards_dir: Path,
    *,
    total: int = 200,
    n: int = 2,
    drop_last: int = 0,
    cancel_shard: int | None = None,
    skip_all: bool = False,
    extra_outcomes: int = 0,
    duplicate_index: bool = False,
    wrong_denominator: bool = False,
) -> Path:
    """Write N shard artifacts that mimic real cargo-mutants output."""
    shards_dir.mkdir(parents=True, exist_ok=True)
    planned = [_mutant(i) for i in range(total)]
    summaries = _summaries(total)
    baseline = {"scenario": "Baseline", "summary": "Success"}
    keep = total - drop_last

    for k in range(n):
        directory = shards_dir / f"mutation-shard-{k}"
        directory.mkdir()
        # mutants.json is written BEFORE the run: a truncated run still lists
        # every mutant planned for this shard.
        sub_planned = [planned[i] for i in range(k, total, n)]
        indices = [i for i in range(k, total, n) if i < keep]
        entries = [_outcome(i, summaries[i]) for i in indices]
        cancelled = cancel_shard is not None and k == cancel_shard

        if skip_all:
            (directory / "shard_meta.json").write_text(
                json.dumps(
                    {
                        "shard": k,
                        "shards": n,
                        "exit_code": "",
                        "step_outcome": "skipped",
                        "step_conclusion": "skipped",
                        "job_status": "success",
                        "skip": "true",
                    }
                ),
                encoding="utf-8",
            )
            continue

        for offset in range(extra_outcomes):
            extra = _outcome(1000 + offset, "MissedMutant")
            extra["scenario"]["Mutant"]["name"] = f"not/planned.rs:{offset}:1: invented"
            if k == 0:
                entries.append(extra)

        data = {
            "outcomes": [baseline] + entries,
            "start_time": "2026-10-28T23:00:00Z",
            "end_time": None if cancelled else "2026-10-28T23:30:00Z",
            "cargo_mutants_version": "27.1.0",
            **_counters(entries),
        }
        (directory / "mutants.json").write_text(json.dumps(sub_planned), encoding="utf-8")
        (directory / "outcomes.json").write_text(json.dumps(data), encoding="utf-8")
        for name, predicate in (
            ("caught.txt", "CaughtMutant"),
            ("missed.txt", "MissedMutant"),
            ("timeout.txt", "Timeout"),
            ("unviable.txt", "Unviable"),
        ):
            lines = [e["scenario"]["Mutant"]["name"] for e in entries if e["summary"] == predicate]
            (directory / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        meta = {
            "shard": 0 if duplicate_index else k,
            "shards": n + 1 if wrong_denominator else n,
            "exit_code": "" if cancelled else "2",
            "step_outcome": "cancelled" if cancelled else "success",
            "step_conclusion": "cancelled" if cancelled else "success",
            "job_status": "cancelled" if cancelled else "success",
            "skip": "false",
        }
        (directory / "shard_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return shards_dir


def _derive_after_aggregate(agg, parser, shards_dir: Path, out: Path, **kwargs) -> dict[str, str]:
    summary = agg.aggregate(shards_dir, out, expect_shards=2, **kwargs)
    values = parser.derive(
        out,
        summary["exit_code"],
        step_outcome=summary["step_outcome"],
        step_conclusion=summary["step_outcome"],
        job_status="success",
    )
    return {"_summary": summary, **values}


# --- Complete aggregate keeps the real result -------------------------------


def test_complete_two_shard_round_reproduces_missed_14_of_200(tmp_path):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards")
    out = tmp_path / "mutants.out"

    summary = agg.aggregate(shards, out, expect_shards=2, shard_result="success")
    assert summary["complete"] is True
    assert summary["skip"] is False
    assert summary["planned"] == 200
    assert summary["recorded"] == 200
    assert summary["exit_code"] == "2"
    assert summary["problems"] == []

    merged = json.loads((out / "outcomes.json").read_text(encoding="utf-8"))
    assert merged["end_time"] is not None
    assert merged["total_mutants"] == 200
    assert merged["caught"] == 28
    assert merged["missed"] == 169
    assert merged["unviable"] == 3
    assert len(merged["outcomes"]) == 201  # 1 baseline + 200 mutants
    planned_names = {m["name"] for m in json.loads((out / "mutants.json").read_text())}
    assert len(planned_names) == 200

    values = parser.derive(
        out, "2", step_outcome="success", step_conclusion="success", job_status="success"
    )
    assert values["status"] == "missed"
    assert values["score"] == "14"
    assert values["total"] == "200"
    assert values["caught"] == "28"
    assert values["missed"] == "169"
    assert values["status"] in parser._VALID_STATUSES
    comment = parser.render_comment(values)
    assert "**Status:** `missed`" in comment
    assert "**Score** | **14**" in comment


def test_cli_end_to_end_with_exact_workflow_flags(tmp_path):
    """Both CLIs are driven exactly as the workflow drives them."""
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards")
    out = tmp_path / "mutants.out"
    gh_output = tmp_path / "gh_output.txt"
    comment = tmp_path / "comment.md"

    assert (
        agg.main(
            [
                "--shards-dir",
                str(shards),
                "--output",
                str(out),
                "--expect-shards",
                "2",
                "--shard-result",
                "success",
                "--github-output",
                str(gh_output),
            ]
        )
        == 0
    )
    aggregate_outputs = dict(
        line.split("=", 1) for line in gh_output.read_text(encoding="utf-8").splitlines()
    )
    assert aggregate_outputs["skip"] == "false"
    assert aggregate_outputs["exit_code"] == "2"
    assert aggregate_outputs["step_outcome"] == "success"
    assert aggregate_outputs["step_conclusion"] == "success"

    assert (
        parser.main(
            [
                "--mutants-out",
                str(out),
                "--exit-code",
                aggregate_outputs["exit_code"],
                "--step-outcome",
                aggregate_outputs["step_outcome"],
                "--step-conclusion",
                aggregate_outputs["step_conclusion"],
                "--job-status",
                "success",
                "--output",
                str(gh_output),
                "--comment-file",
                str(comment),
            ]
        )
        == 0
    )
    all_outputs = dict(
        line.split("=", 1) for line in gh_output.read_text(encoding="utf-8").splitlines()
    )
    assert all_outputs["status"] == "missed"
    assert all_outputs["score"] == "14"
    assert all_outputs["total"] == "200"
    assert "**Status:** `missed`" in comment.read_text(encoding="utf-8")


# --- Any incomplete leg must be rejected ------------------------------------


def test_truncated_shard_is_incomplete_and_rejected(tmp_path):
    """Reproduce run 40790621664: 195/200 planned mutants, one cancelled leg."""
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", drop_last=5, cancel_shard=1)
    out = tmp_path / "mutants.out"

    values = _derive_after_aggregate(agg, parser, shards, out, shard_result="cancelled")
    summary = values["_summary"]
    assert summary["complete"] is False
    assert summary["planned"] == 200
    assert summary["recorded"] == 195
    assert summary["exit_code"] == ""
    assert any("planned mutants have no outcome" in p for p in summary["problems"])
    assert json.loads((out / "outcomes.json").read_text())["end_time"] is None
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"
    assert values["total"] == "195"
    assert values["status"] not in parser._VALID_STATUSES
    assert "NOT a passing result" in parser.render_comment(values)


def test_missing_shard_artifact_forces_incomplete(tmp_path):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards")
    import shutil

    shutil.rmtree(shards / "mutation-shard-1")
    values = _derive_after_aggregate(agg, parser, shards, tmp_path / "out")
    assert values["_summary"]["complete"] is False
    assert values["status"] == "incomplete"


@pytest.mark.parametrize("extra_outcomes", [1, 3])
def test_unplanned_outcomes_force_incomplete(tmp_path, extra_outcomes):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", extra_outcomes=extra_outcomes)
    values = _derive_after_aggregate(agg, parser, shards, tmp_path / "out")
    assert any("not in the planned set" in p for p in values["_summary"]["problems"])
    assert values["status"] == "incomplete"


def test_duplicate_shard_index_forces_incomplete(tmp_path):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", duplicate_index=True)
    values = _derive_after_aggregate(agg, parser, shards, tmp_path / "out")
    assert values["_summary"]["complete"] is False
    assert values["status"] == "incomplete"


def test_wrong_shard_denominator_forces_incomplete(tmp_path):
    agg = _load("aggregate_mutation_shards", _AGG)
    shards = build_shards(tmp_path / "shards", wrong_denominator=True)
    summary = agg.aggregate(shards, tmp_path / "out", expect_shards=2)
    assert any("denominator mismatch" in p for p in summary["problems"])
    assert summary["complete"] is False


@pytest.mark.parametrize("result", ["cancelled", "failure", "timed_out"])
def test_non_success_matrix_result_forces_incomplete_even_with_full_artifacts(tmp_path, result):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards")
    values = _derive_after_aggregate(agg, parser, shards, tmp_path / "out", shard_result=result)
    assert values["_summary"]["complete"] is False
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


def test_all_shards_skipped_sets_skip_output_without_a_fake_result(tmp_path):
    agg = _load("aggregate_mutation_shards", _AGG)
    shards = build_shards(tmp_path / "shards", skip_all=True)
    out = tmp_path / "out"
    gh_output = tmp_path / "gh_output.txt"
    assert (
        agg.main(
            [
                "--shards-dir",
                str(shards),
                "--output",
                str(out),
                "--expect-shards",
                "2",
                "--shard-result",
                "success",
                "--github-output",
                str(gh_output),
            ]
        )
        == 0
    )
    outputs = dict(line.split("=", 1) for line in gh_output.read_text().splitlines())
    assert outputs["skip"] == "true"


@pytest.mark.parametrize("matrix_result", ["success", "failure", "cancelled"])
def test_one_skip_artifact_cannot_hide_a_missing_shard(tmp_path, matrix_result):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", skip_all=True)
    missing = shards / "mutation-shard-1"
    (missing / "shard_meta.json").unlink()
    missing.rmdir()
    values = _derive_after_aggregate(
        agg, parser, shards, tmp_path / "out", shard_result=matrix_result
    )
    assert values["_summary"]["skip"] is False
    assert values["_summary"]["complete"] is False
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


@pytest.mark.parametrize("matrix_result", ["", "failure", "cancelled", "timed_out", "skipped"])
def test_skip_artifacts_cannot_override_an_unsuccessful_matrix(tmp_path, matrix_result):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", skip_all=True)
    values = _derive_after_aggregate(
        agg, parser, shards, tmp_path / "out", shard_result=matrix_result
    )
    assert values["_summary"]["skip"] is False
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


@pytest.mark.parametrize(
    "field,value",
    [
        ("shard", 0),  # duplicate index
        ("shard", 2),  # unexpected index
        ("shards", 3),
        ("shards", None),
        ("job_status", "failure"),
        ("job_status", "cancelled"),
        ("step_outcome", "cancelled"),
        ("step_conclusion", "failure"),
        ("step_outcome", ""),
    ],
)
def test_skip_requires_complete_valid_runner_metadata(tmp_path, field, value):
    agg = _load("aggregate_mutation_shards", _AGG)
    parser = _load("parse_mutation_results", _PARSER)
    shards = build_shards(tmp_path / "shards", skip_all=True)
    path = shards / "mutation-shard-1" / "shard_meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta[field] = value
    path.write_text(json.dumps(meta), encoding="utf-8")
    values = _derive_after_aggregate(agg, parser, shards, tmp_path / "out")
    assert values["_summary"]["skip"] is False
    assert values["status"] == "incomplete"
    assert values["score"] == "N/A"


# --- The workflow must really wire all of this ------------------------------


def _parse_step_block(text: str) -> str:
    match = re.search(
        r"- name: Parse mutation results\n(?P<body>.*?)(?=\n      - name: |\Z)",
        text,
        re.DOTALL,
    )
    assert match, "Parse mutation results step not found"
    return match.group("body")


def _job_block(text: str, name: str) -> str:
    match = re.search(
        r"^  " + re.escape(name) + r":\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"job {name!r} not found"
    return match.group("body")


def test_workflow_keeps_all_200_mutants_in_two_deterministic_shards():
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = _job_block(text, "incremental")
    assert re.search(r"matrix:\s*\n\s+shard: \[0, 1\]", block)
    assert "fail-fast: false" in block
    assert "--shard ${{ matrix.shard }}/2" in block
    assert "--sharding round-robin" in block
    timeout = re.search(r"timeout-minutes:\s*(\d+)", block)
    assert timeout and int(timeout.group(1)) == 60, "timeout must not be raised again"
    # No sampling or mutant-limit escape hatch.
    assert "--mutant-limit" not in block
    assert "--shard 0/1" not in block
    # The manual single-crate shard input is preserved.
    assert 'shard_arg="--shard ${{ github.event.inputs.shard }}"' in text


def test_workflow_aggregate_and_parse_bind_real_runner_contexts():
    text = _WORKFLOW.read_text(encoding="utf-8")
    report = _job_block(text, "report")
    assert "needs: incremental" in report
    aggregate_step = re.search(
        r"- name: Aggregate shard results\n(?P<body>.*?)(?=\n      - name: |\Z)",
        report,
        re.DOTALL,
    )
    assert aggregate_step
    assert "SHARD_RESULT: ${{ needs.incremental.result }}" in aggregate_step.group("body")
    for flag in (
        "--shards-dir",
        "--output",
        "--expect-shards",
        "--shard-result",
        "--github-output",
    ):
        assert flag in aggregate_step.group("body")

    # Shard legs persist the authoritative runner contexts into the artifact.
    shard_step = re.search(
        r"- name: Record shard context\n(?P<body>.*?)(?=\n      - name: |\Z)",
        _job_block(text, "incremental"),
        re.DOTALL,
    )
    assert shard_step
    for expression in (
        "${{ steps.mutants.outputs.exit_code }}",
        "${{ steps.mutants.outcome }}",
        "${{ steps.mutants.conclusion }}",
        "${{ job.status }}",
        "${{ steps.changed.outputs.skip }}",
    ):
        assert expression in shard_step.group("body")

    parse_step = _parse_step_block(text)
    for env_name, expression in (
        ("MUTANTS_EXIT_CODE", "${{ steps.aggregate.outputs.exit_code }}"),
        ("MUTANTS_STEP_OUTCOME", "${{ steps.aggregate.outputs.step_outcome }}"),
        ("MUTANTS_STEP_CONCLUSION", "${{ steps.aggregate.outputs.step_conclusion }}"),
        ("JOB_STATUS", "${{ job.status }}"),
    ):
        assert re.search(rf"{env_name}:\s*{re.escape(expression)}", parse_step)
    for flag, env_name in (
        ("--exit-code", "MUTANTS_EXIT_CODE"),
        ("--step-outcome", "MUTANTS_STEP_OUTCOME"),
        ("--step-conclusion", "MUTANTS_STEP_CONCLUSION"),
        ("--job-status", "JOB_STATUS"),
    ):
        assert re.search(rf"{flag} \"\${env_name}\"", parse_step)


def test_workflow_gate_and_skip_semantics_preserved():
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"pass\|missed\)\s+echo \"Valid mutation result", text)
    assert "::error::No valid mutation result" in text
    assert "steps.aggregate.outputs.skip != 'true'" in text
    # The fully merged artifact keeps the original public artifact name.
    assert "name: mutation-results-incremental" in text
    assert "pattern: mutation-shard-*" in text
