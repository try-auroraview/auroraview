set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set shell := ["sh", "-c"]

# Explicit roots ensure the ordinary Python matrix cannot omit these regressions.
[working-directory: ".."]
test python="3.12":
    vx uv run --no-project --python {{python}} --with pytest --with pytest-timeout --with pytest-asyncio --with websockets python -m pytest tests/python/test_bridge_lifecycle_exit.py tests/python/integration/test_bridge.py -q -o addopts='' --timeout=20
