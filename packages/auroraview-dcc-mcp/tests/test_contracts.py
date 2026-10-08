import gc
import subprocess
import sys
import threading
import weakref

import pytest
from auroraview_dcc_mcp import (
    CleanupError,
    ClosedError,
    ContractError,
    ThreadError,
    Tool,
    ToolSet,
)

INPUT = {
    "type": "object",
    "properties": {"name": {"type": "string", "minLength": 1}},
    "required": ["name"],
    "additionalProperties": False,
}
OUTPUT = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "scene": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["result", "scene"],
    "additionalProperties": False,
}


class View:
    def __init__(self):
        self.calls = {}
        self.closed_callbacks = []

    def bind_call(self, method, callback):
        self.calls[method] = callback

    def on_closed(self, callback):
        self.closed_callbacks.append(callback)

    def close(self):
        for callback in self.closed_callbacks:
            callback()


@pytest.fixture
def tools():
    scene = []

    def create(name):
        scene.append(name)
        return name

    owner = ToolSet(
        "scene-tools",
        [
            Tool(
                "create",
                "Create an object",
                INPUT,
                create,
                output_schema=OUTPUT,
                readback=lambda: scene,
            )
        ],
    )
    yield owner, scene
    owner.close()


def test_ui_and_borrowed_consumer_share_contract_and_scene_readback(tools):
    owner, scene = tools
    view = View()
    binding = owner.bind(view)
    consumer = owner.borrow()
    identity = owner.id
    assert binding.list_tools() == consumer.list_tools() == owner.list_tools()
    assert view.calls["create"](name="Cube") == {"result": "Cube", "scene": ["Cube"]}
    assert consumer.call("create", {"name": "Sphere"}) == {
        "result": "Sphere",
        "scene": ["Cube", "Sphere"],
    }
    assert scene == ["Cube", "Sphere"]
    assert owner.id == identity


def test_closing_one_view_releases_only_its_route(tools):
    owner, _ = tools
    first, second = View(), View()
    binding = owner.bind(first)
    owner.bind(second)
    first.close()
    assert binding.closed
    with pytest.raises(ClosedError):
        first.calls["create"](name="stale")
    assert second.calls["create"](name="alive")["scene"] == ["alive"]
    assert not owner.closed


@pytest.mark.parametrize("params", [{}, {"name": 1}, {"name": ""}, {"name": "x", "extra": 1}])
def test_invalid_ui_or_consumer_params_cannot_mutate(tools, params):
    owner, scene = tools
    view = View()
    owner.bind(view)
    for invoke in (lambda: view.calls["create"](**params), lambda: owner.call("create", params)):
        with pytest.raises(ContractError):
            invoke()
    assert scene == []


def test_schema_is_detached_from_original_and_discovery_metadata(tools):
    owner, _ = tools
    descriptor = owner.list_tools()[0]
    descriptor["inputSchema"]["properties"]["name"]["type"] = "integer"
    with pytest.raises(ContractError):
        owner.call("create", {"name": 2})


def test_runtime_routing_keys_cannot_be_overridden_by_frontend():
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    with ToolSet(
        "routing", [Tool("echo", "Echo values", schema, lambda **kwargs: kwargs)]
    ) as owner:
        view = View()
        owner.bind(view)
        assert view.calls["echo"](_token="forged", _name="other") == {
            "_token": "forged",
            "_name": "other",
        }


def test_wrong_thread_fails_before_business_callback(tools):
    owner, scene = tools
    consumer = owner.borrow()
    failures = []

    def worker():
        try:
            consumer.call("create", {"name": "wrong-thread"})
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(2)
    assert isinstance(failures[0], ThreadError)
    assert scene == []


def test_owner_close_releases_handlers_without_stale_view_retention():
    class Handler:
        def __call__(self):
            return "done"

    handler = Handler()
    reference = weakref.ref(handler)
    owner = ToolSet("owned", [Tool("run", "Run owned handler", {"type": "object"}, handler)])
    view = View()
    owner.bind(view)
    del handler
    owner.close()
    gc.collect()
    assert reference() is None
    with pytest.raises(ClosedError):
        view.calls["run"]()
    with pytest.raises(ClosedError):
        owner.borrow()


