# Contributing Guide

Thank you for your interest in contributing to AuroraView! This guide will help you get started.

## Development Setup

### Prerequisites

- **Rust**: 1.75 or higher
- **Python**: 3.7 or higher
- **Node.js**: 18 or higher (for SDK and Gallery)
- **just**: Command runner (install via `cargo install just`)

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview

# Install Rust toolchain
rustup update stable

# Install Python development dependencies
pip install -e ".[dev]"

# Install Node.js dependencies for SDK
cd packages/auroraview-sdk
npm install
cd ../..

# Verify setup
just check
```

### Project Structure

```
auroraview/
├── src/                    # Rust core library
│   ├── lib.rs              # PyO3 module entry
│   ├── ipc/                # IPC system
│   ├── webview/            # WebView implementation
│   └── utils/              # Utilities
├── crates/                 # Additional Rust crates
│   ├── auroraview-core/    # Core functionality
│   └── auroraview-cli/     # CLI tool
├── python/                 # Python bindings
│   └── auroraview/         # Python package
├── packages/               # JavaScript packages
│   └── auroraview-sdk/     # TypeScript SDK
├── gallery/                # Gallery application
├── examples/               # Example scripts
├── tests/                  # Test suites
│   ├── python/             # Python tests
│   └── rust/               # Rust tests
└── docs/                   # Documentation (VitePress)
```

## Development Workflow

### Building

```bash
# Build Rust library
cargo build

# Build Python wheel (development)
maturin develop

# Build TypeScript SDK
cd packages/auroraview-sdk
npm run build
```

### Testing

```bash
# Run all tests
just test

# Rust tests only
cargo test

# Python tests only
pytest tests/python/

# SDK tests only
cd packages/auroraview-sdk
npm test
```

### Linting

```bash
# Run all linters
just lint

# Rust linting
cargo clippy --all-targets --all-features
cargo fmt --check

# Python linting
ruff check python/
ruff format --check python/

# TypeScript linting
cd packages/auroraview-sdk
npm run lint
```

### Documentation

```bash
# Start documentation dev server
cd docs
npm run dev

# Build documentation
npm run build
```

## Code Style

### Rust

- Follow [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- Use `cargo fmt` for formatting
- Use `cargo clippy` for linting
- Document public APIs with doc comments

```rust
/// Creates a new WebView with the specified configuration.
///
/// # Arguments
///
/// * `config` - The WebView configuration
///
/// # Returns
///
/// A new WebView instance
///
/// # Errors
///
/// Returns an error if the WebView cannot be created
pub fn create(config: WebViewConfig) -> Result<Self, Error> {
    // ...
}
```

### Python

- Follow [PEP 8](https://pep8.org/)
- Use type hints for all public APIs
- Use `ruff` for linting and formatting
- Document with docstrings (Google style)

```python
def create_webview(
    title: str,
    url: str | None = None,
    html: str | None = None,
    width: int = 800,
    height: int = 600,
) -> WebView:
    """Create a new WebView instance.

    Args:
        title: The window title.
        url: URL to load (mutually exclusive with html).
        html: HTML content to load (mutually exclusive with url).
        width: Window width in pixels.
        height: Window height in pixels.

    Returns:
        A new WebView instance.

    Raises:
        ValueError: If both url and html are provided.
    """
```

### TypeScript

- Use TypeScript strict mode
- Export types for public APIs
- Use JSDoc for documentation

```typescript
/**
 * Call a Python API method.
 *
 * @param method - The method name (e.g., "api.get_data")
 * @param params - Optional parameters to pass
 * @returns The method result
 * @throws {AuroraViewError} If the call fails
 *
 * @example
 * ```ts
 * const user = await av.call<User>('api.get_user', { id: 1 });
 * ```
 */
async call<T>(method: string, params?: unknown): Promise<T>;
```

## Testing Guidelines

### Rust Tests

Place tests in `tests/` directories:

```rust
// crates/auroraview-core/tests/webview_test.rs
use auroraview_core::WebView;
use rstest::rstest;

