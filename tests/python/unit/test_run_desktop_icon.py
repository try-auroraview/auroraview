"""Regression tests for GH-528: ``run_desktop(icon=...)`` runtime window icon.

The README documents ``run_desktop(title=..., url=..., icon="...")`` as the way
to customize the *native window* icon. The PyO3 ``_core.run_desktop`` function
used to omit the ``icon`` parameter entirely, so the documented call raised
``TypeError: run_desktop() got an unexpected keyword argument 'icon'``.

These tests pin the API/documentation contract at the binding boundary. The
genuine native icon path (``WebViewConfig.icon`` -> ``load_window_icon`` ->
``with_window_icon``) is covered by the Rust tests in
``src/webview/desktop/icon.rs``; tests here guard against the kwarg being
dropped again at the PyO3 boundary.
"""

from __future__ import annotations

import pytest

_core = pytest.importorskip(
    "auroraview._core",
    reason="auroraview._core PyO3 extension not built; run `vx just build` first",
)


@pytest.mark.parametrize("runner_name", ["run_desktop", "run_standalone"])
def test_runner_accepts_icon_kwarg(runner_name):
    """Both the primary runner and its legacy alias must accept ``icon``."""
    import inspect

    runner = getattr(_core, runner_name)
    sig = inspect.signature(runner)
    assert "icon" in sig.parameters, f"{runner_name} is missing the `icon` parameter"
    # Omitted -> default AuroraView icon.
    assert sig.parameters["icon"].default is None


def test_run_desktop_icon_is_documented():
    """The ``icon`` parameter is documented as a runtime window icon."""
    doc = _core.run_desktop.__doc__ or ""
    assert "icon" in doc
    assert "window icon" in doc.lower()


def test_run_desktop_icon_kwarg_round_trip():
    """The ``icon`` kwarg reaches ``WebViewConfig.icon`` unchanged.

    ``_dump_run_desktop_icon`` is a ``test-helpers``-gated hook that mirrors the
    exact flatten point in ``run_desktop`` without launching the blocking event
    loop. Standard release wheels (built without ``test-helpers``) do not expose
    it, so skip cleanly there; ``test_runner_accepts_icon_kwarg`` above still
    guards the public signature in every build.
    """
    hook = getattr(_core, "_dump_run_desktop_icon", None)
    if hook is None:
        pytest.skip("_dump_run_desktop_icon missing — rebuild with the test-helpers feature")

    assert hook(None) is None
    assert hook("assets/my-icon.png") == "assets/my-icon.png"
