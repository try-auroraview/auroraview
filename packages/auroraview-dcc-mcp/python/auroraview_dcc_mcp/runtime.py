"""Owner and consumer lifetimes, independent of AuroraView and host SDKs."""

import functools
import re
import threading
import uuid
import weakref

from . import _registry
from .contracts import CleanupError, ClosedError, ContractError, ThreadError, Tool, identifier


class ToolSession:
    """A borrowed tool consumer; close releases only this consumer's resources."""

    def __init__(self, owner):
        self._owner = weakref.ref(owner)
        self._thread = owner._thread
        self._lock = threading.RLock()
        self._closed = False
        self._subscriptions = {}
        self._pending = {}
        self._acquiring = 0
        self.token = _registry.register(self)

    @property
    def closed(self):
        with self._lock:
            return self._closed

    def _get_owner(self):
        with self._lock:
            if self._closed:
                raise ClosedError("The tool consumer lease has been released")
            owner = self._owner()
            if owner is None:
                raise ClosedError("The tool owner has been released")
            if owner.closed:
                raise ClosedError("The tool owner has been released")
            return owner

    def list_tools(self):
        return self._get_owner().list_tools()

    def call(self, method, params=None):
        return self._get_owner().call(method, params)

    def subscribe(self, event, callback):
        """Subscribe through the injected host source; return an unsubscribe."""
        owner = self._get_owner()
        if not isinstance(event, str) or not event or not callable(callback):
            raise ContractError("An event name and callable callback are required")
        subscription = uuid.uuid4().hex
        with self._lock:
            if self._closed:
                raise ClosedError("The tool consumer lease has been released")
            self._subscriptions[subscription] = callback
            self._acquiring += 1
        try:
            unsubscribe = owner._subscribe(
                event, functools.partial(_registry.deliver, self.token, subscription)
            )
            if not callable(unsubscribe):
                raise ContractError("Host subscribe must return an unsubscribe callable")
        except Exception:
            with self._lock:
                self._subscriptions.pop(subscription, None)
                self._acquiring -= 1
            self._release_if_clean()
            raise
        with self._lock:
            self._pending[subscription] = unsubscribe
            self._acquiring -= 1
            closed = self._closed
        if closed:
            try:
                self._unsubscribe(subscription)
            except Exception as error:
                raise CleanupError([error]) from error
            finally:
                self._release_if_clean()
            raise ClosedError("The tool consumer closed while its subscription was acquired")
        return functools.partial(self._unsubscribe, subscription)

    def _deliver(self, subscription, args, kwargs):
        with self._lock:
            callback = None if self._closed else self._subscriptions.get(subscription)
        if callback is not None:
            try:
                self._get_owner()._check_thread()
            except ClosedError:
                return
            callback(*args, **kwargs)

    def _unsubscribe(self, subscription):
        with self._lock:
            self._subscriptions.pop(subscription, None)
            unsubscribe = self._pending.get(subscription)
        if unsubscribe is not None:
            if threading.get_ident() != self._thread:
                raise ThreadError(
                    "Host unsubscription must run on the tool owner's registered thread"
                )
            unsubscribe()
            with self._lock:
                self._pending.pop(subscription, None)

    def _cleanup(self):
        errors = []
        with self._lock:
            subscriptions = list(self._pending)
        for subscription in subscriptions:
            try:
                self._unsubscribe(subscription)
            except Exception as error:
                errors.append(error)
        return errors

    def close(self):
        # Revoke before any fallible external teardown. Already leased calls
        # may finish; no lock is held while running a host callback.
        with self._lock:
            self._closed = True
            self._subscriptions.clear()
            _registry.revoke(self.token)
        errors = self._cleanup()
        if errors:
            raise CleanupError(errors)
        self._release_if_clean()

    def _release_if_clean(self):
        with self._lock:
            if not self._closed or self._pending or self._acquiring:
                return
        owner = self._owner()
        if owner is not None:
            owner._release(self)

    def __enter__(self):
        self._get_owner()
        return self

    def __exit__(self, *args):
        self.close()


