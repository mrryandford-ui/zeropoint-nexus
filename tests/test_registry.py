"""
tests/test_registry.py

Unit tests for zeropoint/registry.py.

Run: pytest tests/test_registry.py -v
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from zeropoint.registry import ToolRegistry, _snake_to_camel


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


def _make_mock_tool_class(tmp_path: Path, module_name: str, class_name: str) -> None:
    """Write a minimal BaseTool subclass to a temp module file."""
    tools_dir = tmp_path / "zeropoint" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "zeropoint" / "__init__.py").touch()
    (tools_dir / "__init__.py").touch()
    (tools_dir / "base.py").write_text("""
class ToolError(Exception):
    def __init__(self, msg, code=None):
        self.msg = msg
        self.code = code
    def to_mcp(self):
        return {"isError": True, "content": [{"type": "text", "text": self.msg}]}

class BaseTool:
    def __init__(self, config=None):
        self.config = config or {}
    async def startup(self): pass
    async def shutdown(self): pass
    async def safe_execute(self, params):
        op = params.get("_op", "")
        return {"isError": False, "content": [{"type": "text", "text": f"op:{op}"}]}
""")
    module_file = tools_dir / f"{module_name}.py"
    module_file.write_text(f"""
from zeropoint.tools.base import BaseTool
class {class_name}(BaseTool):
    pass
""")


def _purge_cached_modules(prefix: str) -> None:
    """Remove any already-imported modules whose name starts with *prefix*.

    This ensures monkeypatch.syspath_prepend can shadow real production modules
    when the real package has already been imported earlier in the test session.
    """
    to_delete = [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")]
    for key in to_delete:
        del sys.modules[key]


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

def test_registry_load_and_instance_cache(tmp_path, monkeypatch):
    """Two tools in the same module share one instance."""
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

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

    registry = ToolRegistry(config_path)
    registry.load()

    assert len(registry) == 2
    # Both tools must share the same instance
    assert registry._tools["filesystem_read"] is registry._tools["filesystem_list"]
    # Instance cache must have exactly one entry for this module
    assert len(registry._instances) == 1


def test_registry_disabled_module_skipped(tmp_path, monkeypatch):
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": False, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    registry = ToolRegistry(config_path)
    registry.load()
    assert len(registry) == 0


def test_registry_bad_module_reported(tmp_path, monkeypatch, caplog):
    """A tool pointing to a non-existent module must emit a WARNING summary."""
    _purge_cached_modules("zeropoint.tools.nonexistent_module")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

    config_path = _make_config(
        {"nonexistent_module": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "ghost_tool", "module": "nonexistent_module", "class": "GhostTool"}],
        config_path,
    )

    import logging
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
async def test_call_unknown_tool(tmp_path, monkeypatch):
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    registry = ToolRegistry(config_path)
    registry.load()

    result = await registry.call("does_not_exist", {})
    assert result["isError"] is True
    assert "UNKNOWN_TOOL" in str(result) or "Unknown tool" in str(result)


@pytest.mark.asyncio
async def test_call_op_stripping(tmp_path, monkeypatch):
    """filesystem_read -> op 'read' must be passed as _op.

    The mock BaseTool.safe_execute always returns isError=False regardless of
    path, so this test is fully isolated from any production allowed_roots check.
    We explicitly purge any cached real zeropoint.tools.filesystem module before
    prepending tmp_path so the registry always loads the mock.
    """
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

    config_path = _make_config(
        {"filesystem": {"enabled": True, "config": {}}},
        tmp_path,
    )
    _make_manifest(
        [{"name": "filesystem_read", "module": "filesystem", "class": "FilesystemTool"}],
        config_path,
    )

    registry = ToolRegistry(config_path)
    registry.load()

    result = await registry.call("filesystem_read", {"path": "/tmp"})
    assert result["isError"] is False
    assert "op:read" in result["content"][0]["text"]


###############################################################################
# ToolRegistry — lifecycle
###############################################################################

@pytest.mark.asyncio
async def test_startup_shutdown_called_once_per_instance(tmp_path, monkeypatch):
    """startup/shutdown called exactly once per unique instance, not per tool name."""
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

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

def test_list_tools_returns_registered_only(tmp_path, monkeypatch):
    _purge_cached_modules("zeropoint.tools.filesystem")
    monkeypatch.syspath_prepend(str(tmp_path))
    _make_mock_tool_class(tmp_path, "filesystem", "FilesystemTool")

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
