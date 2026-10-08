# AGENTS.md — AuroraView

> Lightweight WebView framework for DCC hosts (Maya, Houdini, Blender, 3ds Max…):
> Rust core + PyO3 bindings, WebView2 embedded into a Qt host on Windows.
> Navigation map for AI agents, not a reference manual. Follow the links; do not
> read everything up front.

## Build & test

```bash
vx just dev      # install deps (vx uv sync --group dev) + build extension module
vx just build    # build the extension module (maturin develop)
vx just test     # Rust crate tests + Python unit/integration tests
vx just check    # format + lint + test (run before opening a PR)
vx just lint     # unsafe-audit + clippy + ruff
vx just format   # cargo fmt + ruff format
```

Every tool command goes through `vx`; task orchestration goes through
`vx just <recipe>`. Do not call `cargo` / `pytest` / `maturin` directly — the
`just` recipes carry the platform- and feature-specific flags. Full recipe list:
`vx just --list`.

## Repo layout

| Path | Role |
|---|---|
| `crates/` | Rust crates (`auroraview-core` protocol + WebView backend abstraction, `auroraview-cli`, `auroraview-pack`, …) |
| `python/auroraview/` | Python package — `AuroraView` base class and DCC host layer |
| `packages/auroraview-sdk/` | TypeScript/JS front-end SDK |
| `gallery/` | Gallery demo app, used as the E2E baseline |
| `examples/` | Runnable examples |
| `tests/` | Python unit + integration tests; Rust integration tests live in `crates/<name>/tests/` |
| `docs/` | VitePress site for humans (DCC integration, API, RFCs); `docs/zh/` is the Chinese mirror |
| `llms.txt` | AI-friendly core usage index (5-minute read) |
| `llms-full.txt` | Complete usage index — every API signature and module note |

## Task → where to look

| Your task | Go here |
|---|---|
| Understand the architecture and conventions | `llms.txt` |
| Look up full API and architecture detail | `llms-full.txt` |
| Human-readable deep docs | `docs/` |
| Packaging internals, release, CI | `docs/contributing/pack-architecture.md` |
| Injected JavaScript layout | `docs/architecture/js-assets.md` |
| Front-end JS ↔ Python bridge | `docs/guide/communication.md` |
| Python layer API | `llms-full.txt` + `python/auroraview/` |
| CI pipeline | `docs/contributing/ci-pipeline.md` |

## 30-second orientation

- **Commands**: all tools via `vx`, all tasks via `vx just <recipe>`.
- **Compatibility floor**: Python 3.7+, no third-party Python runtime deps (a single `.pyd`).
- **Stack**: Rust (windows-rs / webview2-com / PyO3) + Python abi3 wheel + TypeScript SDK.
- **Event loop**: the Qt host owns the event loop — Rust does not take over the message pump.

## Release

- release-please drives versioning from Conventional Commits on `main`.
- `feat:` → minor, `fix:` → patch, `chore:`/`docs:`/`ci:` → **no release**.
- Use `chore:`/`docs:` for config and doc work so release-please does not cut a
  valueless version.
- release-please also bumps `Cargo.toml` (`workspace.package.version`),
  `pyproject.toml` and `packages/auroraview-sdk/package.json`. Never edit those
  versions by hand.

## Do / Don't

- **Do** single-source agent instructions here. This is the only agent contract
  file at the repo root.
- **Don't** add `CLAUDE.md` / `GEMINI.md` / `CURSOR.md` / `ANTHROPIC.md` /
  `OPENAI.md` / `COPILOT.md` / `CODEBUDDY.md` / `.cursorrules` / `.clinerules` /
  `.windsurfrules` at the root. Vendor-specific notes live under
  `docs/integrations/`, linked from here.
- **Do** run `vx just build` / `vx just test` — never bare `cargo build` or `pytest`.
- **Don't** put emoji in code.
- **Do** keep function names short and use industry-standard terms; avoid
  `optimized`, `fixed`, and similar noise words.
- **Do** put Rust integration tests in each crate's `tests/` directory using
  `rstest`; **don't** write inline unit tests.
- **Do** treat `crates/auroraview-cli/skills/<name>/SKILL.md` as the source of
  truth for Skills — `auroraview-cli skills install` redistributes them into
  each tool's local mirror, never copy into those mirrors by hand.
- **Do** dispatch all front-end events through `window.auroraview.trigger()`;
  **don't** mix in native `CustomEvent`.
- **Don't** hardcode an exact version in tests (`assert __version__ == "X.Y.Z"`)
  — release-please bumps will break it. Use `>=` or read package metadata.
- **Don't** commit build artifacts to the repo root (`audit-result.json`,
  `clippy_check.txt`, `commit_msg.txt`, `coverage.json`).

## References

- Repository: https://github.com/try-auroraview/auroraview
- PyPI: https://pypi.org/project/auroraview
- `./CHANGELOG.md`, `./CONTRIBUTING.md`
