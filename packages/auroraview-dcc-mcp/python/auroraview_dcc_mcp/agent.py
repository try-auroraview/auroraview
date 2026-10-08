"""Borrow existing DCC-MCP services through their public skill interface."""

import functools
import json
import tempfile
import threading
import weakref
from pathlib import Path

from . import _registry
from .contracts import ClosedError, ContractError
from .runtime import ToolSession

_attach_lock = threading.RLock()


class AgentBinding(ToolSession):
    """One owned skill on a borrowed server, without starting or stopping it.

    Core unload removes the skill's executable actions but retains its catalog
    metadata. A retained or reloaded stale declaration cannot invoke a closed
    binding because every script resolves its revoked process-local token.

    MCP arguments use ``{"params": <business parameters>}``. The nested object
    preserves business keys that Core reserves at its script entry boundary;
    UI and local sessions continue accepting the business parameters directly.
    """

    def __init__(self, owner, server):
        super().__init__(owner)
        self._server = weakref.ref(server)
        self.skill_name = owner.name
        self.method_names = {
            tool["name"]: "{}__{}".format(owner.name, tool["name"].replace(".", "_"))
            for tool in owner.list_tools()
        }
        self.tool_names = tuple(self.method_names.values())
        self._directory = None
        self._skill_path = None
        self._loaded = False
        self._hook = None

    @classmethod
    def attach(cls, owner, server):
        try:
            from dcc_mcp_core import SkillMetadata, ToolDeclaration
            from dcc_mcp_core.server_base import DccServerBase
        except ImportError as error:
            raise ContractError("Install auroraview-dcc-mcp[core] to attach a server") from error
        if not isinstance(server, DccServerBase):
            raise ContractError("attach requires an existing DccServerBase")
        descriptors = owner.list_tools()
        names = [
            "{}__{}".format(owner.name, tool["name"].replace(".", "_")) for tool in descriptors
        ]
        # Published Core follows the 64-character client-compatible MCP policy.
        if any(len(name) > 64 for name in names):
            raise ContractError("Combined MCP tool names must not exceed 64 characters")
        if len(set(names)) != len(names):
            raise ContractError("Tool names collide after MCP dot-to-underscore conversion")
        with _attach_lock:
            if (
                server.get_skill(owner.name) is not None
                or server.get_skill_info(owner.name) is not None
            ):
                raise ContractError("Skill name already exists: {}".format(owner.name))
            registry = server.registry
            if registry is not None:
                for tool_name in names:
                    if registry.get_action(tool_name) is not None:
                        raise ContractError("Tool name already exists: {}".format(tool_name))
            binding = owner._retain(cls(owner, server))
            try:
                binding._directory = tempfile.TemporaryDirectory(prefix="auroraview-tools-")
                root = Path(binding._directory.name)
                binding._skill_path = root
                scripts = root / "scripts"
                scripts.mkdir()
                declarations = []
                for index, descriptor in enumerate(descriptors):
                    script = scripts / "tool_{}.py".format(index)
                    script.write_text(
                        "from auroraview_dcc_mcp._registry import invoke\n\n"
                        "def main(params):\n"
                        "    return invoke({!r}, {!r}, params)\n".format(
                            binding.token, descriptor["name"]
                        ),
                        encoding="utf-8",
                    )
                    annotations = descriptor["annotations"]
                    declaration = ToolDeclaration(
                        name=binding.tool_names[index],
                        description=descriptor["description"],
                        input_schema=json.dumps(_input_schema(owner, descriptor, index)),
                        output_schema=(
                            json.dumps(descriptor["outputSchema"])
                            if "outputSchema" in descriptor
                            else None
                        ),
                        source_file=str(script),
                        read_only=annotations["readOnlyHint"],
                        destructive=annotations["destructiveHint"],
                        idempotent=annotations["idempotentHint"],
                        thread_affinity="main",
                        enforce_thread_affinity=True,
                        requires_in_process=True,
                    )
                    declarations.append(declaration)
                skill = SkillMetadata(
                    name=owner.name,
                    description=owner.description,
                    dcc=owner.dcc,
                    skill_path=str(root),
                    tools=declarations,
                    scripts=[str(script.relative_to(root)) for script in scripts.iterdir()],
                )
                # Set before the call because a failing Core load can have
                # partially registered metadata or actions that we must revoke.
                binding._loaded = True
                if server.load_skill_object(skill) is False:
                    raise ContractError("DCC-MCP refused to load skill: {}".format(owner.name))
                binding._loaded = True
                if binding.closed or owner.closed:
                    raise ClosedError("The tool owner closed while its skill was loading")
                binding._hook = functools.partial(_registry.close, binding.token)
                server.register_quit_hook(binding._hook)
            except Exception as attach_error:
                try:
                    binding.close()
                except Exception as cleanup_error:
                    raise cleanup_error from attach_error
                raise
        return binding

    def _cleanup(self):
        errors = super()._cleanup()
        with _attach_lock:
            return self._cleanup_skill(errors)

    def _cleanup_skill(self, errors):
        server = self._server()
        if self._loaded:
            try:
                if server is not None:
                    skill = server.get_skill(self.skill_name)
                    if skill is not None and Path(skill.skill_path) != self._skill_path:
                        raise ContractError(
                            "Owned skill was replaced; refusing foreign skill cleanup"
                        )
                    if (
                        skill is not None or server.is_skill_loaded(self.skill_name)
                    ) and server.unload_skill(self.skill_name) is False:
                        raise RuntimeError(
                            "DCC-MCP failed to unload skill: {}".format(self.skill_name)
                        )
                self._loaded = False
            except Exception as error:
                errors.append(error)
        if self._hook is not None:
            try:
                if server is not None:
                    server.unregister_quit_hook(self._hook)
                self._hook = None
            except Exception as error:
                errors.append(error)
        if not self._loaded and self._hook is None and self._directory is not None:
            try:
                self._directory.cleanup()
                self._directory = None
            except Exception as error:
                errors.append(error)
        return errors


def _input_schema(owner, descriptor, index):
    # Keep fragment references rooted in the business schema when embedding it
    # in the outer MCP transport envelope. Tool contracts require Draft 7+.
    schema = descriptor["inputSchema"]
    schema.setdefault("$schema", "http://json-schema.org/draft-07/schema#")
    schema["$id"] = "https://auroraview.invalid/schemas/{}/{}".format(owner.id, index)
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"params": schema},
        "required": ["params"],
        "additionalProperties": False,
    }
