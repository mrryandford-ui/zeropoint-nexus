"""
Unit tests — WebtoolsTool
Uses aiohttp mocking to avoid real network calls.
"""
import pytest
import sys
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientError

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.tools.webtools import WebtoolsTool, _extract_ddg_url
from zeropoint.tools.base import ToolError

BASE_CONFIG = {
    "allowed_domains": [],
    "blocked_domains": ["*.onion", "localhost", "127.0.0.1"],
    "timeout_seconds": 10,
    "max_response_size_mb": 1,
    "follow_redirects": True,
    "max_redirects": 5,
    "user_agent": "ZeroPoint-Test/1.0",
    "rate_limit": {"requests_per_minute": 120, "burst": 20},
}


@pytest.fixture
def tool():
    t = WebtoolsTool(config=BASE_CONFIG)
    # Provide a mock session so startup() isn't needed
    t._session = MagicMock()
    return t


# ── URL guard ──────────────────────────────────────────────────────────────────

class TestURLGuard:
    def test_blocks_localhost(self, tool):
        with pytest.raises(ToolError) as exc:
            tool._check_url("http://localhost/api")
        assert exc.value.code in ("URL_BLOCKED", "URL_NOT_ALLOWED")

    def test_blocks_127(self, tool):
        with pytest.raises(ToolError):
            tool._check_url("http://127.0.0.1:8080/")

    def test_blocks_private_ip(self, tool):
        with pytest.raises(ToolError):
            tool._check_url("http://192.168.1.1/admin")

    def test_blocks_onion(self, tool):
        with pytest.raises(ToolError):
            tool._check_url("http://something.onion/")

    def test_allows_public(self, tool):
        tool._check_url("https://example.com/path")  # should not raise

    def test_allowed_domains_enforced(self):
        t = WebtoolsTool(config={**BASE_CONFIG, "allowed_domains": ["example.com"]})
        t._session = MagicMock()
        with pytest.raises(ToolError):
            t._check_url("https://notexample.com/")
        t._check_url("https://example.com/ok")  # allowed


# ── Rate limiting ──────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_rate_limit_triggers(self):
        t = WebtoolsTool(config={**BASE_CONFIG, "rate_limit": {"requests_per_minute": 2, "burst": 2}})
        t._session = MagicMock()
        import time
        t._check_rate_limit()
        t._check_rate_limit()
        with pytest.raises(ToolError) as exc:
            t._check_rate_limit()
        assert exc.value.code == "RATE_LIMITED"


# ── Fetch ──────────────────────────────────────────────────────────────────────

class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_success_text(self, tool):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.content_type = "text/html"
        mock_response.read = AsyncMock(return_value=b"<html>hello</html>")
        mock_response.url = MagicMock(__str__=lambda _: "https://example.com")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        tool._session.request = MagicMock(return_value=mock_response)

        result = await tool.safe_execute({
            "_op": "fetch", "url": "https://example.com", "parse_as": "text"
        })
        import json
        data = json.loads(result["content"][0]["text"])
        assert data["status_code"] == 200
        assert "hello" in data["body"]

    @pytest.mark.asyncio
    async def test_fetch_json_parse(self, tool):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.content_type = "application/json"
        mock_response.read = AsyncMock(return_value=b'{"key": "value"}')
        mock_response.url = MagicMock(__str__=lambda _: "https://api.example.com")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        tool._session.request = MagicMock(return_value=mock_response)

        result = await tool.safe_execute({
            "_op": "fetch", "url": "https://api.example.com", "parse_as": "json"
        })
        import json
        data = json.loads(result["content"][0]["text"])
        assert data["body"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_fetch_client_error(self, tool):
        tool._session.request = MagicMock(side_effect=ClientError("timeout"))
        result = await tool.safe_execute({
            "_op": "fetch", "url": "https://example.com"
        })
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_fetch_missing_url(self, tool):
        result = await tool.safe_execute({"_op": "fetch"})
        assert result["isError"] is True


# ── Helpers ────────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_ddg_url_encoded(self):
        href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath&rut=abc"
        assert _extract_ddg_url(href) == "https://example.com/path"

    def test_extract_ddg_url_passthrough(self):
        href = "https://already.real.com/"
        assert _extract_ddg_url(href) == href
