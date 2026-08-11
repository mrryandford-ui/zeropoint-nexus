"""
Unit tests — BaseTool ABC
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

# We test via a concrete subclass
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.tools.base import BaseTool, ToolResult, ToolError


# ── Concrete stub for testing ──────────────────────────────────────────────────

class EchoTool(BaseTool):
    name = "echo"
    module = "echo"
    description = "Returns whatever you pass in."

    async def execute(self, params):
        if params.get("fail"):
            raise ToolError("deliberate failure", code="TEST_ERROR")
        if params.get("crash"):
            raise RuntimeError("unexpected crash")
        return ToolResult(data={"echo": params.get("value", "")})


@pytest.fixture
def tool():
    return EchoTool(config={})


# ── ToolResult ─────────────────────────────────────────────────────────────────

class TestToolResult:
    def test_to_mcp_structure(self):
        r = ToolResult(data={"key": "val"}, tool_name="test", duration_ms=12.5)
        mcp = r.to_mcp()
        assert "content" in mcp
        assert mcp["content"][0]["type"] == "text"
        assert "_meta" in mcp
        assert mcp["_meta"]["tool"] == "test"
        assert mcp["_meta"]["duration_ms"] == 12.5

    def test_json_serialization(self):
        r = ToolResult(data={"items": [1, 2, 3], "nested": {"a": True}})
        mcp = r.to_mcp()
        import json
        parsed = json.loads(mcp["content"][0]["text"])
        assert parsed["items"] == [1, 2, 3]


# ── ToolError ──────────────────────────────────────────────────────────────────

class TestToolError:
    def test_to_mcp_is_error(self):
        err = ToolError("something went wrong", code="BAD_THING")
        mcp = err.to_mcp()
        assert mcp["isError"] is True
        assert "BAD_THING" in mcp["content"][0]["text"]
        assert "something went wrong" in mcp["content"][0]["text"]

    def test_data_field(self):
        err = ToolError("msg", code="X", data={"detail": 42})
        assert err.data == {"detail": 42}


# ── BaseTool.safe_execute ──────────────────────────────────────────────────────

class TestSafeExecute:
    @pytest.mark.asyncio
    async def test_success_path(self, tool):
        result = await tool.safe_execute({"value": "hello"})
        assert "content" in result
        import json
        data = json.loads(result["content"][0]["text"])
        assert data["echo"] == "hello"

    @pytest.mark.asyncio
    async def test_tool_error_returns_is_error(self, tool):
        result = await tool.safe_execute({"fail": True})
        assert result["isError"] is True
        assert "TEST_ERROR" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_internal_error(self, tool):
        result = await tool.safe_execute({"crash": True})
        assert result["isError"] is True
        assert "INTERNAL_ERROR" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_duration_recorded(self, tool):
        result = await tool.safe_execute({"value": "x"})
        assert result["_meta"]["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_tool_name_set(self, tool):
        result = await tool.safe_execute({"value": "x"})
        assert result["_meta"]["tool"] == "echo"


# ── require() helper ───────────────────────────────────────────────────────────

class TestRequireHelper:
    def test_raises_on_missing_key(self, tool):
        with pytest.raises(ToolError) as exc_info:
            tool.require({"a": 1}, "a", "b")
        assert "b" in str(exc_info.value)
        assert exc_info.value.code == "MISSING_PARAMS"

    def test_passes_when_all_present(self, tool):
        tool.require({"a": 1, "b": 2}, "a", "b")  # should not raise

    def test_raises_on_none_value(self, tool):
        with pytest.raises(ToolError):
            tool.require({"a": None}, "a")
