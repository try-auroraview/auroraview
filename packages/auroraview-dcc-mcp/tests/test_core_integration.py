"""Published Core and HTTP/MCP integration; no native-host acceptance claim."""

import importlib.util
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dcc_mcp_core
import pytest
import requests
from auroraview_dcc_mcp import CleanupError, ClosedError, ContractError, Tool, ToolSet
from dcc_mcp_core import (  # noqa: E402
    BridgeExecution,
    DccServerOptions,
    ExecutionOptions,
    GatewayOptions,
    HostExecutionBridge,
    HostUiDispatcherBase,
    ObservabilityOptions,
)
from dcc_mcp_core.server_base import DccServerBase  # noqa: E402
from jsonschema import ValidationError, validators


class Pump(HostUiDispatcherBase):
    def poke_host_pump(self):
        pass


@pytest.fixture
def service(tmp_path):
    expected_version = os.environ.get("AURORAVIEW_TEST_CORE_VERSION")
    if expected_version:
        assert dcc_mcp_core.__version__ == expected_version
    pump = Pump()
    server = DccServerBase(
        DccServerOptions(
            dcc_name="auroraview_contract_test",
            builtin_skills_dir=tmp_path,
            port=0,
            gateway=GatewayOptions(port=0, enable_failover=False),
            observability=ObservabilityOptions(
                enable_file_logging=False, enable_job_persistence=False, enable_telemetry=False
            ),
            execution=ExecutionOptions(mode=BridgeExecution(HostExecutionBridge(dispatcher=pump))),
        )
    )
    handle = server.start(install_atexit_hook=False)
    yield server, handle.mcp_url(), pump
    server.stop()


def rpc(url, pump, method, params=None):
    def post():
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=10,
        )
        response.raise_for_status()
        if response.headers.get("Content-Type", "").startswith("text/event-stream"):
            return json.loads(
                next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
            )
        return response.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(post)
        deadline = time.monotonic() + 12
        while not future.done() and time.monotonic() < deadline:
            pump.drain_queue(8)
            time.sleep(0.002)
        return future.result(timeout=1)


def result_value(response):
    assert "error" not in response, response
    result = response["result"]
    assert not result.get("isError", False), result
    if "structuredContent" in result:
        return result["structuredContent"]
    return json.loads(result["content"][0]["text"])


def list_mcp_tools(url, pump):
    tools, cursor = [], None
    for _ in range(100):
        result = rpc(url, pump, "tools/list", {"cursor": cursor} if cursor else {})["result"]
        tools.extend(result["tools"])
        cursor = result.get("nextCursor")
        if not cursor:
            return tools
    raise AssertionError("MCP tool discovery exceeded 100 pages")


def test_mcp_discovery_execution_readback_and_borrowed_service_cleanup(service):
    server, url, pump = service
    assert dcc_mcp_core.__version__
    owner_thread = threading.get_ident()
    scene, threads = [], []

    def create(name):
        threads.append(threading.get_ident())
        scene.append(name)
        return {"created": name}

    def readback():
        threads.append(threading.get_ident())
        return {"objects": list(scene)}

    owner = ToolSet(
        "studio-scene",
        [
            Tool(
                "scene.create",
                "Create an object and read back scene state",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                create,
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "object"}, "scene": {"type": "object"}},
                    "required": ["result", "scene"],
                },
                readback=readback,
            )
        ],
        dcc="auroraview_contract_test",
    )
    binding = owner.attach(server)
    assert binding.method_names == {"scene.create": "studio-scene__scene_create"}
    skill = server.get_skill(binding.skill_name)
    assert skill is not None
    assert skill.dcc == "auroraview_contract_test"
    assert skill.tools[0].requires_in_process is True
    script = Path(skill.tools[0].source_file)
    assert script.is_file()
    spec = importlib.util.spec_from_file_location("stale_skill_test", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {tool["name"] for tool in list_mcp_tools(url, pump)}
    assert set(binding.tool_names).issubset(names), sorted(names)
    initialized = rpc(
        url,
        pump,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "auroraview-contract-test", "version": "1.0.0"},
        },
    )
    assert initialized["result"]["serverInfo"]
    value = result_value(
        rpc(
            url,
            pump,
            "tools/call",
            {"name": binding.tool_names[0], "arguments": {"params": {"name": "Cube"}}},
        )
    )
    assert value == {"result": {"created": "Cube"}, "scene": {"objects": ["Cube"]}}
    assert threads == [owner_thread, owner_thread]
    assert scene == ["Cube"]
    with pytest.raises(ContractError, match="already exists"):
        owner.attach(server)
    binding.close()
    assert not script.exists()
    assert not server.is_skill_loaded(binding.skill_name)
    assert server.get_skill(binding.skill_name) is not None, (
        "Core retains unloaded catalog metadata"
    )
    with pytest.raises(ClosedError):
        module.main(params={"name": "stale"})
    names = {tool["name"] for tool in list_mcp_tools(url, pump)}
    assert not set(binding.tool_names).intersection(names)
    assert owner.call("scene.create", {"name": "UI-still-open"})["scene"]["objects"] == [
        "Cube",
        "UI-still-open",
    ]
    owner.close()


