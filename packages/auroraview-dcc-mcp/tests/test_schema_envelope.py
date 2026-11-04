"""Validate generated MCP schemas with an ordinary offline client."""

import socket
from types import SimpleNamespace
from urllib import request

import pytest
from auroraview_dcc_mcp import ContractError
from auroraview_dcc_mcp.agent import _input_schema
from auroraview_dcc_mcp.contracts import _validate, schema_validator
from jsonschema import ValidationError, validators

DIALECTS = (
    "http://json-schema.org/draft-07/schema#",
    "https://json-schema.org/draft/2019-09/schema",
    "https://json-schema.org/draft/2020-12/schema",
)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("original_id", [None, "https://schemas.example.test/echo.json"])
def test_envelope_resolves_local_references_without_network(dialect, original_id, network_guard):
    schema = {
        "$schema": dialect,
        "type": "object",
        "definitions": {"name": {"type": "string", "minLength": 1}},
        "properties": {"name": {"$ref": "#/definitions/name"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    if original_id is not None:
        schema["$id"] = original_id
    envelope = _input_schema(SimpleNamespace(id="offline-contract"), {"inputSchema": schema}, 0)
    validator_type = validators.validator_for(envelope)
    validator_type.check_schema(envelope)
    validator = validator_type(envelope)
    validator.validate({"params": {"name": "Cube"}})
    for invalid in ({"name": ""}, {"name": 42}, {}, {"name": "Cube", "extra": True}):
        with pytest.raises(ValidationError):
            validator.validate({"params": invalid})
    assert network_guard == []


@pytest.mark.parametrize("dialect", DIALECTS)
def test_envelope_rejects_indirect_remote_reference_without_network(dialect, network_guard):
    # A local pointer can enter annotation data and turn it into a schema.
    schema = {
        "$schema": dialect,
        "type": "object",
        "properties": {"name": {"$ref": "#/default"}},
        "default": {"$ref": "https://auroraview.invalid/schemas/missing"},
    }
    envelope = _input_schema(SimpleNamespace(id="offline-contract"), {"inputSchema": schema}, 0)
    _, validator = schema_validator(envelope, "discovered input schema")
    with pytest.raises(ContractError, match="schema resolution failed"):
        _validate(validator, {"params": {"name": "Cube"}}, "discovered input")
    assert network_guard == []


@pytest.mark.parametrize("host", ["auroraview.invalid", "localhost", "203.0.113.1", "127.0.0.1"])
def test_unit_guard_blocks_resolution_before_system_resolver(host, network_guard):
    with pytest.raises(pytest.fail.Exception, match="forbidden: getaddrinfo"):
        socket.getaddrinfo(host, 80)
    assert network_guard == [("getaddrinfo", (host, 80))]


@pytest.mark.parametrize(
    "operation",
    ["connect", "connect_ex", "bind", "sendto"]
    + (["sendmsg"] if hasattr(socket.socket, "sendmsg") else []),
)
def test_unit_guard_blocks_connections_and_datagrams(operation, network_guard):
    address = ("203.0.113.1", 80)
    with socket.socket(type=socket.SOCK_DGRAM) as client:
        with pytest.raises(pytest.fail.Exception, match="forbidden: " + operation):
            if operation == "sendto":
                client.sendto(b"test", address)
            elif operation == "sendmsg":
                client.sendmsg([b"test"], [], 0, address)
            else:
                getattr(client, operation)(address)
    assert [name for name, _ in network_guard] == [operation]


def test_unit_guard_blocks_http_before_resolution(network_guard):
    with pytest.raises(pytest.fail.Exception, match="forbidden: urllib"):
        request.urlopen("https://auroraview.invalid/schemas/missing")
    assert [operation for operation, _ in network_guard] == ["urllib"]


@pytest.mark.integration
@pytest.mark.parametrize("host", ["auroraview.invalid", "localhost", "203.0.113.1"])
def test_integration_guard_still_blocks_dns_and_external_addresses(host, network_guard):
    with pytest.raises(pytest.fail.Exception, match="forbidden: getaddrinfo"):
        socket.getaddrinfo(host, 80)
    assert network_guard == [("getaddrinfo", (host, 80))]
