"""Compose explicitly authorized native Client methods with public Tool/ToolSet.

This is an application composition example, not another SDK client or protocol.
The caller supplies its already connected Client, explicit Tool keyword
declarations (without handler/readback), and existing owner-thread dispatcher.
Only the declared method names are exposed; native discovery grants nothing.

Call ``tools_from_client(...)`` on the thread that will own ToolSet calls and
unsubscription. Its returned ToolSet can bind a UI or attach to the caller's
existing, correctly dispatched DCC-MCP server. Close those bindings and the
ToolSet at application unload; this example never closes the borrowed client,
server, or native task. A dispatcher must schedule callbacks on that same
thread, return None/True on acceptance, and raise or return False on refusal.

``expected_identity`` selects caller-pinned JSON fields from Client.identity.
For the current Unreal client, parent_id is a PID, not a session nonce. Include
new native session/version fields when the host provides them. Local pre/post
checks cannot atomically prevent a wrong-target native operation: the native
handler must verify expected target/generation within its own execution. Put
those expected values in the declared input schema and caller's parameters.

The native result is validated with the caller's output_schema and returned
without a synthetic result/scene envelope. readback=None is intentional: two
RPCs do not establish an atomic GameThread operation/readback. A local timeout
does not establish native task cancellation; declared start/status/cancel/result
operations and authoritative receipts remain the native host's responsibility.
"""

import inspect
import json
import math
import threading

from auroraview_dcc_mcp import ContractError, ThreadError, Tool, ToolSet


def _json_object(value):
    if not isinstance(value, dict) or not value or any(not isinstance(k, str) for k in value):
        raise ContractError("Expected identity must be a nonempty JSON object with string keys")

    def check_keys(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ContractError("Identity object keys must be strings")
            for child in item.values():
                check_keys(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check_keys(child)

    try:
        check_keys(value)
        return json.loads(json.dumps(value, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError, RecursionError) as error:
        raise ContractError("Identity fields must be JSON values") from error


def tools_from_client(
    client,
    declarations,
    *,
    expected_identity,
    dispatch,
    timeout=5.0,
    max_timeout=30.0,
    name="native-tools",
    dcc="native",
):
    """Return a ToolSet borrowing Client.call/on/identity; create no transport.

    Each declaration uses public Tool constructor fields, including name,
    description, input_schema and output_schema. Its name is the exact native
    method. The caller explicitly selects annotations and any expected-session
    parameters; no method names, task API or authorization token are invented.
    """
    for duration in (timeout, max_timeout):
        try:
            valid = type(duration) in (int, float) and math.isfinite(duration) and duration > 0
        except OverflowError:
            valid = False
        if not valid:
            raise ContractError("Call timeout and caller bound must be finite and positive")
    if timeout > max_timeout:
        raise ContractError("Call timeout exceeds the caller's bound")
    if not callable(dispatch):
        raise ContractError("An existing Client and owner-thread dispatcher are required")
    for method in ("call", "on"):
        callback = getattr(client, method, None)
        if (
            not callable(callback)
            or inspect.iscoroutinefunction(callback)
            or inspect.iscoroutinefunction(callback.__call__)
        ):
            raise ContractError("Client.{} must be synchronous and callable".format(method))
    expected = _json_object(expected_identity)
    pinned = json.dumps(expected, allow_nan=False, sort_keys=True)
    owner_thread = threading.get_ident()

    def check_identity():
        observed = client.identity
        if not isinstance(observed, dict) or any(key not in observed for key in expected):
            raise ContractError("Native identity is missing expected fields")
        selected = {key: observed[key] for key in expected}
        if json.dumps(_json_object(selected), allow_nan=False, sort_keys=True) != pinned:
            raise ContractError("Native identity differs from the caller's pinned fields")

    check_identity()

    def handler(method):
        def invoke(**params):
            check_identity()
            result = client.call(method, params, timeout=timeout)
            check_identity()
            return result

        return invoke

    def subscribe(event, callback):
        check_identity()
        active = True

        def receive(*args, **kwargs):
            if not active:
                return

            def deliver():
                if not active:
                    return
                if threading.get_ident() != owner_thread:
                    raise ThreadError("Dispatcher did not reach the ToolSet owner thread")
                check_identity()
                callback(*args, **kwargs)

            accepted = dispatch(deliver)
            if accepted is not None and accepted is not True:
                # A coroutine dispatcher has not scheduled owner-thread work.
                if (
                    inspect.iscoroutine(accepted)
                    and inspect.getcoroutinestate(accepted) == inspect.CORO_CREATED
                ):
                    accepted.close()
                raise ContractError("Owner-thread dispatcher did not accept the callback")

        remove = client.on(event, receive)
        if (
            not callable(remove)
            or inspect.isawaitable(remove)
            or (
                callable(getattr(remove, "cancel", None))
                and callable(getattr(remove, "done", None))
            )
        ):
            if (
                inspect.iscoroutine(remove)
                and inspect.getcoroutinestate(remove) == inspect.CORO_CREATED
            ):
                remove.close()
            raise ContractError("Client.on must synchronously return an unsubscribe callable")

        def unsubscribe():
            nonlocal active
            active = False  # queued callbacks stay inactive even if removal needs retry
            return remove()

        return unsubscribe

    tools = []
    for declaration in declarations:
        fields = dict(declaration)
        if fields.get("output_schema") is None:
            raise ContractError("A native declaration requires its output_schema")
        if "handler" in fields or "readback" in fields:
            raise ContractError("Native declarations cannot replace handler or add readback")
        tools.append(Tool(handler=handler(fields["name"]), readback=None, **fields))
    return ToolSet(name, tools, dcc=dcc, subscribe=subscribe)
