"""
Tool Registry — loads tool_registration.json, instantiates tool classes,
and routes incoming MCP tool-call requests to the correct handler.

Hardening (2026-09-11):
 - Instance cache (_instances) maintained directly in registry — no more
   object.__setattr__ injection onto tool objects.
 - _register_tool() failures are collected and emitted as a visible WARNING
   summary after load() completes, rather than silently skipping.
 - O(n) _tool_instances() rebuild removed; O(1) dict lookup used instead.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from zeropoint.tools.base import BaseTool, ToolError

logger = logging.getLogger(__name__)


###############################################################################
# Registry
###############################################################################

class ToolRegistry:
    """
    Loads all enabled tools from mcp_server_config.yaml and the
    tool_registration.json manifest, then routes call() requests.

    Usage:
        registry = ToolRegistry(config_path="config/mcp_server_config.yaml")
        registry.load()
        await registry.startup()

        response = await registry.call("filesystem_read", {"path": "/workspace/zeropoint"})

        await registry.shutdown()
    """

    def __init__(self, config_path: str | Path):
        self._cfg_path = Path(config_path)
        self._cfg: dict[str, Any] = {}
        self._manifest: list[dict] = []

        # tool_name -> BaseTool instance
        self._tools: dict[str, BaseTool] = {}
        # instance_key -> BaseTool instance (one per module class, shared across tool names)
        self._instances: dict[str, BaseTool] = {}
        # module_name -> config dict
        self._module_cfg: dict[str, dict] = {}
        # tool_name -> module_name
        self._tool_module: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Parse config + manifest and instantiate all enabled tools.

        After loading, a WARNING is emitted if any tools failed to register,
        so failures are never silently swallowed.
        """
        self._cfg = yaml.safe_load(self._cfg_path.read_text())

        manifest_path = self._cfg_path.parent / "tool_registration.json"
        if not manifest_path.exists():
            manifest_path = self._cfg_path.parent.parent / "tool_registration.json"
        self._manifest = json.loads(manifest_path.read_text()).get("tools", [])

        tools_cfg: dict[str, Any] = self._cfg.get("tools", {})
        for module_name, module_cfg in tools_cfg.items():
            if not module_cfg.get("enabled", True):
                logger.info("Module '%s' is disabled — skipping.", module_name)
                continue
            self._module_cfg[module_name] = module_cfg.get("config", {})

        failed: list[str] = []
        for tool_spec in self._manifest:
            module_name = tool_spec.get("module", "")
            if module_name not in self._module_cfg:
                logger.debug(
                    "Tool '%s' module '%s' is disabled — skipping.",
                    tool_spec["name"], module_name,
                )
                continue
            ok = self._register_tool(tool_spec, self._module_cfg[module_name])
            if not ok:
                failed.append(tool_spec.get("name", "<unknown>"))

        logger.info(
            "ToolRegistry loaded: %d tools across %d modules.",
            len(self._tools), len(self._module_cfg),
        )
        if failed:
            logger.warning(
                "TOOL LOAD FAILURES (%d): %s — these tools will not be available.",
                len(failed), ", ".join(failed),
            )

    def _register_tool(self, spec: dict, module_config: dict) -> bool:
        """Import the tool class, cache the instance, and register the tool.

        Returns True on success, False on failure (caller logs the summary).
        """
        tool_name = spec["name"]
        py_module = spec.get("module", "")
        py_class = spec.get("class", "")

        tools_cfg = self._cfg.get("tools", {})
        cfg_block = tools_cfg.get(py_module, {})
        full_module = cfg_block.get("module") or f"zeropoint.tools.{py_module}"
        class_name = cfg_block.get("class") or py_class or _snake_to_camel(py_module) + "Tool"

        try:
            mod = importlib.import_module(full_module)
            cls: type[BaseTool] = getattr(mod, class_name)
        except (ImportError, AttributeError) as exc:
            logger.error(
                "Cannot load tool '%s' from %s.%s: %s",
                tool_name, full_module, class_name, exc,
            )
            return False

        # One instance per module class — shared across all tool names in that module.
        # Instance cache lives in self._instances (keyed by full_module.class_name).
        instance_key = f"{full_module}.{class_name}"
        if instance_key not in self._instances:
            self._instances[instance_key] = cls(config=module_config)

        self._tools[tool_name] = self._instances[instance_key]
        self._tool_module[tool_name] = py_module
        logger.debug("Registered tool '%s' → %s", tool_name, self._instances[instance_key])
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Call startup() on each unique tool instance."""
        for instance in self._instances.values():
            await instance.startup()
        logger.info("All tools started up.")

    async def shutdown(self) -> None:
        """Call shutdown() on each unique tool instance."""
        for instance in self._instances.values():
            await instance.shutdown()
        logger.info("All tools shut down.")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    async def call(self, tool_name: str, params: dict[str, Any]) -> dict:
        """
        Route an MCP tool call to the correct BaseTool instance.
        Returns an MCP-formatted response dict (always — errors included).
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolError(
                f"Unknown tool: '{tool_name}'. "
                f"Available: {sorted(self._tools.keys())}",
                code="UNKNOWN_TOOL",
            ).to_mcp()

        module_name = self._tool_module.get(tool_name, "")
        prefix = f"{module_name}_"
        operation = (
            tool_name[len(prefix):]
            if module_name and tool_name.startswith(prefix)
            else tool_name
        )
        tool_params = dict(params)
        if operation:
            tool_params["_op"] = operation
        return await tool.safe_execute(tool_params)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """Return MCP-formatted tool descriptors for all registered tools."""
        return [
            {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "inputSchema": spec.get("input_schema", {}),
            }
            for spec in self._manifest
            if spec["name"] in self._tools
        ]

    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


###############################################################################
# Helpers
###############################################################################

def _snake_to_camel(s: str) -> str:
    return "".join(word.capitalize() for word in s.split("_"))
