"""
Tool Registry — loads tool_registration.json, instantiates tool classes,
and routes incoming MCP tool-call requests to the correct handler.
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
        # module_name -> config dict (from mcp_server_config.yaml tools section)
        self._module_cfg: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Parse config + manifest and instantiate all enabled tools."""
        self._cfg = yaml.safe_load(self._cfg_path.read_text())

        manifest_path = self._cfg_path.parent / "tool_registration.json"
        if not manifest_path.exists():
            # Fall back to repo root
            manifest_path = self._cfg_path.parent.parent / "tool_registration.json"
        self._manifest = json.loads(manifest_path.read_text()).get("tools", [])

        tools_cfg: dict[str, Any] = self._cfg.get("tools", {})
        for module_name, module_cfg in tools_cfg.items():
            if not module_cfg.get("enabled", True):
                logger.info("Module '%s' is disabled — skipping.", module_name)
                continue
            self._module_cfg[module_name] = module_cfg.get("config", {})

        for tool_spec in self._manifest:
            module_name = tool_spec.get("module", "")
            if module_name not in self._module_cfg:
                logger.debug(
                    "Tool '%s' module '%s' is disabled — skipping.",
                    tool_spec["name"], module_name,
                )
                continue
            self._register_tool(tool_spec, self._module_cfg[module_name])

        logger.info(
            "ToolRegistry loaded: %d tools across %d modules.",
            len(self._tools), len(self._module_cfg),
        )

    def _register_tool(self, spec: dict, module_config: dict) -> None:
        """Import the tool class and store an instance."""
        tool_name = spec["name"]
        py_module = spec.get("module", "")
        py_class = spec.get("class", "")

        # Resolve Python module + class from the manifest spec or config block
        # Config block wins if it has explicit module/class keys.
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
            return

        # One instance per module (shared across all tools in that module).
        instance_key = f"{full_module}.{class_name}"
        if instance_key not in self._tool_instances():
            instance = cls(config=module_config)
            # Store under instance key so multiple tool names can share it.
            object.__setattr__(instance, "_instance_key", instance_key)
        else:
            instance = self._tool_instances()[instance_key]

        self._tools[tool_name] = instance
        logger.debug("Registered tool '%s' → %s", tool_name, instance)

    def _tool_instances(self) -> dict[str, BaseTool]:
        """Reverse map: instance_key -> BaseTool, derived from self._tools."""
        seen: dict[str, BaseTool] = {}
        for inst in self._tools.values():
            key = getattr(inst, "_instance_key", id(inst))
            seen[key] = inst
        return seen

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Call startup() on each unique tool instance."""
        seen: set[int] = set()
        for tool in self._tools.values():
            if id(tool) not in seen:
                await tool.startup()
                seen.add(id(tool))
        logger.info("All tools started up.")

    async def shutdown(self) -> None:
        """Call shutdown() on each unique tool instance."""
        seen: set[int] = set()
        for tool in self._tools.values():
            if id(tool) not in seen:
                await tool.shutdown()
                seen.add(id(tool))
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
        _, separator, operation = tool_name.partition("_")
        tool_params = dict(params)
        if separator and operation:
            tool_params["_op"] = operation
        return await tool.safe_execute(tool_params)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_tools(self) -> list[dict]:
        """Return MCP-formatted tool descriptors for all registered tools."""
        out = []
        for spec in self._manifest:
            if spec["name"] in self._tools:
                out.append({
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "inputSchema": spec.get("input_schema", {}),
                })
        return out

    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


###############################################################################
# Helpers
###############################################################################

def _snake_to_camel(s: str) -> str:
    return "".join(word.capitalize() for word in s.split("_"))

