"""
Unit tests — FilesystemTool
"""
import pytest
import sys
import pathlib
import tempfile
import os

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.tools.filesystem import FilesystemTool
from zeropoint.tools.base import ToolError


@pytest.fixture
def tmp(tmp_path):
    """Temp dir that is inside an allowed root."""
    return tmp_path


@pytest.fixture
def tool(tmp):
    return FilesystemTool(config={
        "allowed_roots": [str(tmp)],
        "deny_patterns": ["**/*.key", "**/secrets/**"],
        "max_file_size_mb": 1,
        "allow_symlinks": False,
        "sandbox_mode": True,
    })


# ── Read ───────────────────────────────────────────────────────────────────────

class TestRead:
    @pytest.mark.asyncio
    async def test_read_text_file(self, tool, tmp):
        f = tmp / "hello.txt"
        f.write_text("hello world")
        result = await tool.safe_execute({"_op": "read", "path": str(f)})
        import json
        data = json.loads(result["content"][0]["text"])
        assert data["content"] == "hello world"
        assert data["size_bytes"] == 11

    @pytest.mark.asyncio
    async def test_read_with_line_range(self, tool, tmp):
        f = tmp / "lines.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5")
        result = await tool.safe_execute({"_op": "read", "path": str(f), "start_line": 2, "end_line": 3})
        import json
        data = json.loads(result["content"][0]["text"])
        assert "line2" in data["content"]
        assert "line4" not in data["content"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_returns_error(self, tool, tmp):
        result = await tool.safe_execute({"_op": "read", "path": str(tmp / "nope.txt")})
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_read_outside_root_denied(self, tool):
        result = await tool.safe_execute({"_op": "read", "path": "/etc/passwd"})
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_read_denied_pattern(self, tool, tmp):
        f = tmp / "id_rsa.key"
        f.write_text("secret")
        result = await tool.safe_execute({"_op": "read", "path": str(f)})
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_read_binary_as_base64(self, tool, tmp):
        f = tmp / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        result = await tool.safe_execute({"_op": "read", "path": str(f), "encoding": "base64"})
        import json, base64
        data = json.loads(result["content"][0]["text"])
        assert base64.b64decode(data["content"]) == b"\x00\x01\x02\x03"


# ── Write ──────────────────────────────────────────────────────────────────────

class TestWrite:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tool, tmp):
        path = str(tmp / "out.txt")
        result = await tool.safe_execute({"_op": "write", "path": path, "content": "written!"})
        import json
        data = json.loads(result["content"][0]["text"])
        assert data["bytes_written"] == 8
        assert pathlib.Path(path).read_text() == "written!"

    @pytest.mark.asyncio
    async def test_write_append(self, tool, tmp):
        path = str(tmp / "append.txt")
        pathlib.Path(path).write_text("first")
        await tool.safe_execute({"_op": "write", "path": path, "content": " second", "mode": "append"})
        assert pathlib.Path(path).read_text() == "first second"

    @pytest.mark.asyncio
    async def test_write_create_new_fails_if_exists(self, tool, tmp):
        path = str(tmp / "exists.txt")
        pathlib.Path(path).write_text("original")
        result = await tool.safe_execute({"_op": "write", "path": path, "content": "new", "mode": "create_new"})
        assert result["isError"] is True
        assert pathlib.Path(path).read_text() == "original"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tool, tmp):
        path = str(tmp / "deep" / "nested" / "file.txt")
        await tool.safe_execute({"_op": "write", "path": path, "content": "deep"})
        assert pathlib.Path(path).exists()

    @pytest.mark.asyncio
    async def test_write_outside_root_denied(self, tool):
        result = await tool.safe_execute({"_op": "write", "path": "/tmp/evil.txt", "content": "x"})
        assert result["isError"] is True


# ── List ───────────────────────────────────────────────────────────────────────

class TestList:
    @pytest.mark.asyncio
    async def test_list_directory(self, tool, tmp):
        (tmp / "a.txt").write_text("a")
        (tmp / "b.txt").write_text("b")
        (tmp / "subdir").mkdir()
        result = await tool.safe_execute({"_op": "list", "path": str(tmp)})
        import json
        data = json.loads(result["content"][0]["text"])
        names = [e["name"] for e in data["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_list_with_glob_pattern(self, tool, tmp):
        (tmp / "a.py").write_text("")
        (tmp / "b.txt").write_text("")
        result = await tool.safe_execute({"_op": "list", "path": str(tmp), "pattern": "*.py"})
        import json
        data = json.loads(result["content"][0]["text"])
        names = [e["name"] for e in data["entries"]]
        assert "a.py" in names
        assert "b.txt" not in names

    @pytest.mark.asyncio
    async def test_list_recursive(self, tool, tmp):
        sub = tmp / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("")
        result = await tool.safe_execute({"_op": "list", "path": str(tmp), "recursive": True})
        import json
        data = json.loads(result["content"][0]["text"])
        names = [e["name"] for e in data["entries"]]
        assert "deep.txt" in names

    @pytest.mark.asyncio
    async def test_list_not_a_dir_error(self, tool, tmp):
        f = tmp / "file.txt"
        f.write_text("x")
        result = await tool.safe_execute({"_op": "list", "path": str(f)})
        assert result["isError"] is True
