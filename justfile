# justfile for AuroraView development
# Run `vx just --list` to see all available commands
#
# Quick Start:
#   vx just rebuild-pylib         - Rebuild Rust core Python module (release mode)
#   vx just rebuild-pylib-verbose - Same as above with verbose output
#   vx just test                  - Run all tests
#   vx just format                - Format code
#   vx just lint                  - Run linting
#
# Note: This justfile uses vx for tool management.
#       Run `vx setup` to install all required tools.
#       Prefer `vx just <command>` to keep tool/runtime resolution reproducible.


# Set shell for Windows compatibility
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set shell := ["sh", "-c"]

windows_rust_target := "x86_64-pc-windows-msvc"

# Default recipe to display help
default:
    @vx just --list

# Check canonical repository links without building or installing dependencies.
check-repository-links:
    vx python scripts/check_repository_links.py

# Optional integration tests stay independent of GUI/native runtime acceptance.
test-dcc-mcp:
    vx uv run --extra dcc-mcp pytest tests/python/unit/test_dcc_mcp_adapter.py tests/python/unit/test_dcc_mcp_host.py tests/python/integration/test_dcc_mcp_registration.py tests/python/integration/test_dcc_mcp_coexistence.py tests/python/integration/test_dcc_mcp_skill_isolation.py tests/python/integration/test_dcc_mcp_tool_invocation.py -v

dcc-mcp-package-check:
    cd packages/auroraview-dcc-mcp; vx just check

# Prepare pinned GitHub release artifacts using SOURCE_RUN_ID and RELEASE_TAG.
dcc-mcp-release-prepare:
    vx uv run --no-project --python 3.11 scripts/ci/dcc_mcp_release.py

# Resume partial PyPI uploads only when existing public files match the receipt.
dcc-mcp-release-pypi-precheck:
    vx uv run --no-project --python 3.11 scripts/ci/dcc_mcp_release.py --check-pypi before

# Publication succeeds only after official PyPI serves both selected digests.
dcc-mcp-release-pypi-readback:
    vx uv run --no-project --python 3.11 scripts/ci/dcc_mcp_release.py --check-pypi after

# Check the release helper without publishing artifacts.
dcc-mcp-release-check:
    vx uvx ruff check --target-version py311 scripts/ci/dcc_mcp_release.py scripts/ci/test_dcc_mcp_release.py
    vx uvx ruff format --check --target-version py311 scripts/ci/dcc_mcp_release.py scripts/ci/test_dcc_mcp_release.py
    vx uv run --no-project --python 3.11 -m unittest discover -s scripts/ci -p test_dcc_mcp_release.py -v

dcc-mcp-release-format:
    vx uvx ruff format --target-version py311 scripts/ci/dcc_mcp_release.py scripts/ci/test_dcc_mcp_release.py

# Validate Gallery release boundaries and failure diagnostics without launching UI.
gallery-ci-check:
    vx uvx ruff check --target-version py311 scripts/ci/test_gallery_ci.py tests/test_gallery_cdp.py
    vx uvx ruff format --check --target-version py311 scripts/ci/test_gallery_ci.py tests/test_gallery_cdp.py
    vx uv run --no-project --python 3.11 --with pytest --with pyyaml -m unittest discover -s scripts/ci -p test_gallery_ci.py -v

test-parent-ipc:
    vx cargo test -p auroraview-core --test parent_ipc_tests

test-webview-factory:
    vx uv run python -m pytest tests/python/integration/test_webview.py -k test_create_with_auto_show_true -v


# ============================================================================
# Submodule Migration Tasks
# ============================================================================

# Set up independent repositories (Step 1)
migrate-setup-repos:
    @echo "Setting up independent repositories..."
    @pwsh -File scripts/setup_independent_repos.ps1

# Migrate to submodules (Step 2)
migrate-to-submodules:
    @echo "Migrating to submodules..."
    @pwsh -File scripts/migrate_to_submodules.ps1

# Update workspace configuration for submodules (Step 3)
migrate-update-workspace:
    @echo "Please manually update:"
    @echo "1. Cargo.toml - add submodules to workspace.members"
    @echo "2. crates/auroraview-cli/Cargo.toml - update auroraview-pack path"
    @echo ""
    @echo "See temp_migration/QUICK_START.md for details"

# Verify submodule setup
migrate-verify:
    @echo "Verifying submodule setup..."
    @git submodule status
    @echo ""
    @echo "Building with submodules..."
    cargo build
    @echo ""
    @echo "Running tests..."
    cargo test
    @echo ""
    @echo "Verifying CLI..."
    cargo run -p auroraview-cli -- --version

# Complete migration workflow
migrate-all: migrate-setup-repos migrate-to-submodules
    @echo ""
    @echo "========================================"
    @echo "Migration Phase 1 & 2 Complete!"
    @echo "========================================"
    @echo ""
    @echo "Next steps:"
    @echo "1. Run: just migrate-update-workspace"
    @echo "2. Manually update Cargo.toml files (see output above)"
    @echo "3. Run: just migrate-verify"
    @echo "4. Commit changes: git add . && git commit -m 'chore: migrate to submodules'"

# Initialize submodules for fresh clone
submodule-init:
    @echo "Initializing submodules..."
    git submodule init
    git submodule update --recursive

# Update submodules to latest
submodule-update:
    @echo "Updating submodules to latest..."
    git submodule update --remote

# Update specific submodule
submodule-update-protect:
    @echo "Updating auroraview-protect submodule..."
    git submodule update --remote submodules/auroraview-protect

# Update specific submodule
submodule-update-pack:
    @echo "Updating auroraview-pack submodule..."
    git submodule update --remote submodules/auroraview-pack

# Install dependencies
install:
    @echo "Installing dependencies..."
    vx uv sync --group dev

# Build the extension module
[unix]
build: assets-build sdk-build-assets
    @echo "Building extension module..."
    vx uv run maturin develop --features "ext-module,python-bindings,abi3-py38,win-webview2"

[windows]
build: assets-build sdk-build-assets
    @echo "Building extension module with MSVC..."
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; vx rustc -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx uv run maturin develop --features "ext-module,python-bindings,abi3-py38,win-webview2"

# Build with release optimizations
[unix]
build-release: assets-build sdk-build-assets
    @echo "Building release version..."
    vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"

[windows]
build-release: assets-build sdk-build-assets
    @echo "Building release version with MSVC..."
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; vx rustc -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"

# Build Python library (PyO3 bindings)
[unix]
rebuild-pylib: assets-build sdk-build-assets
    @echo "Building Python library with maturin..."
    vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"
    @echo "[OK] Python library rebuilt and installed successfully!"

[windows]
rebuild-pylib: assets-build sdk-build-assets
    @echo "Building Python library with maturin (MSVC)..."
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; vx rustc -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"
    @echo "[OK] Python library rebuilt and installed successfully!"

# Build Python library with verbose output
[unix]
rebuild-pylib-verbose: assets-build sdk-build-assets
    @echo "Building Python library with maturin (verbose)..."
    vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2" --verbose
    @echo "[OK] Python library rebuilt and installed successfully!"

[windows]
rebuild-pylib-verbose: assets-build sdk-build-assets
    @echo "Building Python library with maturin (verbose, MSVC)..."
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; vx rustc -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2" --verbose
    @echo "[OK] Python library rebuilt and installed successfully!"

# Build CLI binary
build-cli:
    @echo "Building CLI binary..."
    vx cargo build -p auroraview-cli --release
    @echo "[OK] CLI built: target/release/auroraview.exe"

# Build all workspace crates (including SDK assets)
[unix]
build-all: assets-build sdk-build-all
    @echo "Building all workspace crates..."
    vx cargo build -p auroraview-core
    vx cargo build -p auroraview-pack
    vx cargo build -p auroraview-cli --release
    vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"
    @echo "[OK] All crates built successfully!"

[windows]
build-all: assets-build sdk-build-all
    @echo "Building all workspace crates with MSVC..."
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; vx rustc -vV
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo build -p auroraview-core
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo build -p auroraview-pack
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx cargo build -p auroraview-cli --release
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; vx uv run maturin develop --release --features "ext-module,python-bindings,abi3-py38,win-webview2"
    @echo "[OK] All crates built successfully!"

# Run CI grep guards (RFC 0016 §5 / RFC 0017 §5).
#
# These scripts enforce two invariants that cannot be expressed at the
# Rust type level:
#
#   - RFC 0016: Browser-mode `attach_drag_drop_handler` second arg must
#     be the literal `false`; `BrowserConfig` / `TabManagerConfig` must
#     not expose a `capture_file_drop` field.
#   - RFC 0017: Python passthrough must keep `capture_file_drop` as
#     `Optional[bool]` (no `setdefault` / `or False` / `dict.get(..., False)`)
#     all the way to the Rust PyO3 boundary.
ci-grep:
    @echo "[ci-grep] RFC 0017 capture_file_drop tri-state guard..."
    vx python scripts/ci/check_capture_file_drop_defaults.py
    @echo "[ci-grep] RFC 0016 Browser-mode capture_file_drop guard..."
    vx python scripts/ci/check_browser_no_drag_drop_capture.py
    @echo "[ci-grep] host-adapter contract Rust/Python capability parity guard..."
    vx python scripts/ci/check_contract_capability_parity.py

# Keep Blender's test dependencies separate from the runner's Python environment.
prepare-blender-test-site wheel site python_version:
    vx uv pip install --target "{{site}}" --python-version "{{python_version}}" --only-binary :all: "{{wheel}}" pytest pytest-timeout pytest-asyncio

# Pytest must run inside bpy; a sys.executable subprocess is an ordinary Python process.
# The strict runner rejects missing imports, skipped cases and an empty selection.
test-blender-host blender site:
    "{{blender}}" --background --factory-startup --python-exit-code 1 --python scripts/ci/run_blender_tests.py -- --test-site "{{site}}" -- tests/python/integration/test_blender_integration.py -v --tb=short --timeout=60

# Run all tests
[unix]
test:
    @echo "Running CI grep guards (RFC 0016 §5 / RFC 0017 §5)..."
    vx just ci-grep
    @echo "Running workspace crate tests..."
    vx cargo test -p auroraview-contract
    vx cargo test -p auroraview-core
    vx cargo test -p auroraview-pack
    vx cargo test -p auroraview-cli
    @echo "Running Rust integration tests (with rstest)..."
    # Note: names are aligned with Cargo.toml [[test]] targets.
    vx cargo test --test mdns_integration --features "test-helpers"
    vx cargo test --test protocol_handlers_integration --features "test-helpers"
    vx cargo test --test protocol_integration --features "test-helpers"
    vx cargo test --test timer_integration --features "test-helpers"
    vx cargo test --test ipc_message_queue_integration --features "test-helpers"
    vx cargo test --test http_discovery_integration --features "test-helpers"
    vx cargo test --test standalone_integration --features "test-helpers"
    vx cargo test --test config_integration --features "test-helpers"
    vx cargo test --test ipc_json_integration --features "test-helpers"
    vx cargo test --test file_protocol_integration --features "test-helpers"
    vx cargo test --test port_allocator_integration --features "test-helpers"

    @echo "Running Rust doc tests..."
    vx cargo test --doc
    @echo "Running Python tests..."
    vx uv run pytest -q -rA tests/python/unit tests/python/integration