def test_borrowed_session_does_not_keep_owner_alive(tools):
    owner = ToolSet("weak-owner", [Tool("run", "Run", {"type": "object"}, lambda: None)])
    session = owner.borrow()
    reference = weakref.ref(owner)
    del owner
    gc.collect()
    assert reference() is None
    with pytest.raises(ClosedError):
        session.call("run")
    session.close()


def test_owner_close_during_call_does_not_hold_lock_or_cancel_readback():
    entered, closed = threading.Event(), threading.Event()
    calls = []

    def handler(name):
        calls.append(("mutation", threading.get_ident()))
        entered.set()
        assert closed.wait(2), "close deadlocked behind the user callback"
        return name

    def readback():
        calls.append(("readback", threading.get_ident()))
        return ["Cube"]

    owner = ToolSet(
        "inflight",
        [Tool("create", "Create", INPUT, handler, output_schema=OUTPUT, readback=readback)],
    )
    session = owner.borrow()

    def closer():
        assert entered.wait(2)
        owner.close()
        closed.set()

    thread = threading.Thread(target=closer)
    thread.start()
    assert session.call("create", {"name": "Cube"}) == {"result": "Cube", "scene": ["Cube"]}
    thread.join(2)
    assert calls == [("mutation", threading.get_ident()), ("readback", threading.get_ident())]
    with pytest.raises(ClosedError):
        session.call("create", {"name": "later"})


def test_schema_and_result_errors_are_explicit():
    with pytest.raises(ContractError, match="local"):
        Tool(
            "run",
            "Run",
            {"type": "object", "$ref": "https://example.com/schema.json"},
            lambda: None,
        )
    with pytest.raises(ContractError, match="read-only"):
        Tool("run", "Run", {"type": "object"}, lambda: None, read_only=True)
    with pytest.raises(ContractError, match="requires an output_schema"):
        Tool("run", "Run", {"type": "object"}, lambda: None, readback=lambda: None)
    with ToolSet(
        "bad-result", [Tool("run", "Run", {"type": "object"}, lambda: float("nan"))]
    ) as owner:
        with pytest.raises(ContractError, match="JSON serializable"):
            owner.call("run")
    with ToolSet(
        "bad-output",
        [Tool("run", "Run", {"type": "object"}, lambda: 1, output_schema={"type": "string"})],
    ) as owner:
        with pytest.raises(ContractError, match="result"):
            owner.call("run")


def test_session_close_unsubscribes_only_owned_callbacks_and_retries_failure():
    callbacks = {}
    fail_once = [True]

    def subscribe(event, callback):
        callbacks[callback] = event

        def unsubscribe():
            if event == "fail" and fail_once[0]:
                fail_once[0] = False
                raise RuntimeError("host teardown failed")
            callbacks.pop(callback)

        return unsubscribe

    received = []
    owner = ToolSet(
        "events", [Tool("run", "Run", {"type": "object"}, lambda: True)], subscribe=subscribe
    )
    first, second = owner.borrow(), owner.borrow()
    first.subscribe("fail", lambda value: received.append(("first", value)))
    second.subscribe("other", lambda value: received.append(("second", value)))
    stale = next(callback for callback, event in callbacks.items() if event == "fail")
    with pytest.raises(CleanupError, match="host teardown failed"):
        first.close()
    stale(1)
    assert received == []
    assert second.call("run") is True
    first.close()
    assert list(callbacks.values()) == ["other"]
    next(iter(callbacks))(2)
    assert received == [("second", 2)]
    owner.close()
    assert callbacks == {}


def test_subscription_handle_can_remove_one_listener_without_closing_session():
    callbacks = []

    def subscribe(event, callback):
        callbacks.append(callback)
        return lambda: callbacks.remove(callback)

    with ToolSet(
        "events", [Tool("run", "Run", {"type": "object"}, lambda: True)], subscribe=subscribe
    ) as owner:
        session = owner.borrow()
        unsubscribe = session.subscribe("changed", lambda: None)
        unsubscribe()
        unsubscribe()
        assert callbacks == []
        assert session.call("run") is True


