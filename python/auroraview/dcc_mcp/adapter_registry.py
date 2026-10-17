# -*- coding: utf-8 -*-
"""Weak, generation-scoped routes to live AuroraView adapters.

This is a view-routing table, not a second MCP server or tool catalog. A host
registers each view once and owns the returned Registration. Explicit callers
use both view_id and generation from list_views(); legacy omission is accepted
only when exactly one view is live. Closing an old registration cannot remove
a replacement with the same view_id. No registration owns the host service.
"""

from __future__ import annotations

import threading
import uuid
import weakref
from typing import Any, Dict, Iterator, List, Optional

_lock = threading.RLock()
_entries: "Dict[str, Registration]" = {}


class AmbiguousViewError(RuntimeError):
    """A caller omitted its target while multiple live views exist."""


class StaleViewError(RuntimeError):
    """A route was closed, collected, replaced, or has an old generation."""


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128 or "\x00" in value:
        raise ValueError("{} must contain 1-128 non-null characters".format(label))
    return value


def _live() -> List["Registration"]:
    """Compact dead weak references. Caller holds _lock."""
    dead = [key for key, entry in _entries.items() if entry._adapter() is None]
    for key in dead:
        del _entries[key]
    return list(_entries.values())


class Registration:
    """One view's revocable routing identity; never stops a borrowed service.

    Registering the same live adapter twice is idempotent and returns the same
    owner handle, not a second independent lease. A future host-service manager
    must own this handle once per view and maintain its service leases separately.
    """

    __slots__ = ("_view_id", "_generation", "_adapter")

    def __init__(self, view_id: str, adapter: Any) -> None:
        self._view_id = view_id
        self._generation = uuid.uuid4().hex
        self._adapter = weakref.ref(adapter)

    @property
    def view_id(self) -> str:
        return self._view_id

    @property
    def generation(self) -> str:
        return self._generation

    @property
    def active(self) -> bool:
        with _lock:
            return _entries.get(self.view_id) is self and self._adapter() is not None

    def _get(self) -> Any:
        with _lock:
            adapter = self._adapter()
            if _entries.get(self.view_id) is not self or adapter is None:
                raise StaleViewError(
                    "AuroraView route is no longer active: {}".format(self.view_id)
                )
            return adapter

    def execute(self, tool: str, params: Any) -> Any:
        """Recheck at execution, including after a host queued this handle.

        An already executing call may finish against its original adapter; it
        is never redirected to a new generation. Host thread scheduling remains
        the existing dispatcher's responsibility, and no registry lock is held
        while invoking host code.
        """
        adapter = self._get()
        return adapter.execute(tool, params)

    def close(self) -> bool:
        """Compare-and-remove only this registration; repeated close is safe."""
        with _lock:
            if _entries.get(self.view_id) is not self:
                return False
            del _entries[self.view_id]
            return True


def register(adapter: Any, *, view_id: Optional[str] = None) -> Registration:
    """Register one weak view route and return its exact cleanup handle."""
    if adapter is None:
        raise ValueError("cannot register a None adapter")
    weakref.ref(adapter)  # Validate before modifying the registry.
    if view_id is not None:
        _identifier(view_id, "view_id")
    with _lock:
        for entry in _live():
            if entry._adapter() is adapter:
                if view_id is not None and entry.view_id != view_id:
                    raise ValueError("adapter is already registered under another view_id")
                return entry
        view_id = view_id or uuid.uuid4().hex
        if view_id in _entries:
            raise ValueError("AuroraView view_id is already registered: {}".format(view_id))
        entry = Registration(view_id, adapter)
        _entries[view_id] = entry
        return entry


def unregister(adapter: Any) -> None:
    """Legacy adapter-identity cleanup. New owners should retain close handles.

    A Registration is accepted for precise generation-scoped cleanup. This
    compatibility function does not stop any server or unregister shared tools.
    """
    if isinstance(adapter, Registration):
        adapter.close()
        return
    with _lock:
        for entry in _live():
            if entry._adapter() is adapter:
                entry.close()


def resolve(
    view_id: Optional[str] = None, generation: Optional[str] = None
) -> Optional[Registration]:
    """Resolve a view route; explicit IDs require their matching generation."""
    if view_id is None and generation is not None:
        raise ValueError("generation requires view_id")
    if view_id is not None:
        _identifier(view_id, "view_id")
        _identifier(generation, "generation")
    with _lock:
        live = _live()
        if view_id is None:
            if len(live) > 1:
                raise AmbiguousViewError(
                    "Multiple AuroraView views are live; use list_views and pass view_id plus generation"
                )
            return live[0] if live else None
        entry = _entries.get(view_id)
        if entry is None or entry.generation != generation:
            raise StaleViewError("Unknown or stale AuroraView route: {}".format(view_id))
        return entry


def list_views() -> List[Dict[str, str]]:
    """List route identities without invoking host code or retaining views."""
    with _lock:
        return [{"view_id": entry.view_id, "generation": entry.generation} for entry in _live()]


def adapters() -> List[Any]:
    """Return live adapters in registration order, without choosing a target."""
    with _lock:
        result = []
        for entry in _live():
            adapter = entry._adapter()
            if adapter is not None:
                result.append(adapter)
        return result


def current() -> Optional[Any]:
    """Return the sole live adapter, None, or raise for an ambiguous target."""
    entry = resolve()
    return entry._get() if entry is not None else None


def clear() -> None:
    """Revoke all registrations. Intended for isolated tests."""
    with _lock:
        _entries.clear()


def iter_adapters() -> Iterator[Any]:
    """Iterate over live adapters in registration order."""
    yield from adapters()


current_adapter = current