[windows]
test:
    @echo "Running CI grep guards (RFC 0016 §5 / RFC 0017 §5)..."
    vx just ci-grep
    @echo "Running workspace crate tests..."
    vx cargo test -p auroraview-contract
    vx cargo test -p auroraview-core
    vx cargo test -p auroraview-pack
    vx cargo test -p auroraview-cli
    @echo ""
    @echo "Note: Rust integration tests are skipped on Windows due to STATUS_DLL_NOT_FOUND (abi3/PyO3 linking) on some machines."
    @echo "These tests run successfully in CI on Linux."
    @echo "Running Rust doc tests..."
    vx cargo test --doc
    @echo "Running Python tests..."
    vx uv run pytest -q -rA tests/python/unit tests/python/integration



# Run tests with coverage
test-cov:
    @echo "Running tests with coverage..."
    vx uv run pytest -v --cov=auroraview --cov-report=html --cov-report=term-missing tests/python/unit tests/python/integration


# Run only fast tests (exclude slow tests)
test-fast:
    @echo "Running fast tests..."
    vx uv run pytest tests/python/ -v -m "not slow"

# Run security audit (check for vulnerabilities in dependencies)
audit:
    @echo "Running cargo audit..."
    cargo audit --ignore RUSTSEC-2024-0413 --ignore RUSTSEC-2024-0416 --ignore RUSTSEC-2026-0118 --ignore RUSTSEC-2026-0119 --ignore RUSTSEC-2026-0002 || true
    @echo ""
    @echo "Note: unmaintained warnings (RUSTSEC-2024-0413/0416) are ignored."
    @echo "      These are from GTK3 bindings used by wry (standalone mode)."

# Ensure cargo-nextest is available for fast Rust integration runs
[unix]
nextest-install:
    @if vx cargo nextest --version >/dev/null 2>&1; then \
        echo "cargo-nextest already available"; \
    else \
        echo "Installing cargo-nextest..."; \
        vx cargo install cargo-nextest --locked; \
    fi

[windows]
nextest-install:
    @if (vx cargo nextest --version *> $null) { Write-Host "cargo-nextest already available" } else { Write-Host "Installing cargo-nextest..."; vx cargo install cargo-nextest --locked }

# Ensure cargo-llvm-cov is available for local Rust coverage runs
[unix]
llvm-cov-install:
    @echo "Ensuring llvm-tools-preview Rust component..."
    vx rustup component add llvm-tools-preview
    @if vx cargo llvm-cov --version >/dev/null 2>&1; then \
        echo "cargo-llvm-cov already available"; \
    else \
        echo "Installing cargo-llvm-cov..."; \
        vx cargo install cargo-llvm-cov --locked; \
    fi

[windows]
llvm-cov-install:
    @if (vx cargo llvm-cov --version *> $null) { Write-Host "cargo-llvm-cov already available" } else { Write-Host "Installing cargo-llvm-cov..."; vx cargo install cargo-llvm-cov --locked }

# Run Rust integration tests with cargo-nextest
[unix]
test-rust-fast: nextest-install
    @echo "Running Rust integration tests with cargo-nextest..."
    vx cargo nextest run --config-file .config/nextest.toml --features "test-helpers" --tests
    @echo "[OK] Rust integration tests passed"

[windows]
test-rust-fast:
    @echo "Skipping cargo-nextest integration path on Windows due to abi3/PyO3 DLL constraints."
    @echo "Use Linux CI for full Rust integration coverage."

# Test Python unit tests without slow markers
test-python-unit-fast:
    @echo "Running fast Python unit tests..."
    vx uv run pytest tests/python/unit -q --tb=short -m "not slow and not qt" \
        --ignore=tests/python/unit/integration/qt \
        --ignore=tests/python/unit/test_qt_signals.py



# Test with Python 3.7
test-py37:
    @echo "Testing with Python 3.7..."
    vx uv venv --python 3.7 .venv-py37
    vx uv pip install -e . pytest pytest-cov --python .venv-py37\Scripts\python.exe
    .venv-py37\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with Python 3.8
test-py38:
    @echo "Testing with Python 3.8..."
    vx uv venv --python 3.8 .venv-py38
    vx uv pip install -e . pytest pytest-cov --python .venv-py38\Scripts\python.exe
    .venv-py38\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with Python 3.9
test-py39:
    @echo "Testing with Python 3.9..."
    vx uv venv --python 3.9 .venv-py39
    vx uv pip install -e . pytest pytest-cov --python .venv-py39\Scripts\python.exe
    .venv-py39\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with Python 3.10
test-py310:
    @echo "Testing with Python 3.10..."
    vx uv venv --python 3.10 .venv-py310
    vx uv pip install -e . pytest pytest-cov --python .venv-py310\Scripts\python.exe
    .venv-py310\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with Python 3.11
test-py311:
    @echo "Testing with Python 3.11..."
    vx uv venv --python 3.11 .venv-py311
    vx uv pip install -e . pytest pytest-cov --python .venv-py311\Scripts\python.exe
    .venv-py311\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with Python 3.12
test-py312:
    @echo "Testing with Python 3.12..."
    vx uv venv --python 3.12 .venv-py312
    vx uv pip install -e . pytest pytest-cov --python .venv-py312\Scripts\python.exe
    .venv-py312\Scripts\python.exe -m pytest tests/ -v -o addopts=""

# Test with all supported Python versions
test-all-python:
    @echo "Testing with all supported Python versions..."
    vx just test-py37
    vx just test-py38
    vx just test-py39
    vx just test-py310
    vx just test-py311
    vx just test-py312
    @echo "[OK] All Python versions tested successfully!"

# nox wrappers for multi-Python testing
nox:
    @echo "Running nox session: pytest (multi-Python)"
    vx uvx nox -s pytest

nox-qt:
    @echo "Running nox session: pytest-qt (multi-Python with Qt)"
    vx uvx nox -s pytest-qt


nox-all:
    @echo "Running nox session: pytest-all (full suite)"
    vx uvx nox -s pytest-all


# ═══════════════════════════════════════════════════════════════════════════════
# Package-Level Test Commands (for isolated CI)
# ═══════════════════════════════════════════════════════════════════════════════

# Test auroraview-signals crate (standalone, no deps)
test-signals:
    @echo "Testing auroraview-signals..."
    vx cargo test -p auroraview-signals
    vx cargo clippy -p auroraview-signals -- -D warnings

# Test auroraview-protect crate (standalone, no deps)
test-protect:
    @echo "Testing auroraview-protect..."
    vx cargo test -p auroraview-protect
    vx cargo clippy -p auroraview-protect -- -D warnings

# Test auroraview-plugin-core crate (standalone, no deps)
test-plugin-core:
    @echo "Testing auroraview-plugin-core..."
    vx cargo test -p auroraview-plugin-core
    vx cargo clippy -p auroraview-plugin-core -- -D warnings

# Test auroraview-plugin-fs crate (depends on plugin-core)
test-plugin-fs:
    @echo "Testing auroraview-plugin-fs..."
    vx cargo test -p auroraview-plugin-fs
    vx cargo clippy -p auroraview-plugin-fs -- -D warnings

# Test auroraview-extensions crate (standalone, no deps)
test-extensions:
    @echo "Testing auroraview-extensions..."
    vx cargo test -p auroraview-extensions
    vx cargo clippy -p auroraview-extensions -- -D warnings

# Test auroraview-telemetry crate (standalone)
test-telemetry:
    @echo "Testing auroraview-telemetry..."
    vx cargo test -p auroraview-telemetry
    vx cargo clippy -p auroraview-telemetry -- -D warnings

# Test auroraview-plugins crate (depends on plugin-core, plugin-fs, extensions)
test-plugins:
    @echo "Testing auroraview-plugins..."
    vx cargo test -p auroraview-plugins
    vx cargo clippy -p auroraview-plugins -- -D warnings

# Test auroraview-core crate (depends on signals, plugins)
test-core:
    @echo "Testing auroraview-core..."
    vx cargo test -p auroraview-core
    vx cargo clippy -p auroraview-core -- -D warnings

# Test auroraview-pack crate (depends on protect)
test-pack:
    @echo "Testing auroraview-pack..."
    vx cargo test -p auroraview-pack
    vx cargo clippy -p auroraview-pack -- -D warnings

# Test auroraview-cli crate (depends on core, pack)
test-cli:
    @echo "Testing auroraview-cli..."
    vx cargo test -p auroraview-cli
    vx cargo clippy -p auroraview-cli -- -D warnings

# Test all standalone crates (no internal dependencies)
test-standalone:
    @echo "Testing standalone crates..."
    vx just test-signals
    vx just test-protect
    vx just test-plugin-core
    vx just test-extensions


# Test Python package only (no Rust rebuild)
test-python:
    @echo "Running Python tests..."
    vx uv run pytest tests/python/unit tests/python/integration -v --tb=short

# Test Python unit tests only
test-python-unit:
    @echo "Running Python unit tests..."
    vx uv run pytest tests/python/unit -v --tb=short

# Test Python integration tests only
test-python-integration:
    @echo "Running Python integration tests..."
    vx uv run pytest tests/python/integration -v --tb=short \
        --ignore=tests/python/integration/test_gallery_e2e.py \
        --ignore=tests/python/integration/test_gallery_real_e2e.py

# ═══════════════════════════════════════════════════════════════════════════════
# Legacy Test Commands (for backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

# Run only Rust unit tests
test-unit:
    @echo "Running Rust unit tests..."
    vx cargo test --lib
    vx cargo test -p auroraview-contract
    vx cargo test -p auroraview-core
    vx cargo test -p auroraview-pack
    vx cargo test -p auroraview-cli
    @echo "Running Python unit tests..."
    vx uv run pytest tests/python/unit -v


# Run only Rust integration tests
test-integration:
    @echo "Running Rust integration tests (cargo-nextest)..."
    vx just test-rust-fast
    @echo "Running Python integration tests..."
    vx uv run pytest tests/python/integration -v


# Watch mode for continuous testing
test-watch:
    @echo "Running tests in watch mode..."
    vx cargo watch -x test

# Run specific test file
test-file FILE:
    @echo "Running tests in {{FILE}}..."
    vx uv run pytest {{FILE}} -v


# Run tests with specific marker
test-marker MARKER:
    @echo "Running tests with marker {{MARKER}}..."
    vx uv run pytest tests/ -v -m {{MARKER}}


# Format code
format:
    @echo "Formatting Rust code..."
    vx cargo fmt --all
    @echo "Formatting Python code..."
    vx uv run ruff format python/ tests/ examples/

# Refresh workspace-hack dependencies for faster incremental Rust builds
hakari-sync:
    @echo "Regenerating cargo-hakari workspace-hack crate..."
    vx cargo hakari generate
    vx cargo hakari manage-deps -y

# Verify workspace-hack metadata is up-to-date (CI friendly)
hakari-check:
    @echo "Checking cargo-hakari state..."
    vx cargo hakari generate --diff
    vx cargo hakari manage-deps --dry-run

# Verify Rust unsafe usage stays inside reviewed FFI boundaries
unsafe-audit:
    @echo "Auditing Rust unsafe usage..."
    vx python scripts/audit_unsafe.py

# Run linting
lint: unsafe-audit
    @echo "Linting Rust code..."
    vx cargo clippy --all-targets --all-features -- -D warnings
    @echo "Linting Python code..."
    vx uv run ruff check python/ tests/ examples/