#[rstest]
fn test_webview_creation() {
    let webview = WebView::new(Default::default());
    assert!(webview.is_ok());
}
```

### Python Tests

Use pytest with fixtures:

```python
# tests/python/test_webview.py
import pytest
from auroraview import WebView

@pytest.fixture
def webview():
    return WebView.create("Test", html="<h1>Test</h1>")

def test_webview_title(webview):
    assert webview.title == "Test"
```

### TypeScript Tests

Use Vitest:

```typescript
// packages/auroraview-sdk/tests/client.test.ts
import { describe, it, expect } from 'vitest';
import { createAuroraView } from '../src';

describe('AuroraViewClient', () => {
  it('should create client', () => {
    const client = createAuroraView();
    expect(client).toBeDefined();
  });
});
```

## Pull Request Process

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/my-fix
```

### 2. Make Changes

- Write code following the style guidelines
- Add tests for new functionality
- Update documentation if needed

### 3. Commit

Use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add new feature"
git commit -m "fix: resolve issue with..."
git commit -m "docs: update getting started guide"
git commit -m "test: add tests for..."
```

Commit types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

### 4. Push and Create PR

```bash
git push origin feature/my-feature
```

Then create a Pull Request on GitHub.

### 5. CI Checks

Your PR must pass:
- Rust tests and clippy
- Python tests and ruff
- TypeScript tests and eslint
- Documentation build

#### CI Concurrency Control

All CI workflows are configured with concurrency control to automatically cancel redundant runs:

- When you push new commits to a PR, any in-progress CI runs for that PR are automatically cancelled
- This saves CI resources and provides faster feedback on your latest changes
- The concurrency is scoped by workflow and PR number, so different PRs run independently

```yaml
# Example concurrency configuration used in all workflows
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

This means:
- You don't need to wait for old CI runs to complete before pushing new commits
- The CI will always test your latest code
- Release workflows (tag pushes) are never cancelled to ensure releases complete

### 6. Review

- Address review comments
- Keep the PR focused on one change
- Squash commits if requested

## Adding New Features

### Adding a New Python API

1. Add Rust implementation in `src/`:

```rust
// src/webview/aurora_view.rs
#[pymethods]
impl AuroraView {
    pub fn new_feature(&self, param: String) -> PyResult<String> {
        // Implementation
        Ok(result)
    }
}
```

2. Add Python wrapper in `python/auroraview/`:

```python
# python/auroraview/webview.py
def new_feature(self, param: str) -> str:
    """Description of the new feature.

    Args:
        param: Description of parameter.

    Returns:
        Description of return value.
    """
    return self._inner.new_feature(param)
```

3. Add tests:

```python
# tests/python/test_new_feature.py
def test_new_feature(webview):
    result = webview.new_feature("test")
    assert result == "expected"
```

4. Update documentation:

```markdown
<!-- docs/api/webview.md -->
### new_feature(param)

Description of the new feature.
```

### Adding a New SDK Feature

1. Add TypeScript implementation:

```typescript
// packages/auroraview-sdk/src/features/new-feature.ts
export async function newFeature(param: string): Promise<string> {
  const av = getAuroraView();
  return av.call('api.new_feature', { param });
}
```

2. Export from index:

```typescript
// packages/auroraview-sdk/src/index.ts
export { newFeature } from './features/new-feature';
```

3. Add tests:

```typescript
// packages/auroraview-sdk/tests/new-feature.test.ts
describe('newFeature', () => {
  it('should work', async () => {
    const result = await newFeature('test');
    expect(result).toBe('expected');
  });
});
```

## Release Process

Releases are automated via GitHub Actions:

1. Merge PR to `main`
2. Release-please creates a release PR
3. Merge release PR to trigger release
4. CI builds and publishes:
   - Python wheels to PyPI
   - TypeScript SDK to npm
   - Documentation to GitHub Pages

## Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and discussions
- **Discord**: Real-time chat (link in README)

## Code of Conduct

Please read and follow our [Code of Conduct](https://github.com/try-auroraview/auroraview/blob/main/CODE_OF_CONDUCT.md).
