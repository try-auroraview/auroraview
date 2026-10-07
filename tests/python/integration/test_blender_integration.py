"""Headless import and host checks; no visible WebView rendering is certified."""

import pytest


@pytest.fixture(scope="module")
def blender():
    """Ordinary Python suites may skip; the dedicated host runner forbids skips."""
    return pytest.importorskip("bpy", reason="Requires the actual Blender process")


@pytest.mark.blender
def test_blender_import(blender):
    """A missing Core or native dependency in a real host is a test failure."""
    from auroraview import WebView

    assert blender.app.version_string
    assert WebView is not None


@pytest.mark.blender
def test_blender_webview_creation(blender):
    """Construct and close the wrapper without showing a native window."""
    from auroraview import WebView

    view = WebView(title="Blender Test", width=800, height=600)
    try:
        assert view.title == "Blender Test"
    finally:
        view.close()


@pytest.mark.blender
def test_blender_operator_registration(blender):
    """Register a real temporary operator and always restore the host registry."""

    class AURORAVIEW_OT_ci_probe(blender.types.Operator):
        bl_idname = "auroraview.ci_probe"
        bl_label = "AuroraView CI host probe"

        def execute(self, context):
            return {"FINISHED"}

    blender.utils.register_class(AURORAVIEW_OT_ci_probe)
    try:
        assert blender.ops.auroraview.ci_probe() == {"FINISHED"}
    finally:
        blender.utils.unregister_class(AURORAVIEW_OT_ci_probe)


@pytest.mark.blender
def test_blender_dcc_environment(blender):
    """Do not turn a missing public dispatcher API into a passing skip."""
    from auroraview.utils.thread_dispatcher import get_current_dcc_name

    dcc_name = get_current_dcc_name()
    assert dcc_name is not None
    assert "blender" in dcc_name.lower()
