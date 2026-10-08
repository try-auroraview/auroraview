# AuroraView Offscreen

An optional, process-isolated HTML renderer for hosts that draw their own native
surfaces. The host receives complete RGBA frames and forwards input; Chromium
runs in a hidden Electron helper and never owns the host event loop.

## Quick checks

Run from the repository root with [vx](https://github.com/loonghao/vx):

```powershell
vx just --justfile packages/auroraview-offscreen/justfile test 3.12
vx just --justfile packages/auroraview-offscreen/justfile wheel 3.12
vx just --justfile packages/auroraview-offscreen/justfile check-wheel 3.12
```

These commands test the transport, owned process cleanup, packaging integrity,
Node protocol/input/pixel contracts, and build a pure Python wheel under `dist/`.
They do not download Electron, start Blender or verify desktop interaction.

## Architecture and ownership

| Layer | Responsibility |
| --- | --- |
| `python/auroraview_offscreen` | Nonblocking child transport, strict framing, generation-scoped surfaces and owned process-tree cleanup. No third-party Python runtime dependencies. |
| `helper/stdio.cjs` | Node-mode broker; waits for the owner's start handshake, then launches Electron over an authenticated private local pipe. |
| `helper/main.cjs` | Hidden CPU offscreen rendering, local CDP input, frame backpressure and the existing AuroraView SDK bridge. |
| Host adapter | Native docking, drawing, coordinates, main-thread timers and host API execution. |
| Existing backend | Tool schemas, tool execution, subscriptions and backend lifecycle. The renderer does not implement another tool server. |

Importing `auroraview_offscreen` starts nothing. Construct `RendererProcess`
explicitly using a verified bundle and call `poll()` from the host's existing
main-thread timer. No Python background thread or nested event loop is needed.
`resolve_bundle()` validates critical launch files against the bundle inventory;
the maintainer acquisition/build tools perform full publisher and archive checks.

The broker launches the same Electron binary with `ELECTRON_RUN_AS_NODE=1` so
Windows stdin remains readable and stdout stays strictly binary. The parent
assigns process-tree ownership and configures its nonblocking pipes before
sending the private `start` command. Only then can Chromium descendants spawn.

Every renderer process gets a private temporary Chromium profile. Its surfaces
share that profile; separate processes do not contend for cache locks or share
cookies and local storage. Graceful exit removes only the broker's owned profile.
The host must continue polling during shutdown; the transport enforces bounded
termination through its owned process tree when graceful exit cannot complete.

Each ordinary `poll()` cleanup attempt and default `terminate()` uses one 250 ms
deadline for inventory, parent exit and descendant exit. If the OS has not
finished, `closed` stays false, new commands are rejected and the host retains
the renderer for the next timer tick. Linux checks the isolated process group
and session plus each member's PID/start time; recycled PIDs cannot satisfy
ownership. Exited zombies hold no transport endpoints and their new parent owns
the final `waitpid`.

Only final teardown may explicitly use `terminate(timeout=3)`; the accepted
timeout range is `(0, 3]` seconds. It does not change the ordinary timer budget.
Failed construction also attempts this bounded final cleanup. If cleanup cannot
complete, the public `auroraview_offscreen.RendererCleanupError` preserves the
original startup failure as `__cause__`, the cleanup error as `.error`, and the
still-owned renderer as `.renderer`. The caller must retain that renderer in its
existing closing-owner collection and continue `poll()` retries, or explicitly
retry `terminate(timeout=...)`. Its tree, pipes and log remain owned until actual
completion; discarding the exception does not establish successful cleanup. No
background reaper or additional host timer is created.

The [Blender adapter](https://github.com/try-auroraview/auroraview-blender) owns
the native dock surface and GPU upload. The optional Core
[`BackendSession`](../../python/auroraview/integration/backend.py) borrows an
existing typed backend port; closing a borrowed session releases its connections
without stopping the external server. See the runnable
[`backend_session.py`](../../examples/backend_session.py) example.

## Build a maintainer runtime bundle

The Python wheel contains only the transport. Electron and helper assets are a
separate optional bundle, built by a maintainer. `runtime-lock.json` pins the
official Electron release, archive size/SHA256 and publisher checksum file.
Acquisition verifies GitHub publisher metadata and `SHASUMS256.txt`, then checks
the downloaded archive. The bundler verifies the extracted runtime, preserves
Electron/Chromium licenses, builds an inventory and verifies every ZIP member.
Checksum verification does not make a code-signing claim.

The supported bundle target is Windows x64. Choose absolute output paths outside
the source tree; these examples use a local `P:` artifact directory:

```powershell
vx just --justfile packages/auroraview-offscreen/justfile sdk-build
vx just --justfile packages/auroraview-offscreen/justfile runtime-acquire P:/artifacts/offscreen/acquired
vx just --justfile packages/auroraview-offscreen/justfile runtime-build P:/artifacts/offscreen/acquired P:/artifacts/offscreen/runtime.zip
vx just --justfile packages/auroraview-offscreen/justfile runtime-verify P:/artifacts/offscreen/runtime.zip
```

The bundle includes `electron/`, `helper/`, both publisher licenses,
`runtime-lock.json`, provenance/checksums and `bundle-manifest.json`.
`event_bridge.js` comes from the SDK build at
`packages/auroraview-sdk/dist/inject/event_bridge.js`; no second bridge source is
maintained here. The SDK also exports the asset as
`@auroraview/sdk/inject/event-bridge`.

For a native renderer check with an already acquired verified runtime:

```powershell
vx just --justfile packages/auroraview-offscreen/justfile native P:/artifacts/offscreen/acquired/electron/electron.exe
```

This checks real CPU paint, committed Unicode, shortcuts, pointer/wheel input,
resize, SDK request/results, multiple surfaces, profile isolation and EOF exit.
It runs hidden helper windows and does not operate Blender UI. Native docking
and installed-host acceptance remain separate checks.

## Protocol and limits

[`helper/protocol.json`](helper/protocol.json) describes protocol version 1.
Commands are UTF-8 newline-delimited JSON; messages use two little-endian uint32
lengths, a UTF-8 JSON header and an optional binary payload. Diagnostics use
stderr. Parent stdin EOF closes the owned renderer.

| Contract | Limit or behavior |
| --- | --- |
| Command / message header / payload | 1 MiB / 64 KiB / 64 MiB. Invalid lengths fail before payload allocation. |
| Surfaces / dimensions | At most 8 live surfaces; each dimension 1–4096 pixels. A host may impose a smaller pixel budget. |
| Queues | At most 128 helper commands, 256 pending SDK calls per surface and 1024 lifetime surface identities. |
| Frames | Complete `rgba8`, straight alpha, top-left origin, `stride = width * 4`; exact payload length. Device scale is 1. |
| Identity | `surface_id` plus increasing `generation`; stale generations cannot address recreated surfaces. |
| Resize | `resize_revision` begins at 0 and increments once per accepted resize, including unchanged dimensions. |
| Backpressure | One in-flight envelope and bounded latest-frame mailboxes. Ordered controls take priority and may displace pending pixels. |
| Input | CSS/frame pixels with a top-left origin. Finite coordinates outside the surface preserve captured pointer releases. |

Windows can enforce a minimum hidden native window size. CDP sets the requested
CSS viewport; the renderer crops only the matching current backing image so
small surfaces retain their exact requested frame dimensions.

Pages use the existing `auroraview.call`, `on`, `send_event` and structured call
result protocol. The SDK is injected before page application scripts. A narrow
sandbox preload exposes bridge messaging only; Node integration is disabled.
There is no arbitrary evaluation RPC, native plugin invocation, remote debugging
port or visible/focused helper window. Local CDP performs input and logical focus
emulation. Front-end calls must be authorized and executed by the supplied host
backend; the renderer is not an authorization boundary for untrusted tools.

## Support boundary and CI

The Python package requires Python 3.10+, but Windows nonblocking subprocess
pipes require Python 3.12+. The supported host path is Windows x64 with Python
3.12+ and an explicitly configured verified runtime. Older Blender interpreters
fail early for offscreen transport. This package does not change native panel
support in the host adapter.

Linux Python 3.12/3.13 transport and cleanup tests cover the portable protocol
layer; no Linux Electron bundle or native dock is supplied. macOS native rendering
is not verified. Text input supports committed Unicode. Native IME composition
and candidate windows, clipboard integration, accessibility and native browser
popups require separate host-specific work and are not claimed by these tests.

The independent [workflow](../../.github/workflows/offscreen.yml) runs Windows and
Linux transport/process-exit/tool tests, Node unit contracts and pure wheel
builds. An explicit backend/bridge lifecycle job includes tests outside Core's
default `testpaths`:

```powershell
vx just --justfile packages/auroraview-offscreen/justfile test-backend 3.12
vx just --justfile packages/auroraview-offscreen/justfile example-backend 3.12
```

CI does not acquire the large Electron runtime or claim real Blender acceptance.
Publisher runtime verification, hidden native renderer proof, native host input
and installed extension acceptance are distinct delivery gates.
