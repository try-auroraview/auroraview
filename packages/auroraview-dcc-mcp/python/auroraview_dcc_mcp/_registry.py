"""Process-local revocable tokens used by view wrappers and skill scripts."""

import threading
import uuid
import weakref

from .contracts import ClosedError

_lock = threading.RLock()
_leases = weakref.WeakValueDictionary()


def register(lease):
    token = uuid.uuid4().hex
    with _lock:
        _leases[token] = lease
    return token


def revoke(token):
    with _lock:
        _leases.pop(token, None)


def resolve(token):
    with _lock:
        lease = _leases.get(token)
    if lease is None:
        raise ClosedError("The tool consumer lease has been released")
    return lease


def invoke(token, tool, params):
    """Entry point for immutable generated scripts; never evaluates parameters."""
    return resolve(token).call(tool, params)


def close(token, *args, **kwargs):
    try:
        lease = resolve(token)
    except ClosedError:
        return
    lease.close()


def deliver(token, subscription, *args, **kwargs):
    try:
        lease = resolve(token)
    except ClosedError:
        return
    lease._deliver(subscription, args, kwargs)
