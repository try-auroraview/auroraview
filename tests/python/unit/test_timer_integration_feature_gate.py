"""Regression guard for the timer_integration test target's feature contract.

``tests/rust/timer_integration_tests.rs`` is an integration test (a separate
crate), so the ``auroraview`` library is compiled WITHOUT ``cfg(test)``. Those
tests call ``Timer::should_tick``, which in ``src/webview/timer.rs`` is gated
behind ``#[cfg(any(test, target_os = "windows", feature = "test-helpers"))]``.
On Linux, without ``--features test-helpers``, ``should_tick`` does not exist,
so a plain ``cargo test --no-run`` (what cargo-mutants builds as its unmutated
baseline) fails with E0599 -> 0 mutants / baseline_failed.

The fix is the standard Cargo idiom already used by ipc_roundtrip_integration
and window_utils_integration: declare ``required-features`` on the ``[[test]]``
target referencing the package's EXISTING ``test-helpers`` feature, so
no-feature builds skip it cleanly and feature-enabled builds compile it with
every original test case intact. These tests keep that contract from
regressing and assert no original case/assertion/threshold was weakened.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_CARGO_TOML = _ROOT / "Cargo.toml"
_TIMER_RS = _ROOT / "src/webview/timer.rs"
_TIMER_TEST = _ROOT / "tests/rust/timer_integration_tests.rs"


def _test_target_block(name: str) -> str:
    """Return the raw ``[[test]]`` block for *name* from Cargo.toml."""
    text = _CARGO_TOML.read_text(encoding="utf-8")
    # Split only at lines that start a new ``[[...]]`` table header. A
    # ``required-features = ["..."]`` value starts with ``[`` mid-line and must
    # not be mistaken for a header, otherwise the value gets truncated away.
    blocks = re.split(r"(?=^\[\[)", text, flags=re.MULTILINE)
    for block in blocks:
        if re.search(r'^name = "' + re.escape(name) + r'"', block, re.MULTILINE):
            return block
    raise AssertionError(f"[[test]] target {name!r} not found in Cargo.toml")


def test_timer_integration_declares_existing_test_helpers_feature():
    block = _test_target_block("timer_integration")
    assert 'required-features = ["test-helpers"]' in block, (
        'timer_integration must declare required-features = ["test-helpers"] '
        "so no-feature builds skip it instead of failing with E0599"
    )
    # The feature must be the package's real, pre-existing helper feature.
    features = _CARGO_TOML.read_text(encoding="utf-8")
    assert re.search(r"^test-helpers\s*=", features, re.MULTILINE), (
        "test-helpers must remain defined in [features]"
    )


def test_sibling_targets_keep_their_feature_contract():
    # Guard that the established required-features idiom was not disturbed.
    assert 'required-features = ["python-bindings"]' in _test_target_block(
        "ipc_roundtrip_integration"
    )
    assert 'required-features = ["python-bindings"]' in _test_target_block(
        "window_utils_integration"
    )


def test_should_tick_stays_gated_behind_test_helpers():
    # should_tick is a test helper; it must NOT become an unconditional
    # production API just to make the baseline compile.
    src = _TIMER_RS.read_text(encoding="utf-8")
    assert re.search(r'#\[cfg\(any\([^)]*feature = "test-helpers"[^)]*\)\)\]', src), (
        'should_tick\'s cfg gate referencing feature="test-helpers" must remain'
    )
    assert "pub fn should_tick" in src


def test_original_timer_cases_assertions_and_thresholds_preserved():
    body = _TIMER_TEST.read_text(encoding="utf-8")
    # Four #[rstest] timing cases, all #[ignore]-gated (timing-sensitive by
    # design) -- none may be deleted to dodge the compile failure.
    assert body.count("#[rstest]") >= 4, "original test cases must be preserved"
    assert len(re.findall(r"#\[ignore\s*=", body)) >= 4, (
        "original #[ignore] timing tests must be preserved"
    )
    # 10 should_tick() calls/assertions across those cases.
    assert body.count("should_tick()") >= 10, "original should_tick assertions must be preserved"
    # The multi-tick threshold (at least 4 successful ticks) is unchanged.
    assert "successful_ticks >= 4" in body, "original threshold must be preserved"
    assert "use _core::webview::timer::Timer;" in body
