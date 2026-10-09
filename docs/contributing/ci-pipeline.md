# CI Pipeline Architecture

This document describes the CI/CD pipeline architecture for AuroraView, optimized for package isolation and efficient builds.

## Overview

AuroraView uses a **package-isolated CI strategy** where each package (Rust crates, SDK, MCP, Gallery, Docs) has its own CI workflow. This approach:

- **Reduces CI time**: Only affected packages are built and tested
- **Improves feedback**: Faster feedback for focused changes
- **Respects dependencies**: Dependency chains trigger downstream tests automatically

## Package Structure

```
AuroraView
├── Rust Crates
│   ├── aurora-signals (standalone)
│   ├── aurora-protect (standalone)
│   ├── auroraview-plugin-core (standalone)
│   ├── auroraview-plugin-fs → plugin-core
│   ├── auroraview-extensions (standalone)
│   ├── auroraview-plugins → plugin-core, plugin-fs, extensions
│   ├── auroraview-core → signals, plugins
│   ├── auroraview-pack → protect (optional)
│   ├── auroraview-cli → core, pack
│   └── auroraview (root) → core, signals
├── Frontend Packages
│   ├── @auroraview/sdk (TypeScript)
│   └── auroraview-gallery → SDK
├── Python Packages
│   └── auroraview (Python bindings)
└── Documentation
    └── docs (VitePress)
```

## Workflow Files

| Workflow | Purpose | Trigger |
|----------|---------|---------|
| `pr-checks.yml` | PR validation | Pull requests |
| `rust-crates-ci.yml` | Rust crate testing | Crate changes |
| `python-ci.yml` | Python testing | Python changes |
| `sdk-ci.yml` | SDK build & test | SDK changes |
| `mcp-ci.yml` | MCP server CI | MCP changes |
| `docs.yml` | Documentation | Docs changes |
| `build-gallery.yml` | Gallery packaging | Release |

## Dependency Chain Detection

When a file changes, the CI automatically detects which packages need to be tested based on the dependency graph.

### Example: `aurora-signals` Change

```
aurora-signals changed
    └── triggers: auroraview-core (depends on signals)
        └── triggers: auroraview-cli (depends on core)
            └── triggers: auroraview (root, depends on core)
```

### Example: `auroraview-plugin-core` Change

```
auroraview-plugin-core changed
    ├── triggers: auroraview-plugin-fs (depends on plugin-core)
    └── triggers: auroraview-plugins (depends on plugin-core)
        └── triggers: auroraview-core (depends on plugins)
            └── triggers: auroraview-cli, auroraview (root)
```

## Local Development Commands

Use `just` commands for package-level testing:

```bash
# Test individual crates
just test-signals          # aurora-signals
just test-protect          # aurora-protect
just test-plugin-core      # auroraview-plugin-core
just test-plugin-fs        # auroraview-plugin-fs
just test-extensions       # auroraview-extensions
just test-plugins          # auroraview-plugins
just test-core             # auroraview-core
just test-pack             # auroraview-pack
just test-cli              # auroraview-cli

# Test groups
just test-standalone       # All standalone crates
just test-python           # Python tests only
just test-python-unit      # Python unit tests
just test-python-integration  # Python integration tests

# SDK and Gallery
just sdk-test              # SDK unit tests
just sdk-ci                # Full SDK CI
just gallery-test          # Gallery E2E tests

# MCP
just mcp-test              # MCP tests
just mcp-ci                # Full MCP CI
```

## Path Filters

The CI uses path filters to determine which workflows to run:

| Category | Paths | Triggers |
|----------|-------|----------|
| `rust` | `src/**`, `crates/**`, `Cargo.*` | Rust builds, wheel builds |
| `python` | `python/**`, `tests/python/**` | Python tests |
| `sdk` | `packages/auroraview-sdk/**` | SDK build |
| `gallery` | `gallery/**` | Gallery E2E |
| `docs` | `docs/**`, `*.md` | Docs build |
| `ci` | `.github/**`, `justfile` | All checks |

## Artifact Reuse

To avoid duplicate builds, artifacts are shared between jobs:

1. **SDK Assets**: Built once, used by wheel builds and Gallery
2. **Wheels**: Built once per platform, used by Python tests and Gallery pack
3. **CLI**: Built once per platform, used by Gallery pack

## Best Practices

### For Contributors

1. **Focus changes**: Keep PRs focused on specific packages
2. **Run local tests**: Use `just test-<package>` before pushing
3. **Check CI summary**: Review the "Detected Changes" summary in PR checks

### For Maintainers

1. **Monitor CI times**: Track build times per package
2. **Update dependencies**: Keep the dependency graph in sync with `Cargo.toml`
3. **Cache optimization**: Ensure cache keys are package-specific

## Release Workflow

The release process is handled by `.github/workflows/release.yml`, which manages:

1. **Version Management**: Uses `release-please` to automate version bumps and changelog generation
2. **Wheel Building**: Builds platform-specific wheels for all supported platforms
3. **Package Publishing**: Publishes to PyPI (Python) and npm (TypeScript SDK)
4. **GitHub Releases**: Creates release assets including CLI binaries and Gallery executables

### Supported Platforms