class UIBinding(ToolSession):
    """A token-only set of ``bind_call`` wrappers on a view."""


class ToolSet:
    """An explicit tool owner. Host code retains it and closes it at unload.

    ``subscribe`` optionally injects the host's existing event subscription
    function: ``subscribe(event, callback) -> unsubscribe``. No event bus,
    renderer, native server or host scheduler is created here.
    """

    def __init__(self, name, tools, description="", *, dcc="python", subscribe=None):
        self.name = identifier(name, "Tool set name")
        if not isinstance(dcc, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", dcc):
            raise ContractError("dcc must be a non-empty host identifier")
        self.dcc = dcc
        if not isinstance(description, str):
            raise ContractError("Tool set description must be a string")
        declarations = list(tools)
        if not declarations or len(declarations) > 128:
            raise ContractError("A tool set must contain 1-128 tools")
        if any(not isinstance(tool, Tool) for tool in declarations):
            raise ContractError("tools must contain Tool declarations")
        if len({tool.name for tool in declarations}) != len(declarations):
            raise ContractError("Tool names must be unique within a set")
        if subscribe is not None and not callable(subscribe):
            raise ContractError("subscribe must be callable")
        self.description = description
        self.id = uuid.uuid4().hex
        self._thread = threading.get_ident()
        self._lock = threading.RLock()
        self._tools = {tool.name: tool for tool in declarations}
        self._event_source = subscribe
        self._bindings = set()
        self._closed = False

    @property
    def closed(self):
        with self._lock:
            return self._closed

    def _check_thread(self):
        if threading.get_ident() != self._thread:
            raise ThreadError("Tool calls must run on the tool owner's registered thread")

    def _check_open(self):
        if self._closed:
            raise ClosedError("The tool owner has been released")

    def list_tools(self):
        with self._lock:
            self._check_open()
            return [tool.descriptor() for tool in self._tools.values()]

    def call(self, method, params=None):
        self._check_thread()
        with self._lock:
            self._check_open()
            try:
                tool = self._tools[method]
            except KeyError:
                raise ContractError("Unknown tool: {}".format(method)) from None
        return tool.invoke({} if params is None else params)

    def _subscribe(self, event, callback):
        self._check_thread()
        with self._lock:
            self._check_open()
            source = self._event_source
        if source is None:
            raise ContractError("This tool set has no host event subscription source")
        return source(event, callback)

    def _retain(self, binding):
        with self._lock:
            self._check_open()
            self._bindings.add(binding)
        return binding

    def _release(self, binding):
        with self._lock:
            self._bindings.discard(binding)

    def borrow(self):
        return self._retain(ToolSession(self))

    def bind(self, view):
        self._check_thread()
        descriptors = self.list_tools()
        if not callable(getattr(view, "bind_call", None)):
            raise ContractError("The view must provide bind_call(name, callable)")
        binding = self._retain(UIBinding(self))
        try:
            for descriptor in descriptors:
                name = descriptor["name"]

                # Keep routing identifiers outside the callable's parameter
                # namespace: frontend data cannot override either identifier.
                invoke = _ui_wrapper(binding.token, name)
                view.bind_call(name, invoke)
            on_closed = getattr(view, "on_closed", None)
            if callable(on_closed):
                on_closed(functools.partial(_registry.close, binding.token))
        except Exception:
            binding.close()
            raise
        return binding

    def attach(self, server):
        self._check_thread()
        from .agent import AgentBinding

        return AgentBinding.attach(self, server)

    def close(self):
        with self._lock:
            self._closed = True
            self._tools.clear()
            self._event_source = None
            bindings = list(self._bindings)
        errors = []
        for binding in bindings:
            try:
                binding.close()
            except CleanupError as error:
                errors.extend(error.errors)
        if errors:
            raise CleanupError(errors)

    def __enter__(self):
        with self._lock:
            self._check_open()
        return self

    def __exit__(self, *args):
        self.close()


def _ui_wrapper(token, name):
    def invoke(**params):
        return _registry.invoke(token, name, params)

    return invoke