def test_mcp_name_collision_or_overflow_refuses_registration(service):
    server, _, _ = service
    for owner in (
        ToolSet(
            "collision",
            [
                Tool("scene.create", "Create", {"type": "object"}, lambda: None),
                Tool("scene_create", "Create alias", {"type": "object"}, lambda: None),
            ],
        ),
        ToolSet("a" * 64, [Tool("run", "Run", {"type": "object"}, lambda: None)]),
    ):
        with pytest.raises(ContractError, match="collide|64 characters"):
            owner.attach(server)
        assert server.get_skill(owner.name) is None
        owner.close()


def test_mcp_envelope_preserves_shared_schema_validation_before_mutation(service):
    server, url, pump = service
    mutations = []

    def mutate(**params):
        mutations.append(params)
        return True

    owner = ToolSet(
        "reserved-params",
        [
            Tool(
                "run",
                "Run only valid business arguments",
                {"type": "object", "propertyNames": {"not": {"pattern": "^_"}}},
                mutate,
            )
        ],
    )
    binding = owner.attach(server)
    with pytest.raises(ContractError):
        owner.call("run", {"_private": "value"})
    response = rpc(
        url,
        pump,
        "tools/call",
        {
            "name": binding.tool_names[0],
            "arguments": {"params": {"_private": "value"}},
        },
    )
    assert response.get("error") is not None or response.get("result", {}).get("isError") is True, (
        response
    )
    assert mutations == []
    owner.close()


def test_mcp_envelope_preserves_underscore_business_keys(service):
    server, url, pump = service
    with ToolSet(
        "business-keys",
        [
            Tool(
                "echo",
                "Echo declared business parameters",
                {
                    "type": "object",
                    "properties": {"_token": {"type": "string"}},
                    "required": ["_token"],
                    "additionalProperties": False,
                },
                lambda **params: params,
            )
        ],
    ) as owner:
        binding = owner.attach(server)
        params = {"_token": "business-value"}
        assert owner.call("echo", params) == params
        assert (
            result_value(
                rpc(
                    url,
                    pump,
                    "tools/call",
                    {
                        "name": binding.tool_names[0],
                        "arguments": {"params": params},
                    },
                )
            )
            == params
        )


def test_cleanup_failure_revokes_token_then_retries_only_owned_skill(service, monkeypatch):
    server, url, pump = service
    owner = ToolSet("cleanup-test", [Tool("run", "Run", {"type": "object"}, lambda: True)])
    binding = owner.attach(server)
    original = server.unload_skill
    attempts = []

    def unload(name):
        attempts.append(name)
        return False if len(attempts) == 1 else original(name)

    monkeypatch.setattr(server, "unload_skill", unload)
    with pytest.raises(CleanupError, match="failed to unload"):
        binding.close()
    with pytest.raises(ClosedError):
        binding.call("run")
    binding.close()
    assert attempts == ["cleanup-test", "cleanup-test"]
    assert "result" in rpc(url, pump, "tools/list"), "Borrowed server must remain available"
    owner.close()


@pytest.mark.parametrize(
    "dialect",
    [
        "http://json-schema.org/draft-07/schema#",
        "https://json-schema.org/draft/2019-09/schema",
        "https://json-schema.org/draft/2020-12/schema",
    ],
)
def test_discovered_envelope_preserves_local_schema_references(service, dialect):
    server, url, pump = service
    mutations = []

    def echo(name):
        mutations.append(name)
        return name

    schema = {
        "$schema": dialect,
        "type": "object",
        "definitions": {"name": {"type": "string", "minLength": 1}},
        "properties": {"name": {"$ref": "#/definitions/name"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    with ToolSet("schema-refs", [Tool("echo", "Echo a name", schema, echo)]) as owner:
        binding = owner.attach(server)
        tools = list_mcp_tools(url, pump)
        discovered = next((tool for tool in tools if tool["name"] == binding.tool_names[0]), None)
        assert discovered is not None, json.dumps(
            {"names": [tool["name"] for tool in tools], "expected": binding.tool_names}
        )
        envelope = discovered["inputSchema"]
        validator = validators.validator_for(envelope)(envelope)
        validator.validate({"params": {"name": "Cube"}})
        with pytest.raises(ValidationError):
            validator.validate({"params": {"name": ""}})
        with pytest.raises(ContractError):
            owner.call("echo", {"name": ""})
        invalid = rpc(
            url,
            pump,
            "tools/call",
            {"name": binding.tool_names[0], "arguments": {"params": {"name": ""}}},
        )
        assert invalid.get("error") or invalid.get("result", {}).get("isError"), invalid
        assert mutations == []
        assert (
            result_value(
                rpc(
                    url,
                    pump,
                    "tools/call",
                    {
                        "name": binding.tool_names[0],
                        "arguments": {"params": {"name": "Cube"}},
                    },
                )
            )
            == "Cube"
        )
        assert mutations == ["Cube"]


def test_close_during_skill_load_cannot_resurrect_actions(service, monkeypatch):
    server, url, pump = service
    owner = ToolSet("closing-load", [Tool("run", "Run", {"type": "object"}, lambda: True)])
    original = server.load_skill_object

    def load(skill):
        owner.close()
        return original(skill)

    monkeypatch.setattr(server, "load_skill_object", load)
    with pytest.raises(ClosedError, match="closed while"):
        owner.attach(server)
    names = {tool["name"] for tool in list_mcp_tools(url, pump)}
    assert "closing-load__run" not in names
    assert not server.is_skill_loaded("closing-load")
    owner.close()