| Platform | Architecture | Python Wheel | PyPI Upload | GitHub Release |
|----------|-------------|--------------|-------------|----------------|
| Windows | x64 (amd64) | ✅ Yes | ✅ Yes | ✅ Yes |
| macOS | universal2 (x64+ARM64) | ✅ Yes | ✅ Yes | ✅ Yes |
| Linux | x86_64 | ✅ Yes | ❌ No | ✅ Yes |
| Windows | ARM64 | ❌ No | ❌ No | CLI/Gallery only |
| Linux | ARM64 | ❌ No | ❌ No | CLI/Gallery only |

**Why no ARM64 Python wheels?**

- **Linux ARM64**: `wry` depends on `webkit2gtk` which requires native ARM64 system libraries (`libwebkit2gtk-4.1-dev`). Cross-compiling from x86_64 requires a complete ARM64 sysroot with these libraries, which is extremely complex and unreliable. `pkg-config` cannot resolve ARM64 library paths without a properly configured cross-compilation sysroot.
- **Windows ARM64**: `maturin` requires a Python interpreter matching the target architecture to determine correct wheel filenames and ABI tags. GitHub Actions runners only provide x86_64 Python interpreters.
- **Workaround**: ARM64 users can build from source (`pip install .` with Rust toolchain), or use the CLI/Gallery ARM64 binaries which are pure Rust builds without Python dependency.

Note: Linux x86_64 wheels are not uploaded to PyPI because they require system libraries (webkit2gtk) and use non-standard platform tags. Linux users should install from GitHub Releases or build from source.

### NPM Publishing

The SDK release job publishes the verified `@auroraview/sdk` tarball to
`https://registry.npmjs.org` using OIDC trusted publishing. The existing workflow
uses GitHub-hosted runners, Node 24 and npm 11, with `id-token: write` and the
`npm` environment.

The npm trusted publisher must match organization `try-auroraview`, repository
`auroraview`, workflow filename `release.yml`, and environment `npm`. This
external npm binding needs separate verification; the presence of a repository
secret named `NPM_TOKEN` does not establish a valid publisher, and this workflow
does not consume that secret. See the
[official npm trusted-publisher documentation](https://docs.npmjs.com/trusted-publishers/).

### PyPI Publishing

The Python package is published to PyPI as `auroraview`. Key considerations:

1. **File Size Limit**: PyPI has a 100MB limit per file. Source distributions (sdist) often exceed this due to bundled assets, so they are built separately for GitHub Releases only.
2. **Platform Tags**: Only Windows and macOS wheels are uploaded to PyPI. Linux wheels use non-standard tags and are excluded.
3. **ABI3 Support**: Python 3.8+ uses abi3 (stable ABI) for a single wheel per platform. Python 3.7 requires separate non-abi3 builds; CI publishes dedicated `cp37` wheels for Linux/Windows, while macOS 3.7 users should build from source.

### DCC-MCP Contract Publication

The independent `auroraview-dcc-mcp` package uses `dcc-mcp-contracts.yml`.
GitHub preview publication and the optional PyPI trusted-publisher job are
separate delivery gates. If PyPI fails after the preview succeeds, a maintainer
must correct publisher configuration, then rerun the failed jobs on that same
verified publication run. Do not recreate the preview/tag or start another
dispatch just to retry PyPI.

## Troubleshooting

### CI runs all checks unexpectedly

- Check if `.github/**` or `justfile` was modified (triggers all checks)
- Verify path filters are correctly configured

### Dependency not detected

- Ensure the dependency is listed in the workflow's dependency chain computation
- Check `rust-crates-ci.yml` for the dependency graph logic

### Cache misses

- Cache keys are based on `Cargo.lock` hash
- Different packages may have different cache keys

### NPM publish fails with 404

Error: `404 Not Found - PUT https://registry.npmjs.org/@auroraview%2fsdk`

Inspect the publish job's failure and confirm that the package's npm trusted
publisher matches `try-auroraview/auroraview`, workflow `release.yml`, environment
`npm`, and permits direct `npm publish`. A maintainer must correct a missing or
mismatched external binding before rerunning the failed jobs on the same
verified release run. Existing-version retries compare the official registry's
integrity with the verified archive before skipping publication.

### PyPI publish fails with "File too large"

Error: `400 File too large. Limit for project 'auroraview' is 100 MB`

**Solution**:
- This is expected for source distributions (sdist) containing Rust code and assets
- The CI workflow automatically excludes sdist from PyPI uploads
- sdist is built separately and uploaded to GitHub Releases only
- Users needing source can download from GitHub Releases

### ARM64 builds fail

ARM64 Python wheel builds have been removed from CI due to fundamental cross-compilation limitations:

- **Linux ARM64**: `wry`/`webkit2gtk` cannot be cross-compiled without a complete ARM64 sysroot. The `pkg-config` tool fails with "not been configured to support cross-compilation" because ARM64 development libraries are not available on x86_64 runners.
- **Windows ARM64**: `maturin` cannot find a matching Python interpreter. Error: "Need a Python interpreter to compile for Windows without PyO3's generate-import-lib feature". Even with `generate-import-lib`, maturin still needs an interpreter for wheel packaging metadata.

CLI and Gallery ARM64 binaries (pure Rust, no Python) are still built via cross-compilation and available in GitHub Releases.