# Verify Python type exports with pyright
verifytypes:
    @echo "Verifying Python type exports..."
    vx uv run python scripts/python_verifytypes.py --warn-only


# Fix linting issues automatically
fix:
    @echo "Fixing linting issues..."
    vx cargo clippy --fix --allow-dirty --allow-staged
    vx uv run ruff check --fix python/ tests/ examples/

# Run all checks (format, lint, test)
check: format lint test
    @echo "All checks passed!"

# CI-specific commands
ci-install:
    @echo "Installing CI dependencies (including Qt)..."
    vx uv sync --group dev --group test
    vx uv pip install qtpy PySide6 pytest-qt

ci-assets-build: assets-build
    @echo "[OK] CI frontend assets prepared!"

ci-sdk-assets: sdk-build-assets
    @echo "[OK] CI SDK assets prepared!"

# CI build command - consistent across all platforms
# Uses ext-module for proper Python extension module compilation
[unix]
ci-build: ci-assets-build ci-sdk-assets
    @echo "Building extension for CI (Unix)..."
    vx uv pip install maturin
    py_minor=$$(vx uv run python -c "import sys; print(sys.version_info[1])"); \
    if [ "$$py_minor" -ge 8 ]; then \
        features="ext-module,python-bindings,abi3-py38"; \
    else \
        features="ext-module,python-bindings"; \
    fi; \
    echo "Using maturin features: $$features"; \
    vx uv run maturin develop --features "$$features"

[windows]
ci-build: ci-assets-build ci-sdk-assets
    @echo "Building extension for CI (Windows)..."
    vx uv pip install maturin
    $pyMinor = [int](vx uv run python -c "import sys; print(sys.version_info[1])")
    if ($pyMinor -ge 8) { $features = "ext-module,python-bindings,abi3-py38,win-webview2" } else { $features = "ext-module,python-bindings,win-webview2" }
    $env:CARGO_BUILD_TARGET = "{{windows_rust_target}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; Write-Host "Using maturin features: $features"; vx uv run maturin develop --features $features

[unix]
ci-docs-rust: ci-assets-build
    @echo "Running Rust doc tests and documentation build..."
    vx cargo test --doc
    RUSTDOCFLAGS="-D warnings" vx cargo doc --no-deps --document-private-items
    @echo "[OK] Rust documentation checks completed"

[windows]
ci-docs-rust: ci-assets-build
    @echo "Running Rust doc tests and documentation build..."
    vx cargo test --doc
    $env:RUSTDOCFLAGS = "-D warnings"; vx cargo doc --no-deps --document-private-items
    @echo "[OK] Rust documentation checks completed"

[unix]
ci-cli-build TARGET:
    @echo "Building CLI for target {{TARGET}}..."
    vx rustup target add {{TARGET}}
    vx just ci-assets-build
    vx cargo build -p auroraview-cli --release --target {{TARGET}}
    @echo "[OK] CLI built: target/{{TARGET}}/release/"

[windows]
ci-cli-build TARGET:
    @echo "Building CLI for target {{TARGET}}..."
    rustup target add "{{TARGET}}"
    vx just ci-assets-build
    $env:CARGO_BUILD_TARGET = "{{TARGET}}"; Write-Host "Using Rust target: $env:CARGO_BUILD_TARGET"; cargo build -p auroraview-cli --release --target "{{TARGET}}"
    @echo "[OK] CLI built: target/{{TARGET}}/release/"

[unix]
ci-cli-smoke TARGET BIN:
    @echo "Running CLI smoke tests for {{BIN}}..."
    ./target/{{TARGET}}/release/{{BIN}} --help
    ./target/{{TARGET}}/release/{{BIN}} --version
    @echo "[OK] CLI smoke tests passed"

[windows]
ci-cli-smoke TARGET BIN:
    @echo "Running CLI smoke tests for {{BIN}}..."
    & "target/{{TARGET}}/release/{{BIN}}" --help
    & "target/{{TARGET}}/release/{{BIN}}" --version
    @echo "[OK] CLI smoke tests passed"


[unix]
ci-test-rust: nextest-install
    @echo "Running Rust integration tests with cargo-nextest..."
    vx cargo nextest run --config-file .config/nextest.toml --profile ci --features "test-helpers" --tests
    @echo "Running Rust doc tests..."
    @echo "Note: lib tests are skipped due to abi3 linking issues with PyO3"
    @echo "      Python tests provide additional coverage for Python bindings"
    vx cargo test --doc


[windows]
ci-test-rust:
    @echo "Running Rust doc tests..."
    @echo "Note: cargo-nextest integration is skipped on Windows due to STATUS_DLL_NOT_FOUND (abi3/PyO3 linking) on some machines."
    @echo "      Linux CI runs the Rust integration suite via cargo-nextest."
    vx cargo test --doc


[unix]
ci-rust-coverage-lcov: llvm-cov-install nextest-install
    @echo "Running Rust integration coverage with cargo-llvm-cov + cargo-nextest..."
    vx cargo llvm-cov nextest --no-report --features "test-helpers" --config-file .config/nextest.toml --profile ci --tests
    vx cargo llvm-cov report --lcov --output-path rust-coverage.lcov
    @echo "[OK] Rust coverage report: rust-coverage.lcov"

[windows]
ci-rust-coverage-lcov:
    @echo "Rust lcov coverage is only generated on Linux CI."
    @echo "Use the Linux CI rust-tests job for full Rust integration coverage."

ci-test-python:
    @echo "Running Python unit tests with coverage..."
    vx uv run pytest tests/ -v --tb=short -m "not slow" \
        --cov=auroraview \
        --cov-report=term-missing \
        --cov-report=html \
        --cov-report=xml \
        --cov-fail-under=0 \
        --timeout=60

ci-test-basic:
    @echo "Running basic import tests..."
    vx uv run python -c "import auroraview; print('AuroraView imported successfully')"

ci-lint:
    @echo "Running CI linting..."
    vx just unsafe-audit
    vx cargo fmt --all -- --check
    vx cargo clippy --all-targets --all-features -- -D warnings
    vx uvx ruff check python/ tests/
    vx uvx ruff format --check python/ tests/

# Coverage commands
coverage-python:
    @echo "Running Python tests with coverage..."
    vx uv run pytest -v --cov=auroraview --cov-report=html --cov-report=term-missing --cov-report=xml tests/python/unit tests/python/integration
# Shortcut alias for Python coverage
pycov:
    @echo "[Alias] Running Python coverage via coverage-python..."
    @vx just coverage-python



coverage-rust:
	@echo "Running Rust tests with coverage (preferring cargo-llvm-cov) in headless mode..."
	if (Get-Command py -ErrorAction SilentlyContinue) { $pyBase = py -c "import sys; print(sys.base_prefix)" } else { $pyBase = python -c "import sys; print(sys.base_prefix)" }; $env:Path = "$pyBase;$pyBase\DLLs;$pyBase\bin;$env:Path"; if (Get-Command cargo-llvm-cov -ErrorAction SilentlyContinue) { $ignore = "(src[/\\]webview[/\\](aurora_view\\.rs|embedded\\.rs|standalone\\.rs|protocol\\.rs|timer_bindings\\.rs|webview_inner\\.rs|backend[/\\].*|platform[/\\].*)|src[/\\]service_discovery[/\\]mdns_service\\.rs)"; if ($env:CI -eq "true") { vx rustup component add llvm-tools-preview; vx cargo llvm-cov --workspace --html --tests --no-default-features --features "python-bindings threaded-ipc test-helpers" --ignore-filename-regex $ignore --fail-under-lines 50 } else { vx cargo llvm-cov --workspace --html --tests --no-default-features --features "python-bindings threaded-ipc test-helpers" --ignore-filename-regex $ignore; $json = vx cargo llvm-cov --summary-only --json --workspace --tests --no-default-features --features "python-bindings threaded-ipc test-helpers" --ignore-filename-regex $ignore | Out-String | ConvertFrom-Json; $covered = [double]$json.data[0].totals.lines.covered; $count = [double]$json.data[0].totals.lines.count; if ($count -gt 0) { $lines = [math]::Round((100.0 * $covered / $count), 2) } else { $lines = 0 }; if ($lines -ge 50) { echo ("[OK] Rust coverage lines: {0}% (>=50) report: target/llvm-cov/html/index.html" -f $lines) } else { echo ("[WARN] Rust coverage lines: {0}% (<50)" -f $lines) } } } elseif (Get-Command cargo-tarpaulin -ErrorAction SilentlyContinue) { vx cargo tarpaulin --no-default-features --features "python-bindings threaded-ipc test-helpers" --out Html --out Xml --output-dir target/tarpaulin; if ($LASTEXITCODE -eq 0) { echo "[OK] Rust coverage report: target/tarpaulin/tarpaulin-report.html" } else { echo "[WARN] cargo-tarpaulin exited with code $LASTEXITCODE" } } else { echo "[INFO] No Rust coverage tool found."; echo "      Install recommended: cargo install cargo-llvm-cov"; echo "      Also run: rustup component add llvm-tools-preview" }

# Run coverage for individual crates
coverage-crate CRATE:
    @echo "Running coverage for crate: {{CRATE}}..."
    vx cargo llvm-cov --package {{CRATE}} --html --tests --output-dir target/llvm-cov/{{CRATE}}
    @echo "[OK] Coverage report: target/llvm-cov/{{CRATE}}/html/index.html"

# Run coverage for auroraview-core crate
coverage-core:
    @echo "Running coverage for auroraview-core..."
    vx cargo llvm-cov --package auroraview-core --html --tests --output-dir target/llvm-cov/auroraview-core
    @echo "[OK] Coverage report: target/llvm-cov/auroraview-core/html/index.html"

# Run coverage for auroraview-pack crate
coverage-pack:
    @echo "Running coverage for auroraview-pack..."
    vx cargo llvm-cov --package auroraview-pack --html --tests --output-dir target/llvm-cov/auroraview-pack
    @echo "[OK] Coverage report: target/llvm-cov/auroraview-pack/html/index.html"

# Run coverage for auroraview-cli crate
coverage-cli:
    @echo "Running coverage for auroraview-cli..."
    vx cargo llvm-cov --package auroraview-cli --html --tests --output-dir target/llvm-cov/auroraview-cli
    @echo "[OK] Coverage report: target/llvm-cov/auroraview-cli/html/index.html"

# Run coverage for all crates with lcov output (for CI)
[unix]
coverage-rust-lcov: ci-rust-coverage-lcov
    @echo "[OK] Reused CI-aligned Rust coverage flow"

[windows]
coverage-rust-lcov:
    @echo "Rust lcov coverage is only generated on Linux CI."

coverage-all: coverage-rust coverage-python
    @echo "All coverage reports generated!"

# Run benchmarks
bench:
    @echo "Running benchmarks..."
    vx cargo bench --bench ipc_bench

# Run benchmarks and save baseline
bench-save BASELINE="main":
    @echo "Running benchmarks and saving baseline: {{BASELINE}}..."
    vx cargo bench --bench ipc_bench -- --save-baseline {{BASELINE}}

# Compare benchmarks against baseline
bench-compare BASELINE="main":
    @echo "Comparing benchmarks against baseline: {{BASELINE}}..."
    vx cargo bench --bench ipc_bench -- --baseline {{BASELINE}}

