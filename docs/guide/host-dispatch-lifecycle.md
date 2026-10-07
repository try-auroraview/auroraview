# Host-dispatched RPC and nonblocking lifecycle

This contract lets a host adapter provide its UI-thread scheduler while Core
continues to own the JavaScript bridge, request IDs and result/error envelopes.

## Dispatch RPC on the host thread

```python
view.set_call_dispatcher(host_scheduler.submit)
view.bind_call("tool.inspect", inspect_host_state)
view.show(wait=False)
```

`submit` receives a zero-argument callback, enqueues it on the host thread and
returns immediately. It must not wait for the result or call host APIs from a
WebView thread. The bound function remains synchronous; Core settles the existing
JavaScript Promise after that callback runs. `None` restores the default dispatch
behavior. In DCC mode a missing or unsafe main-thread dispatcher rejects the call.

Dictionary parameters are keyword arguments, lists are positional arguments,
omitted parameters call with no arguments and explicit null is one argument.
Non-JSON return values and handler/scheduler errors reject the Promise. Rebinding
an existing name replaces its Python callable without installing another native
callback. New method/event/protocol registrations belong on the native owner
thread; bind them before asynchronous startup. Core replays registrations on the
new owner before publishing its command proxy.

## Close intent and completion

```python
view.request_close()  # idempotent, does not join the native owner thread
finished = view.wait(timeout=0)  # poll from a host UI callback
```

`close()` is equivalent to requesting close. A close request cancels queued RPCs
and fire-and-forget callbacks and suppresses late RPC results. Disconnecting an
event also invalidates its already-queued callback. Already-running Python functions cannot be forcibly
interrupted. Host adapters must stop their own queues/timers and remove host
registrations during disable. Never block the host thread waiting for work that
requires that same thread.

Instances are single-use after closing: reopening creates a fresh `WebView`.
`startup_error` exposes asynchronous construction failures. `wait(0)` distinguishes
close intent from completion of the owner loop.

If `cleanup_pending` is true, an owned host timer still requires cleanup on its
starting thread. Let that host loop tick, or request close again on the owner
thread. A stopped host loop stays explicitly pending; Core does not stop a Qt
timer from a foreign thread or report completed cleanup prematurely.

`close_pending` reports native close delivery that failed. Request close again
to retry only failed targets; successful targets are not sent a second time.
Other cleanup still proceeds if one target fails. `wait(0)` remains false while
delivery or host-timer cleanup is pending. Timer close observers are notified
once before their callback references are released.
Observer execution is outside the WebView lifecycle lock. A foreign or reentrant
close remains pending until every observer has returned. `EventTimer.cleanup()`
returns false when an outer cleanup/notification is still in progress, and true
only after stop, notification and reference cleanup have completed; observer
return values themselves are ignored.

Cross-thread commands use a proxy captured on the native creating thread. Core
does not obtain a proxy by calling into a foreign unsendable PyO3 object. Commands
without a proxy counterpart, such as focus/resize, fail explicitly off-owner.
`create_emitter()` retains the native `EventEmitter` interface: it is captured on
the owner thread and safely shared, rather than substituted with a narrower
command proxy. Both legacy embedded factories use the normal Python state
initialization around their already-created native core.

## Platform and verification boundaries

- Background-thread `show_async()` is enabled only on Windows
- Linux/macOS reject that path before spawning a native owner thread
- Existing same-thread embedded/host-pumped paths remain separate
- These Python contracts have strict-owner fake regressions; they do not establish
  native WebView GUI compatibility on any platform

Promise timeout does not undo host mutations. Host integrations still require
native GUI unload/exit verification and independent review; the Python regression
suite does not establish complete native resource disposal by itself.
