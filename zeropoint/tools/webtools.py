"""
WebtoolsTool — HTTP fetch, web search, and HTML scrape.
Registered tool names: webtools_fetch, webtools_search, webtools_scrape
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from zeropoint.tools.base import BaseTool, ToolError, ToolResult


class WebtoolsTool(BaseTool):
    name = "webtools"
    module = "webtools"
    description = "HTTP fetch, web search, and HTML scrape."

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        self._allowed: list[str] = self.config.get("allowed_domains", [])
        self._blocked: list[str] = self.config.get("blocked_domains", [])
        self._timeout: int = self.config.get("timeout_seconds", 30)
        self._max_size: int = self.config.get("max_response_size_mb", 16) * 1024 * 1024
        self._follow_redirects: bool = self.config.get("follow_redirects", True)
        self._max_redirects: int = self.config.get("max_redirects", 5)
        self._user_agent: str = self.config.get(
            "user_agent", "ZeroPoint-MCP/1.0"
        )
        rl = self.config.get("rate_limit", {})
        self._rpm: int = rl.get("requests_per_minute", 60)
        self._burst: int = rl.get("burst", 10)
        self._req_times: deque[float] = deque()
        self._session: aiohttp.ClientSession | None = None

    async def startup(self) -> None:
        connector = aiohttp.TCPConnector(
            ssl=True,
            limit=20,
            limit_per_host=5,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": self._user_agent},
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        )

    async def shutdown(self) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _check_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        # Block private/link-local IP ranges
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ToolError(f"Blocked: private/loopback IP '{host}'", code="URL_BLOCKED")
        except ValueError:
            pass  # Not a bare IP — hostname check below

        for pattern in self._blocked:
            pat = pattern.lstrip("*.")
            if host == pat or host.endswith("." + pat):
                raise ToolError(
                    f"Domain '{host}' is blocked by policy.", code="URL_BLOCKED"
                )

        if self._allowed:
            ok = any(
                host == a.lstrip("*.") or host.endswith("." + a.lstrip("*."))
                for a in self._allowed
            )
            if not ok:
                raise ToolError(
                    f"Domain '{host}' not in allowed_domains list.", code="URL_NOT_ALLOWED"
                )

    def _check_rate_limit(self) -> None:
        now = time.monotonic()
        window = 60.0
        self._req_times = deque(
            t for t in self._req_times if now - t < window
        )
        if len(self._req_times) >= self._rpm:
            raise ToolError("Rate limit exceeded — slow down requests.", code="RATE_LIMITED")
        self._req_times.append(now)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        op = params.pop("_op", "fetch")
        if op == "search":
            return await self._search(params)
        elif op == "scrape":
            return await self._scrape(params)
        else:
            return await self._fetch(params)

    # ------------------------------------------------------------------
    # webtools_fetch
    # ------------------------------------------------------------------

    async def _fetch(self, params: dict) -> ToolResult:
        self.require(params, "url")
        url: str = params["url"]
        self._check_url(url)
        self._check_rate_limit()

        method: str = params.get("method", "GET").upper()
        headers: dict = params.get("headers", {})
        body: str | None = params.get("body")
        parse_as: str = params.get("parse_as", "auto")

        assert self._session is not None
        t0 = time.perf_counter()
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=body,
                allow_redirects=self._follow_redirects,
                max_redirects=self._max_redirects,
            ) as resp:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                raw = await resp.read()
                if len(raw) > self._max_size:
                    raise ToolError("Response too large.", code="RESPONSE_TOO_LARGE")

                content_type = resp.content_type or ""
                if parse_as == "json" or (parse_as == "auto" and "json" in content_type):
                    try:
                        import json
                        body_out = json.loads(raw)
                    except Exception:
                        body_out = raw.decode("utf-8", errors="replace")
                else:
                    body_out = raw.decode("utf-8", errors="replace")

                return ToolResult(data={
                    "status_code": resp.status,
                    "headers": dict(resp.headers),
                    "body": body_out,
                    "latency_ms": latency_ms,
                    "url": str(resp.url),
                })

        except aiohttp.ClientError as exc:
            raise ToolError(f"HTTP request failed: {exc}", code="HTTP_ERROR")

    # ------------------------------------------------------------------
    # webtools_search — DuckDuckGo HTML (no API key required)
    # ------------------------------------------------------------------

    async def _search(self, params: dict) -> ToolResult:
        self.require(params, "query")
        query: str = params["query"]
        max_results: int = min(params.get("max_results", 10), 50)

        search_url = "https://html.duckduckgo.com/html/"
        self._check_rate_limit()

        assert self._session is not None
        try:
            async with self._session.post(
                search_url,
                data={"q": query, "b": "", "kl": params.get("language", "us-en")},
                headers={"Accept": "text/html"},
            ) as resp:
                html = await resp.text()
        except aiohttp.ClientError as exc:
            raise ToolError(f"Search request failed: {exc}", code="HTTP_ERROR")

        soup = BeautifulSoup(html, "lxml")
        results = []
        for i, result in enumerate(soup.select(".result__body")[:max_results]):
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if not title_el:
                continue
            href = title_el.get("href", "")
            # DuckDuckGo wraps URLs — extract real URL
            real_url = _extract_ddg_url(href)
            results.append({
                "rank": i + 1,
                "title": title_el.get_text(strip=True),
                "url": real_url,
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
            })

        return ToolResult(data={"results": results, "total_results": len(results), "query": query})

    # ------------------------------------------------------------------
    # webtools_scrape
    # ------------------------------------------------------------------

    async def _scrape(self, params: dict) -> ToolResult:
        self.require(params, "url")
        url: str = params["url"]
        self._check_url(url)
        self._check_rate_limit()

        selectors: dict[str, str] = params.get("selectors", {})
        return_markdown: bool = params.get("return_markdown", True)

        fetch_params = {"url": url, "parse_as": "text"}
        fetch_result = await self._fetch(fetch_params)
        html = fetch_result.data.get("body", "")

        soup = BeautifulSoup(html, "lxml")

        extracted = {}
        for label, css in selectors.items():
            els = soup.select(css)
            extracted[label] = [el.get_text(strip=True) for el in els]

        markdown = ""
        if return_markdown:
            # Strip scripts/styles then convert to rough markdown
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            markdown = _html_to_markdown(soup)

        return ToolResult(data={
            "extracted": extracted,
            "markdown": markdown,
            "url": url,
        })


###############################################################################
# Helpers
###############################################################################

def _extract_ddg_url(href: str) -> str:
    if href.startswith("//duckduckgo.com/l/?"):
        match = re.search(r"uddg=([^&]+)", href)
        if match:
            from urllib.parse import unquote
            return unquote(match.group(1))
    return href


def _html_to_markdown(soup: BeautifulSoup) -> str:
    """Very lightweight HTML → Markdown converter."""
    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "a", "pre", "code"]):
        tag = el.name
        text = el.get_text(strip=True)
        if not text:
            continue
        if tag == "h1":
            lines.append(f"# {text}")
        elif tag == "h2":
            lines.append(f"## {text}")
        elif tag == "h3":
            lines.append(f"### {text}")
        elif tag == "h4":
            lines.append(f"#### {text}")
        elif tag == "li":
            lines.append(f"- {text}")
        elif tag in ("pre", "code"):
            lines.append(f"```\n{text}\n```")
        else:
            lines.append(text)
    return "\n\n".join(lines)
