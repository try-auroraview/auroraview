# Compose a native client with shared tools

Use the host's existing client and dispatcher. The application declares which
native methods may be exposed through `ToolSet`, then binds a panel or attaches
the existing DCC-MCP service. The
[executable composition example](../examples/native_tool_client.py) implements
this using the public `Client.call`, `Client.on`, `Client.identity`, `Tool` and
`ToolSet` interfaces. It is application source, not a new public SDK class.

## Ownership and execution

| Responsibility | Owner |
| --- | --- |
| Authorization, MCP discovery and execution lane | Existing DCC-MCP service |
| Explicit declarations, schemas and consumer lifetime | `ToolSet` and application |
| Python callback thread and event queue | Existing host dispatcher |
| Connection, authentication and RPC deadline | Existing native client |
| Scene access, native task lifetime and authoritative state | Native host |
| Page communication and rendering | AuroraView bridge and renderer |

The Python owner thread and the native host thread may differ. A tool callback
can use the already connected Unreal client to request a GameThread operation.
Both UI and Core callbacks must reach the Python `ToolSet` owner thread. Native
events arrive on client workers and must pass through the injected dispatcher
before reaching a consumer. The example creates no server, thread or queue.

## Explicit composition

Import `tools_from_client` from the example after placing it in your application.
The native client and dispatcher below already exist and remain application-owned.
Choose pinned identity fields from a trusted target selection, rather than
accepting any connection that happens to be available.

```python
tools = tools_from_client(
    client,
    [{
        "name": "unreal.engine.info",
        "description": "Read identity and readiness from the native engine",
        "input_schema": {"type": "object", "additionalProperties": False},
        "output_schema": {
            "type": "object",
            "required": ["pid", "context", "engine_version"],
            "properties": {
                "pid": {"type": "integer"},
                "context": {"enum": ["editor", "game"]},
                "engine_version": {"type": "string"},
            },
        },
        "read_only": True,
        "destructive": False,
    }],
    expected_identity={"pid": selected_pid, "context": "editor"},
    dispatch=host.dispatch,
    timeout=5.0,
    max_timeout=10.0,
    dcc="unreal",
)
ui = tools.bind(view)
agent = tools.attach(existing_server)
```

The declaration name is the exact native method name. Output schemas are
mandatory; invalid input and undeclared methods fail before an RPC. An RPC
result is validated and returned without another result envelope. Native method
discovery, schema annotations and session routing tokens do not grant permission.
The application must expose only capabilities authorized by its DCC-MCP policy.

The contract package supports Python 3.7+. A host client can have a higher
Python requirement; the current Unreal client requires Python 3.9+.

## Identity, readback and deadlines

The example detaches the selected JSON identity fields and checks them before
and after calls and before owner-thread event delivery. Type changes are
refused. These are local connection checks, not atomic target attestation. In
the current Unreal client, `parent_id` identifies the PID; it is not a session
nonce. Native session, generation and version fields can be selected when the
host supplies them.

For a mutation, the native handler must validate the expected target/session
within the same native execution that performs the operation and returns its
authoritative state. Declare those parameters and the native result schema
explicitly. The example uses `readback=None`: separate mutation and readback
RPCs can interleave on the GameThread. The shared package's local `readback`
callback does not make two native requests atomic.

The call timeout must be finite, positive and within the caller's explicit
maximum. A timeout only limits waiting; it does not prove that native work
stopped. Long-running native tasks need host-owned bounded start/status/cancel/
result operations, native deadline enforcement and cancellation acknowledgement.
The composition example neither invents these operations nor cancels borrowed
tasks or closes the client.

## Unload and retry

Close UI/agent bindings and borrowed sessions, then close the owner at application
unload. Host unsubscribe runs on the owner thread and must complete synchronously.
Return `None` or `True` on completion, or raise on failure. `False`, awaitables and
Future-like results are refused; pending removal remains available for retry.
`close()` aggregates failures in `CleanupError` after revoking event delivery.
An unstarted coroutine result is closed to avoid leaking it; already started
host work and Futures are neither waited on nor cancelled.

The published `0.1.0-preview.1` wheel predates cleanup-result validation. Its
host adapters must raise on removal failure; it does not detect `False` or an
awaitable. The behavior described here requires a wheel built from this source
or a later verified publication. Pin the artifact checksum, not just the
unchanged preview package version.

A failed close leaves the route inactive. Retry close on the owner thread to
finish removal. Other consumers, the tool owner and borrowed services remain
usable. A dispatcher must accept a callback with `None`/`True`, or report refusal
with an exception/`False`; it must execute on the registered owner thread.

## Decision: compose existing ports

The current requirement is to expose selected native operations through the
same contracts used by a panel and DCC-MCP. Existing native clients already own
transport, authentication and bounded work. A second generic client/task API
would duplicate those responsibilities and risk ambiguous cleanup and thread
ownership. Keep the small composition example until multiple real consumers
demonstrate a missing shared abstraction. This keeps host lifecycle details in
their plugins, at the cost of explicitly wiring each host's dispatcher and
declarations.

Source tests use fake native ports. Installed-wheel tests verify the shared
contract runtime independently from the checkout; the example is copied as
application source. Neither proves native Unreal task behavior, Blender
docking, input/focus handling or GUI acceptance. Verify those in the host plugin
and record package/host versions and authoritative state separately.
