"""Regression guard for the mutation-testing workflow's Rust toolchain.

cargo-mutants builds its unmutated baseline with ``cargo test --no-run``, which
compiles the ``auroraview`` package *including dev-dependencies*. Those pull in
``auroraview-mcp`` -> ``dcc-mcp-protocols`` (git tag ``v0.15.0``), whose workspace
declares ``rust-version = "1.95"``.

The shipped library MSRV is 1.90 (see root Cargo.toml / README); that is valid for
production wheels because they don't build dev-deps. But the mutation job DOES,
so pinning it to 1.90.0 made the baseline fail with "rustc 1.90.0 is not supported
by the following package: dcc-mcp-protocols@0.15.0 requires rustc 1.95" ->
0 mutants / baseline_failed instead of a real mutation run.

These tests keep every ``dtolnay/rust-toolchain@`` pin in the workflow fixed and
at or above that dev-dep floor, and assert the three jobs stay consistent.
"""

from __future__ import annotations

import re
from pathlib import Path

# Minimum toolchain that can compile the locked dev-dependency graph. Bump this
# only together with the dcc-mcp-protocols git tag / its declared rust-version.
MIN_TOOLCHAIN = (1, 95, 0)

_WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/mutation-testing.yml"
_REF_RE = re.compile(r"dtolnay/rust-toolchain@([0-9]+\.[0-9]+\.[0-9]+)")


def _toolchain_refs():
    text = _WORKFLOW.read_text(encoding="utf-8")
    return [tuple(int(part) for part in v.split(".")) for v in _REF_RE.findall(text)]


def test_all_three_jobs_pin_a_fixed_toolchain():
    refs = _toolchain_refs()
    # Increment (PR), full (schedule) and single-crate (dispatch) jobs.
    assert len(refs) == 3, f"expected 3 toolchain pins, found {len(refs)}"
    # All refspecs are concrete X.Y.Z versions (no floating @stable/@nightly).
    assert all(len(v) == 3 for v in refs)


def test_toolchain_meets_dev_dependency_msrv_floor():
    refs = _toolchain_refs()
    assert refs, "no toolchain pins found"
    for ref in refs:
        assert ref >= MIN_TOOLCHAIN, (
            f"{'.'.join(map(str, ref))} is below the dev-dep MSRV floor "
            f"{'.'.join(map(str, MIN_TOOLCHAIN))} (dcc-mcp-protocols@0.15.0); "
            "cargo-mutants baseline would fail with 0 mutants / baseline_failed"
        )


def test_jobs_use_the_same_toolchain():
    refs = _toolchain_refs()
    assert refs, "no toolchain pins found"
    # Keep the three jobs coherent so they all build the same dependency graph.
    assert len(set(refs)) == 1, f"jobs disagree on toolchain: {refs}"
