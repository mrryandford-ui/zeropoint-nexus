"""
tests/test_registry.py

Unit tests for zeropoint/registry.py.

Run: pytest tests/test_registry.py -v
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from zeropoint.registry import ToolRegistry, _snake_to_camel
from zeropoint.tools.base import BaseTool, ToolResult


###############################################################################
# Helpers to build minimal temp config + manifest
###############################################################################

def _make_config(tools: dict, tmp_path: Path) -> Path:
    cfg = {
        "server": {"host": "127.0.0.1", "port": 8765, "auth": {"enabled": False}},
        "tools": tools,
        "observability": {},
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "mcp_server_config.yaml"
    config_path.write_text(yaml.dump(cfg))
    return config_path


def _make_manifest(tools: list[dict], config_path: Path) -> None:
    manifest = {"tools": tools}
    manifest_path = config_path.parent.parent / "tool_registration.json"
    manifest_path.write_text(json.dumps(manifest))


def _make_mock_module(class_name: str) -> types.ModuleType:
    """Return an in-memory module with a concrete BaseTool subclass.

    The subclass implements the abstract execute() method, returning a
    ToolResult whose data echoes the _op param.  safe_execute() in BaseTool
    then wraps it into the standard MCP dict with isError absent/False.
    """

    class _MockTool(BaseTool):
        name = "mock"
        description = "mock tool"

        async def execute(self, params: dict) -> ToolResult:
            op = params.get("_op", "")
            return ToolResult(data={"text": f"op:{op}"})

    _MockTool.__name__ = class_name
    _MockTool.__qualname__ = class_name

    mod = types.ModuleType(f"_mock_module_{class_name}")
    setattr(mod, class_name, _MockTool)
    return mod


###############################################################################
# _snake_to_camel
###############################################################################

def test_snake_to_camel_basic():
    assert _snake_to_camel("filesystem") == "Filesystem"
    assert _snake_to_camel("android_tool") == "AndroidTool"
    assert _snake_to_camel("web_tools") == "WebTools"


###############################################################################
# ToolRegistry — load + instance cache
###############################################################################

def test_registry_load_and_instance_cache(tmp_path):
    """Two tools in the same module share one instance."""
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {"root": "/tmp"}}},
        tmp_path,
    )
    _make_manifest(
        [
            {"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"},
            {"name": "filesystem_list", "module": "filesystem", "class": "FilesystemTool"},
        ],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    assert len(registry) == 2
    assert registry._tools["filesystem_read"] is registry._tools["filesystem_list"]
    assert len(registry._instances) == 1


def test_registry_disabled_module_skipped(tmp_path):
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": False, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    assert len(registry) == 0


def test_registry_bad_module_reported(tmp_path, caplog):
    """A tool pointing to a non-existent module must emit a WARNING summary."""
    config_path = _make_config(
        {"nonexistent_module": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "ghost_tool", "module": "nonexistent_module", "class": "GhostTool"}],
        config_path,
    )

    import logging
    with patch(
        "zeropoint.registry.importlib.import_module",
        side_effect=ImportError("No module named 'zeropoint.tools.nonexistent_module'"),
    ):
        with caplog.at_level(logging.WARNING):
            registry = ToolRegistry(config_path)
            registry.load()

    assert len(registry) == 0
    assert "TOOL LOAD FAILURES" in caplog.text
    assert "ghost_tool" in caplog.text


###############################################################################
# ToolRegistry — call routing
###############################################################################

@pytest.mark.asyncio
async def test_call_unknown_tool(tmp_path):
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    result = await registry.call("does_not_exist", {})
    assert result["isError"] is True
    assert "UNKNOWN_TOOL" in str(result) or "Unknown tool" in str(result)


@pytest.mark.asyncio
async def test_call_op_stripping(tmp_path):
    """filesystem_read -> op 'read' must be passed as _op.

    importlib.import_module is patched so the real zeropoint.tools.filesystem
    (with allowed_roots enforcement) is never loaded.
    """
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    result = await registry.call("filesystem_read", {"path": "/tmp"})
    assert result.get("isError") is not True
    content_text = result["content"][0]["text"]
    assert "op:read" in content_text


###############################################################################
# ToolRegistry — lifecycle
###############################################################################

@pytest.mark.asyncio
async def test_startup_shutdown_called_once_per_instance(tmp_path):
    """startup/shutdown called exactly once per unique instance, not per tool name."""
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [
            {"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"},
            {"name": "filesystem_list", "module": "filesystem", "class": "FilesystemTool"},
        ],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    startup_count = 0
    shutdown_count = 0

    async def mock_startup(self):
        nonlocal startup_count
        startup_count += 1

    async def mock_shutdown(self):
        nonlocal shutdown_count
        shutdown_count += 1

    instance = list(registry._instances.values())[0]
    instance.startup = lambda: mock_startup(instance)
    instance.shutdown = lambda: mock_shutdown(instance)

    await registry.startup()
    await registry.shutdown()

    assert startup_count == 1, "startup() called more than once for shared instance"
    assert shutdown_count == 1, "shutdown() called more than once for shared instance"


###############################################################################
# ToolRegistry — introspection
###############################################################################

def test_list_tools_returns_registered_only(tmp_path):
    mock_mod = _make_mock_module("FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [
            {"name": "filesystem_read", "module": "filesystem",
             "class": "FilesystemTool", "description": "Read files"},
            {"name": "filesystem_write", "module": "filesystem",
             "class": "FilesystemTool", "description": "Write files"},
        ],
        config_path,
    )

    with patch("zeropoint.registry.importlib.import_module", return_value=mock_mod):
        registry = ToolRegistry(config_path)
        registry.load()

    tools = registry.list_tools()

    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "filesystem_read" in names
    assert "filesystem_write" in names
    for t in tools:
        assert "description" in t
        assert "inputSchema" in t