# Clean build artifacts
clean:
    @echo "Cleaning build artifacts..."
    vx cargo clean
    rm -rf dist/ build/ htmlcov/
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    find . -type f -name "*.so" -delete
    find . -type f -name "*.pyd" -delete

# Setup development environment
dev: install build
    @echo "Development environment ready!"
    @echo "Try: just test"

# Build release wheels
release:
    @echo "Building release wheels..."
    vx uv run maturin build --release --features "ext-module,python-bindings,win-webview2"
    @echo "Wheels built in target/wheels/"

# Launch the AuroraView CLI (`python -m auroraview.__main__`).
# Moved here from `vx.toml [scripts]`, where the command took no arguments.
# See docs/guide/cli.md for the flags, including `--url`.
auroraview *ARGS:
    vx uv run python -m auroraview.__main__ {{ARGS}}

# Run examples
example EXAMPLE:
    @echo "Running example: {{EXAMPLE}}"
    vx uv run python examples/{{EXAMPLE}}.py

# Show project info
info:
    @echo "Project Information:"
    @echo "  Rust version: $(vx rustc --version)"
    @echo "  Python version: $(vx uv run python --version)"
    @echo "  UV version: $(vx uv --version)"
    @echo "  Node version: $(vx node --version)"

# Documentation
docs:
    @echo "Building documentation..."
    vx cargo doc --no-deps --document-private-items --open

# Comprehensive checks
check-all: format lint test coverage-all
    @echo "All checks completed!"

# ============================================================================
# Harness workflows (Agent-friendly, reproducible entrypoints)
# ============================================================================

# Show deterministic tool/runtime info used by harness tasks
harness-info:
    @echo "Harness runtime info:"
    @echo "  vx: $(vx --version)"
    @echo "  just: $(vx just --version)"
    @echo "  rust: $(vx rustc --version)"
    @echo "  python: $(vx uv run python --version)"
    @echo "  node: $(vx node --version)"

# Fast feedback loop for local or agent iterative execution
harness-quick:
    @echo "Running harness quick checks..."
    vx just ci-lint
    vx just ci-test-basic
    @echo "[OK] harness-quick completed"

# Diff-aware harness plan for iterative verification
harness-changed BASE="origin/main":
    @echo "Running diff-aware harness plan against {{BASE}}..."
    vx uv run python scripts/harness_changed.py --base {{BASE}}

# Full validation loop aligned with CI quality gates
harness-verify:
    @echo "Running harness verify checks..."
    vx just ci-lint
    vx just ci-test-rust
    vx just ci-test-python
    @echo "[OK] harness-verify completed"

# Deterministic gallery UI regression loop (pack + CDP + Playwright)
harness-gallery-e2e:
    @echo "Running harness gallery e2e..."
    vx just gallery-e2e-packed-playwright
    @echo "[OK] harness-gallery-e2e completed"

# Collect and print structured JSON summary from test artifacts
harness-summary:
    @echo "Collecting test result summary..."
    vx uv run python scripts/harness_summary.py
    @echo "[OK] harness-summary completed"

# Write structured JSON summary to a file
harness-summary-file OUTPUT="test-summary.json":
    @echo "Writing test result summary to {{OUTPUT}}..."
    vx uv run python scripts/harness_summary.py --output {{OUTPUT}}

# Run Python tests with JSON report output (for agent consumption)
test-python-json:
    @echo "Running Python tests with JSON report..."
    vx uv run pytest tests/python/unit -q --tb=short -m "not slow and not qt" \
        --json-report --json-report-file=test-report.json \
        --ignore=tests/python/unit/integration/qt \
        --ignore=tests/python/unit/test_qt_signals.py
    @echo "[OK] JSON report: test-report.json"

# Run Rust tests with agent profile (JSON + JUnit, retries, full output)
[unix]
test-rust-agent: nextest-install
    @echo "Running Rust tests with agent profile..."
    vx cargo nextest run --config-file .config/nextest.toml --profile agent --features "test-helpers" --tests
    @echo "[OK] Agent JUnit report: target/nextest/ci/agent-junit.xml"

[windows]
test-rust-agent:
    @echo "Skipping cargo-nextest agent path on Windows due to abi3/PyO3 DLL constraints."

# Run full agent test loop: Rust + Python with structured output + summary
[unix]
harness-agent: test-rust-agent test-python-json harness-summary
    @echo "[OK] harness-agent completed"

[windows]
harness-agent: test-python-json harness-summary
    @echo "[OK] harness-agent completed (Rust nextest skipped on Windows)"

# CI Python tests with JSON report + GitHub Actions annotations
ci-test-python-json:
    @echo "Running Python tests with JSON report + GH annotations..."
    vx uv run pytest tests/python/unit tests/python/integration -v --tb=short \
        -m "not slow" \
        --json-report --json-report-file=test-report.json \
        --cov=auroraview \
        --cov-report=term-missing \
        --cov-report=xml \
        --cov-fail-under=0 \
        --timeout=60
    @echo "[OK] CI Python JSON tests completed"

# ============================================================================
# Advanced Testing Commands (mutation, parallelism, partitioning)
# ============================================================================

# Run Rust integration tests with nextest fast profile (no retries, short timeout)
[unix]
test-rust-turbo: nextest-install
    @echo "Running Rust tests with fast profile (turbo mode)..."
    vx cargo nextest run --config-file .config/nextest.toml --profile fast --features "test-helpers" --tests
    @echo "[OK] Rust turbo tests passed"

[windows]
test-rust-turbo:
    @echo "Skipping cargo-nextest turbo path on Windows due to abi3/PyO3 DLL constraints."

# Run Rust integration tests with CI partitioning (for sharded CI jobs)
[unix]
ci-test-rust-partition SLICE:
    @echo "Running Rust tests partition {{SLICE}}..."
    vx cargo nextest run --config-file .config/nextest.toml --profile ci --features "test-helpers" --tests --partition hash:{{SLICE}}
    @echo "[OK] Rust partition {{SLICE}} passed"

# Run Python tests in parallel via pytest-xdist
test-python-parallel WORKERS="auto":
    @echo "Running Python tests in parallel ({{WORKERS}} workers)..."
    vx uv run pytest tests/python/unit -q --tb=short -m "not slow and not qt" -n {{WORKERS}} \
        --ignore=tests/python/unit/integration/qt \
        --ignore=tests/python/unit/test_qt_signals.py
    @echo "[OK] Parallel Python tests passed"

# Run mutation testing on a specific crate (requires cargo-mutants)
mutants-crate CRATE:
    @echo "Running mutation tests for {{CRATE}}..."
    vx cargo mutants -p {{CRATE}} --test-tool=nextest -- --config-file .config/nextest.toml --features "test-helpers"
    @echo "[OK] Mutation testing for {{CRATE}} completed"
    @echo "Report: mutants.out/

# Dry-run mutation testing (list mutants without running)
mutants-list CRATE:
    @echo "Listing mutants for {{CRATE}}..."
    vx cargo mutants -p {{CRATE}} --list

# Run mutation testing on core crates (quick subset)
mutants-quick:
    @echo "Running quick mutation tests on core crates..."
    vx cargo mutants -p auroraview-signals --test-tool=nextest -- --config-file .config/nextest.toml
    vx cargo mutants -p auroraview-protect --test-tool=nextest -- --config-file .config/nextest.toml
    @echo "[OK] Quick mutation testing completed"

# Run diff-based mutation testing (only mutate files changed vs base)
[unix]
mutants-diff BASE="origin/main":
    @echo "Running diff-based mutation testing against {{BASE}}..."
    @file_args=""; for f in $(vx git diff --name-only --diff-filter=ACMR {{BASE}}...HEAD -- '*.rs' | grep -E '^(crates|src)/' | head 20); do file_args="$file_args --file $f"; done; \
    if [ -z "$file_args" ]; then echo "No changed Rust files found"; else \
    vx cargo mutants $file_args --test-tool=nextest -- --config-file .config/nextest.toml --profile mutation --features "test-helpers"; fi
    @echo "[OK] Diff-based mutation testing completed"

[windows]
mutants-diff BASE="origin/main":
    @echo "Diff-based mutation testing is only supported on Unix."

# Collect unified coverage + mutation report
harness-coverage:
    @echo "Collecting coverage and mutation report..."
    vx uv run python scripts/harness_coverage.py
    @echo "[OK] harness-coverage completed"

# Write unified coverage report to a file
harness-coverage-file OUTPUT="coverage-report.json":
    @echo "Writing coverage report to {{OUTPUT}}..."
    vx uv run python scripts/harness_coverage.py --output {{OUTPUT}}

# ═══════════════════════════════════════════════════════════════════════════════
# Snapshot & Flaky Test Commands
# ═══════════════════════════════════════════════════════════════════════════════

# Run Rust tests and update insta snapshots
snapshot-review:
    @echo "Running Rust tests with insta snapshot review..."
    INSTA_UPDATE=new vx cargo test --workspace
    @echo "[OK] Snapshots generated. Run 'vx cargo insta review' to accept."

# Accept all pending insta snapshots
snapshot-accept:
    @echo "Accepting all pending insta snapshots..."
    vx cargo insta accept --all
    @echo "[OK] All snapshots accepted"

# Reject all pending insta snapshots
snapshot-reject:
    @echo "Rejecting all pending insta snapshots..."
    vx cargo insta reject --all
    @echo "[OK] All pending snapshots rejected"

# Run Rust snapshot tests in CI mode (fail on mismatch)
snapshot-ci:
    @echo "Running insta snapshot tests in CI mode..."
    CI=true vx cargo test --workspace
    @echo "[OK] All snapshots match"

# Detect flaky Rust tests (using nextest flaky-detect profile with retries)
[unix]
test-flaky-detect: nextest-install
    @echo "Running flaky test detection (3 retries per test)..."
    vx cargo nextest run --config-file .config/nextest.toml --profile flaky-detect --features "test-helpers" --tests
    @echo "[OK] Flaky detection run completed"

[windows]
test-flaky-detect:
    @echo "Skipping flaky detection on Windows due to abi3/PyO3 DLL constraints."

# Detect flaky Python tests (re-run failures up to 3 times)
test-python-flaky-detect:
    @echo "Running Python flaky test detection (rerun failures up to 3 times)..."
    vx uv run pytest tests/python/unit -v --tb=short --reruns 3 --reruns-delay 1 \
        -m "not slow and not qt" \
        --ignore=tests/python/unit/integration/qt \
        --ignore=tests/python/unit/test_qt_signals.py
    @echo "[OK] Python flaky detection completed"

# Run Python tests with auto-rerun for flaky tests (CI-friendly)
ci-test-python-rerun:
    @echo "Running Python tests with auto-rerun for flaky tests..."
    vx uv run pytest tests/python/unit tests/python/integration -v --tb=short \
        --reruns 2 --reruns-delay 1 \
        -m "not slow" \
        --cov=auroraview \
        --cov-report=term-missing \
        --cov-report=xml \
        --cov-fail-under=0 \
        --timeout=60
    @echo "[OK] Python tests with rerun completed"

# Setup development module for Maya

