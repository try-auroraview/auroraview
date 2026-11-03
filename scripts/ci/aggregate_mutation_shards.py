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
no changed line is mutatable, cargo-mutants exits 0 on every shard but writes
neither ``mutants.json`` nor ``outcomes.json``. Provided every leg finished
normally (persisted exit code 0, step/job ``success``, no cancellation) and
the shard matrix result is ``success``, the aggregate emits an explicit
``skip`` / N/A instead of an ``incomplete`` result. A cancelled leg, a missing
artifact on just one leg, a bad exit code or a failed matrix is still rejected:
an empty set never masks a genuinely broken run.
"""

from __future__ import annotations

import argparse
import json
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
# A zero-mutant --in-diff run uploads only shard_meta.json. These are the only
# artifact notices that a legitimate empty set may produce; anything else is a
# real completeness defect and must keep the result invalid.
_EMPTY_SET_ARTIFACT_PROBLEM = re.compile(
    r"^shard \d+: (mutants\.json missing/invalid|outcomes\.json missing/invalid)$"
)


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
) -> bool:
    """True only for a provably empty, fully completed ``--in-diff`` run.

    cargo-mutants writes neither ``mutants.json`` nor ``outcomes.json`` when the
    changed lines contain no mutatable code, yet exits 0 on every shard. Treat
    that shape as an explicit N/A (skip) instead of ``incomplete`` -- but only
    when every leg finished normally and no unrelated completeness check
    failed. A cancelled leg, a missing artifact on just one leg, a bad exit
    code, a failed matrix result or a declared skip must still be rejected.
    """
    if planned or recorded:
        return False
    if not problems or "no planned mutants found" not in problems:
        return False
    if any(
        problem != "no planned mutants found" and not _EMPTY_SET_ARTIFACT_PROBLEM.match(problem)
        for problem in problems
    ):
        return False
    if shard_result != "success":
        return False
    if len(shard_dirs) != expect_shards or set(legs) != expected_indices:
        return False
    for _, meta in legs.values():
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
    return True


def aggregate(
    shards_dir: Path,
    output: Path,
    *,
    expect_shards: int = 2,
    shard_result: str = "success",
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

    # A legitimate empty --in-diff set is an explicit N/A, not a defect. The
    # missing-manifest/outcomes notices are expected for that shape; drop them
    # so they are not reported as problems, but keep `complete` false through
    # the explicit empty_diff flag (there is no scored result to publish).
    empty_diff = _legitimate_empty_diff(
        problems=problems,
        legs=legs,
        shard_dirs=shard_dirs,
        expect_shards=expect_shards,
        expected_indices=expected_indices,
        planned=planned,
        recorded=recorded,
        shard_result=shard_result,
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
    args = parser.parse_args(argv)

    summary = aggregate(
        args.shards_dir,
        args.output,
        expect_shards=args.expect_shards,
        shard_result=args.shard_result,
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
