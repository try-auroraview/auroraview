"""Explicit, synchronous business contracts shared by UI and MCP callers."""

import inspect
import json
import re
from typing import Any, Callable, Dict, Mapping, Optional

from jsonschema import Draft7Validator, validators


class ContractError(ValueError):
    """A declaration, parameter or result violates a tool contract."""


class ClosedError(RuntimeError):
    """The owner or consumer lease has been released."""


class ThreadError(RuntimeError):
    """A host operation reached a thread other than its registered owner."""


class CleanupError(RuntimeError):
    """Some owned resources remain and close() may be retried."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__("; ".join(str(error) for error in self.errors))


def identifier(value, label, dotted=False):
    pattern = r"[A-Za-z][A-Za-z0-9_.-]{0,63}" if dotted else r"[A-Za-z][A-Za-z0-9_-]{0,63}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ContractError("{} must be a 1-64 character identifier".format(label))
    return value


def json_value(value, label):
    """Detach values at the transport boundary and reject non-JSON results."""

    def check_keys(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ContractError("{} contains a non-string object key".format(label))
                check_keys(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check_keys(child)

    try:
        check_keys(value)
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as error:
        raise ContractError("{} must be JSON serializable: {}".format(label, error)) from error


def schema_validator(schema, label):
    if not isinstance(schema, Mapping):
        raise ContractError("{} must be a JSON Schema object".format(label))
    schema = json_value(dict(schema), label)

    dialect = schema.get("$schema", "http://json-schema.org/draft-07/schema#")
    supported = {
        "http://json-schema.org/draft-07/schema#",
        "https://json-schema.org/draft/2019-09/schema",
        "https://json-schema.org/draft/2020-12/schema",
    }
    if dialect not in supported:
        raise ContractError("{} requires Draft 7, 2019-09 or 2020-12".format(label))
    _check_schema_refs(schema, label)
    validator = validators.validator_for(schema, default=Draft7Validator)
    try:
        validator.check_schema(schema)
    except Exception as error:
        raise ContractError("Invalid {}: {}".format(label, error)) from error

    def deny_remote(uri):
        raise ContractError("{} permits only local schema references: {}".format(label, uri))

    if "registry" in inspect.signature(validator).parameters:
        from referencing import Registry

        instance = validator(schema, registry=Registry(retrieve=deny_remote))
    else:
        # jsonschema <=4.17 is the Python 3.7 implementation. Its public
        # resolver hook also blocks references reached indirectly via a local
        # JSON pointer into an otherwise literal annotation value.
        class LocalResolver(validators.RefResolver):
            def resolve_remote(self, uri):
                return deny_remote(uri)

        instance = validator(schema, resolver=LocalResolver.from_schema(schema))
    return schema, instance


def _check_schema_refs(schema, label):
    """Inspect schema positions, never object-property names or literal data."""
    if not isinstance(schema, dict):
        return
    for keyword in ("$ref", "$dynamicRef", "$recursiveRef"):
        if keyword in schema:
            reference = schema[keyword]
            if not isinstance(reference, str) or not reference.startswith("#"):
                raise ContractError("{} permits only local schema references".format(label))
    for keyword in ("properties", "patternProperties", "definitions", "$defs", "dependentSchemas"):
        children = schema.get(keyword, {})
        if isinstance(children, dict):
            for child in children.values():
                _check_schema_refs(child, label)
    for keyword in (
        "additionalProperties",
        "additionalItems",
        "contains",
        "not",
        "if",
        "then",
        "else",
        "propertyNames",
        "unevaluatedProperties",
        "unevaluatedItems",
        "contentSchema",
    ):
        _check_schema_refs(schema.get(keyword), label)
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        children = schema.get(keyword, [])
        if isinstance(children, list):
            for child in children:
                _check_schema_refs(child, label)
    items = schema.get("items")
    for child in items if isinstance(items, list) else [items]:
        _check_schema_refs(child, label)
    dependencies = schema.get("dependencies", {})
    if isinstance(dependencies, dict):
        for child in dependencies.values():
            _check_schema_refs(child, label)


def _validate(validator, value, label):
    try:
        error = next(validator.iter_errors(value), None)
    except Exception as error:
        raise ContractError("{} schema resolution failed: {}".format(label, error)) from error
    if error is not None:
        raise ContractError("{}: {}".format(label, error.message))


class Tool:
    """One explicitly registered keyword-only operation.

    ``output_schema`` describes the final response. With ``readback``, that
    response is ``{"result": handler(**params), "scene": readback()}``.
    Both callbacks run synchronously in the same owner-thread invocation.
    """

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("Tool declarations are immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Mapping[str, Any],
        handler: Callable[..., Any],
        *,
        output_schema: Optional[Mapping[str, Any]] = None,
        readback: Optional[Callable[[], Any]] = None,
        read_only: bool = False,
        destructive: bool = True,
        idempotent: bool = False,
    ) -> None:
        self.name = identifier(name, "Tool name", dotted=True)
        if not isinstance(description, str) or not description.strip():
            raise ContractError("Tool description must be non-empty")
        self.description = description
        for label, callback in (("handler", handler), ("readback", readback)):
            if callback is not None and (
                not callable(callback) or inspect.iscoroutinefunction(callback)
            ):
                raise ContractError("{} must be synchronous and callable".format(label))
        if handler is None:
            raise ContractError("handler is required")
        if any(type(flag) is not bool for flag in (read_only, destructive, idempotent)):
            raise ContractError("Tool annotations must be booleans")
        if read_only and destructive:
            raise ContractError("A read-only tool cannot be destructive")
        self.read_only = read_only
        self.destructive = destructive
        self.idempotent = idempotent
        schema, self._input_validator = schema_validator(input_schema, "input_schema")
        if schema.get("type") != "object":
            raise ContractError("input_schema must declare type: object")
        self._input_json = json.dumps(schema)
        self._output_json = None
        self._output_validator = None
        if readback is not None and output_schema is None:
            raise ContractError("A readback tool requires an output_schema for result and scene")
        if output_schema is not None:
            schema, self._output_validator = schema_validator(output_schema, "output_schema")
            if readback is not None and (
                schema.get("type") != "object"
                or not {"result", "scene"}.issubset(schema.get("required", []))
                or not {"result", "scene"}.issubset(schema.get("properties", {}))
            ):
                raise ContractError(
                    "Readback output_schema must require result and scene properties"
                )
            self._output_json = json.dumps(schema)
        self._handler = handler
        self._readback = readback
        self._sealed = True

    @property
    def input_schema(self) -> Dict[str, Any]:
        return json.loads(self._input_json)

    @property
    def output_schema(self) -> Optional[Dict[str, Any]]:
        return json.loads(self._output_json) if self._output_json is not None else None

    def descriptor(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "idempotentHint": self.idempotent,
            },
        }
        if self.output_schema is not None:
            result["outputSchema"] = self.output_schema
        return result

    def invoke(self, params):
        params = json_value(params, "Tool parameters")
        _validate(self._input_validator, params, "{} parameters".format(self.name))
        result = self._handler(**params)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise ContractError("Tool handlers must return synchronously")
        if self._readback is not None:
            scene = self._readback()
            if inspect.isawaitable(scene):
                if inspect.iscoroutine(scene):
                    scene.close()
                raise ContractError("Scene readback must return synchronously")
            result = {"result": result, "scene": scene}
        result = json_value(result, "Tool result")
        if self._output_validator is not None:
            _validate(self._output_validator, result, "{} result".format(self.name))
        return result