maya-setup-dev:
    @echo "=========================================="
    @echo "Setting up Maya Development Environment"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Creating symlink to project root..."
    @powershell -Command "New-Item -ItemType Directory -Force -Path '$env:USERPROFILE\Documents\maya\modules' | Out-Null; if (Test-Path '$env:USERPROFILE\Documents\maya\modules\auroraview') { Remove-Item -Recurse -Force '$env:USERPROFILE\Documents\maya\modules\auroraview' }; New-Item -ItemType SymbolicLink -Path '$env:USERPROFILE\Documents\maya\modules\auroraview' -Target '{{justfile_directory()}}' -Force | Out-Null"
    @echo "[OK] Symlink created: ~/Documents/maya/modules/auroraview -> {{justfile_directory()}}"
    @echo ""
    @echo "[2/3] Installing Maya module file..."
    @powershell -Command "Copy-Item -Path '{{justfile_directory()}}\examples\maya-outliner\auroraview.mod' -Destination '$env:USERPROFILE\Documents\maya\modules\auroraview.mod' -Force"
    @echo "[OK] Module file installed: ~/Documents/maya/modules/auroraview.mod"
    @echo ""
    @echo "[3/3] Installing userSetup.py..."
    @powershell -Command "New-Item -ItemType Directory -Force -Path '$env:USERPROFILE\Documents\maya\2024\scripts' | Out-Null; Copy-Item -Path '{{justfile_directory()}}\examples\maya-outliner\userSetup_dev.py' -Destination '$env:USERPROFILE\Documents\maya\2024\scripts\userSetup.py' -Force"
    @echo "[OK] userSetup.py installed for Maya 2024"
    @echo ""
    @echo "=========================================="
    @echo "Development environment ready!"
    @echo "=========================================="
    @echo ""
    @echo "Module configuration:"
    @echo "  Symlink: ~/Documents/maya/modules/auroraview -> {{justfile_directory()}}"
    @echo "  Module file: ~/Documents/maya/modules/auroraview.mod"
    @echo "  PYTHONPATH: {{justfile_directory()}}/python"
    @echo "  PYTHONPATH: {{justfile_directory()}}/examples/maya-outliner"
    @echo ""
    @echo "Next steps:"
    @echo "  1. Run: vx just maya-dev (rebuild + launch Maya)"

    @echo "  2. Click 'Outliner' button on AuroraView shelf"
    @echo ""

# Complete Maya development workflow (setup + rebuild + launch)
maya-dev:
    @echo "=========================================="
    @echo "Maya Development Workflow"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Killing all Maya processes..."
    -@powershell -Command "try { Get-Process maya -ErrorAction Stop | Stop-Process -Force; Write-Host '[OK] Maya processes terminated' } catch { Write-Host '[OK] No Maya processes running' }"
    @echo ""
    @echo "[2/3] Rebuilding Rust core..."
    @vx just rebuild-pylib

    @echo ""
    @echo "[3/3] Launching Maya 2024..."
    @powershell -Command "Start-Process -FilePath 'C:\Program Files\Autodesk\Maya2024\bin\maya.exe'"
    @echo "[OK] Maya launched"
    @echo ""
    @echo "=========================================="
    @echo "Maya Development Mode Active"
    @echo "=========================================="
    @echo ""
    @echo "✓ Symlinks are active (changes reflect immediately)"
    @echo "✓ Click 'Outliner' button on AuroraView shelf"
    @echo "✓ Or run in Script Editor:"
    @echo "    from maya_integration import maya_outliner"
    @echo "    maya_outliner.main()"
    @echo ""
    @echo "To rebuild after code changes:"
    @echo "  vx just maya-dev"

    @echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# Maya Development Commands
# ═══════════════════════════════════════════════════════════════════════════════

# Maya debugging workflow (legacy - use maya-dev instead)
maya-debug:
    @echo "=========================================="
    @echo "Maya Debug Workflow"
    @echo "=========================================="
    @echo ""
    @echo "[1/4] Killing all Maya processes..."
    -@powershell -Command "try { Get-Process maya -ErrorAction Stop | Stop-Process -Force; Write-Host '[OK] Maya processes terminated' } catch { Write-Host '[OK] No Maya processes running' }"
    @echo ""
    @echo "[2/4] Rebuilding Rust core..."
    @vx just rebuild-pylib

    @echo ""
    @echo "[3/4] Creating launch script..."
    @echo @echo off > launch_maya_temp.bat
    @echo set PYTHONPATH={{justfile_directory()}}\python >> launch_maya_temp.bat
    @echo "C:\Program Files\Autodesk\Maya2024\bin\maya.exe" >> launch_maya_temp.bat
    @echo "[OK] Launch script created"
    @echo ""
    @echo "[4/4] Launching Maya 2024..."
    @start launch_maya_temp.bat
    @echo "[OK] Maya launched"
    @echo ""
    @echo "=========================================="
    @echo "Maya launched with AuroraView in PYTHONPATH"
    @echo "=========================================="
    @echo ""
    @echo "In Maya Script Editor, run:"
    @echo "  import sys"
    @echo "  sys.path.append(r'{{justfile_directory()}}\examples\maya-outliner')"
    @echo "  from maya_integration import maya_outliner"
    @echo "  maya_outliner.main()"
    @echo ""



# ═══════════════════════════════════════════════════════════════════════════════
# SDK Commands (TypeScript SDK for frontend)
# ═══════════════════════════════════════════════════════════════════════════════

# Install SDK dependencies
sdk-install:
    @echo "Installing SDK dependencies..."
    cd packages/auroraview-sdk; vx bun install
    @echo "[OK] SDK dependencies installed!"

# Build SDK npm package
[unix]
sdk-build: sdk-install
    @echo "Building SDK npm package..."
    cd packages/auroraview-sdk; vx bun run build
    @echo "[OK] SDK built in packages/auroraview-sdk/dist/"

[windows]
sdk-build: sdk-install
    @echo "Building SDK npm package..."
    cd packages/auroraview-sdk; vx bun run build
    @echo "[OK] SDK built in packages/auroraview-sdk/dist/"

# Build SDK assets (inject scripts for Rust)
[unix]
sdk-build-assets: sdk-install
    @echo "Building SDK assets (inject scripts)..."
    cd packages/auroraview-sdk; vx bun run build:assets
    @echo "[OK] Assets built in crates/auroraview-core/src/assets/js/"

[windows]
sdk-build-assets: sdk-install
    @echo "Building SDK assets (inject scripts)..."
    cd packages/auroraview-sdk; vx bun run build:assets
    @echo "[OK] Assets built in crates/auroraview-core/src/assets/js/"

# Build SDK all (npm package + assets)
sdk-build-all: sdk-install
    @echo "Building SDK (all)..."
    cd packages/auroraview-sdk; vx bun run build:all
    @echo "[OK] SDK and assets built!"

# Run SDK unit tests
[unix]
sdk-test: sdk-install
    @echo "Running SDK unit tests..."
    cd packages/auroraview-sdk; vx bun run test
    @echo "[OK] SDK tests passed!"

[windows]
sdk-test: sdk-install
    @echo "Running SDK unit tests..."
    cd packages/auroraview-sdk; vx bun run test
    @echo "[OK] SDK tests passed!"

# Run SDK tests with coverage
[unix]
sdk-test-cov: sdk-install
    @echo "Running SDK tests with coverage..."
    cd packages/auroraview-sdk; vx bun run test:coverage
    @echo "[OK] SDK coverage report: packages/auroraview-sdk/coverage/"

[windows]
sdk-test-cov: sdk-install
    @echo "Running SDK tests with coverage..."
    cd packages/auroraview-sdk; vx bun run test:coverage
    @echo "[OK] SDK coverage report: packages/auroraview-sdk/coverage/"

# Run SDK E2E tests (requires Playwright)
[unix]
sdk-test-e2e: sdk-playwright-install sdk-build
    @echo "Running SDK E2E tests..."
    @# E2E test HTML imports from /dist/index.js; npx serve roots at test-app/
    @ln -sfn "{{justfile_directory()}}/packages/auroraview-sdk/dist" \
             "{{justfile_directory()}}/packages/auroraview-sdk/tests/e2e/test-app/dist"
    cd packages/auroraview-sdk; vx bun run test:e2e
    @echo "[OK] SDK E2E tests passed!"

[windows]
sdk-test-e2e: sdk-playwright-install sdk-build
    @echo "Running SDK E2E tests..."
    # E2E test HTML imports from /dist/index.js; npx serve roots at test-app/
    if (!(Test-Path "packages/auroraview-sdk/tests/e2e/test-app/dist")) { cmd /c mklink /D "packages\auroraview-sdk\tests\e2e\test-app\dist" "{{justfile_directory()}}\packages\auroraview-sdk\dist" }
    cd packages/auroraview-sdk; vx bun run test:e2e
    @echo "[OK] SDK E2E tests passed!"

# Run all SDK tests (unit + E2E)
[unix]
sdk-test-all: sdk-playwright-install
    @echo "Running all SDK tests..."
    cd packages/auroraview-sdk; vx bun run test:all
    @echo "[OK] All SDK tests passed!"

[windows]
sdk-test-all: sdk-playwright-install
    @echo "Running all SDK tests..."
    cd packages/auroraview-sdk; vx bun run test:all
    @echo "[OK] All SDK tests passed!"

# Run SDK type check
[unix]
sdk-typecheck: sdk-install
    @echo "Running SDK type check..."
    cd packages/auroraview-sdk; vx bun run typecheck
    @echo "[OK] SDK type check passed!"

[windows]
sdk-typecheck: sdk-install
    @echo "Running SDK type check..."
    cd packages/auroraview-sdk; vx bun run typecheck
    @echo "[OK] SDK type check passed!"

# Install Playwright for SDK E2E tests
[unix]
sdk-playwright-install: sdk-install
    @echo "Installing Playwright for SDK E2E tests..."
    cd packages/auroraview-sdk; vx bun run playwright install chromium --with-deps
    @echo "[OK] Playwright installed!"

[windows]
sdk-playwright-install: sdk-install
    @echo "Installing Playwright for SDK E2E tests..."
    cd packages/auroraview-sdk; vx bun run playwright install chromium --with-deps
    @echo "[OK] Playwright installed!"

# Full SDK CI check (typecheck + test + coverage + build)
sdk-ci: sdk-install sdk-typecheck sdk-test-cov sdk-build-all
    @echo "[OK] SDK CI check passed!"

# ═══════════════════════════════════════════════════════════════════════════════
# Gallery Commands
# ═══════════════════════════════════════════════════════════════════════════════

# Install gallery dependencies using bun (CI/local parity path)
gallery-ci-install:
    @echo "Installing gallery dependencies (bun)..."
    cd gallery; vx bun install
    @echo "[OK] Gallery dependencies installed!"

# Build gallery frontend using bun (CI/local parity path)
gallery-ci-build: sdk-build gallery-ci-install
    @echo "Building gallery frontend (bun)..."
    cd gallery; vx bun run build
    @echo "[OK] Gallery built in gallery/dist/"

# Install Python Playwright for Gallery CI/E2E flows
gallery-ci-playwright-install:
    @echo "Installing Python Playwright for Gallery tests..."
    vx uv run --with playwright python -m playwright install chromium
    @echo "[OK] Gallery Playwright installed!"


# Build gallery frontend (builds SDK first)
gallery-build: sdk-build
    @echo "Building gallery frontend..."
    cd gallery; vx bun install; vx bun run build
    @echo "[OK] Gallery built in gallery/dist/"

