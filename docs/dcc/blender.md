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
before showing a WebView. The session installs a deferred main-thread call
dispatcher; Core retains the JavaScript Promise and RPC protocol.

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
