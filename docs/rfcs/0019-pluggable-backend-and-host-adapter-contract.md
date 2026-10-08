# RFC 0019: Pluggable Rendering Backend and Host Adapter Contract

- Number: 0019
- Title: Make the WebView backend a real pluggable seam, and define the contract that `auroraview-unreal` / `auroraview-maya` / `auroraview-unity` implement
- Status: Draft
- Created: 2026-09-19
- Revised: 2026-09-22 (aligned to the contracts landed in PR #471; see §0.1)
- Authors: AuroraView Core Team
- Affected code: `crates/auroraview-contract`, `crates/auroraview-core/src/backend/`, `src/webview/backend/`, `crates/auroraview-ue`, `python/auroraview/adapter/`, `python/auroraview/utils/thread_dispatcher/`, `python/auroraview/dcc_mcp/`, `crates/auroraview-cli/skills/`
- Related:
  - [PR #471](https://github.com/try-auroraview/auroraview/pull/471) — host-adapter and render-backend contracts (**merged 2026-09-22**; lands §1/§2 of this RFC's contract layer)
  - [PR #463](https://github.com/try-auroraview/auroraview/pull/463) — host-agnostic parent/child IPC bridge and `--parent-hwnd` embedding (**merged 2026-09-22**)
  - [PR #460](https://github.com/try-auroraview/auroraview/pull/460) — DCC-MCP WebView adapter (**merged 2026-09-19**)
  - [`docs/design/adapter-contract.md`](../design/adapter-contract.md) — the design record for #471; **this RFC is its RFC-layer counterpart**
  - RFC 0007 (WebView/Browser unified architecture), RFC 0011 (unified IPC), RFC 0018 (packed CLI mode)

> **Note on numbering.** This document was referred to as "RFC 0008" during planning.
> `0008` is already taken twice (`0008-ai-agent-integration.md`, `0008-auroraview-testing-redesign.md`),
> so it is filed as `0019`, the next free number. Content is unchanged.

---

## 0. Scope and non-goals

**In scope:** design only. No implementation code ships with this RFC.

**Out of scope (deliberately deferred):**

- Creating GitHub repositories or moving code between repositories. The physical split
  into `try-auroraview/*` is blocked on an owner decision (S2 in
  [`docs/design/adapter-contract.md`](../design/adapter-contract.md)). Every contract below is written
  so that it works **identically whether the adapter lives in this monorepo or in its own repo**.
- CEF/Chromium implementation work. This RFC fixes the seam and the feature names; the
  second backend lands after the seam is proven.
- Changing the organization's CI topology.

### 0.1 Relationship to PR #471 (read this first)

This RFC was drafted before [#471](https://github.com/try-auroraview/auroraview/pull/471) and
[#463](https://github.com/try-auroraview/auroraview/pull/463) merged. Both are now on `main`, and
they land the contract layer this RFC argued for — under **different names and a different
registration mechanism**.

To prevent the exact doc/code divergence this project has hit repeatedly, this revision
defers to the merged code on every point of overlap:

| Concept | Original RFC 0019 draft (**superseded**) | Merged in #471 (**authoritative — used below**) |
|---|---|---|
| Backend factory trait | `Backend` | `RenderBackend` |
| Created surface trait | `BackendWebView` | `RenderSurface` |
| Surface description | `BackendInit` | `SurfaceSpec` |
| Backend registry | `BackendFactory::registered()` | `BackendRegistry` |
| Backend classification | CEF named as the second backend | `BackendFamily::{Native, Chromium, Other}`; `ChromiumBackend` declared |
| Capability set | `BackendCapabilities { native_parenting, owned_event_loop, cdp, screenshot }` | `Features` bitflags + `CapabilitySupport` probe results |
| Host contract | Python `auroraview.hosts` entry point with `detect()` / `parent_handle()` / `dispatcher()` / `lifecycle_hooks()` | Rust `HostAdapter` + `HostRegistry`; Python `python/auroraview/adapter/`; `AURORAVIEW_HOST` override |
| Missing-feature reporting | not covered | `CapabilitySupport::{Supported, Unsupported { reason, how_to_enable }, Unknown { reason }}` + `require()` |

Two consequences shape the rest of this document:

1. **§1 and §2 no longer propose a new abstraction.** They are scoped to the three
   follow-ups #471 explicitly deferred, restated in #471's vocabulary.
2. **§3 no longer proposes an entry-point protocol.** The `auroraview.hosts` entry point
   group from the original draft has **zero occurrences** anywhere in `pyproject.toml`,
   `Cargo.toml` or `python/`; it was a proposal only, and #471 shipped a different
   mechanism. It is removed and replaced by the merged `HostAdapter` / `HostRegistry`
   contract.

Reciprocal reference: [`docs/design/adapter-contract.md`](../design/adapter-contract.md) §8
lists "surface creation is not rewired" and "`BackendFactory` delegates to `BackendRegistry`"
as the next step after the contract is agreed. **This RFC is that next step**, and it is the
document the design record should point at for the follow-up scope.

---

## 1. Current state (verified against `main` @ `a760fc89`)

The planning assumption "the backend is hardcoded to wry, there is no abstraction" is
**half wrong**. There are in fact *three* backend abstractions, and none of them is yet the
seam we need end to end.

### 1.1 Layer 0 — `auroraview-contract` (new, merged in #471, dependency-free leaf)

[#471](https://github.com/try-auroraview/auroraview/pull/471) added
`crates/auroraview-contract` with a deliberately **empty `[dependencies]` section**, making it
the leaf of the dependency graph. It holds contracts only — no implementation, no host SDK,
no WebView engine:

| File | Contents |
| --- | --- |
| `host.rs` (754 L) | `HostAdapter`, `HostRegistry`, `HostInfo`, `HostJob`, `UiFramework`, `ThreadModel`, `EmbedMode`, `ENV_HOST` = `AURORAVIEW_HOST` |
| `backend.rs` (834 L) | `RenderBackend`, `RenderSurface`, `BackendRegistry`, `BackendFamily`, `SurfaceSpec`, `NativeWebviewBackend`, `ChromiumBackend`, `ENV_BACKEND` = `AURORAVIEW_BACKEND` |
| `capability.rs` (543 L) | `Features` bitflags, `CapabilitySupport`, `CapabilityReport`, `CapabilityProbe`, `CapabilityError` |
| `registry.rs` (473 L) | `Registry`, `Entry`, `Selection` — shared priority-registry mechanics |

The Python mirror is `python/auroraview/adapter/` (`base.py`, `backends.py`, `hosts.py`,
`capability.py`, `registry.py`), with `scripts/ci/check_contract_capability_parity.py`
guarding that the two sides do not drift.

`auroraview-core` depends on the contract and re-exports it as
`auroraview_core::contract`, pinned by `crates/auroraview-core/tests/contract_reexport.rs`.
That re-export is what guarantees one copy of the contract per process — two copies would
mean two distinct `dyn HostAdapter` types and an adapter registering into a `HostRegistry`
that core never reads.

**Not yet wired:** `NativeWebviewBackend::available()` is `false` until the crate that links
the engine calls `set_linked(true)`, and `ChromiumBackend` is a declared-but-unlinked
descriptor. `default_backend_registry().select()` therefore returns `None` today, which is
the honest answer. Nobody constructs a surface through the registry yet.

### 1.2 Layer 1 — `auroraview_core::backend` (exists, aspirational, off the hot path)

`crates/auroraview-core/src/backend/` contains a complete, well-documented abstraction:

| File | Contents |
| --- | --- |
| `traits.rs` (289 L) | `WebViewBackend`, `EmbeddableBackend`, `EventLoopBackend` |
| `factory.rs` (172 L) | `BackendType` enum, `BackendConfig`, `BackendFactory`, `AURORAVIEW_BACKEND` env var |
| `wry_impl.rs` (362 L) | `WryBackend` — the only implementation |
| `lifecycle.rs` (448 L) | `AtomicLifecycle` lock-free state machine |
| `message_processor.rs` (356 L) | `MessageProcessor`, `ProcessingMode` |
| `settings.rs` (161 L) | `WebViewSettings` / `WebViewSettingsImpl` |

Problems (all three still true after #471):

1. **Nothing on the hot path uses it.** The only consumers are
   `crates/auroraview-core/tests/backend_tests.rs` and a re-export block in
   `src/webview/backend/mod.rs`. It is a parallel abstraction.
2. **The enum lies.** `BackendType` declares four variants, but `BackendFactory::create`
   maps `WebView2` to `WryBackend` (an alias, not a backend), and returns
   `Err(WebViewError::Internal("... not yet implemented"))` for `WKWebView` and `WebKitGTK`.
3. **`mod wry_impl` is private.** `wry_impl` is not `pub`, so no external crate can
   implement against it or learn from it.

Per [`docs/design/adapter-contract.md`](../design/adapter-contract.md) §7, `WebViewBackend` is
intended to *become one implementation of* `RenderBackend`. That migration has not happened.

### 1.3 Layer 2 — `PyBindingsBackend` (the real hot path, leaks wry/tao)

The code that actually creates a WebView is `NativeBackend`
(`src/webview/backend/native.rs`, 1382 L), which implements the `PyBindingsBackend` trait
declared in `src/webview/backend/mod.rs` (242 L).

`PyBindingsBackend` is a good operational trait — `load_url`, `load_html`, `eval_js`,
`emit`, `process_events`, `process_ipc_only`, `run_blocking`, `lifecycle_state`,
`request_close` — but **three of its methods leak wry/tao types into the signature**:

```rust
fn webview(&self) -> Arc<Mutex<WryWebView>>;                              // src/webview/backend/mod.rs:127
fn window(&self) -> Option<&tao::window::Window>;                         // src/webview/backend/mod.rs:133
fn take_event_loop(&mut self) -> Option<tao::event_loop::EventLoop<UserEvent>>; // src/webview/backend/mod.rs:166
```

These three signatures are the entire reason a second backend is impossible today.
Any new backend would have to produce a `wry::WebView`, which is a contradiction.

### 1.4 Dependency facts

- Root crate `Cargo.toml`: `wry = { workspace = true }` and `tao = { workspace = true }`,
  **unconditional**. `wry 0.54.4` / `tao 0.34.6` are pinned at `[workspace.dependencies]`.
- `crates/auroraview-core`: `wry` is **already optional**, gated behind the `wry-builder`
  feature. So core is closer to being backend-free than the root crate is.
- Other direct wry users that will need to route through the seam:
  `crates/auroraview-browser/src/{browser.rs,tab/manager.rs,tab/state.rs}`,
  `crates/auroraview-desktop/src/window/{builder.rs,mod.rs}`,
  `src/webview/desktop/webview_builder.rs`, `src/webview/{child_window,event_loop,message_processor,protocol_handlers,tab_manager,webview_inner}.rs`,
  `crates/auroraview-cli/src/{cli/run.rs,packed/webview/*,protocol_handlers.rs}`.

### 1.5 Python surface that must not break

`BackendType` is **public API**:

- `python/auroraview/core/backend.py` defines `BackendType` (`WRY`, `WEBVIEW2`, `WKWEBVIEW`,
  `WEBKITGTK`) and `get_backend_type()`.
- It is re-exported from `python/auroraview/core/__init__.py` and
  `python/auroraview/__init__.py`, and listed in `__all__`.

`AURORAVIEW_BACKEND` is also already a documented env var on both sides
(`BackendFactory::ENV_BACKEND` in Rust, docstring in `backend.py`), accepting
`wry` / `webview2`|`wv2`|`webview_2` / `wkwebview`|`wk`|`webkit` / `webkitgtk`|`gtk`.
#471 declares the same constant as `auroraview_contract::backend::ENV_BACKEND`, so the name
is now fixed in the contract crate as well.

**This is the good news: the user-facing selection mechanism already exists and already
has the name we want. It just does not reach the hot path.**

---

## 2. Design — Part 1: the three follow-ups PR #471 deferred

### 2.0 Principle: finish #471, do not re-open it

#471's own PR description states: *"Rewiring them, and having `BackendFactory` delegate to
`BackendRegistry`, are follow-ups."* As of this revision **none of those three follow-ups has
been started**. §2 is therefore not a competing design — it is the work item list that #471
handed forward, expressed in the vocabulary #471 landed.

Four rules govern the whole section:

1. **No new traits.** `RenderBackend`, `RenderSurface`, `SurfaceSpec`, `BackendRegistry`,
   `Features` and `CapabilitySupport` already exist in `auroraview-contract`. Work means
   *implementing and wiring them*, not redeclaring them.
2. **The contract crate stays dependency-free.** Anything that would pull `wry`, `tao` or a
   host SDK into `auroraview-contract` is by definition out of bounds.
3. **Version discipline.** The contract is versioned independently at `1.0.0` and is
   additive-only. Widening `RenderSurface::native_handle()` (§2.2) is a **removal-level
   change** under the policy in `crates/auroraview-contract/Cargo.toml` and must be
   coordinated across every host repository before it lands.
4. **One process, one contract.** Adapters import the contract through
   `auroraview_core::contract`, never through a direct `auroraview-contract` dependency.

### 2.1 Follow-up 1 — remove the three wry/tao signatures from `PyBindingsBackend`

**Status: not started.** The three signatures in §1.3 are unchanged on `main`:

- `src/webview/backend/mod.rs:127` — `fn webview(&self) -> Arc<Mutex<WryWebView>>`
- `src/webview/backend/mod.rs:133` — `fn window(&self) -> Option<&tao::window::Window>`
- `src/webview/backend/mod.rs:166` — `fn take_event_loop(&mut self) -> Option<tao::event_loop::EventLoop<UserEvent>>`

**Target state:** no symbol from `wry` or `tao` appears in any `pub` signature in
`src/webview/backend/`. `NativeBackend` keeps them as *private* helpers if it must — the
wry/tao coupling belongs inside one backend implementation, not on a trait that is supposed
to be backend-neutral.

**Why it still matters, unchanged from the original draft:** until this is done, a second
backend would have to produce a `wry::WebView`, which is a contradiction. This is the single
highest-value item in §2.

**Exit test:** `cargo build` succeeds with `--no-default-features --features backend-wry`,
and a grep guard (mirroring `scripts/ci/check_contract_capability_parity.py`) fails the build
if `wry::` or `tao::` reappears in a `pub fn` signature under `src/webview/backend/`.

### 2.2 Follow-up 2 — replace `Option<u64>` handles with a typed `NativeHandle`

**Status: not started, and now a contract-level decision.** `grep -rn NativeHandle --include=*.rs`
returns **zero hits**. There is no shared handle type — and, importantly, **no single handle
representation either**. The tree carries three, and they disagree about signedness:

**`Option<u64>`** — the contract layer and most of core:

- `crates/auroraview-contract/src/backend.rs:77` — `SurfaceSpec::parent_handle: Option<u64>`
- `crates/auroraview-contract/src/backend.rs:197` — `RenderSurface::native_handle() -> Option<u64>`
- `crates/auroraview-contract/src/host.rs:219` — `HostInfo::parent_handle: Option<u64>`
- `crates/auroraview-contract/src/host.rs:268` — `HostAdapter::parent_handle() -> Option<u64>`
- `crates/auroraview-core/src/backend/factory.rs:77` — `BackendConfig::parent_handle: Option<u64>`
- `crates/auroraview-core/src/backend/traits.rs:244` — `EmbeddableBackend::native_handle() -> Option<u64>`
- `crates/auroraview-core/src/config.rs:73` — `parent_hwnd: Option<u64>`
- `src/webview/backend/mod.rs:138` — `PyBindingsBackend::native_handle() -> Option<u64>`
- `src/webview/config.rs:347` — `parent_hwnd: Option<u64>`
- `crates/auroraview-extensions/src/view_manager.rs:117` — `parent_hwnd: Option<u64>`
- `crates/auroraview-plugins/src/extensions/mod.rs:91`, `types.rs:312` — `parent_hwnd: Option<u64>`

**`Option<isize>`** — the DCC and parent/child paths, i.e. every path that touches a real
host window:

- `crates/auroraview-core/src/parent_ipc/context.rs:27` — `ChildInfo::parent_hwnd: Option<isize>` (from #463)
- `crates/auroraview-core/src/parent_ipc/context.rs:71` — `parse_hwnd() -> Option<isize>` (from #463)
- `crates/auroraview-dcc/src/config.rs:109` — `parent_hwnd: Option<isize>`
- `crates/auroraview-dcc/src/window_manager.rs:26` — `parent_hwnd: Option<isize>`
- `crates/auroraview-dcc/src/webview.rs:51` — `webview_hwnd: Option<isize>`
- `crates/auroraview-dcc/src/webview.rs:386` — `parent_hwnd() -> Option<isize>`
- `src/bindings/runtime_dcc.rs:117` — `parent_hwnd: Option<isize>`

**`isize`** (bare, Windows platform layer — not optional at all):

- `src/platform/windows/webview2.rs:29`, `:623` — `parent_hwnd: isize`

(`crates/auroraview-cli/src/cli/run.rs:113` keeps `parent_hwnd: Option<String>`; that is the
CLI's textual argument form and is a legitimate difference, not part of this problem.)

**Why this matters more than a missing table row.** The split is not random: `u64` is what the
contract layer chose, and `isize` is what every path that actually touches a host window uses.
That is exactly the argument the original draft made for `NativeHandle` — *"it is unsigned on
Windows where `HWND` is signed"* — and the tree has already half-resolved it in favour of the
signed form. The DCC paths did not wait for the contract; they voted with `isize`. Any A/B
decision taken from the older text ("all handles are `u64`") would push the wrong way.

A bare `u64` also cannot express a macOS `NSView*`. The original draft proposed one neutral type:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NativeHandle {
    Win32(std::num::NonZeroIsize),
    AppKit(NonNull<c_void>),
    X11(u32),
    Wayland(NonNull<c_void>),
}
```

**What changed:** this is no longer a free choice. #471 landed `Option<u64>` *into the
published contract crate*, and that crate is versioned independently with an additive-only
`1.0` policy. Changing `RenderSurface::native_handle()` and `SurfaceSpec::parent_handle` is
therefore a **major-bump, coordinated-across-every-host-repo change**, not a local refactor.
Note that the contract's `u64` is the *minority* representation on live host-window paths; it
is the one that would have to move under option B.

Two viable resolutions, to be chosen before any code moves:

| Option | Cost | Notes |
| --- | --- | --- |
| **A. Keep `u64`, add `NativeHandle` beside it** | no breaking change | `NativeHandle` becomes the *in-process* type used below the contract; `RenderSurface` keeps `Option<u64>` at the boundary. Cheapest, but leaves two handle types. |
| **B. Widen the contract** | contract `2.0` | One type everywhere. Requires a coordinated major bump across every host repository once they exist — materially easier **now**, while no host repo has been created yet, than after S2. |

The original draft's migration advice still applies either way: keep `parent_handle` as a
deprecated field that converts through `NativeHandle::try_from(u64)`, so no Python or C
caller breaks. **Recommendation: decide before S2 splits any repository.** Option B is
inexpensive today and expensive later.

### 2.3 Follow-up 3 — make `BackendFactory` delegate to `BackendRegistry`

**Status: not started.** `crates/auroraview-core/src/backend/factory.rs` is still a closed
`match`:

```rust
pub fn create(config: &BackendConfig) -> WebViewResult<Box<dyn WebViewBackend>> {
    match backend_type {
        BackendType::Wry               => Ok(Box::new(WryBackend::new())),      // real
        BackendType::WebView2          => Ok(Box::new(WryBackend::new())),      // alias, Windows only
        BackendType::WKWebView         => Err(WebViewError::Internal("not yet implemented")),  // macOS
        BackendType::WebKitGTK         => Err(WebViewError::Internal("not yet implemented")),  // Linux
    }
}
```

`BackendRegistry` already provides the replacement — priority ordering, lazy construction,
`AURORAVIEW_BACKEND` override, a failed override that degrades to priority order with a
warning instead of an error, and a probe that returns `CapabilitySupport` rather than
throwing. #471 ships `NativeWebviewBackend` (priority 100) and `ChromiumBackend`
(priority 50).

**Target state:**

- `BackendFactory::create` becomes a `BackendRegistry` lookup. `BackendType` is preserved as
  a **compatibility alias** over registry lookups so the public Rust API does not churn.
- `WryBackend` (Layer 1, `traits.rs`) becomes the `RenderBackend` implementation behind
  `NativeWebviewBackend`, and calls `NativeWebviewBackend::set_linked(true)` — which is what
  finally makes `default_backend_registry().select()` return `Some(..)`.
- `WKWebView` / `WebKitGTK` stop returning `Err(Internal("not yet implemented"))` and start
  returning a structured `BackendError::unsupported(..)` / `CapabilitySupport::Unsupported`
  carrying `how_to_enable`, per the contract's "probing never fails" rule.

**Exit test:** `AURORAVIEW_BACKEND=<unknown>` fails on both the Rust and Python paths with an
error that lists the registered backends — replacing today's split behaviour where an
unimplemented backend errors from `BackendFactory` but silently succeeds through
`NativeBackend`.

### 2.4 Cargo feature naming

Existing precedent in the root `Cargo.toml` is mixed (`feature-tabs`, `features-core`,
`win-webview2`, `runtime-dcc`, `wry-builder`). We add one consistent family and do not
rename anything existing:

| Feature | Effect | Default |
| --- | --- | --- |
| `backend-wry` | `dep:auroraview-wry` (moved out of `wry_impl.rs`); wry 0.54 / tao 0.34 | **yes** |
| `backend-cef` | `dep:auroraview-cef` | no |
| `backend-chromium` | reserved; maps to `BackendFamily::Chromium` in #471 | no |

Rules:

1. `backend-wry` is in `default`, so `cargo build` and the published wheel are byte-for-byte
   equivalent to today.
2. Multiple backends may be compiled in; runtime selection is via `AURORAVIEW_BACKEND`.
   Building with **zero** backends is a compile error (add a `compile_error!` guard).
3. `win-webview2` stays as-is; it configures the WebView2 runtime inside the wry backend,
   it is not a backend of its own. This resolves the current `BackendType::WebView2`
   alias confusion: `webview2` remains a valid `AURORAVIEW_BACKEND` string that selects
   the wry backend on Windows, exactly as it does today.
4. `backend-chromium` is the feature name for what #471 calls
   `BackendFamily::Chromium` / `ChromiumBackend`. One engine family, one feature name,
   one registry entry.

New crate layout under `crates/`:

```text
crates/auroraview-wry/        # today's backend/wry_impl.rs, promoted, pub
crates/auroraview-cef/        # placeholder: RenderBackend impl only, no CEF code yet
```

### 2.5 The Chromium integration point, and why it is harder than wry

#471 models the second backend as `BackendFamily::Chromium` rather than naming CEF
specifically. That is the right call: the seam must not be engine-specific. CEF remains the
right *first* Chromium-family backend to design against because it is the hardest, and it
exposes which parts of our seam are wry-shaped by accident. Three constraints must be
handled by the seam, not worked around per-backend:

1. **Multi-process.** CEF spawns a separate subprocess and needs a helper executable on
   disk. `SurfaceSpec` needs an app-support field (helper path, cache dir) that wry simply
   ignores. `Features` must therefore grow a `needs_subprocess_helper` bit — additive, so it
   is a minor contract bump.
2. **Window creation is asynchronous.** With wry, `create_surface` returns a live view. With
   CEF the browser is created on the UI thread and reports readiness later. `RenderSurface`
   therefore needs a readiness signal, and `create_surface` must be allowed to return a
   surface whose `navigate` is not yet valid. Core already queues operations through
   `MessageQueue`, so this is absorbable — but it must be designed in now, not retrofitted.
3. **Message pump.** CEF wants `CefDoMessageLoopWork` on a timer, which conflicts with
   Qt/DCC hosts owning the loop. This is the `skip_message_pump` / `process_ipc_only` split,
   which already exists for wry — confirming that split is the right abstraction. CEF
   additionally needs a scheduled-pump-work callback.

Net: `RenderSurface` ships with its current nine methods and gains a readiness signal and a
pump-scheduling hook when the Chromium backend lands. Both need wry-compatible defaults, so
the wry path is unaffected.

### 2.6 What is explicitly NOT breaking

| Surface | Guarantee |
| --- | --- |
| `auroraview.BackendType` | Same enum, same four members, still exported from `auroraview` and `auroraview.core`. New members are **added**, never removed. |
| `get_backend_type()` | Unchanged default (`WRY`). |
| `AURORAVIEW_BACKEND` | Same name, same accepted strings. New strings `cef` / `chromium` accepted; unknown strings still raise `ValueError` as today. |
| `create_webview(...)` / `WebView(...)` kwargs | No new required arguments. `parent` accepts the same int handle as today. |
| `eval_js` / `load_url` / `load_html` / `emit` | Identical signatures and semantics. |
| `window.auroraview.*` JS protocol | Unchanged. Backend choice is invisible to page code. |
| Wheel contents | A default build ships exactly one backend (wry), so the wheel does not grow. |

The only behavioural change: requesting a backend that is not compiled in currently
returns `Err(Internal("not yet implemented"))` from `BackendFactory` but silently works
through `NativeBackend`. After the seam lands it fails consistently in both paths, with
an error listing the registered backends. This is a bug fix, not a break.

### 2.7 Sequencing

| Phase | Deliverable | Exit test |
| --- | --- | --- |
| P0 | §2.1: remove the three wry/tao signatures from `PyBindingsBackend`. Decide §2.2 (NativeHandle option A or B) and record the decision here. | `cargo build` + full wheel build produce no diff in behaviour; `AURORAVIEW_BACKEND` still honoured; grep guard passes. |
| P1 | §2.3: `BackendFactory` delegates to `BackendRegistry`; `WryBackend` becomes the `RenderBackend` behind `NativeWebviewBackend` and announces `set_linked(true)`; `backend-wry` feature lands in `default`; `wry`/`tao` become optional in the root crate. | `cargo build --no-default-features --features backend-wry` works; `default_backend_registry().select()` returns `Some(native)`; building with no backend fails with a clear error. |
| P2 | `crates/auroraview-cef` placeholder implementing `RenderBackend` + `RenderSurface` with structured `Unsupported` bodies behind `backend-cef`. | CI compiles the crate and asserts `probe(..)` reports the subprocess-helper requirement with a `how_to_enable`. |
| P3 | Real Chromium-family implementation. | Gallery app runs on `AURORAVIEW_BACKEND=chromium` on Windows. |

P0/P1 are pure refactors with no user-visible change and can land in 0.6.x.
P2/P3 are additive and can land in 0.7.

---

## 3. Design — Part 2: host adapter package contract

### 3.0 The contract already exists — #471 shipped it

The original draft proposed a Python `auroraview.hosts` entry-point group. **That proposal is
withdrawn.** It has zero occurrences in the repository, and #471 landed a better mechanism
that covers the same ground in both languages.

Rust (`crates/auroraview-contract/src/host.rs`), Python (`python/auroraview/adapter/base.py`):

```rust
pub trait HostAdapter: Send + Sync {
    // identity
    fn id(&self) -> &'static str;              // "maya", "unreal"
    fn display_name(&self) -> &'static str;
    fn ui_framework(&self) -> UiFramework;      // Qt | Slate | Win32 | Cocoa | Gtk | Wpf | Html | Unknown
    fn thread_model(&self) -> ThreadModel;      // HostUiThread | GameThread | StaApartment | Any
    fn embed_mode(&self) -> EmbedMode;          // NativeChild | OutOfProcess | Floating

    // discovery -- cheap, must not panic/raise, no module-scope host imports
    fn detect(&self) -> bool;
    fn version(&self) -> Option<String>;
    fn parent_handle(&self) -> Option<u64>;

    // the only required dispatch primitive
    fn run_deferred(&self, job: HostJob) -> HostResult<()>;

    // deliberately NOT required -- see 3.2
    fn try_run_sync(&self, job: HostJob) -> HostResult<()> { /* refuses */ }

    fn probe(&self, feature: Features) -> CapabilitySupport;
    fn info(&self) -> HostInfo;
}

pub struct HostRegistry { /* priority-ordered, lazy */ }
impl HostRegistry {
    pub fn register<A: HostAdapter + Default + 'static>(&mut self, priority: i32);
    pub fn detect_with(&self, env_override: Option<&str>) -> Option<Selection<Arc<dyn HostAdapter>>>;
    pub fn detect(&self) -> Option<Selection<Arc<dyn HostAdapter>>>;  // honours AURORAVIEW_HOST
    pub fn list(&self) -> Vec<(i32, String, bool)>;
}
```

Python registration, in-tree or from a separate distribution:

```python
register_host_adapter(GodotHostAdapter, priority=140)                      # in-tree
register_host_adapter("auroraview_godot.adapter:GodotHostAdapter", 140)    # separate dist
```

The string form is resolved lazily, so `auroraview_godot` is imported only when discovery
actually probes it — the same mechanism the dispatcher already uses.

Three behaviours the original draft did not specify, all now settled by #471:

- **Capability probing never fails.** Missing features are *data*. `probe()` returns
  `CapabilitySupport::{Supported, Unsupported { reason, how_to_enable }, Unknown { reason }}`.
  `Unsupported` always carries `how_to_enable`; `Unknown` is how an implementation says
  "runtime dependent, verify at runtime" instead of guessing. `require()` is the single
  fallible conversion, used only by callers that cannot degrade gracefully.
- **A broken adapter must not break discovery.** A candidate that panics or raises while
  probed is skipped with a warning; Python catches `Exception`, Rust uses
  `catch_unwind(AssertUnwindSafe(..))`. Discovery is shared infrastructure.
- **A failed `AURORAVIEW_HOST` override degrades to priority order with a warning**, never an
  error.

### 3.1 The split rule

One sentence, testable in review:

> **Anything that imports a host module (`maya`, `unreal`, `hou`, `nuke`, `bpy`, `pymxs`,
> `UnityEditor`) leaves core. Everything host-agnostic, and everything shared by two or
> more dispatchers, stays.**

This rule is not stylistic — it is what preserves the project's "no mandatory third-party
Python dependency, one `.pyd`" guarantee, which is the reason DCC hosts accept AuroraView
at all.

### 3.2 Key decision: blocking sync dispatch is NOT part of the contract

`try_run_sync` has a default implementation that **refuses**. Blocking the host thread is the
concrete failure mode behind two real constraints:

- **PowerPoint / Office (COM STA)**: blocking the apartment's message pump makes the host
  report "not responding".
- **Unreal (GameThread)**: blocking stalls the editor.

`ThreadModel::blocking_dispatch_is_safe()` encodes this, and the refusal message differs
accordingly: an adapter that simply has not implemented sync gets "implement it or use
`run_deferred`"; an STA/GameThread host gets "your thread model forbids it". Only
`run_deferred` is required, which is safe everywhere.

**Note for the original draft's `lifecycle_hooks()`:** #471 does not define a lifecycle-hook
contract. The closest landed feature is `ThreadModel` plus the deferred/async dispatch
split, which removes most of the *reason* the draft wanted hooks (blocking the host during
PIE start/stop or scene open). Lifecycle hooks remain an open item — see §6.

### 3.3 Reuse the dispatcher, do not fork it

The built-in adapters are ~15 lines of metadata each and delegate `run_deferred` to the
matching dispatcher backend (`python/auroraview/adapter/hosts.py`). The dispatcher keeps
owning threading; the adapter adds identity, discovery and embedding. **Zero dispatch logic
is duplicated**, and `DispatcherPriority` (MAYA 200 → FALLBACK 0) is mirrored as
`AdapterPriority` so both registries read identically.

#471 ships `MayaHostAdapter`, `HoudiniHostAdapter`, `NukeHostAdapter`, `MaxHostAdapter`,
`BlenderHostAdapter`, `UnrealHostAdapter`, `PowerPointHostAdapter` and
`StandaloneHostAdapter`.

### 3.4 What moves, what stays

**Verified status: nothing has moved.** #471 states "no repository is created and no code is
migrated", and that is accurate. Every row below is therefore an *open item*, not a record
of work done.

| Item | Today | Decision | Status |
| --- | --- | --- | --- |
| `python/auroraview/utils/thread_dispatcher/base.py` | core | **Stays** | as decided — `ThreadDispatcherBackend` ABC is the contract |
| `.../backends/fallback.py`, `qt.py` | core | **Stays** | as decided — host-agnostic; Qt is not one DCC |
| `.../backends/{maya,blender,houdini,max,nuke,unreal}.py` | core | **Moves out** to the matching package | **not started** — all six still in `python/auroraview/utils/thread_dispatcher/backends/` |
| `.../registry.py` | core | **Stays** | as decided — the discovery point, now mirrored by `HostRegistry` |
| `.../wrapper.py` | core | **Stays** | as decided |
| `python/auroraview/adapter/` | new in #471 | **Stays** | landed; the host contract's Python half |
| `crates/auroraview-ue` (568 L: `GameThreadId`, `UeGameThreadExecutor`) | monorepo | **Moves out** to `auroraview-unreal` | **not started** — still in `crates/`; depends on no wry/tao, so already portable |
| `python/auroraview/integration/qt/` + `QtWebView` | core | **Stays** | as decided — Qt crosses Maya/Houdini/Nuke/3ds Max |
| `AuroraView` (HWND path) | core | **Stays** | as decided |
| `detect_host_dcc()` (#460, `python/auroraview/dcc_mcp/host_detect.py:53`) | core | **Stays**, delegates when no adapter claims the process | **not started** — env-var probe is still the primary path, not the fallback |
| `docs/dcc/*.md` | core | Move host-specific pages out with their packages; keep `docs/dcc/index.md` as the pointer | **not started** — all 8 pages including `photoshop.md` and `substance-painter.md` remain |

Note the asymmetry this reveals: **unreal is the only host with crate-level code today**
(`crates/auroraview-ue`), yet it is also the host whose Rust code is *most* separable —
it has no wry dependency. Maya, by contrast, has only a 45-line Python dispatcher. So the
"migration" is uneven by nature: unreal moves a Rust crate plus a dispatcher, maya moves
one dispatcher and needs new parent-window/lifecycle code, unity moves nothing and needs
everything.

### 3.5 Package names and layout

Distribution name uses a hyphen, import name uses an underscore (PyPI normalises both):

| PyPI dist | Import | Repo (proposed) | Host module |
| --- | --- | --- | --- |
| `auroraview-unreal` | `auroraview_unreal` | `try-auroraview/auroraview-unreal` | `unreal` |
| `auroraview-maya` | `auroraview_maya` | `try-auroraview/auroraview-maya` | `maya`, `maya.utils` |
| `auroraview-unity` | `auroraview_unity` | `try-auroraview/auroraview-unity` | `UnityEditor` (C#) |

Canonical layout — the Rust `crates/` directory is present only where a host needs
native code, which is why it is optional in this template:

```text
auroraview-<host>/
├── crates/auroraview-<host>/     # OPTIONAL. Native code (today: only unreal)
│   └── src/lib.rs
├── python/auroraview_<host>/
│   ├── __init__.py               # exports: adapter (see §3.0), and a host WebView subclass
│   ├── adapter.py                # HostAdapter impl (Rust: HostAdapter impl crate)
│   ├── dispatcher.py             # ThreadDispatcherBackend impl
│   ├── host.py                   # parent window discovery
│   └── lifecycle.py              # host lifecycle hooks (PIE, scene open, shutdown)
├── skills/auroraview-<host>/     # SKILL.md + tools.yaml + scripts/
├── tests/
│   ├── unit/
│   └── integration/              # requires a live host; skipped in normal CI
└── pyproject.toml
```

Each package depends on `auroraview-contract` **via `auroraview_core::contract`** on the Rust
side, and on the public `auroraview.adapter` surface on the Python side.

### 3.6 Per-host notes

**Unreal** — smallest delta, highest value. The dispatcher already exists
(`unreal.register_slate_post_tick_callback`, 30 s sync timeout, `is_game_thread()`
vs `is_in_game_thread()` compatibility shim). `crates/auroraview-ue` already provides
`GameThreadId` / `UeGameThreadExecutor` with no wry dependency. `UnrealHostAdapter` exists
in `python/auroraview/adapter/hosts.py`. Remaining work is `host.py` (Slate parent handle)
and `lifecycle.py` (PIE begin/end, GC pinning). `ThreadModel::GameThread` already refuses
blocking dispatch for this host.

**Maya** — Qt-first. Dispatcher exists (`maya.utils.executeDeferred` /
`executeInMainThreadWithResult`). Parent handle comes from
`maya.OpenMayaUI.MQtUtil.mainWindow()`. `MayaHostAdapter` exists. The real work is
`lifecycle.py`: a Maya panel must survive scene open/close and workspace switching, which is
where most Maya UI bugs live.

**PowerPoint** — new since the original draft, and the reason the contract distinguishes
`ThreadModel::StaApartment`. `PowerPointHostAdapter` exists in #471. It is a useful
existence proof that `HostAdapter` generalises past DCC applications.

**Unity — a correction to the plan.** Unity ships no Python interpreter, so
`auroraview-unity` **cannot be an ordinary pip package**. It has to be a UPM package
(`Packages/...` with `package.json`) exposing a C# API, with the Python side, if any,
arriving through the Unity Python integration rather than the reverse. Its dispatcher is
`EditorApplication.delayCall`, not a thread-dispatcher backend.

This is a different build, test, and release pipeline from the other two — which is an
independent argument for the proposed ordering: **ship the contract for all three, but
implement unreal and maya first, and treat unity as a separate pipeline decision.** Note
that `EmbedMode::OutOfProcess` is the contract's answer for hosts with no in-process
embedding path, which covers Unity.

### 3.7 Version coupling

- **Python:** `auroraview-unreal` declares `auroraview>=0.6,<0.7`. Upper bound is
  mandatory — the contract is not yet stable. Publish a compatibility table in each
  adapter README mapping adapter version to core version range.
- **Rust:** in-monorepo, `crates/auroraview-ue` uses `version.workspace = true`. Once split,
  it pins a published `auroraview-contract`. During the transition, a path dependency plus a
  CI job that builds each adapter repo against core `main` is the pragmatic choice;
  publishing `auroraview-core` to crates.io is the end state.
- **The contract is versioned independently at `1.0.0`** and is additive-only: a new
  `#[non_exhaustive]` enum variant or a new `Features` bit is a minor bump; removing or
  renaming anything is a major bump coordinated across every host repository. This is why
  the §2.2 `NativeHandle` decision should be made before S2.
- **Contract surface is deliberately narrow.** Adapters may depend on exactly two things:
  (a) the Python `auroraview` public API, and (b) the `auroraview.adapter` /
  `auroraview_core::contract` protocol. Everything else — including
  `crates/auroraview-core` internals — is private, so core can refactor freely between
  adapter releases.
- **Contract test:** ship `auroraview-host-contract`, a pytest plugin each adapter repo runs
  in CI. It asserts the contract methods exist, `run_deferred` dispatches onto the host
  thread, `detect()` is side-effect free and cannot raise, `probe()` returns
  `CapabilitySupport` for every `Features` flag, and `parent_handle()` returns `None` or a
  positive int. This is what makes "implements the contract" a CI fact rather than a README
  claim.

---

## 4. Design — Part 3: agent-first gap list

### 4.1 What already exists

| Asset | Current capability |
| --- | --- |
| `crates/auroraview-ai-agent` | `ActionRegistry` with 6 built-in browser actions (Navigate, Search, Click, Type, Screenshot, Scroll); `protocol/{a2ui,agui}.rs`; providers; session; ui |
| `crates/auroraview-mcp` | MCP server, `cdp/`, `registry.rs`, and `CdpAuroraViewAdapter` implementing `dcc_mcp_protocols::adapters::DccAdapter` over CDP |
| `packages/auroraview-ai` | `DCCTool` / `DCCToolCategory` decorators, agent config, protocol, tools |
| `packages/auroraview-sdk` | TS bridge (`core/{bridge,events,types}.ts`), `inject/`, React/Vue adapters, `AgentSidebar.tsx`, extensions |
| `crates/auroraview-testing` | CDP-based testing, `a11y/`, `snapshot.rs`, `inspector.rs`, Python bindings |
| `crates/auroraview-cli skills` | `auroraview skills` subcommand; **one** skill shipped: `qt-to-auroraview-migration` |
| PR #460 | `python/auroraview/dcc_mcp/` — `AuroraViewAdapter`, `detect_host_dcc`, `AuroraViewQtHost`, `start_server`, `adapter_registry`, plus the `auroraview-webview` skill package exposing `eval_js` / `screenshot` / `load_url` / `load_html` |

The gap is not capability, it is **coherence and discoverability**. Ranked:

### 4.2 G1 — P0: two competing MCP adapter contracts exist on `main` right now

> **Priority corrected to P0 and reclassified from "future gap" to "current defect".**
> The original draft framed this as a design question pending PR #460. #460 merged on
> 2026-09-19. **Both adapter contracts are live on `main` today**, so this is a defect in the
> shipped product, not a gap to be designed.

Two implementations of "AuroraView as a DCC-MCP adapter" coexist:

- Rust `CdpAuroraViewAdapter` in `crates/auroraview-mcp/src/adapter/mod.rs`, implementing
  `DccAdapter` (and `DccConnection` / `DccSnapshot`).
- Python `AuroraViewAdapter` in `python/auroraview/dcc_mcp/adapter.py`, structurally
  compatible with `dcc_mcp_core.WebViewAdapter`.

PR #460's own rationale states it chose `WebViewAdapter` "instead of the Rust `DccAdapter`
trait, which the CLI does not consume." Both are correct about their own layer, and an
agent sees two different tool sets for one product.

**Resolution (unchanged, now urgent):** one contract per consumer. `WebViewAdapter`
(PR #460) is the control-plane surface the CLI consumes and becomes the canonical
agent-facing adapter. `CdpAuroraViewAdapter` is repositioned as the in-process CDP transport
that backs it, not as a parallel adapter. Both must expose the **same tool names** for the
same operations, enforced by a shared fixture.

**Exit test:** a fixture asserts that `AuroraViewAdapter` and `CdpAuroraViewAdapter` expose
identical tool names for identical operations, and CI fails when they diverge.

### 4.3 G2 — Agents write code where they should emit data

Today an agent building AuroraView UI writes HTML/CSS/JS by hand. That is slow, hard to
validate, and produces inconsistent UI. The highest-leverage agent-first change is a
**declarative UI schema** — a JSON component spec the agent emits, which a renderer turns
into DOM. Agents are reliable at structured output and unreliable at long code generation.

*(Untouched by #463 and #471 — unchanged from the original draft.)*

### 4.4 G3 — No typed tool discovery from Python

`@webview.command` / `bind_call` bindings have no introspectable schema. An agent must read
source to learn what a panel exposes. Add `webview.tool_schema() -> dict` returning JSON
Schema, derived from the existing decorator metadata — the same metadata RFC 0018 already
extends for `cli=True` (see `docs/rfcs/0018-packed-cli-mode.md`).

*(Untouched by #463 and #471 — unchanged from the original draft.)*

### 4.5 G4 — No headless validation loop

An agent cannot check whether the UI it just produced is correct without opening a window.
`crates/auroraview-testing` (CDP + snapshot) and `python/auroraview/testing/inspector.py`
already provide the primitives. Close the loop with a supported
`auroraview.testing.render_offscreen()` + DOM assertion path, so an agent can iterate
without a display.

*(Untouched by #463 and #471 — unchanged from the original draft.)*

### 4.6 G5 — Screenshot round-trip is CSP-fragile

`window.auroraview.screenshot` depends on html2canvas and, as PR #460 notes, breaks under a
strict CSP. Vision feedback is the main way an agent verifies UI, so this needs a native
path — `Page.captureScreenshot` through the CDP client that `crates/auroraview-mcp/src/cdp`
already owns, exposed as a first-class tool.

*(Untouched by #463 and #471 — unchanged from the original draft.)*

### 4.7 G6 — One skill shipped, no authoring kit

`crates/auroraview-cli/skills/` contains exactly one skill (`qt-to-auroraview-migration`).
If "agent-first" means agents build skills for AuroraView, they need a scaffold and a
validator: `auroraview skills new <name>` generating the `SKILL.md` + `tools.yaml` +
`scripts/` shape PR #460 established, plus `auroraview skills validate`. The
`auroraview-webview` skill in PR #460 becomes the worked example.

*(Untouched by #463 and #471 — unchanged from the original draft.)*

### 4.8 G7 — Agents poll where they should subscribe

Events reach agents only by polling. An event feed (SSE or WS) over the existing
`window.auroraview.trigger()` stream, plus a subscribe tool, would let an agent react to UI
state instead of sampling it. #463's parent/child IPC bridge is adjacent infrastructure but
does not close this gap on its own.

*(Unchanged from the original draft; #463 provides plumbing, not the agent-facing feed.)*

---

## 5. Alignment with in-flight and merged work

| Work | Status | Relationship |
| --- | --- | --- |
| [PR #471](https://github.com/try-auroraview/auroraview/pull/471) — host-adapter and render-backend contracts | **merged 2026-09-22** | **Supersedes this RFC's §1/§2 contract layer and §3's entry-point proposal.** Ships `auroraview-contract` (`RenderBackend`, `RenderSurface`, `BackendRegistry`, `HostAdapter`, `HostRegistry`, `CapabilitySupport`), the Python mirror in `python/auroraview/adapter/`, and the capability-parity CI guard. §2 of this RFC is its deferred follow-up list. Design record: [`docs/design/adapter-contract.md`](../design/adapter-contract.md). |
| [PR #463](https://github.com/try-auroraview/auroraview/pull/463) — parent/child IPC bridge and `--parent-hwnd` | **merged 2026-09-22** | Supplies the parent-handle plumbing that `SurfaceSpec::parent_handle` and `HostAdapter::parent_handle()` **will** consume once surface creation is rewired (`--parent-hwnd` / `AURORAVIEW_PARENT_HWND`, plus `AURORAVIEW_PARENT_ID` / `AURORAVIEW_PARENT_PORT` for child mode; see `crates/auroraview-core/src/parent_ipc/`). **Note the type mismatch:** #463 carries the handle as `Option<isize>` (`ChildInfo::parent_hwnd`, `parse_hwnd()`), while the contract's `SurfaceSpec::parent_handle` / `HostAdapter::parent_handle()` are `Option<u64>`, so wiring them needs one explicit, deliberate conversion — see §2.2. Resolves the "PIP-3214 path A groundwork" row from the original draft: the plumbing exists, so §2.2's handle type is the remaining question. |
| [PR #460](https://github.com/try-auroraview/auroraview/pull/460) — DCC-MCP WebView adapter | **merged 2026-09-19** | Supplies the canonical Python adapter and the `auroraview-webview` skill. §3.4 keeps `detect_host_dcc()` as the fallback and reuses the skill layout as the template for G6. §4.2 resolves its contract conflict with the Rust `CdpAuroraViewAdapter`. **Merged first, as the original draft required.** |
| RFC 0007 | — | Splits WebView/Browser into feature crates. This RFC is orthogonal — 0007 composes *features above* the WebView, this one abstracts *the renderer below* it. |
| RFC 0011 (unified IPC) | — | `RenderSurface`'s event path is the backend-facing edge of the same IPC contract; it must stay message-compatible. #463's `parent_ipc/` module is the concrete realization for the parent/child case. |
| RFC 0018 (packed CLI mode) | — | Its `@webview.command(..., cli=True)` metadata is the same metadata G3 wants as JSON Schema. One extension serves both. |

---

## 6. Open questions

1. **`NativeHandle` — option A or B (§2.2)?** Keep `Option<u64>` at the contract boundary
   and add `NativeHandle` below it (no breaking change, two handle types), or widen the
   contract to `NativeHandle` everywhere (contract `2.0`, coordinated major bump)?
   **Recommendation: decide before S2 creates any host repository** — option B is cheap now
   and expensive later.
2. Does `RenderSurface` need to be object-safe *and* `Send`? `WryWebView` is `!Send` on
   Windows. Today `NativeBackend` works around this with `Arc<Mutex<WryWebView>>` plus
   UI-thread marshalling. #471 requires `Send + Sync` on the trait; keeping that pattern
   inside each backend implementation needs a spike to confirm for CEF.
3. Should `auroraview-core` be published to crates.io before or after the adapter split?
4. For Unity: is a UPM-only package acceptable, or is a pip-installable Python bridge
   required for parity? `EmbedMode::OutOfProcess` covers Unity's lack of in-process
   embedding, but the packaging question is open.
5. **Lifecycle hooks.** The original draft proposed `HostAdapter::lifecycle_hooks()`
   (`startup` / `before_show` / `shutdown`). #471 does not define this; `ThreadModel` plus
   the deferred-dispatch split covers part of the motivation. Is a lifecycle contract still
   needed for Maya scene-open teardown and Unreal PIE begin/end?
6. **`DccType` / `BackendType` deprecation.** [`docs/design/adapter-contract.md`](../design/adapter-contract.md) §7
   describes both as "kept as deprecated shims". Verified: `BackendType` in
   `crates/auroraview-core/src/backend/factory.rs` carries **no `#[deprecated]` attribute**
   — it is `#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]` only. Removing or
   formally deprecating the shims is still open work, not done work.

---

## 7. Success criteria

- [ ] No symbol from `wry` or `tao` appears in any `pub` signature in `src/webview/backend/`,
      enforced by a CI grep guard.
- [ ] `default_backend_registry().select()` returns `Some(native)` in a normal build — i.e.
      `WryBackend` is registered as the `RenderBackend` behind `NativeWebviewBackend` and has
      announced `set_linked(true)`.
- [ ] `AURORAVIEW_BACKEND=<unknown>` fails with an error listing the registered backends, on
      both the Rust and Python paths.
- [ ] `cargo build --no-default-features --features backend-cef` (or `backend-chromium`)
      compiles with no wry in the tree.
- [ ] `WKWebView` / `WebKitGTK` return a structured `Unsupported` carrying `how_to_enable`,
      not `Err(Internal("not yet implemented"))`.
- [ ] The §2.2 `NativeHandle` decision is recorded in §6 and reflected in the contract crate
      at the version level the decision implies.
- [ ] A host package can add main-thread dispatch and parent-window discovery with zero
      changes to `auroraview` core, proven by a fixture adapter registered through
      `register_host_adapter()`.
- [ ] The `auroraview-host-contract` pytest plugin passes for unreal and maya.
- [ ] `AuroraViewAdapter` (PR #460) and `CdpAuroraViewAdapter` expose identical tool names
      for identical operations, enforced by a shared CI fixture.
- [ ] `docs/rfcs/0019-*.md` and [`docs/design/adapter-contract.md`](../design/adapter-contract.md)
      cross-reference each other and contain no contradictory statement about the backend or
      host contract.
