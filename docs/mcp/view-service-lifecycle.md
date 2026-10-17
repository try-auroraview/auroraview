# View routing and shared host service lifecycle

## Status and scope

The product target is that every AuroraView in a supported installation is
MCP-capable without application-specific server setup. Views inside the same
host process reuse that process's service. Opening another view must not create
another listener, gateway, host dispatcher, or copy of the host's tool catalog.

This change implements the first, deliberately smaller part of that contract:

- A weak adapter registry with explicit `view_id` and opaque `generation`.
- An exact `Registration.close()` handle for revoking one view route.
- A `list_views` skill tool and explicit routing for WebView tools.
- Legacy target omission only when exactly one registered view is live.

It does **not** implement automatic service acquisition, a host service broker,
service reference counting, complete skill catalog removal, or automatic
binding to every native view's close lifecycle. The existing `start_server`
helper is not evidence that those requirements are satisfied. The public
interfaces in the proposed sections below are design requirements, not shipped
APIs.

Routing tests using synthetic adapters establish routing behavior only. Neither
this document nor those tests establish a successful real MCP request, a live
Blender integration, or native WebView, docking, input, or screenshot support.
Those require the separate acceptance gates below.

## Implemented routing contract

The implementation lives in
[`adapter_registry.py`](../../python/auroraview/dcc_mcp/adapter_registry.py) and
the [`WebView skill`](../../skills/auroraview-webview/tools.yaml).

`register(adapter, view_id=...)` returns a `Registration` with a `view_id` and
fresh opaque `generation`. Omitting `view_id` generates an ID. The registry
holds a weak reference to the adapter; its host must retain the adapter for as
long as the route should exist. A duplicate live ID cannot replace another
adapter.

Registering the same live adapter again is idempotent and returns the same
registration. This does not create two independently owned leases. A future
host manager must own that registration once and track service leases
separately.

Explicit tool calls supply both fields obtained from `list_views`. The routing
fields are removed before forwarding business parameters to the adapter.
Unknown or stale identities fail instead of falling back to another view.
Without either field, one live view is selected for compatibility; multiple
live views are ambiguous. A generation without a view ID is invalid.

The legacy `AURORAVIEW_ADAPTER` factory is only a fallback when no registered
view and no explicit route are supplied. It cannot override an explicit route
or suppress an ambiguity error.

`Registration.execute()` checks that its exact registration is still active
when execution begins. Hosts that queue calls must queue this guarded operation,
not resolve an adapter and later execute the unguarded adapter. An already
admitted call may finish against its original adapter; it never changes target
to a replacement generation. The registry does not hold its lock while running
host code.

`Registration.close()` removes only that registration by identity. It is safe
to repeat and cannot remove a newer registration reusing the same view ID.
Closing a route does not stop a service or unregister shared host tools. The
legacy `unregister(adapter)` compatibility path is not a substitute for an exact
generation-scoped cleanup handle.

Route IDs identify targets, not permissions. They are discoverable and must not
be treated as authentication credentials or authorization to expose a listener.
This change does not alter network binding or access policy.

## Proposed ownership model

Keep three lifetimes separate:

| Layer | Owner | Release responsibility |
| --- | --- | --- |
| Host service | The host add-on, or a manager that explicitly created it | Owns the listener, host execution integration, and service stop |
| Service capability registration | The host's AuroraView integration | Owns its shared skill/tool registrations and service hooks |
| View lease | One concrete view incarnation | Owns its route, pending requests, subscriptions, and view-specific registrations |

A borrowed view lease never acquires authority to stop a host-owned service.
Closing view A cannot remove view B's route, shared scene tools, or a host
subscription belonging to another consumer.

The proposed manager can expose `acquire_service(...)`, then
`register_view(...) -> ViewLease`, with `ViewLease.release()` for cleanup.
These are suggested API responsibilities, not current function signatures.
Consumers should not receive an unrestricted `stop` callback for a shared
service.

### Existing host-owned service

The integration receives the existing service through the host's public API.
For Blender, `dcc_mcp_blender.get_server()` can identify the current service.
If it is already running, the integration borrows it and its existing execution
bridge. It must not replace its dispatcher, change service configuration, or
call `stop()` when the last view closes.

The host retains its own service-lifetime anchor. The host's explicit shutdown
revokes dependent leases and performs its normal service teardown. Merely
closing all AuroraView windows does not constitute that shutdown.

### Newly created, manager-owned service

If no service exists, a host-level acquisition operation may create one after
the required dependencies and execution environment are available. The manager
retains the exact created object and a service epoch. Each active view lease
pins that service's lifetime.

