#!/usr/bin/env python3
"""Summarise a ``cargo-mutants`` run for the ``Mutation Testing`` workflow.

The workflow used to parse results inline in bash with::

    caught=$(grep -c "." mutants.out/caught.txt 2>/dev/null || echo "0")

On an empty file ``grep -c`` prints ``0`` *and* exits 1, so ``|| echo "0"``
appends a second ``0`` and the variable becomes ``"0\n0"``. Feeding that into
``$((caught + missed))`` aborts the step under ``bash -e``. Worse, a run that
produced no results at all (missing ``mutants.out``, a failed unmutated
baseline, or zero generated mutants) was reported as ``score=100`` plus
"All mutations were caught by tests." -- a false pass.

This module reads the authoritative ``mutants.out/outcomes.json`` when present,
falls back to counting non-empty lines in the legacy ``*.txt`` files, and
emits single-line, integer-valued GitHub Actions outputs. It never reports a
passing score for an invalid / no-baseline / zero-mutant run; those statuses
are surfaced so the job fails honestly instead of appearing green.

Run 40773589794 exposed a second false-pass path: the 30-minute job cap
cancelled the cargo-mutants step mid-run, so ``exit_code`` was never persisted
and ``outcomes.json`` held only 129 of 200 planned mutants with
``end_time: null``. The old parser treated the empty exit code as OK and
reported ``status=missed score=14`` as a *valid* result. The workflow now also
passes the real step outcome/conclusion and job status; together with the
artifact's own completion markers (``end_time`` and the ``mutants.json``
manifest) a cancelled/incomplete/partial run is reported as ``incomplete``
with ``score=N/A`` and is rejected by the gate. Genuine ``missed`` results are
still reported and scored, never hidden.

Exit status is always 0 (outputs must be written even for invalid results); a
dedicated workflow step fails the job based on the ``status`` output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# cargo-mutants exit codes. 0 = all caught, 2 = missed mutants found,
# 3 = timeout, 4 = unmutated (clean tree) baseline failed, 1 = usage/other.
# An EMPTY code is NOT ok: it means the cargo-mutants step was cancelled
# before it could persist its exit code.
_KNOWN_OK_CODES = {"0", "2"}
_STATUS_BY_CODE = {"1": "error", "3": "timeout", "4": "baseline_failed"}

_SUMMARY = {
    "pass": "All {total} mutants were caught by the test suite (score {score}%).",
    "missed": "{missed} mutant(s) survived; add tests for the affected code paths (score {score}%).",
    "baseline_failed": (
        "The unmutated baseline failed to build/test, so no mutants were tested. "
        "This is NOT a passing result."
    ),
    "no_mutants": (
        "cargo-mutants generated 0 mutants, so nothing was verified. This is NOT a passing result."
    ),
    "no_results": (
        "No mutation results directory was produced; the run did not complete. "
        "This is NOT a passing result."
    ),
    "error": "cargo-mutants exited abnormally ({code}); results are incomplete. NOT a passing result.",
    "timeout": "cargo-mutants timed out; results are incomplete. NOT a passing result.",
    "incomplete": (
        "The mutation run did not finish: the mutants step or job was cancelled/"
        "timed out, its exit code is missing, or only part of the planned mutants "
        "was evaluated. The result set is incomplete. This is NOT a passing result."
    ),
}

# Statuses that represent a genuine, usable mutation-testing result. Anything
# else must fail the job rather than being hidden behind a green check.
_VALID_STATUSES = frozenset({"pass", "missed"})

# GitHub Actions outcome/conclusion/status values that prove the cargo-mutants
# step was interrupted rather than finishing. NOTE: ``failure`` is deliberately
# NOT here -- cargo-mutants exits 2 (missed mutants) as a *completed* run, and
# its step legitimately has outcome=failure. Only cancellation/skip means the
# result set is partial.
_INTERRUPTED_STATUSES = frozenset(
    {"cancelled", "timed_out", "skipped", "action_required", "stale", "neutral"}
)


def count_nonempty_lines(path: Path) -> int:
    """Return the number of non-empty lines in *path*, or 0 if unreadable.

    Always returns a single ``int`` -- never a multi-line string. This replaces
    the ``grep -c ... || echo 0`` pattern that produced ``"0\\n0"`` on empty
    files and broke shell arithmetic.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def _load_outcomes(mutants_out: Path) -> dict | None:
    """Return parsed outcomes.json, or None when absent/unreadable/invalid."""
    try:
        data = json.loads((mutants_out / "outcomes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return data if isinstance(data, dict) else None


def _planned_mutants(mutants_out: Path) -> int | None:
    """Number of mutants cargo-mutants planned to test.

    ``mutants.json`` is written before the run starts and lists every planned
    mutant. It is the authoritative denominator for completeness; a partial
    ``outcomes.json`` cannot be mistaken for a finished run when this file is
    present. Returns None when the manifest is absent (older/synthetic runs).
    """
    try:
        data = json.loads((mutants_out / "mutants.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return len(data) if isinstance(data, list) else None


def _recorded_mutants(outcomes: dict | None) -> int | None:
    """Count mutant scenarios actually present in outcomes.json.

    The ``outcomes`` list also holds one ``Baseline`` entry, which is not a
    mutant. Returns None when the list is unusable.
    """
    if not outcomes:
        return None
    entries = outcomes.get("outcomes")
    if not isinstance(entries, list):
        return None
    return sum(
        1 for entry in entries if isinstance(entry, dict) and entry.get("scenario") != "Baseline"
    )


def _run_interrupted(*signals: str) -> bool:
    """True when a GitHub Actions outcome/conclusion/status shows interruption.

    Only ``cancelled`` / ``timed_out`` / ``skipped`` (and their rarer variants)
    count. A ``failure`` step is NOT evidence of interruption: cargo-mutants
    exits 2 for a completed run with missed mutants, and its step fails while
    still having produced a full, valid result set. Empty/unset values and
    ``success`` are ignored so artifact-only callers still work.
    """
    return any((s or "").strip().lower() in _INTERRUPTED_STATUSES for s in signals)


def _baseline_failed(outcomes: dict | None) -> bool:
    """True when outcomes.json records a failed 'Baseline' scenario."""
    if not outcomes:
        return False
    for entry in outcomes.get("outcomes", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("scenario") == "Baseline" and entry.get("summary") != "Success":
            return True
    return False


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def derive(
    mutants_out: Path,
    exit_code: str = "",
    *,
    step_outcome: str = "",
    step_conclusion: str = "",
    job_status: str = "",
) -> dict[str, str]:
    """Compute the GitHub Actions outputs for a mutation run.

    The result always contains: caught, missed, timeout, unviable, total,
    score, status, summary. ``score`` is a bare integer string for valid runs
    and ``"N/A"`` for any invalid/no-baseline/no-mutant/incomplete result.

    Completeness is established from the artifact itself (``end_time`` and the
    ``mutants.json`` manifest) AND from the workflow-supplied step/job status,
    so a partial run cannot be reported as a complete ``missed``/``pass``
    result even if one signal is missing.
    """
    code = (exit_code or "").strip()
    outcomes = _load_outcomes(mutants_out) if mutants_out.is_dir() else None
    planned = _planned_mutants(mutants_out) if mutants_out.is_dir() else None
    recorded = _recorded_mutants(outcomes)

    if outcomes is not None:
        caught = _as_int(outcomes.get("caught"))
        missed = _as_int(outcomes.get("missed"))
        timeout = _as_int(outcomes.get("timeout"))
        unviable = _as_int(outcomes.get("unviable"))
        total = _as_int(outcomes.get("total_mutants"))
    else:
        caught = missed = timeout = unviable = total = 0
        if mutants_out.is_dir():
            caught = count_nonempty_lines(mutants_out / "caught.txt")
            missed = count_nonempty_lines(mutants_out / "missed.txt")
            timeout = count_nonempty_lines(mutants_out / "timeout.txt")
            unviable = count_nonempty_lines(mutants_out / "unviable.txt")
            total = caught + missed + timeout + unviable

    # A cancelled/partial run can never be reported as a complete, scored
    # result. Four independent signals, any one of which is sufficient:
    #  1. the workflow says the step/job did not finish successfully;
    #  2. outcomes.json still has end_time == null (written mid-run);
    #  3. fewer mutant scenarios recorded than mutants.json planned;
    #  4. no exit code was persisted (the step never reached its last line).
    incomplete = _run_interrupted(step_outcome, step_conclusion, job_status)
    if outcomes is not None and "end_time" in outcomes and outcomes.get("end_time") is None:
        incomplete = True
    if planned is not None and recorded is not None and recorded < planned:
        incomplete = True
    if not code:
        incomplete = True

    # Determine status, most severe first. An invalid baseline / no results can
    # never be reported as 100% pass, regardless of what the counters say.
    if not mutants_out.is_dir():
        status = "no_results"
    elif _baseline_failed(outcomes) or code == "4":
        status = "baseline_failed"
    elif incomplete:
        # Proven interruption/truncation wins over a generic error code: a
        # killed process may report e.g. 137, but the result set is still only
        # partial and must never be published as a scored, valid result.
        status = "incomplete"
    elif code in _STATUS_BY_CODE:
        status = _STATUS_BY_CODE[code]
    elif code and code not in _KNOWN_OK_CODES:
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
    if status in _VALID_STATUSES and denominator > 0:
        score = str(caught * 100 // denominator)
    else:
        score = "N/A"

    summary = _SUMMARY[status].format(
        total=total, missed=missed, score=score, code=code or "unknown"
    )

    return {
        "caught": str(caught),
        "missed": str(missed),
        "timeout": str(timeout),
        "unviable": str(unviable),
        "total": str(total),
        "score": score,
        "status": status,
        "summary": summary,
    }


def write_outputs(values: dict[str, str], output_path: Path | None) -> None:
    """Write ``key=value`` lines to a GitHub Actions output file (or stdout)."""
    lines = [f"{key}={value}" for key, value in values.items()]
    # Guard against accidental multi-line values corrupting $GITHUB_OUTPUT.
    for line in lines:
        assert "\n" not in line, f"multi-line output value: {line!r}"
    if output_path is None:
        sys.stdout.write("\n".join(lines) + "\n")
    else:
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def render_comment(values: dict[str, str], missed_text: str = "") -> str:
    """Render the PR comment body. Only a genuine ``pass`` says "all caught"."""
    lines = [
        "## Mutation Testing Results",
        "",
        f"**Status:** `{values['status']}`",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Caught | {values['caught']} |",
        f"| Missed | {values['missed']} |",
        f"| Timeout | {values['timeout']} |",
        f"| Unviable | {values['unviable']} |",
        f"| Total mutants | {values['total']} |",
        f"| **Score** | **{values['score']}** |",
        "",
        values["summary"],
    ]
    if values["status"] == "missed" and missed_text.strip():
        lines += [
            "",
            "<details><summary>Missed mutants</summary>",
            "",
            "```",
            missed_text.strip()[:3000],
            "```",
            "</details>",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mutants-out",
        type=Path,
        default=Path("mutants.out"),
        help="cargo-mutants output directory",
    )
    parser.add_argument(
        "--exit-code",
        default="",
        help="cargo-mutants process exit code (${{ steps.mutants.outputs.exit_code }})",
    )
    parser.add_argument(
        "--step-outcome",
        default="",
        help="${{ steps.mutants.outcome }} of the cargo-mutants step",
    )
    parser.add_argument(
        "--step-conclusion",
        default="",
        help="${{ steps.mutants.conclusion }} of the cargo-mutants step",
    )
    parser.add_argument(
        "--job-status",
        default="",
        help="${{ job.status }} while parsing the results",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="path to $GITHUB_OUTPUT; omit to print to stdout",
    )
    parser.add_argument(
        "--comment-file",
        type=Path,
        default=None,
        help="path to write the rendered PR comment Markdown",
    )
    args = parser.parse_args(argv)

    values = derive(
        args.mutants_out,
        args.exit_code,
        step_outcome=args.step_outcome,
        step_conclusion=args.step_conclusion,
        job_status=args.job_status,
    )
    write_outputs(values, args.output)
    if args.comment_file is not None:
        missed_text = ""
        try:
            missed_text = (args.mutants_out / "missed.txt").read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            pass
        args.comment_file.write_text(render_comment(values, missed_text), encoding="utf-8")
    print(
        f"mutation results: status={values['status']} score={values['score']} "
        f"total={values['total']} caught={values['caught']} missed={values['missed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
