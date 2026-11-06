"""Authentication-page classification must match the complete hostname."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def measure():
    path = Path(__file__).resolve().parents[3] / "examples/blender_loading_probe/measure.py"
    spec = importlib.util.spec_from_file_location("loading_probe_measure", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url,title,expected",
    [
        ("https://passport.woa.com/login", "Sign in", True),
        ("https://PASSPORT.WOA.COM/login", "Sign in", True),
        ("https://passport.woa.com.example.org/", "Document", False),
        ("https://other-passport.woa.com/", "Document", False),
        ("https://example.org/passport.woa.com", "Document", False),
        ("https://example.org/", "OA登录", True),
        ("https://example.org/", "Document", False),
    ],
)
def test_auth_page_classification_rejects_hostname_substrings(measure, url, title, expected):
    assert measure.is_auth_page(url, title) is expected