The final retention release permits shutdown only after dependent requests,
subscriptions, and owned registration cleanup have completed. A failed cleanup
remains owned and retryable. One view must not directly wrap the shared server
as `BackendSession.own(stop=server.stop)` while other views still depend on it.

Stop targets the exact owned service and epoch. A delayed release must not call
a module-global `stop_server()` that could now refer to a replacement service.

### Shared and view-specific registration

Prefer one shared WebView capability registration per service epoch, with
separate revocable view routes. This avoids creating another skill package for
every view opening. A generic shared capability may remain present while the
host integration owns it; it must not retain closed views or advertise them as
live targets.

If a view explicitly owns additional skill registrations, its release revokes
their invocation immediately and attempts only their own teardown. Full catalog
removal is a separate public-API requirement; unloading executable actions alone
does not fulfill it.

## Proposed service state machine

```text
ABSENT -> STARTING -> RUNNING_OWNED
                  -> RUNNING_BORROWED
STARTING failure  -> CLEANUP_PENDING -> ABSENT
RUNNING_OWNED     -> DRAINING -> STOPPING -> ABSENT
RUNNING_BORROWED  -> integration detached; host service remains running
RUNNING_*        -> DISCONNECTED -> verified reconnect or explicit shutdown
```

The service key must distinguish host processes, for example host type, PID,
and a process-session identifier. A host name such as `blender`, a port number,
or a reused PID alone is insufficient identity. The public service
`instance_id` and an integration epoch distinguish service incarnations.

Concurrent acquisitions for the same key join a single startup operation.
Publish a `STARTING` record before doing fallible startup, and publish a usable
service only after startup succeeds. Do not hold a registry lock while invoking
host callbacks or waiting for main-thread work. Callers waiting for startup must
not block the same host thread needed to finish it.

Conflicting configuration must fail explicitly rather than silently taking
effect on an existing service. If all requesters withdraw while startup is in
progress, its result must be cleaned up or deliberately retained by a host
owner; it must not become an unowned listener. Partial startup failure retains
ownership until cleanup succeeds, before admitting another startup.

Blender's current `start_server()` singleton helper checks for a running object
and then creates one, without an atomic acquisition/ownership contract. A
separate `get_server(); start_server()` sequence cannot prove which caller
created it. Coordinated startup must ultimately be implemented at the host's
singleton boundary, or all participating startup paths must be serialized by
that host. An AuroraView-only lock cannot coordinate unrelated host callers.

## Proposed view state machine and reconnection

```text
REGISTERING -> ACTIVE -> CLOSING -> CLOSED
ACTIVE      -> SUSPENDED -> ACTIVE, only after identity verification
```

Each reopened view receives a new generation even when its logical `view_id`
is reused. Revocation happens before fallible teardown, so old callbacks cannot
deliver into a reopened view. Cleanup failure leaves the lease in `CLOSING`
with retryable resources; it does not reactivate the route.

A transport reconnect to the same running service does not itself create a new
view incarnation. A service restart changes its service identity/epoch and
requires explicit reattachment of still-live views. The host must verify the
destination instead of silently connecting to another Blender process at a
familiar port. Old service callbacks cannot release new-service registrations.

A request whose mutation outcome is unknown after disconnect must not be
automatically replayed. Report the uncertain outcome and perform an appropriate
readback before retrying. Cancelled requests and stale-generation responses must
not update a new view.

### Quit hooks and delayed teardown

Each startup's quit callback must capture the exact registration and lifecycle
epoch created for that startup. It must not read a mutable current-registration
field when the callback eventually runs. Its route cleanup is simply the
captured registration's idempotent `close()`.

If the callback also clears a server's adapter or other state, it must first
verify that the server still has the captured epoch. Unregister obsolete hooks
through the public hook API, but remain safe if a removed callback had already
been queued. A stop failure must not automatically register the adapter again
under a fresh generation and unintentionally revive a revoked route.

Server lifecycle wiring requires separate restart, late-callback, partial-stop,
and cleanup-retry tests. A generation-safe routing handle alone does not prove
the existing server wrapper uses it safely.

## Host dispatch and public integration APIs

The Blender host owns the main-thread scheduler. All `bpy` access, view-affine
execution, subscription delivery, and required host cleanup run through that
existing scheduler. Service reuse must not replace it or create a competing
event loop.

A real MCP client invokes the existing server's tools through its public MCP
endpoint. Network I/O runs asynchronously; the host UI thread must not block
waiting for a request that itself requires that UI thread. Preserve native MCP
results and structured errors instead of claiming that a local test callback
is a protocol invocation.

