# Contributing to DCC WebView

Thank you for contributing to AuroraView / DCC WebView.

## Code of Conduct

Please be respectful and constructive in all interactions with the community.

## Development Setup

### Prerequisites

- `vx` (required runtime/tool manager)
- Git

### Setup

```bash
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview

# Install tools and hooks from vx.toml
vx setup

# Install Python dependencies
vx just install
```

## Canonical Workflow (Harness)

Use **`vx just <task>`** as the only entrypoint for local development and CI.

```bash
# Fast feedback loop
vx just harness-quick

# Full validation aligned with CI
vx just harness-verify

# Gallery packed E2E validation
vx just harness-gallery-e2e
```

## Development Workflow

### Rust

- Run `vx cargo fmt --all` before committing
- Run `vx cargo clippy --all-targets --all-features -- -D warnings`
- Keep modules focused and dependency direction clear

### Python

- Run `vx uvx ruff check python/ tests/`
- Run `vx uvx ruff format --check python/ tests/`
- Keep public APIs typed

### Testing

```bash
# Main workflow
vx just test

# Optional nox matrix
vx uvx nox -s pytest
vx uvx nox -s pytest-qt
vx uvx nox -s pytest-all
```

## Agent-Friendly Contribution Rules

To keep the repository agent-operable and reproducible:

- Keep decisions and operational rules in-repo (docs/code/config), not chat-only
- Prefer mechanical checks (lint/test/tasks) over human-only conventions
- Add or update `justfile` tasks when introducing new workflows
- Keep CI commands and local commands aligned through the same `vx just` task entrypoints

## Commit Messages

Follow Conventional Commits:

- `feat: add new feature`
- `fix: fix bug`
- `docs: update documentation`
- `test: add tests`
- `refactor: refactor code`
- `chore: update dependencies`

All commits should include DCO sign-off:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s` to add sign-off automatically.

## Pull Request Process

1. Create a feature branch from `main`
2. Implement changes with tests
3. Run `vx just harness-verify`
4. Update docs when behavior changes
5. Open PR with clear scope and validation evidence (logs/screenshots if UI related)

## Reporting Issues

Please include:

- DCC software name and version
- Python version
- Operating system
- Reproduction steps
- Expected vs actual behavior
- Error logs / screenshots

## Questions?

Open an issue for discussion.
