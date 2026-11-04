"""Use the freshly built generic extension when a stale local cp311 binary exists."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "python" / "auroraview" / "_core.pyd"
spec = importlib.util.spec_from_file_location("auroraview._core", EXTENSION)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load freshly built extension: {EXTENSION}")
module = importlib.util.module_from_spec(spec)
sys.modules["auroraview._core"] = module
spec.loader.exec_module(module)

raise SystemExit(
    pytest.main(
        [
            *sys.argv[1:],
            "-q",
            "--tb=short",
            "-o",
            "addopts=",
        ]
    )
)
