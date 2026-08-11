"""
BaseTool ABC — all ZeroPoint MCP tools inherit from this.

Every concrete tool must implement:
    - name: str class attribute
    - description: str class attribute
    - async execute(params: dict) -> ToolResult
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


###############################################################################
# Result / Error types
###############################################################################

@dataclass
class ToolResult:
    """Successful tool response payload."""
    data: dict[str, Any]
    tool_name: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_mcp(self) -> dict:
        """Serialize to MCP content block list."""
        return {
            "content": [
                {
                    "type": "text",
                    "text": _json_dumps(self.data),
                }
            ],
            "_meta": {
                "tool": self.tool_name,
                "duration_ms": round(self.duration_ms, 2),
                **self.metadata,
            },
        }


class ToolError(Exception):
    """Raised by a tool when execution fails in a known, reportable way."""

    def __init__(self, message: str, code: str = "TOOL_ERROR", data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}

    def to_mcp(self) -> dict:
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": f"[{self.code}] {self}"
                }
            ],
            "_meta": {"error_data": self.data},
        }


###############################################################################
# BaseTool
###############################################################################

class BaseTool(ABC):
    """
    Abstract base class for all ZeroPoint MCP tools.

    Subclasses set class-level attributes and implement `execute()`.
    The server calls `safe_execute()` which adds timing, logging, and
    error normalization — tools should NOT override `safe_execute()`.
    """

    # --- Required class attributes (override in subclass) ---
    name: str = ""
    description: str = ""
    module: str = ""

    def __init__(self, config: dict[str, Any]):
        """
        Args:
            config: The tool's config block from mcp_server_config.yaml,
                    e.g. cfg["tools"]["filesystem"]["config"]
        """
        self.config = config
        self._log = logging.getLogger(f"zeropoint.tools.{self.name}")
        self._setup()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        """Override for one-time initialization logic (non-async)."""

    async def startup(self) -> None:
        """Called once when the server starts. Override for async init."""

    async def shutdown(self) -> None:
        """Called once when the server shuts down. Override for cleanup."""

    # ------------------------------------------------------------------
    # Execution (override this in each tool)
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with the given validated parameters.

        Raise ToolError for expected failures (bad path, device offline…).
        Let unexpected exceptions propagate — safe_execute() catches them.
        """

    # ------------------------------------------------------------------
    # Safe wrapper — called by the server, not overridden by tools
    # ------------------------------------------------------------------

    async def safe_execute(self, params: dict[str, Any]) -> dict:
        """
        Wrap `execute()` with timing, logging, and error normalization.
        Always returns a serializable MCP response dict.
        """
        t0 = time.perf_counter()
        self._log.debug("Invoking %s with params=%s", self.name, list(params.keys()))
        try:
            result = await self.execute(params)
            result.tool_name = self.name
            result.duration_ms = (time.perf_counter() - t0) * 1000
            self._log.info(
                "%s completed in %.1f ms", self.name, result.duration_ms
            )
            return result.to_mcp()
        except ToolError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._log.warning(
                "%s raised ToolError in %.1f ms: [%s] %s",
                self.name, elapsed, exc.code, exc,
            )
            return exc.to_mcp()
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            self._log.error(
                "%s unexpected error in %.1f ms: %s",
                self.name, elapsed, exc, exc_info=True,
            )
            return ToolError(
                f"Unexpected error in {self.name}: {exc}",
                code="INTERNAL_ERROR",
            ).to_mcp()

    # ------------------------------------------------------------------
    # Param helpers
    # ------------------------------------------------------------------

    @staticmethod
    def require(params: dict, *keys: str) -> None:
        """Raise ToolError if any required key is missing."""
        missing = [k for k in keys if k not in params or params[k] is None]
        if missing:
            raise ToolError(
                f"Missing required parameter(s): {', '.join(missing)}",
                code="MISSING_PARAMS",
            )

    @staticmethod
    def get(params: dict, key: str, default: Any = None) -> Any:
        return params.get(key, default)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


###############################################################################
# Utility
###############################################################################

def _json_dumps(obj: Any) -> str:
    import json

    class _Enc(json.JSONEncoder):
        def default(self, o: Any):
            try:
                return super().default(o)
            except TypeError:
                return str(o)

    return json.dumps(obj, indent=2, cls=_Enc)

