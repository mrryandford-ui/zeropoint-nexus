"""
Integration tests — ZeroPoint MCP WebSocket Server
Spins up a real aiohttp server on a random port and fires
JSON-RPC 2.0 messages over WebSocket.
"""
import pytest
import asyncio
import json
import sys
import pathlib
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, AsyncMock

import aiohttp
from aiohttp import web

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))


# ── Minimal config factory ─────────────────────────────────────────────────────

def _minimal_config(tmp_path: Path) -> Path:
    cfg = {
        "server": {
            "name": "zeropoint-mcp-test",
            "host": "127.0.0.1",
            "port": 0,
            "workers": 1,
            "timeout_seconds": 10,
            "auth": {"enabled": False},
        },
        "tools": {
            "filesystem": {
                "enabled": True,
                "module": "zeropoint.tools.filesystem",
                "class": "FilesystemTool",
                "config": {
                    "allowed_roots": [str(tmp_path)],
                    "deny_patterns": [],
                    "max_file_size_mb": 1,
                    "allow_symlinks": False,
                    "sandbox_mode": True,
                },
            },
            "webtools": {"enabled": False, "module": "zeropoint.tools.webtools",
                         "class": "WebtoolsTool", "config": {}},
            "adb":      {"enabled": False, "module": "zeropoint.tools.adb",
                         "class": "AdbTool", "config": {}},
            "android":  {"enabled": False, "module": "zeropoint.tools.android",
                         "class": "AndroidTool", "config": {}},
        },
        "ray": {},
        "observability": {"metrics": {"enabled": False}, "tracing": {"enabled": False}},
    }
    cfg_path = tmp_path / "test_config.yaml"
    cfg_path.write_text(yaml.dump(cfg))

    manifest = {
        "tools": [
            {
                "name": "filesystem_read",
                "module": "filesystem",
                "class": "FilesystemTool",
                "description": "Read a file.",
                "input_schema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
                "output_schema": {},
                "tags": ["filesystem"],
            },
            {
                "name": "filesystem_write",
                "module": "filesystem",
                "class": "FilesystemTool",
                "description": "Write a file.",
                "input_schema": {
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
                "output_schema": {},
                "tags": ["filesystem"],
            },
        ]
    }
    (tmp_path / "tool_registration.json").write_text(json.dumps(manifest))
    return cfg_path


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def server(tmp_path):
    """Start a real MCP server on a random port. Yield (runner, base_url)."""
    from zeropoint.server import build_app

    cfg_path = _minimal_config(tmp_path)
    app = build_app(str(cfg_path))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    port = site._server.sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    yield runner, base_url
    await runner.cleanup()


@pytest.fixture
async def ws_session(server):
    """Yield (ws, session) connected to the test server's /mcp endpoint."""
    runner, base_url = server
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(f"{base_url.replace('http','ws')}/mcp")
    yield ws, session
    await ws.close()
    await session.close()


async def _send(ws, method: str, params: dict = None, req_id: int = 1) -> dict:
    """Send a JSON-RPC request and wait for a response."""
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params
    await ws.send_str(json.dumps(msg))
    resp = await asyncio.wait_for(ws.receive(), timeout=10)
    return json.loads(resp.data)


# ── Health endpoint ────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, server):
        _, base_url = server
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base_url}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_reports_tool_count(self, server):
        _, base_url = server
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{base_url}/health") as resp:
                data = await resp.json()
                assert data["tools"] >= 1


# ── MCP Protocol ───────────────────────────────────────────────────────────────