# Run gallery (build frontend first, then launch with AuroraView)
gallery: gallery-build
    @echo "Starting AuroraView Gallery..."
    vx uv run python gallery/main.py

# Run gallery dev server (for frontend development)
gallery-dev:
    @echo "Starting gallery dev server..."
    cd gallery; vx bun run dev

# Run Gallery E2E tests
gallery-test:
    @echo "Running Gallery E2E tests..."
    vx uv run pytest tests/python/integration/test_gallery_e2e.py tests/python/integration/test_gallery_contract.py tests/python/integration/test_gallery_plugin_api.py -v --tb=short

# Run Gallery Inspector tests (uses Inspector API, auto-starts Gallery)
gallery-test-inspector: gallery-build
    @echo "Running Gallery Inspector tests (auto-starts Gallery)..."
    vx uv run pytest tests/python/integration/test_gallery_inspector.py tests/python/integration/test_gallery_deep_inspection.py -v --tb=short

# Run Gallery Playwright E2E tests (frontend only, with mock API)
gallery-test-playwright: gallery-ci-playwright-install
    @echo "Running Gallery Playwright E2E tests..."
    vx uv run --with playwright python scripts/test_gallery_e2e.py

# Full Gallery verification path aligned with CI frontend checks
gallery-verify: gallery-ci-build gallery-test-playwright
    @echo "[OK] Gallery verify check passed!"

# ═══════════════════════════════════════════════════════════════════════════════
# Gallery E2E Tests (Playwright + CDP)
# ═══════════════════════════════════════════════════════════════════════════════


# Install Playwright for E2E tests
gallery-e2e-install: gallery-ci-playwright-install
    @echo "[OK] Gallery E2E dependencies ready!"


# Start Gallery with CDP for E2E testing (background process)
# Use this before running gallery-e2e-test
[windows]
gallery-e2e-start: gallery-pack-debug
    @echo "Starting Gallery with CDP enabled (port 9222)..."
    @powershell -Command "Start-Process -FilePath 'gallery\pack-output\auroraview-gallery-debug.exe' -WorkingDirectory 'gallery\pack-output'"
    @echo "[OK] Gallery started. Run: vx just gallery-e2e-test"
    @echo ""
    @echo "CDP endpoint: http://127.0.0.1:9222"
    @echo "Run tests with: vx just gallery-e2e-test"
    @echo "Stop with: vx just gallery-e2e-stop"


[unix]
gallery-e2e-start: gallery-pack-debug
    @echo "Starting Gallery with CDP enabled (port 9222)..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @echo "[OK] Gallery started. Run: vx just gallery-e2e-test"
    @echo ""
    @echo "CDP endpoint: http://127.0.0.1:9222"
    @echo "Run tests with: vx just gallery-e2e-test"
    @echo "Stop with: vx just gallery-e2e-stop"


# Stop Gallery E2E test instance
[windows]
gallery-e2e-stop:
    @echo "Stopping Gallery..."
    @powershell -Command "Get-Process -Name 'auroraview-gallery-debug' -ErrorAction SilentlyContinue | Stop-Process -Force"
    @echo "[OK] Gallery stopped"

[unix]
gallery-e2e-stop:
    @echo "Stopping Gallery..."
    @pkill -f "auroraview-gallery-debug" || true
    @echo "[OK] Gallery stopped"

# Run E2E tests against a running packed Gallery via CDP
[windows]
gallery-e2e-test: gallery-ci-playwright-install
    @echo "Running Gallery CDP E2E tests..."
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'; vx uv run --with pytest --with playwright pytest tests/test_gallery_cdp.py -v --tb=short -o addopts=

[unix]
gallery-e2e-test: gallery-ci-playwright-install
    @echo "Running Gallery CDP E2E tests..."
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 vx uv run --with pytest --with playwright pytest tests/test_gallery_cdp.py -v --tb=short -o addopts=

# Run E2E tests with more verbose stdout (for debugging)
[windows]
gallery-e2e-test-headed: gallery-ci-playwright-install
    @echo "Running Gallery CDP E2E tests with verbose output..."
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'; vx uv run --with pytest --with playwright pytest tests/test_gallery_cdp.py -v --tb=short -s -o addopts=

[unix]
gallery-e2e-test-headed: gallery-ci-playwright-install
    @echo "Running Gallery CDP E2E tests with verbose output..."
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 vx uv run --with pytest --with playwright pytest tests/test_gallery_cdp.py -v --tb=short -s -o addopts=

# Show where Gallery E2E artifacts are written
gallery-e2e-report:
    @echo "Gallery E2E artifacts:"
    @echo "  - pytest output: terminal / CI logs"
    @echo "  - screenshot: gallery/test_screenshot.png"
    @echo "  - script screenshots: test-screenshots/"


# Full E2E workflow: auto pack + start + CDP tests + cleanup
[windows]
gallery-e2e-packed-playwright: gallery-e2e-install gallery-pack-debug
    @echo "=========================================="
    @echo "Gallery E2E CDP Suite (Packed)"
    @echo "=========================================="
    @echo ""
    @echo "[1/4] Starting packed Gallery (debug, CDP enabled)..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "[2/4] Waiting for CDP port (9222)..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo ""
    @echo "[3/4] Running Gallery CDP E2E tests..."
    @vx just gallery-e2e-test
    @echo ""
    @echo "[4/4] Completed"
    @echo "=========================================="

[unix]
gallery-e2e-packed-playwright: gallery-e2e-install gallery-pack-debug
    @echo "=========================================="
    @echo "Gallery E2E CDP Suite (Packed)"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Starting packed Gallery (debug, CDP enabled)..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @echo "[2/3] Waiting for CDP port (9222)..."
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo "[3/3] Running Gallery CDP E2E tests..."
    @bash -lc 'set -e; trap "pkill -f auroraview-gallery-debug || true" EXIT; vx just gallery-e2e-test'
    @echo "[OK] Completed"


# 生成 Gallery 文档截图（Playwright + CDP）
[windows]
gallery-e2e-screenshots: gallery-e2e-install gallery-pack-debug
    @echo "=========================================="
    @echo "Gallery Docs Screenshots (Playwright)"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Starting packed Gallery (debug, CDP enabled)..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo "[2/3] Waiting for CDP port (9222)..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo "[3/3] Capturing documentation screenshots via Playwright..."
    @powershell -NoLogo -File scripts/gallery_e2e_run_playwright.ps1 -ProjectRoot "{{justfile_directory()}}" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp" -SpecFile "specs/gallery-screenshots.e2e.ts" -EnableScreenshots
    @echo "[OK] Screenshots updated: docs/public/gallery/"

[unix]
gallery-e2e-screenshots: gallery-e2e-install gallery-pack-debug
    @echo "=========================================="
    @echo "Gallery Docs Screenshots (Playwright)"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Starting packed Gallery (debug, CDP enabled)..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @echo "[2/3] Waiting for CDP port (9222)..."
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo "[3/3] Capturing documentation screenshots via Playwright..."
    @bash -lc 'set -e; trap "pkill -f auroraview-gallery-debug || true" EXIT; cd tests/e2e; AURORAVIEW_SCREENSHOTS=1 vx npx playwright test --config playwright.config.ts specs/gallery-screenshots.e2e.ts'
    @echo "[OK] Screenshots updated: docs/public/gallery/"

# Backward-compatible alias
gallery-e2e: gallery-e2e-packed-playwright


# Run Gallery real E2E tests (requires gallery-build first)

gallery-test-real: gallery-build
    @echo "Running Gallery real E2E tests..."
    vx uv run pytest tests/python/integration/test_gallery_real_e2e.py -v --tb=short

# Run Gallery test loop (continuous testing)
gallery-test-loop:
    @echo "Running Gallery test loop..."
    vx uv run python scripts/test_gallery_loop.py

# Run Gallery test loop in watch mode
gallery-test-watch:
    @echo "Running Gallery test loop in watch mode..."
    vx uv run python scripts/test_gallery_loop.py --watch

# Generate Gallery screenshots for documentation
gallery-screenshots:
    @echo "Generating Gallery screenshots for documentation (Playwright)..."
    vx just gallery-e2e-screenshots
    @echo "[OK] Screenshots saved to docs/public/gallery/"


# Generate example screenshots for documentation
example-screenshots:
    @echo "Generating example screenshots for documentation..."
    vx uv run python scripts/screenshot_examples.py
    @echo "[OK] Screenshots saved to docs/public/examples/"

# Generate example screenshots (specific example)
example-screenshot EXAMPLE:
    @echo "Generating screenshot for: {{EXAMPLE}}..."
    vx uv run python scripts/screenshot_examples.py --example {{EXAMPLE}}

# List available examples for screenshots
example-list:
    @echo "Available examples:"
    vx uv run python scripts/screenshot_examples.py --list

# Generate all documentation screenshots (gallery + examples)
docs-screenshots: gallery-screenshots example-screenshots
    @echo "[OK] All documentation screenshots generated!"

# ═══════════════════════════════════════════════════════════════════════════════
# Packaging Commands
# ═══════════════════════════════════════════════════════════════════════════════

# Build wheel
build-wheel:
    @echo "Building Python wheel..."
    vx uv run maturin build --release --features "ext-module,python-bindings,win-webview2"
    @echo "[OK] Wheel built in target/wheels/"

# Pack Gallery into standalone executable (release profile)
# Frontend build is handled by gallery/auroraview.pack.toml [build].before
gallery-pack: assets-build
    @echo "Packing Gallery into standalone executable (release)..."
    vx cargo run -p auroraview-cli --release -- pack --config gallery/auroraview.pack.toml
    @echo "[OK] Gallery release package built!"
    @echo ""
    @echo "Output: gallery/pack-output/auroraview-gallery.exe"
    @echo "Run with: just gallery-run-packed"

