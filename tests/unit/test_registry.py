"""
Unit tests — ToolRegistry
"""
import pytest
import sys
import pathlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.registry import ToolRegistry, _snake_to_camel
from zeropoint.tools.base import BaseTool, ToolResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_config(tmp_path: Path, tools_enabled=("filesystem",)) -> Path:
    """Write a minimal mcp_server_config.yaml + tool_registration.json to tmp_path."""
    import yaml

    tools = {}
    for name in tools_enabled:
        tools[name] = {
            "enabled": True,
            "module": f"zeropoint.tools.{name}",
            "class": f"{_snake_to_camel(name)}Tool",
            "config": {
                "allowed_roots": [str(tmp_path)],
                "deny_patterns": [],
                "max_file_size_mb": 1,
                "allow_symlinks": False,
                "sandbox_mode": True,
            }
        }

    cfg = {
        "server": {"name": "test", "auth": {"enabled": False}},
        "tools": tools,
        "ray": {},
    }
    cfg_path = tmp_path / "mcp_server_config.yaml"
    cfg_path.write_text(yaml.dump(cfg))

    manifest = {
        "tools": [
            {
                "name": "filesystem_read",
                "module": "filesystem",
                "class": "FilesystemTool",
                "description": "Read a file.",
                "input_schema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
                "output_schema": {},
                "tags": ["filesystem"],
            },
            {
                "name": "filesystem_list",
                "module": "filesystem",
                "class": "FilesystemTool",
                "description": "List a directory.",
                "input_schema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
                "output_schema": {},
                "tags": ["filesystem"],
            }
        ]
    }
    manifest_path = tmp_path / "tool_registration.json"
    manifest_path.write_text(json.dumps(manifest))

    return cfg_path


# ── _snake_to_camel ────────────────────────────────────────────────────────────

class TestSnakeToCamel:
    def test_single_word(self):
        assert _snake_to_camel("filesystem") == "Filesystem"

    def test_two_words(self):
        assert _snake_to_camel("web_tools") == "WebTools"

    def test_three_words(self):
        assert _snake_to_camel("my_cool_tool") == "MyCoolTool"


# ── ToolRegistry.load() ────────────────────────────────────────────────────────

class TestLoad:
    def test_load_registers_tools(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()
        assert "filesystem_read" in reg.tool_names()

    def test_len_reflects_tool_count(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()
        assert len(reg) >= 1

    def test_disabled_module_skipped(self, tmp_path):
        import yaml
        cfg = {
            "server": {"name": "test", "auth": {"enabled": False}},
            "tools": {
                "filesystem": {
                    "enabled": False,
                    "module": "zeropoint.tools.filesystem",
                    "class": "FilesystemTool",
                    "config": {},
                }
            },
            "ray": {},
        }
        cfg_path = tmp_path / "mcp_server_config.yaml"
        cfg_path.write_text(yaml.dump(cfg))

        manifest = {"tools": [{"name": "filesystem_read", "module": "filesystem",
                                "description": "", "input_schema": {}, "output_schema": {}}]}
        (tmp_path / "tool_registration.json").write_text(json.dumps(manifest))

        reg = ToolRegistry(cfg_path)
        reg.load()
        assert "filesystem_read" not in reg.tool_names()


# ── ToolRegistry.call() ────────────────────────────────────────────────────────

class TestCall:
    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()
        result = await reg.call("nonexistent_tool", {})
        assert result["isError"] is True
        assert "UNKNOWN_TOOL" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_known_tool(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        # Create a real file to read
        (tmp_path / "hello.txt").write_text("hello")
        reg = ToolRegistry(cfg_path)
        reg.load()

        result = await reg.call("filesystem_read", {
            "path": str(tmp_path / "hello.txt"),
        })
        assert not result.get("isError")

    @pytest.mark.asyncio
    async def test_call_derives_operation_from_tool_name(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()

        result = await reg.call("filesystem_list", {"path": str(tmp_path)})

        assert not result.get("isError")


# ── list_tools() ───────────────────────────────────────────────────────────────

class TestListTools:
    def test_list_tools_structure(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()
        tools = reg.list_tools()
        assert isinstance(tools, list)
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t


# ── startup / shutdown ─────────────────────────────────────────────────────────

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_startup_and_shutdown(self, tmp_path):
        cfg_path = _make_config(tmp_path)
        reg = ToolRegistry(cfg_path)
        reg.load()
        await reg.startup()
        await reg.shutdown()
        # No error = pass
