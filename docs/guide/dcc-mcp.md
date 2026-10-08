# Shared UI and agent tools

An AuroraView panel and an agent can call the same explicitly registered host
capability. The independent `auroraview-dcc-mcp` Python package owns that contract;
it does not own rendering, a DCC scene or a second MCP server.

## Package boundaries

| Package | Responsibility |
| --- | --- |
| `auroraview` | Native WebView, page communication and Python integration |
| `@auroraview/sdk` | Frontend calls and event subscriptions |
| `auroraview-dcc-mcp` | Explicit tools, schemas, shared callables and registration cleanup |
| `dcc-mcp-core` | MCP/REST, Skills, discovery and the host execution bridge |
| Host adapter | Scene API, host main-thread pump, native region and application lifecycle |

The contract package supports Python 3.7+ and Core `>=0.20.25,<0.21`. It imports no
AuroraView native extension, Qt, Blender or Unreal module. The rendering backend
and the native plugin keep their own supported-version requirements.

Schemas are objects using JSON Schema Draft 7, 2019-09 or 2020-12; an omitted
`$schema` selects Draft 7. Older or unknown dialects and remote schema
references are refused. Local references and literal data containing `$ref`
remain supported.

## Declare capabilities

```python
from auroraview_dcc_mcp import Tool, ToolSet

# host is supplied by the application adapter. Its scene methods execute on
# the host thread; scene_snapshot reads the application's actual state.
tools = ToolSet(
    "studio-scene",
    [Tool(
        "scene.rename",
        "Rename an object and read the resulting scene state",
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string", "minLength": 1},
            },
            "required": ["object_id", "name"],
            "additionalProperties": False,
        },
        handler=host.rename,
        readback=host.scene_snapshot,
        output_schema={
            "type": "object",
            "properties": {"result": {}, "scene": {"type": "object"}},
            "required": ["result", "scene"],
        },
        destructive=True,
    )],
    dcc="maya",
)

ui = tools.bind(webview)
agent = tools.attach(existing_host_server)
```

`existing_host_server` is the host's running `DccServerBase`. Attachment uses its
public skill loader and existing execution bridge. It neither starts another
service nor replaces the host dispatcher. A duplicate skill name is refused.
Tool names and schemas are declared; arbitrary buttons are not discovered or
converted into tools.

Set `dcc` to the adapter's host identity so Core's host-filtered discovery can
find the skill. UI and session calls use `scene.rename`. Core's MCP names allow
no dots, so this binding registers `studio-scene__scene_rename` and exposes the
mapping in `agent.method_names`. Names that collide after mapping are refused.

MCP wraps the business arguments in a `params` envelope:

```json
{
  "name": "studio-scene__scene_rename",
  "arguments": {"params": {"object_id": "cube-1", "name": "Hero"}}
}
```

Core strips top-level private keys before calling skill scripts. The envelope
keeps business keys intact so the shared validator sees the same payload as
the UI. The registered MCP input schema describes this envelope explicitly.

The page uses the established communication API:

```javascript
const response = await window.auroraview.call('scene.rename', {
  object_id: selectedId,
  name: 'Hero'
})
renderScene(response.scene)
```

The business handler and optional readback run in the same scheduled host
callback. With readback configured, the result is `{result, scene}`. An
`output_schema` is required for readback and describes that complete response. Both routes
apply the same JSON Schema validation and refuse calls on the wrong thread.

## Host scheduling

The host configures the WebView's call dispatcher and Core's execution bridge to
reach its own main thread. Do not touch `bpy`, Unreal objects or Qt widgets from
an HTTP, Rust or renderer worker. Registration does not create a new host pump.

For a new Qt-hosted panel service, the existing framework imports remain valid:

```python
from auroraview.dcc_mcp import AuroraViewAdapter, AuroraViewQtHost, start_server

adapter = AuroraViewAdapter(webview, host_dcc="maya")
host_loop = AuroraViewQtHost(dispatcher)
host_loop.start()  # requires the Qt application thread
server = start_server(adapter, dispatcher=dispatcher)
server.start()
```

That caller owns this newly created server and host loop. An existing DCC-MCP
host should instead use `tools.attach(existing_host_server)` and keep its
current scheduler. The legacy `start_server` inline mode remains for standalone
callers; it is not proof of safe embedded host execution.
`AuroraViewQtHost.stop()` shuts down its dispatcher, so create that loop only
when the caller owns the dispatcher.

## Ownership and cleanup

`ToolSet` owns the business callbacks. Each UI or MCP binding owns only its
registration. Closing one binding invalidates that route; other consumers and
the borrowed service continue. Closing the owning `ToolSet` invalidates all its
routes and releases its callbacks. Already executing host work may finish;
new calls are refused after invalidation.

Generic views need explicit `ui.close()`. Where a view provides the public
`on_closed` hook, its binding subscribes to that hook. A panel that owns the
entire tool set must also close that owner. Cleanup failures are reported and
can be retried; they are not silently reported as complete.

Core's public unload API removes active tools but retains skill catalog
metadata. A closed trampoline refuses invocation even if stale metadata is
loaded again. This package does not claim complete removal from the catalog.

Consumers that borrow the business tool set use a separate session:

```python
session = tools.borrow()
available = session.list_tools()
response = session.call("scene.rename", {"object_id": selected_id, "name": "Hero"})
unsubscribe = session.subscribe("scene.changed", on_scene_changed)
unsubscribe()  # idempotent; detaches only this subscription
session.close()  # releases this panel's subscriptions, leaving tools/server alive
```

For subscriptions, pass the host's existing `subscribe(event, callback)` callable
as `ToolSet(..., subscribe=host.subscribe)`. It must return an unsubscribe
callable. The host owns event delivery and thread scheduling. This package does
not create a second event bus. An owner that is closed or released refuses calls
from borrowed sessions.

Call and subscription operations, including unsubscribe/close when host event
resources exist, must run on the tool owner's thread. A wrong-thread close
revokes the route immediately and reports pending cleanup; retry it on that
thread to detach the host resource.

## Install and migrate

The independent package is built and released separately from the native wheel.
Use the wheel and checksum from its
[preview release](https://github.com/try-auroraview/auroraview/releases/tag/auroraview-dcc-mcp-v0.1.0-preview.1).
The preview is a GitHub release artifact; it is not a claim of PyPI publication.

Existing `auroraview.dcc_mcp.AuroraViewAdapter`, `AuroraViewQtHost` and
`start_server` imports remain supported. Their four panel inspection/navigation
tools are separate from the new explicitly registered scene capabilities.
Install the new contract package in the actual host's Python environment; do
not copy its source or use a developer path as a production dependency.

The [communication guide](./communication) explains RPC and event directions.
See [the package source and tests](https://github.com/try-auroraview/auroraview/tree/main/packages/auroraview-dcc-mcp)
for registration, invalidation and borrowed-service behavior. Package and Core
transport checks do not replace a Blender or Unreal plugin's real native host
acceptance. Each consumer must pin the published artifact and verify scene
readback, Undo where supported, and cleanup in its supported host versions.