# Pack Gallery with local Sentry configuration
# Loads DSN from gallery/.env.sentry (not committed to repo)
[windows]
gallery-pack-local: assets-build
    @echo "Packing Gallery with local Sentry configuration..."
    @if (Test-Path "gallery/.env.sentry") { \
        Write-Host "Loading Sentry configuration from gallery/.env.sentry"; \
        Get-Content "gallery/.env.sentry" | ForEach-Object { \
            if ($_ -match '^([^#][^=]+)=(.*)$') { \
                [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process'); \
            } \
        } \
    } else { \
        Write-Host "WARNING: gallery/.env.sentry not found, Sentry will be disabled" -ForegroundColor Yellow; \
    }
    vx cargo run -p auroraview-cli --release -- pack --config gallery/auroraview.pack.toml
    @echo "[OK] Gallery package built with local config!"

[unix]
gallery-pack-local: assets-build
    @echo "Packing Gallery with local Sentry configuration..."
    @if [ -f "gallery/.env.sentry" ]; then \
        echo "Loading Sentry configuration from gallery/.env.sentry"; \
        export $$(grep -v '^#' gallery/.env.sentry | xargs); \
    else \
        echo "WARNING: gallery/.env.sentry not found, Sentry will be disabled"; \
    fi
    vx cargo run -p auroraview-cli --release -- pack --config gallery/auroraview.pack.toml
    @echo "[OK] Gallery package built with local config!"

# Pack Gallery debug executable (devtools + remote debug + react-devtools)
# Uses dedicated debug config and writes a separate output binary name.
gallery-pack-debug: assets-build
    @echo "Packing Gallery debug executable..."
    vx cargo run -p auroraview-cli --release -- pack --config gallery/auroraview.pack.toml --output auroraview-gallery-debug
    @echo "[OK] Gallery debug package built!"
    @echo ""
    @echo "Output: gallery/pack-output/auroraview-gallery-debug.exe"
    @echo "Run with: vx just gallery-run-packed-debug"


# Run the packed Gallery executable (release)
[windows]
gallery-run-packed:
    @echo "Running packed Gallery (release)..."
    @if (Test-Path "gallery/pack-output/auroraview-gallery.exe") { Start-Process -FilePath "gallery/pack-output/auroraview-gallery.exe" -WorkingDirectory "gallery/pack-output" } else { Write-Host "[ERROR] Packed Gallery not found. Run 'vx just gallery-pack' first." -ForegroundColor Red }


[windows]
gallery-run-packed-debug:
    @echo "Running packed Gallery (debug)..."
    @if (Test-Path "gallery/pack-output/auroraview-gallery-debug.exe") { Start-Process -FilePath "gallery/pack-output/auroraview-gallery-debug.exe" -WorkingDirectory "gallery/pack-output" } else { Write-Host "[ERROR] Packed debug Gallery not found. Run 'vx just gallery-pack-debug' first." -ForegroundColor Red }


[unix]
gallery-run-packed:
    @echo "Running packed Gallery (release)..."
    @if [ -f "gallery/pack-output/auroraview-gallery" ]; then cd gallery/pack-output && ./auroraview-gallery; else echo "[ERROR] Packed Gallery not found. Run 'vx just gallery-pack' first."; fi


[unix]
gallery-run-packed-debug:
    @echo "Running packed Gallery (debug)..."
    @if [ -f "gallery/pack-output/auroraview-gallery-debug" ]; then cd gallery/pack-output && ./auroraview-gallery-debug; else echo "[ERROR] Packed debug Gallery not found. Run 'vx just gallery-pack-debug' first."; fi


# Run Gallery CDP tests (build, start, test, cleanup)
gallery-cdp: gallery-pack
    @echo "=========================================="
    @echo "Gallery CDP Test Suite"
    @echo "=========================================="
    @echo ""
    @echo "[1/4] Starting Gallery with CDP enabled..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "[2/4] Waiting for CDP port (9222)..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo ""
    @echo "[3/4] Running CDP tests (Inspector API + legacy)..."
    -vx uv run pytest tests/test_gallery_cdp.py tests/python/integration/test_gallery_inspector.py tests/python/integration/test_gallery_deep_inspection.py -v --tb=short
    @echo ""
    @echo "[4/4] Cleaning up..."
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "=========================================="
    @echo "[OK] Gallery CDP tests completed!"
    @echo "=========================================="

# Run Gallery CDP tests without rebuilding (assumes gallery-pack already run)
gallery-cdp-only:
    @echo "=========================================="
    @echo "Gallery CDP Test Suite (no rebuild)"
    @echo "=========================================="
    @echo ""
    @echo "[1/3] Starting Gallery with CDP enabled..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "[2/3] Waiting for CDP port (9222)..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo ""
    @echo "[3/3] Running CDP tests..."
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short
    @echo ""
    @echo "Cleaning up..."
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "=========================================="
    @echo "[OK] Gallery CDP tests completed!"
    @echo "=========================================="

# Debug Promise rejection button in packed Gallery via agent-browser (Windows)
[windows]
gallery-debug-promise-rejection: gallery-pack-debug
    @echo "Starting packed debug Gallery with CDP..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo "Capturing initial interactive snapshot via agent-browser..."
    vx npx --yes agent-browser --cdp 9222 snapshot -i
    @echo "Capturing annotated screenshot..."
    vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo "Use these follow-up commands to continue manual debug:"
    @echo "  vx npx --yes agent-browser --cdp 9222 snapshot -i"
    @echo "  vx npx --yes agent-browser --cdp 9222 click @e<id>"
    @echo "Stop with: vx just gallery-debug-promise-rejection-stop"

[windows]
gallery-debug-promise-rejection-stop:
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"

# Debug Promise rejection button in packed Gallery via agent-browser (Unix)
[unix]
gallery-debug-promise-rejection: gallery-pack-debug
    @echo "Starting packed debug Gallery with CDP..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @echo "Waiting for CDP port (9222)..."
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo "Capturing initial interactive snapshot via agent-browser..."
    vx npx --yes agent-browser --cdp 9222 snapshot -i
    @echo "Capturing annotated screenshot..."
    vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo "Use these follow-up commands to continue manual debug:"
    @echo "  vx npx --yes agent-browser --cdp 9222 snapshot -i"
    @echo "  vx npx --yes agent-browser --cdp 9222 click @e<id>"
    @echo "Stop with: vx just gallery-debug-promise-rejection-stop"

[unix]
gallery-debug-promise-rejection-stop:
    @pkill -f "auroraview-gallery-debug" || true

# Pack Gallery for release (generates project without building)

gallery-pack-project: gallery-build
    @echo "Generating Gallery pack project..."
    vx cargo run -p auroraview-cli --release -- pack --config gallery/auroraview.pack.toml --output-dir target/pack
    @echo "[OK] Gallery pack project generated in target/pack/auroraview-gallery/"

# ═══════════════════════════════════════════════════════════════════════════════
# Pack Commands (Application Packaging)
# ═══════════════════════════════════════════════════════════════════════════════

# Test auroraview-pack with verbose output
test-pack-verbose:
    @echo "Testing auroraview-pack crate (verbose)..."
    vx cargo test -p auroraview-pack --lib -- --nocapture
    @echo "[OK] Pack tests passed!"

# Run clippy on pack crate
lint-pack:
    @echo "Linting auroraview-pack crate..."
    vx cargo clippy -p auroraview-pack --all-targets -- -D warnings
    @echo "[OK] Pack lint passed!"

# Pack a URL into standalone executable
pack-url URL OUTPUT="myapp":
    @echo "Packing URL: {{URL}} -> {{OUTPUT}}.exe"
    vx cargo run -p auroraview-cli --release -- pack --url "{{URL}}" --output "{{OUTPUT}}"
    @echo "[OK] Packed to target/pack/{{OUTPUT}}/"

# Pack a frontend directory into standalone executable
pack-frontend FRONTEND OUTPUT="myapp":
    @echo "Packing frontend: {{FRONTEND}} -> {{OUTPUT}}.exe"
    vx cargo run -p auroraview-cli --release -- pack --frontend "{{FRONTEND}}" --output "{{OUTPUT}}"
    @echo "[OK] Packed to target/pack/{{OUTPUT}}/"

# Pack using a config file
pack-config CONFIG:
    @echo "Packing with config: {{CONFIG}}"
    vx cargo run -p auroraview-cli --release -- pack --config "{{CONFIG}}"
    @echo "[OK] Pack completed!"

# Pack and build in one step
pack-build CONFIG:
    @echo "Packing and building with config: {{CONFIG}}"
    vx cargo run -p auroraview-cli --release -- pack --config "{{CONFIG}}" --build
    @echo "[OK] Pack and build completed!"

# Show pack info for a config file
pack-info CONFIG:
    @echo "Pack info for: {{CONFIG}}"
    vx cargo run -p auroraview-cli --release -- info --config "{{CONFIG}}"

# Clean pack output directory
pack-clean:
    @echo "Cleaning pack output..."
    rm -rf target/pack
    @echo "[OK] Pack output cleaned!"

# Full pack workflow: test, lint, then pack gallery
pack-all: test-pack lint-pack gallery-pack
    @echo "[OK] Full pack workflow completed!"

# ═══════════════════════════════════════════════════════════════════════════════
# Documentation Commands (VitePress)
# ═══════════════════════════════════════════════════════════════════════════════

# Install documentation dependencies
docs-install:
    @echo "Installing documentation dependencies..."
    cd docs; vx bun install
    @echo "[OK] Documentation dependencies installed!"

# Generate Python API documentation with pdoc (optional, may fail due to network)
# Note: Only includes core modules that don't require third-party dependencies
# Excludes: integration/qt (requires qtpy), testing (requires pytest)
[unix]
docs-python-api:
    @echo "Generating Python API documentation with pdoc..."
    -vx uv venv .docs-venv --clear
    -vx uv pip install --python .docs-venv/bin/python pdoc>=14.0.0 --quiet
    -.docs-venv/bin/python -m pdoc --output-dir docs/api/python-gen --docformat google \
        python/auroraview/core \
        python/auroraview/ui \
        python/auroraview/utils \
        --no-show-source
    @echo "[OK] Python API docs generation completed (may have skipped due to network issues)"

[windows]
docs-python-api:
    @echo "Generating Python API documentation with pdoc..."
    -vx uv venv .docs-venv --clear
    -vx uv pip install --python .docs-venv\Scripts\python.exe pdoc>=14.0.0 --quiet
    -.docs-venv\Scripts\python.exe -m pdoc --output-dir docs/api/python-gen --docformat google \
        python/auroraview/core \
        python/auroraview/ui \
        python/auroraview/utils \
        --no-show-source
    @echo "[OK] Python API docs generation completed (may have skipped due to network issues)"



# Generate examples documentation from examples/ directory
docs-generate-examples:
    @echo "Generating examples documentation..."
    cd docs; vx bun run generate-examples
    @echo "[OK] Examples documentation generated!"

# Start documentation dev server (auto-generates examples docs)
docs-dev: docs-install docs-generate-examples docs-python-api
    @echo "Starting documentation dev server..."
    cd docs; vx bun run dev

# Alias for docs-dev
docs-serve: docs-dev

# Build documentation (auto-generates examples docs + Python API)
[unix]
docs-build: docs-install docs-generate-examples docs-python-api
    @echo "Building documentation..."
    mkdir -p docs/public
    cp assets/icons/auroraview-logo-text.png docs/public/logo.png || echo "Logo not found, using placeholder"
    cd docs; vx bun run build
    @echo "[OK] Documentation built in docs/.vitepress/dist/"

[windows]
docs-build: docs-install docs-generate-examples docs-python-api
    @echo "Building documentation..."
    New-Item -ItemType Directory -Path docs/public -Force | Out-Null
    if (Test-Path "assets/icons/auroraview-logo-text.png") { Copy-Item "assets/icons/auroraview-logo-text.png" "docs/public/logo.png" -Force } else { Write-Host "Logo not found, using placeholder" }
    cd docs; vx bun run build
    @echo "[OK] Documentation built in docs/.vitepress/dist/"

ci-docs-build: docs-build
    @echo "[OK] CI docs build completed"

# Preview built documentation
[unix]
docs-preview: docs-build
    @echo "Previewing documentation..."
    cd docs; vx bun run preview

[windows]
docs-preview: docs-build
    @echo "Previewing documentation..."
    cd docs; vx bun run preview

# Clean documentation build artifacts
docs-clean:
    @echo "Cleaning documentation build artifacts..."
    rm -rf docs/.vitepress/dist docs/.vitepress/cache docs/node_modules docs/api/python-gen .docs-venv
    @echo "[OK] Documentation artifacts cleaned!"


# ═══════════════════════════════════════════════════════════════════════════════
# (Removed) MCP Server Commands
#
# The standalone Python `auroraview-mcp` package was retired in favour of the
# Rust `crates/auroraview-mcp` adapter + `dcc-mcp-core`'s gateway. See #364.
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Assets Commands (Frontend Assets for Rust Crates)
# ═══════════════════════════════════════════════════════════════════════════════


# Install assets frontend dependencies
assets-install:
    @echo "Installing assets frontend dependencies..."
    cd crates/auroraview-assets/frontend; vx bun install
    @echo "[OK] Assets dependencies installed!"

# Build all assets (loading, error, browser, browser-controller)
assets-build: assets-install
    @echo "Building frontend assets..."
    cd crates/auroraview-assets/frontend; vx bun run build
    @echo "[OK] Assets built in crates/auroraview-assets/frontend/dist/"

# Build assets in watch mode (for development)
assets-dev: assets-install
    @echo "Starting assets dev server..."
    cd crates/auroraview-assets/frontend; vx bun run dev

# Preview built assets
assets-preview: assets-build
    @echo "Previewing built assets..."
    cd crates/auroraview-assets/frontend; vx bun run preview

# Lint assets frontend code
assets-lint: assets-install
    @echo "Linting assets frontend code..."
    cd crates/auroraview-assets/frontend; vx bun run lint

# Type check assets frontend code
assets-typecheck: assets-install
    @echo "Type checking assets frontend code..."
    cd crates/auroraview-assets/frontend; vx bun run typecheck

# Clean assets build artifacts
assets-clean:
    @echo "Cleaning assets build artifacts..."
    rm -rf crates/auroraview-assets/frontend/dist crates/auroraview-assets/frontend/node_modules
    @echo "[OK] Assets artifacts cleaned!"

# Full assets CI check
assets-ci: assets-install assets-typecheck assets-lint assets-build
    @echo "[OK] Assets CI check passed!"

# ═══════════════════════════════════════════════════════════════════════════════
# ProofShot + agent-browser E2E Commands
# ═══════════════════════════════════════════════════════════════════════════════

# Install ProofShot and agent-browser (includes headless Chromium)
e2e-install:
    @echo "Installing ProofShot + agent-browser..."
    vx npm install -g proofshot
    @echo "[OK] ProofShot installed (includes agent-browser + Chromium)"

# Start packed Gallery with CDP and wait for readiness
[windows]
e2e-start: gallery-pack-debug
    @echo "Starting Gallery with CDP (port 9222)..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo "Waiting for CDP readiness..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo "[OK] Gallery running, CDP ready at http://127.0.0.1:9222"

[unix]
e2e-start: gallery-pack-debug
    @echo "Starting Gallery with CDP (port 9222)..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @echo "Waiting for CDP readiness..."
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo "[OK] Gallery running, CDP ready at http://127.0.0.1:9222"

# Wait for CDP port to become available
[windows]
e2e-wait-cdp:
    @echo "Waiting for CDP port (9222)..."
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo "[OK] CDP ready"

[unix]
e2e-wait-cdp:
    @echo "Waiting for CDP port (9222)..."
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo "[OK] CDP ready"

# Stop Gallery E2E process
[windows]
e2e-stop:
    @echo "Stopping Gallery..."
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo "[OK] Gallery stopped"

[unix]
e2e-stop:
    @echo "Stopping Gallery..."
    @pkill -f "auroraview-gallery-debug" || true
    @echo "[OK] Gallery stopped"

# Capture interactive snapshot via agent-browser (element discovery)
e2e-snapshot:
    @echo "Capturing interactive snapshot..."
    vx npx --yes agent-browser --cdp 9222 snapshot -i

# Capture annotated screenshot via agent-browser
e2e-screenshot:
    @echo "Capturing annotated screenshot..."
    vx npx --yes agent-browser --cdp 9222 screenshot --annotate

# Navigate to a URL via agent-browser
e2e-open URL:
    @echo "Navigating to {{URL}}..."
    vx npx --yes agent-browser --cdp 9222 open "{{URL}}"

# Click an element via agent-browser
e2e-click ELEMENT:
    @echo "Clicking element {{ELEMENT}}..."
    vx npx --yes agent-browser --cdp 9222 click "{{ELEMENT}}"

# Fill an input via agent-browser
e2e-fill ELEMENT VALUE:
    @echo "Filling {{ELEMENT}} with value..."
    vx npx --yes agent-browser --cdp 9222 fill "{{ELEMENT}}" "{{VALUE}}"

# Run a ProofShot exec command (wraps agent-browser with session logging)
e2e-exec +ARGS:
    @echo "Running ProofShot exec: {{ARGS}}..."
    proofshot exec {{ARGS}}

# Start a ProofShot recording session against CDP
e2e-record-start DESCRIPTION="E2E verification":
    @echo "Starting ProofShot recording session..."
    proofshot start --description "{{DESCRIPTION}}"
    @echo "[OK] ProofShot session started"

# Stop ProofShot recording and generate artifacts
e2e-record-stop:
    @echo "Stopping ProofShot session and generating artifacts..."
    proofshot stop
    @echo "[OK] Artifacts in ./proofshot-artifacts/"

# Compare screenshots against baseline (visual regression)
e2e-diff:
    @echo "Running visual diff against baseline..."
    proofshot diff --baseline ./test-screenshots/baseline
    @echo "[OK] Visual diff complete"

# Upload ProofShot proof artifacts to current PR
e2e-pr PR="":
    @echo "Uploading proof artifacts to PR..."
    proofshot pr {{PR}}
    @echo "[OK] Proof uploaded to PR"

# Clean ProofShot artifacts
e2e-clean:
    @echo "Cleaning ProofShot artifacts..."
    proofshot clean
    @echo "[OK] Artifacts cleaned"

# Full ProofShot E2E workflow: pack + start + record + test + stop + cleanup
[windows]
e2e-proofshot: e2e-install gallery-pack-debug
    @echo "==========================================="
    @echo "ProofShot E2E Verification Suite"
    @echo "==========================================="
    @echo ""
    @echo "[1/6] Starting Gallery with CDP..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo ""
    @echo "[2/6] Starting ProofShot recording..."
    -proofshot start --description "Gallery E2E verification"
    @echo ""
    @echo "[3/6] Capturing interactive snapshot..."
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    @echo ""
    @echo "[4/6] Capturing annotated screenshot..."
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo ""
    @echo "[5/6] Running Playwright CDP tests..."
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short
    @echo ""
    @echo "[6/6] Stopping ProofShot and collecting artifacts..."
    -proofshot stop
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "==========================================="
    @echo "[OK] ProofShot E2E verification complete!"
    @echo "Artifacts: ./proofshot-artifacts/"
    @echo "==========================================="

[unix]
e2e-proofshot: e2e-install gallery-pack-debug
    @echo "==========================================="
    @echo "ProofShot E2E Verification Suite"
    @echo "==========================================="
    @echo ""
    @echo "[1/6] Starting Gallery with CDP..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo ""
    @echo "[2/6] Starting ProofShot recording..."
    -proofshot start --description "Gallery E2E verification"
    @echo ""
    @echo "[3/6] Capturing interactive snapshot..."
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    @echo ""
    @echo "[4/6] Capturing annotated screenshot..."
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo ""
    @echo "[5/6] Running Playwright CDP tests..."
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short
    @echo ""
    @echo "[6/6] Stopping ProofShot and collecting artifacts..."
    -proofshot stop
    @bash -lc 'pkill -f auroraview-gallery-debug || true'
    @echo ""
    @echo "==========================================="
    @echo "[OK] ProofShot E2E verification complete!"
    @echo "Artifacts: ./proofshot-artifacts/"
    @echo "==========================================="

# Self-iteration loop: build → start → verify → analyze → report
[windows]
e2e-iterate: gallery-pack-debug
    @echo "==========================================="
    @echo "E2E Self-Iteration Loop"
    @echo "==========================================="
    @echo ""
    @echo "[1/5] Starting Gallery with CDP..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @powershell -File scripts/gallery_cdp_wait.ps1
    @echo ""
    @echo "[2/5] Starting ProofShot recording..."
    -proofshot start --description "Self-iteration verification"
    @echo ""
    @echo "[3/5] Capturing snapshot and screenshot..."
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo ""
    @echo "[4/5] Running E2E tests..."
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short
    @echo ""
    @echo "[5/5] Stopping and collecting..."
    -proofshot stop
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo ""
    @echo "==========================================="
    @echo "[OK] Iteration complete. Review:"
    @echo "  Artifacts: ./proofshot-artifacts/"
    @echo "  Next: fix issues, then run 'vx just e2e-iterate' again"
    @echo "==========================================="

[unix]
e2e-iterate: gallery-pack-debug
    @echo "==========================================="
    @echo "E2E Self-Iteration Loop"
    @echo "==========================================="
    @echo ""
    @echo "[1/5] Starting Gallery with CDP..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    @echo ""
    @echo "[2/5] Starting ProofShot recording..."
    -proofshot start --description "Self-iteration verification"
    @echo ""
    @echo "[3/5] Capturing snapshot and screenshot..."
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    @echo ""
    @echo "[4/5] Running E2E tests..."
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short
    @echo ""
    @echo "[5/5] Stopping and collecting..."
    -proofshot stop
    @bash -lc 'pkill -f auroraview-gallery-debug || true'
    @echo ""
    @echo "==========================================="
    @echo "[OK] Iteration complete. Review:"
    @echo "  Artifacts: ./proofshot-artifacts/"
    @echo "  Next: fix issues, then run 'vx just e2e-iterate' again"
    @echo "==========================================="

# CI E2E: full proof-based E2E suitable for CI pipelines
[windows]
e2e-ci: e2e-install gallery-pack-debug
    @echo "Running CI E2E with ProofShot..."
    @powershell -File scripts/gallery_cdp_start.ps1 -ExePath "{{justfile_directory()}}\gallery\pack-output\auroraview-gallery-debug.exe" -WorkDir "{{justfile_directory()}}\gallery\pack-output" -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @powershell -File scripts/gallery_cdp_wait.ps1
    -proofshot start --description "CI E2E verification"
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short --json-report --json-report-file=e2e-report.json
    -proofshot stop
    @powershell -File scripts/gallery_cdp_stop.ps1 -PidFile "{{justfile_directory()}}\.gallery-pid.tmp"
    @echo "[OK] CI E2E complete. Artifacts: ./proofshot-artifacts/"

[unix]
e2e-ci: e2e-install gallery-pack-debug
    @echo "Running CI E2E with ProofShot..."
    cd gallery/pack-output && ./auroraview-gallery-debug &
    @bash -lc 'for i in {1..60}; do curl -sf http://127.0.0.1:9222/json/version >/dev/null && exit 0; sleep 0.5; done; echo "ERROR: CDP not ready"; exit 1'
    -proofshot start --description "CI E2E verification"
    -vx npx --yes agent-browser --cdp 9222 snapshot -i
    -vx npx --yes agent-browser --cdp 9222 screenshot --annotate
    -vx uv run pytest tests/test_gallery_cdp.py -v --tb=short --json-report --json-report-file=e2e-report.json
    -proofshot stop
    @bash -lc 'pkill -f auroraview-gallery-debug || true'
    @echo "[OK] CI E2E complete. Artifacts: ./proofshot-artifacts/"