Relevant public APIs already available include:

- `dcc_mcp_blender.get_server()`, `start_server()`, and the returned server's
  public `is_running`, `mcp_url`, and `instance_id` properties.
- `DccServerBase.load_skill_object()`, `get_skill()`, `get_skill_info()`,
  `unload_skill()`, and public quit-hook registration/removal.
- [`ToolSet`](../../packages/auroraview-dcc-mcp/python/auroraview_dcc_mcp/runtime.py)
  declarations with `bind()`, `borrow()`, and `attach()`.
- [`BackendSession`](../../python/auroraview/integration/backend.py) for borrowing
  a public client, preserving its results and request handles, and explicit
  ownership of a separately supplied runtime-stop operation.

`ToolSet.attach()` publishes explicitly declared tools on an existing service.
It does not expose arbitrary tools already registered by that service. Its
`AgentBinding` revokes a process-local token before unloading its actions and
does not stop the borrowed server.

### Remaining public-API gaps

The reviewed DCC-MCP Core boundary, including 0.20.45, does not provide the
complete direct invocation and ownership-aware skill-removal contract needed
to pretend the server itself is a general `BackendSession` client.

- Use an actual MCP client for existing service tool invocation; do not access
  the private inner server.
- Public skill unload removes executable actions but can leave catalog
  metadata. Combining unload and unregister must not be described as atomic,
  ownership-aware complete removal. Reattaching the same skill name may still
  conflict with retained catalog state.
- A robust registration API should return an ownership token and remove only
  that token's actions, catalog entries, hooks, and discovery state, reporting
  partial cleanup for retry. This requires additional Core support.
- Neither the existing Blender singleton nor the AuroraView server helper
  supplies the proposed host service acquisition and lease manager.
- Automatic view enrollment and close binding are still integration work.
  Optional dependency imports do not establish out-of-box availability. A
  supported product distribution must supply the dependency set or clearly
  report the missing capability; it must not silently install packages.

No new gateway or public-network configuration is required by this design.
Reuse the host's authorized transport and discovery configuration.

## Acceptance matrix

The table specifies required evidence, not results already obtained.

| Gate | Scenario | Required result |
| --- | --- | --- |
| Isolated routing | Register synthetic adapters A and B; explicitly call each | Only the selected adapter receives the business parameters |
| Isolated routing | Omit a route with zero, one, or two live entries | Missing target, sole-view compatibility, or ambiguity respectively |
| Isolated routing | Unknown ID, wrong generation, duplicate live ID, incomplete route | Refusal without executing another adapter |
| Isolated routing | Close A, reopen its ID, then release old A again | New generation survives; stale calls fail |
| Isolated routing | Resolve/queue A, close it before execution | Guarded execution refuses the revoked route |
| Isolated routing | Collect an adapter and retain an old registration handle | Dead view is not listed or callable; old cleanup cannot remove a replacement |
| Isolated routing | Configure the legacy environment factory | Explicit routes and ambiguity cannot be bypassed |
| Server lifecycle | Restart, then execute the old quit callback | Only its captured registration is affected |
| Server lifecycle | Partial startup/stop and retryable cleanup failure | No route resurrection, ownership loss, double stop, or foreign cleanup |
| Real MCP | One actual server, two synthetic view adapters, actual client calls | Distinct routing verified through MCP; synthetic views explicitly labeled |
| Borrowed service | Close all views attached to an existing Blender server | Same host service remains callable through MCP; original tools survive |
| Owned service | Acquire two view leases, release one, then the last | Service survives the first release and stops only after final cleanup |
| Concurrent startup | Simultaneous acquisitions and a caller withdrawing during startup | One service startup, one identity, no unowned listener |
| Reconnection | Disconnect/reconnect client; then restart service | Same-service leases preserved appropriately; old-service identities rejected |
| In-flight work | Close while a request or event is queued | No stale delivery or mutation replay; host dispatcher remains until cleanup finishes |
| Skill removal | Release and reattach an owned skill registration | Executable removal and catalog removal reported separately; unsupported full removal remains a gap |
| Native host | Repeat open/call/close with actual AuroraView and Blender surfaces | Independent native evidence for view creation, main-thread execution, close completion, and any claimed GUI behavior |

Run only the gates supported by the selected environment and authorized
dependencies. Record passed, failed, skipped, and not-run stages separately.
A successful synthetic routing gate must never be presented as a real MCP or
native GUI pass.
