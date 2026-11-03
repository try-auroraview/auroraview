#!/usr/bin/env python3
"""Merge deterministic cargo-mutants shards into one honest result set.

The PR mutation job is split into N ``--shard k/N`` matrix legs so the full
planned mutant set fits inside the 60-minute job cap. Each leg uploads its
own ``mutants.out`` directory. This helper merges those directories back into
a single ``mutants.out`` that ``parse_mutation_results.py`` can judge unchanged.

Aggregate completeness is enforced by NAME, not by a counter:

* exactly ``--expect-shards`` legs, with indices 0..N-1 present once;
* every leg's ``outcomes.json`` has ``end_time`` set and a persisted exit code;
* no leg reports a cancelled/timed-out/skipped step or job;
* the union of per-leg ``mutants.json`` names equals the recorded mutant
  outcome names, each appearing exactly once (no dropped, duplicated or
  invented mutants);
* the shard matrix job's ``needs.<job>.result`` is ``success``.

If any check fails, the merged ``outcomes.json`` keeps ``end_time: null`` and
the aggregate exit code is empty, so the parser reports ``incomplete`` /
``N/A`` and the gate rejects it. Nothing is ever rounded up to a pass.

The one intentional exception is a legitimately empty ``--in-diff`` set: when
no changed line is mutatable, cargo-mutants logs ``No mutants to filter`` on
every shard, exits 0 and writes neither ``mutants.json`` nor ``outcomes.json``.

Emptiness is NEVER inferred from missing files alone: a corrupt, lost or
truncated artifact looks exactly the same. Each shard must upload a positive
``zero_candidates.json`` attestation written by its own cargo-mutants step,
bound to the workflow run (``run_id`` / ``run_attempt`` / ``head_sha``) and to
the SHA-256 of the exact ``mutation.diff`` used. The aggregate verifies every
attestation, requires the diff files to match, requires both artifact files to
be genuinely absent (not present-but-invalid), and requires every leg to have
finished normally with a successful matrix result. Only then does it emit an
explicit ``skip`` / N/A. Cancelled legs, corrupt or missing artifacts without
that proof, bad exit codes and failed matrices still stay ``incomplete``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

_COUNTERS = ("caught", "missed", "timeout", "unviable", "total_mutants", "success")
_TXT_FILES = ("caught.txt", "missed.txt", "timeout.txt", "unviable.txt")
# A shard leg that did not finish normally. ``failure`` is included here on
# purpose: a failed matrix leg cannot be trusted to have uploaded a complete
# artifact, even if its outcomes.json happens to look finished.
_INTERRUPTED = frozenset(
    {"cancelled", "timed_out", "skipped", "failure", "action_required", "stale", "neutral"}
)
# Producer-side proof for a genuinely empty --in-diff set. The shard step
# writes this only when cargo-mutants itself logged "No mutants to filter" for
# THIS run's diff and exited 0. Without it, missing artifacts are incomplete.
_ZERO_CANDIDATE_SCHEMA = 1
_NO_MUTANTS_SIGNAL = "No mutants to filter"
_DIFF_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load_json(path: Path):  # noqa: ANN201
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _mutant_name(entry: dict) -> str | None:
    scenario = entry.get("scenario")
    if isinstance(scenario, dict):
        mutant = scenario.get("Mutant")
        if isinstance(mutant, dict):
            name = mutant.get("name")
            return name if isinstance(name, str) else None
    return None


def _joined_text(chunks: list[str]) -> str:
    parts = []
    for chunk in chunks:
        if chunk and not chunk.endswith("\n"):
            chunk += "\n"
        if chunk:
            parts.append(chunk)
    return "".join(parts)


def _zero_candidate_proofs(
    legs: dict[int, tuple[Path, dict]],
    *,
    expect_shards: int,
    run_id: str,
    run_attempt: str,
    head_sha: str,
) -> bool:
    """Require positive, run-bound zero-candidate evidence on every leg.

    A shard writes ``zero_candidates.json`` only when its own cargo-mutants
    step logged ``No mutants to filter`` for this run's ``mutation.diff`` and
    exited 0. The proofs must all agree with the report job's real run identity
    and with the SHA-256 of the diff actually uploaded in each artifact, so a
    stale or replayed artifact from another run cannot be mistaken for this
    run's empty set.
    """
    if set(legs) != set(range(expect_shards)):
        return False
    if not run_id or not run_attempt or not head_sha:
        return False
    common_digest: str | None = None
    for index, (directory, _) in legs.items():
        proof = _load_json(directory / "zero_candidates.json")
        if not isinstance(proof, dict):
            return False
        if proof.get("schema") != _ZERO_CANDIDATE_SCHEMA:
            return False
        if proof.get("zero_candidates") is not True:
            return False
        if proof.get("shard") != index or proof.get("shards") != expect_shards:
            return False
        if str(proof.get("run_id", "")) != run_id:
            return False
        if str(proof.get("run_attempt", "")) != run_attempt:
            return False
        if str(proof.get("head_sha", "")) != head_sha:
            return False
        if str(proof.get("cargo_mutants_exit_code", "")) != "0":
            return False
        if proof.get("no_mutants_signal") != _NO_MUTANTS_SIGNAL:
            return False
        if proof.get("mutants_found") != 0:
            return False
        try:
            digest = hashlib.sha256((directory / "mutation.diff").read_bytes()).hexdigest()
        except OSError:
            return False
        proof_digest = str(proof.get("diff_sha256", "")).strip().lower()
        if not _DIFF_SHA256.fullmatch(proof_digest) or proof_digest != digest:
            return False
        if common_digest is None:
            common_digest = digest
        elif digest != common_digest:
            return False
    return True


def _legitimate_empty_diff(
    *,
    problems: list[str],
    legs: dict[int, tuple[Path, dict]],
    shard_dirs: list[Path],
    expect_shards: int,
    expected_indices: set[int],
    planned: dict[str, dict],
    recorded: dict[str, dict],
    shard_result: str,
    run_id: str,
    run_attempt: str,
    head_sha: str,
) -> bool:
    """True only for a provably empty, fully completed ``--in-diff`` run.

    Missing ``mutants.json`` / ``outcomes.json`` alone proves nothing: both
    files may be corrupt, truncated or never uploaded. The empty verdict needs
    a positive producer attestation on every leg, plus an otherwise spotless
    run. Any cancelled leg, corrupt/present artifact, bad exit code, failed
    matrix result or declared skip is still rejected as ``incomplete``.
    """
    if planned or recorded or shard_result != "success":
        return False
    if len(shard_dirs) != expect_shards or set(legs) != expected_indices:
        return False

    # With both artifacts genuinely absent on every leg, these are the ONLY
    # completeness notices the aggregate can produce. Any extra problem (an
    # interrupted signal, a missing exit code, a duplicate outcome, a counter
    # or denominator mismatch, ...) disqualifies the run.
    expected_problems = {"no planned mutants found"}
    for index in range(expect_shards):
        expected_problems.add(f"shard {index}: mutants.json missing/invalid")
        expected_problems.add(f"shard {index}: outcomes.json missing/invalid")
    if sorted(problems) != sorted(expected_problems):
        return False

    for _, (directory, meta) in legs.items():
        # Present-but-corrupt artifacts are NOT an empty set. The producer only
        # attests zero candidates when neither file exists at all.
        if (directory / "mutants.json").exists() or (directory / "outcomes.json").exists():
            return False
        signals = [
            str(meta.get(key, "")).strip().lower()
            for key in ("step_outcome", "step_conclusion", "job_status")
        ]
        if any(signal != "success" for signal in signals):
            return False
        if str(meta.get("exit_code", "")).strip() != "0":
            return False
        if str(meta.get("skip", "")).strip().lower() == "true":
            return False
        if str(meta.get("windows_only", "")).strip().lower() == "true":
            return False
        if meta.get("shards") not in (None, expect_shards, str(expect_shards)):
            return False

    return _zero_candidate_proofs(
        legs,
        expect_shards=expect_shards,
        run_id=run_id,
        run_attempt=run_attempt,
        head_sha=head_sha,
    )


def aggregate(
    shards_dir: Path,
    output: Path,
    *,
    expect_shards: int = 2,
    shard_result: str = "success",
    run_id: str = "",
    run_attempt: str = "",
    head_sha: str = "",
) -> dict:
    """Merge shards into *output* and return a machine-readable summary."""
    problems: list[str] = []
    shard_dirs = []
    if shards_dir.is_dir():
        shard_dirs = sorted(p for p in shards_dir.iterdir() if p.is_dir())

    if shard_result and shard_result != "success":
        problems.append(f"shard matrix result={shard_result}")

    legs: dict[int, tuple[Path, dict]] = {}
    for directory in shard_dirs:
        meta = _load_json(directory / "shard_meta.json")
        if not isinstance(meta, dict):
            problems.append(f"{directory.name}: missing/invalid shard_meta.json")
            continue
        try:
            index = int(meta.get("shard"))
        except (TypeError, ValueError):
            problems.append(f"{directory.name}: invalid shard index")
            continue
        if index in legs:
            problems.append(f"duplicate shard index {index}")
            continue
        legs[index] = (directory, meta)

    if len(shard_dirs) != expect_shards:
        problems.append(f"expected {expect_shards} shard artifacts, found {len(shard_dirs)}")
    expected_indices = set(range(expect_shards))
    missing_indices = expected_indices - set(legs)
    if missing_indices:
        problems.append(f"missing shard indices {sorted(missing_indices)}")

    skips = [str(meta.get("skip", "")).strip().lower() for _, meta in legs.values()]
    # Skipping the parser/gate is safe only when EVERY expected leg confirms
    # an intentional no-change skip. One surviving skip artifact must not hide
    # a missing, malformed, failed or cancelled sibling.
    all_skipped = (
        bool(skips)
        and not problems
        and set(legs) == expected_indices
        and shard_result == "success"
        and all(skip == "true" for skip in skips)
        and all(
            meta.get("shards") in (expect_shards, str(expect_shards))
            and meta.get("job_status") == "success"
            and meta.get("step_outcome") == "skipped"
            and meta.get("step_conclusion") == "skipped"
            for _, meta in legs.values()
        )
    )

    planned: dict[str, dict] = {}
    recorded: dict[str, dict] = {}
    baseline: dict | None = None
    counters = dict.fromkeys(_COUNTERS, 0)
    start_times: list[str] = []
    end_times: list[str] = []
    exit_codes: list[str] = []
    txt_chunks: dict[str, list[str]] = {name: [] for name in _TXT_FILES}

    for index in sorted(legs):
        directory, meta = legs[index]
        for key in ("step_outcome", "step_conclusion", "job_status"):
            value = str(meta.get(key, "")).strip().lower()
            if value in _INTERRUPTED:
                problems.append(f"shard {index}: {key}={value}")
        code = str(meta.get("exit_code", "")).strip()
        if not code:
            problems.append(f"shard {index}: exit code not persisted")
        else:
            exit_codes.append(code)
        if meta.get("shards") not in (None, expect_shards, str(expect_shards)):
            problems.append(f"shard {index}: denominator mismatch {meta.get('shards')}")

        manifest = _load_json(directory / "mutants.json")
        if not isinstance(manifest, list):
            problems.append(f"shard {index}: mutants.json missing/invalid")
        else:
            for entry in manifest:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    planned.setdefault(entry["name"], entry)

        outcomes = _load_json(directory / "outcomes.json")
        if not isinstance(outcomes, dict):
            problems.append(f"shard {index}: outcomes.json missing/invalid")
        else:
            end_time = outcomes.get("end_time")
            if not end_time:
                problems.append(f"shard {index}: end_time missing (run truncated)")
            else:
                end_times.append(str(end_time))
            start_time = outcomes.get("start_time")
            if start_time:
                start_times.append(str(start_time))
            entries = outcomes.get("outcomes")
            if not isinstance(entries, list):
                problems.append(f"shard {index}: outcomes list missing")
            else:
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("scenario") == "Baseline":
                        if baseline is None:
                            baseline = entry
                        continue
                    name = _mutant_name(entry)
                    if not name:
                        continue
                    if name in recorded:
                        problems.append(f"shard {index}: duplicate outcome for {name}")
                    else:
                        recorded[name] = entry
            for key in _COUNTERS:
                counters[key] += _as_int(outcomes.get(key))

        for name in _TXT_FILES:
            try:
                txt_chunks[name].append(
                    (directory / name).read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                pass

    missing = set(planned) - set(recorded)
    extra = set(recorded) - set(planned)
    if missing:
        problems.append(f"{len(missing)} planned mutants have no outcome")
    if extra:
        problems.append(f"{len(extra)} outcomes are not in the planned set")
    if not planned:
        problems.append("no planned mutants found")
    if not all_skipped and counters["total_mutants"] != len(recorded):
        problems.append(
            f"counter total_mutants={counters['total_mutants']} != recorded={len(recorded)}"
        )

    # A legitimate empty --in-diff set is an explicit N/A, not a defect. It is
    # accepted only with a run-bound producer attestation on every leg; the
    # missing-manifest/outcomes notices are then dropped from `problems`, but
    # `complete` stays false through the explicit empty_diff flag (there is no
    # scored result to publish).
    empty_diff = _legitimate_empty_diff(
        problems=problems,
        legs=legs,
        shard_dirs=shard_dirs,
        expect_shards=expect_shards,
        expected_indices=expected_indices,
        planned=planned,
        recorded=recorded,
        shard_result=shard_result,
        run_id=run_id,
        run_attempt=run_attempt,
        head_sha=head_sha,
    )
    if empty_diff:
        problems = []

    skip = all_skipped or empty_diff
    complete = not problems and not all_skipped and not empty_diff
    signal = "success"
    if shard_result in {"cancelled", "timed_out", "skipped"}:
        signal = "cancelled"
    elif shard_result not in {"", "success"}:
        signal = "failure"

    if not complete:
        exit_code = ""
    else:
        bad_codes = [code for code in exit_codes if code not in {"0", "2"}]
        if bad_codes:
            exit_code = bad_codes[0]
        elif counters["missed"] > 0:
            exit_code = "2"
        else:
            exit_code = "0"

    output.mkdir(parents=True, exist_ok=True)
    (output / "mutants.json").write_text(
        json.dumps([planned[name] for name in sorted(planned)]), encoding="utf-8"
    )
    merged_entries = ([baseline] if baseline else []) + [
        recorded[name] for name in sorted(recorded)
    ]
    merged = {
        "outcomes": merged_entries,
        "total_mutants": counters["total_mutants"],
        "caught": counters["caught"],
        "missed": counters["missed"],
        "timeout": counters["timeout"],
        "unviable": counters["unviable"],
        "success": counters["success"],
        "start_time": min(start_times) if start_times else None,
        # A null end_time is the parser's authoritative "this run is partial"
        # marker. Never set it when any completeness check failed.
        "end_time": max(end_times) if complete and end_times else None,
        "cargo_mutants_version": "sharded",
    }
    (output / "outcomes.json").write_text(json.dumps(merged), encoding="utf-8")
    for name in _TXT_FILES:
        (output / name).write_text(_joined_text(txt_chunks[name]), encoding="utf-8")
    (output / "aggregate_exit_code.txt").write_text(exit_code, encoding="utf-8")

    return {
        "complete": complete,
        "skip": skip,
        "empty": empty_diff,
        "exit_code": exit_code,
        "step_outcome": signal if complete else ("success" if skip else "failure"),
        "planned": len(planned),
        "recorded": len(recorded),
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards-dir", type=Path, default=Path("shards"))
    parser.add_argument("--output", type=Path, default=Path("mutants.out"))
    parser.add_argument("--expect-shards", type=int, default=2)
    parser.add_argument(
        "--shard-result",
        default="success",
        help="${{ needs.incremental.result }} of the shard matrix job",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="path to $GITHUB_OUTPUT; omit to print to stdout",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("GITHUB_RUN_ID", ""),
        help="GITHUB_RUN_ID; binds zero-candidate proofs to this workflow run",
    )
    parser.add_argument(
        "--run-attempt",
        default=os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        help="GITHUB_RUN_ATTEMPT; binds zero-candidate proofs to this attempt",
    )
    parser.add_argument(
        "--head-sha",
        default=os.environ.get("GITHUB_SHA", ""),
        help="GITHUB_SHA; binds zero-candidate proofs to this commit",
    )
    args = parser.parse_args(argv)

    summary = aggregate(
        args.shards_dir,
        args.output,
        expect_shards=args.expect_shards,
        shard_result=args.shard_result,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        head_sha=args.head_sha,
    )
    lines = [
        f"skip={'true' if summary['skip'] else 'false'}",
        f"empty={'true' if summary['empty'] else 'false'}",
        f"exit_code={summary['exit_code']}",
        f"step_outcome={summary['step_outcome']}",
        f"step_conclusion={summary['step_outcome']}",
    ]
    if args.github_output is None:
        print("\n".join(lines))
    else:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    print(
        "aggregate shards: complete={complete} skip={skip} empty={empty} "
        "planned={planned} recorded={recorded} exit_code={exit_code}".format(**summary)
    )
    if summary["empty"]:
        print(
            "aggregate shards: legitimate empty --in-diff set -> explicit N/A "
            "(skip), no scored mutation result"
        )
    for problem in summary["problems"]:
        print(f"aggregate problem: {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