def test_dotted_ui_method_names_and_immutable_declarations():
    tool = Tool("scene.inspect", "Inspect scene", {"type": "object"}, lambda: [])
    with pytest.raises(AttributeError, match="immutable"):
        tool.name = "different"
    with ToolSet("scene", [tool]) as owner:
        view = View()
        owner.bind(view)
        assert view.calls["scene.inspect"]() == []


def test_import_is_independent_of_native_framework_core_and_host_sdks():
    script = (
        "import sys; import auroraview_dcc_mcp; "
        "assert not {'auroraview', 'dcc_mcp_core', 'bpy', 'unreal', 'PySide6', 'PySide2', 'qtpy'}"
        ".intersection(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", script], check=True, timeout=10)


def test_off_thread_close_revokes_delivery_then_retries_host_unsubscribe_on_owner_thread():
    callbacks, unsubscriptions = [], []

    def subscribe(event, callback):
        callbacks.append(callback)

        def unsubscribe():
            unsubscriptions.append(threading.get_ident())
            callbacks.remove(callback)

        return unsubscribe

    owner = ToolSet(
        "events", [Tool("run", "Run", {"type": "object"}, lambda: True)], subscribe=subscribe
    )
    session = owner.borrow()
    received, errors = [], []
    session.subscribe("changed", lambda: received.append(True))

    def closer():
        try:
            session.close()
        except CleanupError as error:
            errors.extend(error.errors)

    thread = threading.Thread(target=closer)
    thread.start()
    thread.join(2)
    assert len(errors) == 1 and isinstance(errors[0], ThreadError)
    assert unsubscriptions == []
    callbacks[0]()
    assert received == []
    session.close()
    assert unsubscriptions == [threading.get_ident()]
    assert callbacks == []
    owner.close()


def test_literal_ref_property_and_annotation_data_are_not_schema_references():
    literal = {"$ref": "asset://scene/mesh"}
    schema = {
        "type": "object",
        "properties": {"$ref": {"type": "string"}, "asset": {"const": literal}},
        "required": ["$ref", "asset"],
        "default": literal,
        "examples": [literal],
    }
    with ToolSet("literal-data", [Tool("echo", "Echo", schema, lambda **params: params)]) as owner:
        params = {"$ref": "business-value", "asset": literal}
        assert owner.call("echo", params) == params


def test_indirect_remote_schema_reference_never_fetches_or_mutates(monkeypatch):
    from urllib import request

    def forbidden(*args, **kwargs):
        raise AssertionError("Schema resolution must not perform network I/O")

    monkeypatch.setattr(request, "urlopen", forbidden)
    mutations = []
    # A local JSON pointer can enter a literal annotation and then interpret
    # that object as a schema. The resolver must deny that remote reference.
    schema = {
        "type": "object",
        "$ref": "#/default",
        "default": {"$ref": "https://example.com/schema.json"},
    }
    with ToolSet(
        "no-network", [Tool("run", "Run", schema, lambda: mutations.append(True))]
    ) as owner:
        with pytest.raises(ContractError, match="resolution failed"):
            owner.call("run")
    assert mutations == []


def test_pre_draft7_schema_is_rejected_explicitly():
    with pytest.raises(ContractError, match="requires Draft 7"):
        Tool(
            "run",
            "Run",
            {"$schema": "http://json-schema.org/draft-04/schema#", "type": "object"},
            lambda: None,
        )


@pytest.mark.parametrize("close_owner", [True, False])
def test_close_during_subscription_acquisition_retains_failed_cleanup(close_owner):
    callbacks, attempts = [], []

    def subscribe(event, callback):
        callbacks.append(callback)
        (owner if close_owner else session).close()

        def unsubscribe():
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("acquired subscription cleanup failed")
            callbacks.remove(callback)

        return unsubscribe

    owner = ToolSet(
        "acquiring", [Tool("run", "Run", {"type": "object"}, lambda: True)], subscribe=subscribe
    )
    session = owner.borrow()
    with pytest.raises(CleanupError, match="acquired subscription cleanup failed"):
        session.subscribe("changed", lambda: None)
    assert session.closed
    assert len(callbacks) == 1
    owner.close()
    assert attempts == [True, True]
    assert callbacks == []