class TestMCPProtocol:
    @pytest.mark.asyncio
    async def test_initialize(self, ws_session):
        ws, _ = ws_session
        resp = await _send(ws, "initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "pytest", "version": "1.0"},
            "capabilities": {},
        })
        assert resp["id"] == 1
        assert "result" in resp
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "zeropoint-mcp"

    @pytest.mark.asyncio
    async def test_ping(self, ws_session):
        ws, _ = ws_session
        # Initialize first
        await _send(ws, "initialize", {"protocolVersion": "2024-11-05",
                                        "clientInfo": {"name": "test", "version": "1"}})
        resp = await _send(ws, "ping", req_id=2)
        assert "result" in resp
        assert not resp.get("error")

    @pytest.mark.asyncio
    async def test_tools_list_before_init_fails(self, ws_session):
        ws, _ = ws_session
        resp = await _send(ws, "tools/list")
        assert "error" in resp

    @pytest.mark.asyncio
    async def test_tools_list_after_init(self, ws_session):
        ws, _ = ws_session
        await _send(ws, "initialize", {"protocolVersion": "2024-11-05",
                                        "clientInfo": {"name": "test", "version": "1"}})
        resp = await _send(ws, "tools/list", req_id=2)
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert isinstance(tools, list)
        names = [t["name"] for t in tools]
        assert "filesystem_read" in names

    @pytest.mark.asyncio
    async def test_unknown_method(self, ws_session):
        ws, _ = ws_session
        resp = await _send(ws, "nonexistent/method")
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_invalid_json(self, ws_session):
        ws, _ = ws_session
        await ws.send_str("{not valid json")
        resp_msg = await asyncio.wait_for(ws.receive(), timeout=5)
        resp = json.loads(resp_msg.data)
        assert "error" in resp
        assert resp["error"]["code"] == -32700


# ── Tool calls over WebSocket ──────────────────────────────────────────────────

class TestToolCalls:
    @pytest.fixture(autouse=True)
    async def _init(self, ws_session):
        ws, _ = ws_session
        await _send(ws, "initialize", {"protocolVersion": "2024-11-05",
                                        "clientInfo": {"name": "test", "version": "1"}})

    @pytest.mark.asyncio
    async def test_filesystem_write_and_read(self, ws_session, tmp_path):
        ws, _ = ws_session
        test_file = str(tmp_path / "integration_test.txt")

        # Write
        write_resp = await _send(ws, "tools/call", {
            "name": "filesystem_write",
            "arguments": {"_op": "write", "path": test_file, "content": "integration test"},
        }, req_id=2)
        assert "result" in write_resp
        assert not write_resp["result"].get("isError")

        # Read back
        read_resp = await _send(ws, "tools/call", {
            "name": "filesystem_read",
            "arguments": {"_op": "read", "path": test_file},
        }, req_id=3)
        assert "result" in read_resp
        result_data = json.loads(read_resp["result"]["content"][0]["text"])
        assert result_data["content"] == "integration test"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, ws_session):
        ws, _ = ws_session
        resp = await _send(ws, "tools/call", {
            "name": "nonexistent_tool",
            "arguments": {},
        }, req_id=2)
        assert "result" in resp
        assert resp["result"]["isError"] is True

    @pytest.mark.asyncio
    async def test_tool_call_outside_allowed_root(self, ws_session):
        ws, _ = ws_session
        resp = await _send(ws, "tools/call", {
            "name": "filesystem_read",
            "arguments": {"_op": "read", "path": "/etc/passwd"},
        }, req_id=2)
        assert "PATH_DENIED" in resp["result"]["content"][0]["text"]


# ── Multiple concurrent connections ───────────────────────────────────────────

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_multiple_simultaneous_connections(self, server, tmp_path):
        """Two clients can connect and operate independently."""
        _, base_url = server
        ws_url = base_url.replace("http", "ws") + "/mcp"

        async def _client(client_id: int, file_content: str) -> str:
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(ws_url) as ws:
                    await _send(ws, "initialize", {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": f"client-{client_id}", "version": "1"},
                    })
                    path = str(tmp_path / f"concurrent_{client_id}.txt")
                    await _send(ws, "tools/call", {
                        "name": "filesystem_write",
                        "arguments": {"_op": "write", "path": path, "content": file_content},
                    }, req_id=2)
                    read = await _send(ws, "tools/call", {
                        "name": "filesystem_read",
                        "arguments": {"_op": "read", "path": path},
                    }, req_id=3)
                    data = json.loads(read["result"]["content"][0]["text"])
                    return data["content"]

        results = await asyncio.gather(
            _client(1, "client-one-data"),
            _client(2, "client-two-data"),
        )
        assert results[0] == "client-one-data"
        assert results[1] == "client-two-data"
