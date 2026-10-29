# Blender integration

New Blender integrations are maintained in
[auroraview-blender](https://github.com/try-auroraview/auroraview-blender).
The add-on owns Blender panels, operators, main-thread scheduling and host
cleanup. AuroraView Core owns the WebView engine, JavaScript bridge, RPC
messages and generic window lifecycle.

## Choose a tool surface

| Surface | What it displays | Core dependency |
| --- | --- | --- |
| Native Blender sidebar panel | Blender properties, operators and layout controls | None |
| Experimental floating WebView | HTML/CSS/JavaScript in a separate Windows tool window | An explicitly compatible Core build |
| HTML inside a Blender editor region | No implementation is available | Requires a separate rendering/input integration |

Native tool panels participate in Blender's sidebar layout. They do not embed
HTML. A floating OS window does not become a Blender panel by assigning an HWND
parent, and `Panel.draw` does not provide a browser surface. HTML in an editor
region would require an offscreen frame/input contract and Blender GPU
integration; those are not implemented by this add-on.

## Native add-on tools

Use the extension installation and native panel API maintained in the
[Blender repository](https://github.com/try-auroraview/auroraview-blender).
Its extension manifest targets Blender 4.2 and newer. The package contains the
adapter and Blender manifest; it does not bundle Core or a WebView engine.
It is development source, not a published Blender Extensions listing.

Consumers register their tools through the enabled adapter module on Blender's
main thread. Extensions use Blender's repository-specific `bl_ext` namespace;
pass that module to your integration rather than creating a top-level alias.

```python
def register_tools(adapter):
    def draw(layout, context):
        layout.label(text="Selected: %d" % len(context.selected_objects))
        if context.active_object is not None:
            layout.prop(context.active_object, "location")

    adapter.register_panel("EXAMPLE_PT_transform", "Transform", draw)


def unregister_tools(adapter):
    adapter.unregister_panel("EXAMPLE_PT_transform")
```

Keep draw callbacks short and use their current context. Use Blender properties
for editing and operators for actions. Remove consumer panels when their add-on
is disabled; the adapter also tracks its registered panels for cleanup.

## Optional HTML tools

The add-on's
[consumer guide](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/consumer-tools.md)
uses `BlenderSession.open(..., configure=configure)` to bind public Core calls
before showing a WebView. The session installs `set_call_dispatcher` and
`set_event_dispatcher` on one bounded main-thread queue; Core retains the
JavaScript Promise and RPC protocol. Event notifications registered with
`on`/`register_callback` return immediately and ignore callback return values.
Synchronous `closing` veto registrations are refused in this mode. Raw signal
connections are direct and do not acquire host dispatch guarantees.

Close, disconnect and dispatcher replacement invalidate queued notifications,
including `closed`; own cleanup through the add-on/session lifecycle.

This route requires the owner-thread RPC/lifecycle contract tracked in
[Core PR #497](https://github.com/try-auroraview/auroraview/pull/497).
Read the adapter's
[Core compatibility contract](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/core-compatibility.md)
for the required source build. This guide establishes no compatible released
Core version. Installing an arbitrary released wheel is insufficient.

The Windows floating route remains experimental and needs actual WebView
acceptance. Linux/macOS background startup is rejected by this route. The
separate GTK experiment is not enabled by installing the Blender add-on.

## Thread and lifecycle ownership

- Register host classes and timers, start sessions and access `bpy` on Blender's
  main thread. Worker threads may enqueue work; they must not call host APIs
- Never block Blender's main thread waiting for work that needs that thread.
  Keep host callbacks bounded; a JavaScript timeout does not undo host mutations
- Bind host commands before asynchronous WebView startup. Use the add-on's
  `configure` hook instead of registering native callbacks from a foreign thread
- Disable/file-load/reload cleanup must discard stale queued work, remove owned
  host registrations and request closure of owned views. A close request is
  distinct from native completion; poll Core's `wait(0)` without blocking Blender

Blender's
[Python threading guidance](https://docs.blender.org/api/main/info_gotchas_threading.html)
places limits on persistent Python threads. Main-thread dispatch alone does not
certify a long-lived WebView callback thread. Native sidebar tools need no
WebView worker thread.

## Compatibility and verification

Core's existing `BlenderDispatcherBackend`, public imports and automatic host
detection remain available as a legacy compatibility path. They are not the
native panel API, and detection alone does not establish safe native rendering
or cleanup. This documentation migration does not change discovery precedence.

Headless imports and real add-on registration/scheduling checks establish only
the behavior they exercise. Visible HTML rendering, JS/Python RPC, multiple
windows, close/reopen and unload/exit require separate tests against a declared
Blender/OS/Core combination. Consult the adapter's
[validation record](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/validation.md)
for current evidence and remaining gates.

## Verified test matrix (GH-530)

Automated regression runs inside a real, background (headless) Blender process
via `vx just test-blender-host`. The DCC workflow
(`.github/workflows/dcc-integration.yml`) builds an `abi3-py38` wheel and tests
these combinations inside the host's bundled interpreter:

| Blender | Bundled Python | OS | CI runner | Scope |
| --- | --- | --- | --- | --- |
| 3.6.21 | 3.10 | Linux x64 | `ubuntu-latest` | headless import + host checks |
| 5.2.1 | 3.13 | Linux x64 | `ubuntu-latest` | headless import + host checks |

The `cp38-abi3` wheel is forward-compatible with Blender's Python 3.13 and
needs no ABI-specific rebuild. The headless suite
(`tests/python/integration/test_blender_integration.py`) asserts that Core
imports, that `WebView` can be constructed and closed **without showing a
native window**, that a temporary operator registers on the host, and that DCC
auto-detection identifies Blender. `scripts/ci/run_blender_tests.py` fails the
job on any skip and prints the exact Blender, Python, OS and AuroraView
versions into the CI log.

### Local headless validation (Windows x64, 2026-10-28)

A manual run against a legally downloaded official Blender 5.2.1 LTS
(Windows-11-10.0.26100-SP0, bundled Python 3.13.13) confirmed that the
`cp38-abi3` wheel installs, imports and passes the headless host suite in the
Blender process with `collected=4, passed=4, skipped=0` (Core import,
`WebView` construct/close, operator registration, DCC detection). Reproduce by
installing the wheel into an isolated site and running inside Blender:

```powershell
vx just prepare-blender-test-site .\dist\auroraview-...-cp38-abi3-win_amd64.whl .\.blender-test-site 3.13
vx just test-blender-host "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" .\.blender-test-site
```

This is headless import/host evidence — a manual record, not an automated CI
lane — and does not certify any visible-window or bridge behavior.

To keep the 5.2.x baseline while tracking the latest stable release, add a new
matrix entry in `dcc-integration.yml` with the release's download URL and its
bundled Python version; do not replace the 5.2.x row until a newer baseline is
agreed. `prepare-blender-test-site` must use that bundled Python version so the
`abi3` wheel is resolved for the matching interpreter.

### Native acceptance still outstanding (GH-530)

The CI matrix above is **headless import coverage only**. It does not establish
any of the following, which require an owned interactive Blender session on
Windows x64 with a compatible Core build (see the
[owner-thread RPC/lifecycle contract](https://github.com/try-auroraview/auroraview/pull/497))
and recorded reproduction steps:

- Windows x64 interactive acceptance and an automated Windows CI lane — the
  headless import check above was run manually on Windows x64 but is not in
  CI, and no interactive native-window validation has been recorded.
- A visible native WebView window that displays HTML and closes without
  crashing or blocking Blender.
- JavaScript calling a bound Python API and receiving the result, and a
  Python-emitted event reaching JavaScript.
- A bound API call that reads or updates `bpy` on Blender's main thread and
  produces the expected scene result.
- Save/close lifecycle, multiple windows, close/reopen and unload/exit cleanup.
- Interactive validation on macOS and Linux.

Do not advertise support for these flows from documentation or skipped tests;
each needs a passing interactive validation record against a declared
Blender/OS/Core combination.
