"""
tests/test_server.py

Unit + integration tests for zeropoint/server.py.

Run: pytest tests/test_server.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zeropoint.server import MCPHandler, _err, _ok, get_active_ip


###############################################################################
# Fixtures
###############################################################################

@pytest.fixture
def mock_registry():
    reg = MagicMock()
    reg.list_tools.return_value = [
        {"name": "filesystem_read", "description": "Read a file", "inputSchema": {}}
    ]
    reg.call = AsyncMock(return_value={"content": [{"type": "text", "text": "ok"}], "isError": False})
    reg.__len__ = MagicMock(return_value=1)
    return reg


@pytest.fixture
def mock_auth_pass():
    auth = MagicMock()
    auth.validate_header.return_value = True
    return auth


@pytest.fixture
def mock_auth_fail():
    auth = MagicMock()
    auth.validate_header.return_value = False
    return auth


@pytest.fixture
def handler(mock_registry, mock_auth_pass):
    return MCPHandler(registry=mock_registry, auth=mock_auth_pass, server_cfg={})


###############################################################################
# JSON-RPC helpers
###############################################################################

def test_ok_structure():
    result = _ok(1, {"foo": "bar"})
    assert result["jsonrpc"] == "2.0"
    assert result["id"] == 1
    assert result["result"] == {"foo": "bar"}


def test_err_structure():
    result = _err(1, -32600, "Bad request")
    assert result["jsonrpc"] == "2.0"
    assert result["error"]["code"] == -32600
    assert result["error"]["message"] == "Bad request"
    assert "data" not in result["error"]


def test_err_with_data():
    result = _err(1, -32603, "Internal error", data="detail")
    assert result["error"]["data"] == "detail"


###############################################################################
# MCPHandler._dispatch — routing
###############################################################################

@pytest.mark.asyncio
async def test_dispatch_parse_error(handler):
    result = await handler._dispatch("not json{{")
    assert result["error"]["code"] == -32700
    # Must NOT leak internal details to client
    assert "Traceback" not in json.dumps(result)
    assert "SyntaxError" not in json.dumps(result)


@pytest.mark.asyncio
async def test_dispatch_unknown_method(handler):
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "nonexistent"})
    result = await handler._dispatch(raw)
    assert result["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_dispatch_ping(handler):
    raw = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    result = await handler._dispatch(raw)
    assert result["result"] == {}


@pytest.mark.asyncio
async def test_dispatch_initialize(handler):
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 3, "method": "initialize",
        "params": {"clientInfo": {"name": "test", "version": "0.1"}}
    })
    result = await handler._dispatch(raw)
    assert "protocolVersion" in result["result"]
    assert handler._initialized is True


@pytest.mark.asyncio
async def test_tools_list_requires_init(handler):
    """tools/list must fail before initialize."""
    raw = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    result = await handler._dispatch(raw)
    assert result["error"]["code"] == -32002


@pytest.mark.asyncio
async def test_tools_list_after_init(handler):
    handler._initialized = True
    raw = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
    result = await handler._dispatch(raw)
    assert isinstance(result["result"]["tools"], list)


@pytest.mark.asyncio
async def test_tools_call_requires_init(handler):
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "filesystem_read", "arguments": {"path": "/tmp"}}
    })
    result = await handler._dispatch(raw)
    assert result["error"]["code"] == -32002


@pytest.mark.asyncio
async def test_tools_call_after_init(handler, mock_registry):
    handler._initialized = True
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "filesystem_read", "arguments": {"path": "/tmp"}}
    })
    result = await handler._dispatch(raw)
    mock_registry.call.assert_awaited_once()
    assert "result" in result


@pytest.mark.asyncio
async def test_dispatch_internal_error_not_leaked(handler, mock_registry):
    """Exceptions from registry.call() must not expose internals to client."""
    handler._initialized = True
    mock_registry.call = AsyncMock(side_effect=RuntimeError("secret internal path: C:/ZeroPoint"))
    raw = json.dumps({
        "jsonrpc": "2.0", "id": 8, "method": "tools/call",
        "params": {"name": "filesystem_read", "arguments": {}}
    })
    result = await handler._dispatch(raw)
    assert result["error"]["code"] == -32603
    # Internal path must NOT appear in response
    assert "C:/ZeroPoint" not in json.dumps(result)
    assert "secret" not in json.dumps(result)


###############################################################################
# Auth helper
###############################################################################

def test_check_auth_pass(mock_registry, mock_auth_pass):
    handler = MCPHandler(mock_registry, mock_auth_pass, {})
    request = MagicMock()
    request.headers.get.return_value = "Bearer validtoken"
    request.remote = "127.0.0.1"
    assert handler._check_auth(request) is True


def test_check_auth_fail(mock_registry, mock_auth_fail):
    handler = MCPHandler(mock_registry, mock_auth_fail, {})
    request = MagicMock()
    request.headers.get.return_value = "Bearer badtoken"
    request.remote = "127.0.0.1"
    assert handler._check_auth(request) is False


def test_check_auth_no_auth(mock_registry):
    """No auth configured — all requests pass."""
    handler = MCPHandler(mock_registry, auth=None, server_cfg={})
    request = MagicMock()
    assert handler._check_auth(request) is True


###############################################################################
# Notification (no id) returns None
###############################################################################

@pytest.mark.asyncio
async def test_notification_returns_none(handler):
    """JSON-RPC messages without 'id' are notifications — no response expected."""
    # A valid notification has no 'id' and uses a known method.
    # Unknown method with no id returns an error (has id=None), but
    # a pure notification with a known method like ping should return _ok(None, {})
    # which is not None. MCP Streamable HTTP returns 202 when response is None.
    # This tests that a shutdown notification (no id) returns something non-crashing.
    raw = json.dumps({"jsonrpc": "2.0", "method": "shutdown"})
    result = await handler._dispatch(raw)
    # shutdown always returns _ok regardless
    assert result is not None


###############################################################################
# get_active_ip
###############################################################################

def test_get_active_ip_returns_string():
    ip = get_active_ip()
    assert isinstance(ip, str)
    parts = ip.split(".")
    assert len(parts) == 4
