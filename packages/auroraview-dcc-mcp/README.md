# AuroraView DCC-MCP contracts

Declare a host tool once, then bind that callable to an AuroraView panel and
attach it to an existing DCC-MCP service. Registration is explicit: a UI control
does not automatically become an agent tool.

This independent Python package contains contracts and registration lifecycle.
It imports no AuroraView native extension, Qt binding, Blender API or Unreal
module. The host owns scene access, its main-thread dispatcher and its service.
AuroraView owns rendering and page communication. DCC-MCP Core owns MCP, skill
discovery and host execution.

Python 3.7+ is supported. The Core integration targets the public API range
`dcc-mcp-core>=0.20.25,<0.21`; it must be installed for agent attachment. JSON
Schema validation is shared by the UI and agent entry points.
Schemas use Draft 7 (the default), 2019-09 or 2020-12 object declarations with
local references. Older/unknown dialects and remote schema retrieval are refused.

## Install the preview

Download the wheel and `SHA256SUMS` from the
[preview release](https://github.com/try-auroraview/auroraview/releases/tag/auroraview-dcc-mcp-v0.1.0-preview.1),
verify the downloaded bytes against that checksum, then install the wheel with
`vx uv pip install --python <host-python> "<wheel-path>[core]"`. This GitHub
preview is separate from PyPI publication. Pin its artifact and checksum in the
host package manifest.

## Share an explicit capability

```python
from auroraview_dcc_mcp import Tool, ToolSet

tools = ToolSet("studio", [Tool(
    "scene.snapshot",
    "Read the current scene",
    input_schema={"type": "object", "additionalProperties": False},
    handler=host.scene_snapshot,
    output_schema={"type": "object"},
    read_only=True,
    destructive=False,
)], dcc="maya", subscribe=host.subscribe)

ui = tools.bind(webview)
agent = tools.attach(existing_host_server)
session = tools.borrow()
scene = session.call("scene.snapshot")
unsubscribe = session.subscribe("scene.changed", on_scene_changed)
session.close()  # releases this consumer's subscriptions
ui.close()       # invalidates this view's route
agent.close()    # unloads this binding's tools; the borrowed server stays alive
tools.close()    # the owner releases its business callbacks
```

`host`, `webview` and `existing_host_server` are supplied by the application
adapter. Create the owner and run calls on the host thread. Both WebView and
Core must dispatch to that thread; this package refuses a call on another
thread. Event delivery and unsubscribe use that same host thread. Failed host
cleanup remains retryable after the consumer token has been revoked.

For an existing native RPC client, see the
[composition example and ownership contract](docs/native-clients.md).
It borrows the client and dispatcher, requires explicit declarations and native
output schemas, and keeps atomic scene readback in the native handler.

The UI calls `window.auroraview.call('scene.snapshot')`. The MCP binding exposes
`studio__scene_snapshot`: Core rejects dots in MCP tool IDs, so the binding
maps dots to underscores and refuses collisions. `agent.method_names` provides
the declared-method-to-MCP-name map; `agent.tool_names` lists registered IDs.
The explicit `dcc` value also makes the skill visible to host-filtered discovery.
MCP arguments use `{"params": {}}` for this parameterless tool; a mutation uses
`{"params": {"object_id": "cube-1", "name": "Hero"}}`. This declared envelope
preserves business keys that Core would otherwise filter before calling the
script. UI/session callers pass the business object directly.

For mutations, pass `readback=host.scene_snapshot` and an `output_schema` that
requires both `result` and `scene`. The operation and readback run together on
the host thread. The [guide](https://try-auroraview.github.io/auroraview/guide/dcc-mcp)
contains the complete mutation example and migration notes.

## Development

```powershell
vx just install
vx just check
vx just build
vx just test-py37
vx just test-wheel <built-wheel-path>
```

The resulting wheel is independent from the native `auroraview` wheel. Public
preview installation instructions and artifact checksums are recorded in the
release notes after publication. A local source install is a development path,
not proof that a published package was consumed by a DCC.

## Host boundary

`Tool` describes a callable, schemas and execution annotations. `ToolSet.bind`
uses the view's public `bind_call` API. `ToolSet.attach` borrows a running Core
service and uses its public skill loader and existing execution bridge. It does
not start a second server or replace the host's dispatcher.

Scene readback runs in the same scheduled callback as the business operation.
The returned scene data comes from the host, not a frontend prediction. The
adapter must configure both the WebView call dispatcher and the Core execution
bridge to reach that same host thread.

Closing a registration invalidates its token before unloading its own tools.
Stale UI or agent calls are refused. Borrowed services continue running. Core's
public unload API retains skill catalog metadata; it does not establish full
catalog removal. The package reports and tests that boundary explicitly.

## Existing AuroraView imports

The established `auroraview.dcc_mcp.AuroraViewAdapter`, `AuroraViewQtHost` and
`start_server` entry points remain available in the framework. They expose
panel inspection/navigation and are distinct from explicitly registered scene
tools. Installing this package does not replace the native framework or a host
adapter.

Blender offscreen rendering and Unreal native embedding remain host integration
work with their own validation. Package tests alone do not certify docking,
keyboard input, DPI handling or interactive application acceptance.
