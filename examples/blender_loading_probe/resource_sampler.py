"""Launch Blender and persist process-tree resource samples incrementally.

Use ``--launch <blender.exe> <output-prefix>`` for the 20-run, 302-second
acceptance capture. ``--runs 2 --hold-seconds 12`` gives a short harness smoke.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import psutil


def events(path):
    if not path.exists():
        return set()
    result = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            result.add(json.loads(line)["event"])
        except (ValueError, KeyError):
            pass
    return result


def snapshot(host):
    try:
        members = [host] + host.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        members = []
    rows = []
    for member in members:
        try:
            cpu = member.cpu_times()
            rows.append(
                {
                    "pid": member.pid,
                    "name": member.name(),
                    "rss": member.memory_info().rss,
                    "cpu_seconds": cpu.user + cpu.system,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rows


def sample(pid, log, prefix, idle=False):
    try:
        host = psutil.Process(pid)
    except psutil.NoSuchProcess:
        host = None
    prefix.parent.mkdir(parents=True, exist_ok=True)
    samples_path = prefix.with_suffix(".jsonl")
    summary_path = prefix.with_suffix(".json")
    start = time.monotonic()
    previous_cpu = {}
    cpu_delta = 0.0
    first_hidden = None
    last_hidden = None
    baseline = None
    final_events = set()
    active_phase = "idle" if idle else "hidden"
    active_event = "idle_stable" if idle else "hidden_stable"
    with samples_path.open("w", encoding="utf-8") as stream:
        while time.monotonic() - start < 360:
            elapsed = time.monotonic() - start
            observed = events(log)
            if "closed" in observed:
                phase = "closed"
            elif active_event in observed:
                phase = active_phase
            elif idle or "prepare_started" not in observed:
                phase = "preprepare"
            else:
                phase = "preparing_or_reopening"
            rows = snapshot(host) if host is not None else []
            for row in rows:
                old = previous_cpu.get(row["pid"])
                if old is not None and phase == active_phase and first_hidden is not None:
                    cpu_delta += max(0.0, row["cpu_seconds"] - old)
                previous_cpu[row["pid"]] = row["cpu_seconds"]
            sample = {
                "elapsed_seconds": round(elapsed, 3),
                "phase": phase,
                "tree_rss": sum(row["rss"] for row in rows),
                "members": rows,
            }
            stream.write(json.dumps(sample) + "\n")
            stream.flush()
            if phase == "preprepare":
                baseline = sample
            if phase == active_phase and rows:
                if first_hidden is None:
                    first_hidden = sample
                last_hidden = sample
            final_events = observed
            if not rows and elapsed > 2:
                break
            if "closed" in observed and last_hidden is not None:
                break
            time.sleep(1 if phase == active_phase else 0.05)
    hidden_seconds = (
        last_hidden["elapsed_seconds"] - first_hidden["elapsed_seconds"]
        if first_hidden and last_hidden
        else 0
    )
    summary = {
        "baseline": baseline,
        "mode": active_phase,
        "post20_hidden": first_hidden if not idle else None,
        "hidden_end": last_hidden if not idle else None,
        "idle_start": first_hidden if idle else None,
        "idle_end": last_hidden if idle else None,
        "sample_seconds": round(hidden_seconds, 3),
        f"{active_phase}_cpu_one_core_percent": round(cpu_delta / hidden_seconds * 100, 3)
        if hidden_seconds > 0
        else None,
        "events": sorted(final_events),
        "valid": baseline is not None and hidden_seconds >= 300 and "closed" in final_events,
        "samples": str(samples_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", metavar="BLENDER_EXE", required=True)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--hold-seconds", type=float, default=302)
    parser.add_argument("--idle", action="store_true", help="Measure Blender without AuroraView")
    args = parser.parse_args()
    if args.runs < 1 or args.hold_seconds <= 0:
        parser.error("runs and hold-seconds must be positive")
    prefix = args.prefix.resolve()
    log = prefix.with_suffix(".events.jsonl")
    if log.exists() or prefix.with_suffix(".jsonl").exists():
        parser.error("choose a fresh output prefix to keep samples unambiguous")
    profile = prefix.with_name(prefix.name + "-profile")
    probe = Path(__file__).with_name("idle_host.py" if args.idle else "__init__.py")
    command = [
        args.launch,
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(probe),
        "--",
    ]
    if args.idle:
        command.extend(["--seconds", str(args.hold_seconds), "--output", str(log)])
    else:
        command.extend(
            [
                "--retained",
                "--runs",
                str(args.runs),
                "--preprepare-delay",
                "2",
                "--hold-hidden-seconds",
                str(args.hold_seconds),
                "--quit",
                "--output",
                str(log),
                "--profile",
                str(profile),
            ]
        )
    process = subprocess.Popen(command)
    summary = sample(process.pid, log, prefix, args.idle)
    try:
        exit_code = process.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Blender did not exit after resource capture: pid={process.pid}"
        ) from exc
    if exit_code or (args.hold_seconds >= 300 and not summary["valid"]):
        raise RuntimeError(f"Invalid Blender resource capture: exit={exit_code} summary={summary}")


if __name__ == "__main__":
    main()
