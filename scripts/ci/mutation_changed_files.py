"""Classify changed Rust lines for the incremental mutation-testing job.

The ``incremental`` job runs on ``ubuntu-latest``. Code behind
``#[cfg(target_os = "windows")]`` is compiled out on that runner, so a PR whose
changed Rust lines all live inside such regions cannot be validated by
cargo-mutants there. For those PRs the authoritative signal is the Windows-native
test in ``pr-checks.yml`` (``runner.os == 'Windows'``), not this advisory job.

This module reports whether every changed Rust line is Windows-gated so the
workflow can skip with an explicit explanation instead of reporting a misleading
"no mutants completed" result. It only parses a unified diff and reads source
files; it never builds anything and has no third-party dependencies.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_WINDOWS_CFG_RE = re.compile(r'#!?\[cfg\([^)]*target_os\s*=\s*"windows"[^)]*\)\]')


def added_lines(diff_text: str) -> dict[str, set[int]]:
    """Return ``{path: {new-side line numbers}}`` for added lines in a unified diff."""
    result: dict[str, set[int]] = {}
    path: str | None = None
    new_lineno = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/"):
                target = target[2:]
            path = target if target.endswith(".rs") and target != "/dev/null" else None
            continue
        if line.startswith("--- ") or line.startswith("diff ") or line.startswith("index "):
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            new_lineno = int(hunk.group(1))
            continue
        if path is None:
            continue
        if line.startswith("+"):
            result.setdefault(path, set()).add(new_lineno)
            new_lineno += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
        elif line.startswith(" "):
            new_lineno += 1
    return result


def windows_line_ranges(source: str) -> list[tuple[int, int]]:
    """Return 1-based inclusive ranges of lines inside ``cfg(windows)`` items."""
    lines = source.splitlines()
    # A crate-level `#![cfg(target_os = "windows")]` gates the whole file.
    for line in lines[:20]:
        stripped = line.strip()
        if stripped.startswith("#![cfg(") and _WINDOWS_CFG_RE.search(stripped):
            return [(1, len(lines))]
    ranges: list[tuple[int, int]] = []
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if stripped.startswith("#[cfg(") and _WINDOWS_CFG_RE.search(stripped):
            j = i
            while j < n and (
                lines[j].strip().startswith("#[") or lines[j].strip().startswith("//")
            ):
                j += 1
            depth, started, k = 0, False, j
            while k < n:
                for ch in lines[k]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if not started and ";" in lines[k]:
                    break  # blockless item (e.g. `use ...;`)
                if started and depth <= 0:
                    break
                k += 1
            ranges.append((i + 1, min(k + 1, n)))
            i = k + 1
            continue
        i += 1
    return ranges


def _covers(ranges: list[tuple[int, int]], lineno: int) -> bool:
    return any(start <= lineno <= end for start, end in ranges)


def is_windows_only(root: Path, diff_text: str, changed_files: list[str]) -> bool:
    """True iff there are changed Rust lines and every one is Windows-gated.

    Any file that cannot be read, has no attributable added lines, or contains an
    added line outside a ``cfg(windows)`` region makes the whole diff "mixed"
    (returns False), which keeps mutation testing enabled. Detection is
    deliberately conservative: a false negative only runs an advisory job, while
    a false positive would silently skip it.
    """
    by_file = added_lines(diff_text)
    rust_files = [f for f in changed_files if f.endswith(".rs")]
    if not rust_files:
        return False
    for rel in rust_files:
        key = rel[2:] if rel.startswith("b/") else rel
        lines = by_file.get(key) or by_file.get(rel)
        if not lines:
            return False
        source = (root / key).read_text(encoding="utf-8") if (root / key).is_file() else None
        if source is None:
            return False
        ranges = windows_line_ranges(source)
        if not ranges or not all(_covers(ranges, ln) for ln in lines):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", default="mutation.diff")
    parser.add_argument("--files", default="changed-files.txt")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", help="path to GITHUB_OUTPUT to append the result")
    args = parser.parse_args(argv)

    diff_text = Path(args.diff).read_text(encoding="utf-8")
    files = [
        ln.strip() for ln in Path(args.files).read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    value = "true" if is_windows_only(Path(args.root), diff_text, files) else "false"
    line = f"windows_only={value}"
    print(line)
    if args.output:
        with Path(args.output).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
