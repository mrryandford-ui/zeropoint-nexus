"""
ZeroPoint MCP Server — WebSocket + Streamable HTTP entrypoint.

Implements the Model Context Protocol (MCP) 1.0 over WebSocket + JSON-RPC 2.0.
Handles: initialize, tools/list, tools/call, ping, shutdown.

Security hardening (2026-09-11):
 - Default bind address is 127.0.0.1 (loopback only). Override in config or
   via --host if LAN exposure is intentional.
 - Internal exception details are never sent to clients; full traces are
   logged server-side only.
 - Runtime IP detection is in-memory only; the config file is never mutated.
 - Health endpoint requires a valid bearer token.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

import click
import yaml
from aiohttp import web

from zeropoint.auth import build_auth
from zeropoint.observability import init_observability, record_tool_call
from zeropoint.registry import ToolRegistry

logger = logging.getLogger("zeropoint.server")

# Default config path resolves relative to this file — works on any OS.
_DEFAULT_CONFIG = str(
    Path(__file__).parent.parent / "config" / "mcp_server_config.yaml"
)

###############################################################################
# JSON-RPC helpers
###############################################################################

def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}

def _err(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}

###############################################################################
# MCP handler (shared by WebSocket and HTTP transports)
###############################################################################

class MCPHandler:
    """Stateful session handler — one instance per connection (WS) or shared (HTTP)."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_INFO = {"name": "zeropoint-mcp", "version": "1.0.0"}

    def __init__(self, registry: ToolRegistry, auth: Any, server_cfg: dict):
        self.registry = registry
        self.auth = auth
        self.cfg = server_cfg
        self._initialized = False

    # ------------------------------------------------------------------
    # Auth helper (shared across transports)
    # ------------------------------------------------------------------

    def _check_auth(self, request: web.Request) -> bool:
        if not self.auth:
            return True
        peer = request.remote or "unknown"
        return self.auth.validate_header(request.headers.get("Authorization"), peer)

    # ------------------------------------------------------------------
    # WebSocket transport
    # ------------------------------------------------------------------

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        if not self._check_auth(request):
            raise web.HTTPUnauthorized(reason="Invalid or missing bearer token")

        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        peer = request.remote or "unknown"
        logger.info("WebSocket connection from %s", peer)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                response = await self._dispatch(msg.data)
                if response is not None:
                    await ws.send_str(json.dumps(response))
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                break

        logger.info("WebSocket disconnected: %s", peer)
        return ws

    # ------------------------------------------------------------------
    # Core JSON-RPC dispatch (shared by all transports)
    # ------------------------------------------------------------------

    async def _dispatch(self, raw: str) -> dict | None:
        """Parse JSON-RPC, route to method handler, return response.

        Security: full exception details are logged server-side only.
        Clients receive a generic error message — never internal details.
        """
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse error: %s", exc)
            return _err(None, -32700, "Parse error")

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        try:
            if method == "initialize":
                return await self._initialize(req_id, params)
            elif method == "tools/list":
                return await self._tools_list(req_id)
            elif method == "tools/call":
                return await self._tools_call(req_id, params)
            elif method == "ping":
                return _ok(req_id, {})
            elif method == "shutdown":
                logger.info("Received shutdown request.")
                return _ok(req_id, {})
            else:
                return _err(req_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            # Log full trace server-side; send only a generic message to client.
            logger.error(
                "Unhandled error in method '%s': %s", method, exc, exc_info=True
            )
            return _err(req_id, -32603, "Internal error")

    async def _initialize(self, req_id: Any, params: dict) -> dict:
        client_info = params.get("clientInfo", {})
        logger.info(
            "MCP initialize from client: %s %s",
            client_info.get("name", "unknown"),
            client_info.get("version", ""),
        )
        self._initialized = True
        return _ok(req_id, {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": self.SERVER_INFO,
        })

    async def _tools_list(self, req_id: Any) -> dict:
        if not self._initialized:
            return _err(req_id, -32002, "Server not initialized")
        return _ok(req_id, {"tools": self.registry.list_tools()})

    async def _tools_call(self, req_id: Any, params: dict) -> dict:
        if not self._initialized:
            return _err(req_id, -32002, "Server not initialized")
        tool_name = params.get("name", "")
        tool_params = params.get("arguments", {})
        result = await self.registry.call(tool_name, tool_params)
        record_tool_call(tool_name, success=not result.get("isError", False))
        return _ok(req_id, result)

###############################################################################
# Streamable HTTP transport (MCP spec 2025-03-26)
###############################################################################

async def mcp_http_handler(request: web.Request) -> web.Response:
    handler: MCPHandler = request.app["mcp_handler"]

    if not handler._check_auth(request):
        return web.json_response(
            {"jsonrpc": "2.0", "id": None,
             "error": {"code": -32001, "message": "Unauthorized"}},
            status=401,
        )

    try:
        raw = await request.text()
    except Exception as exc:
        logger.warning("Failed to read HTTP request body: %s", exc)
        return web.json_response(
            {"jsonrpc": "2.0", "id": None,
             "error": {"code": -32700, "message": "Parse error"}},
            status=400,
        )

    response = await handler._dispatch(raw)
    if response is None:
        return web.Response(status=202)
    return web.json_response(response)

###############################################################################
# HTTP health endpoint (auth-gated)
###############################################################################

async def health_handler(request: web.Request) -> web.Response:
    handler: MCPHandler = request.app["mcp_handler"]
    if not handler._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    registry: ToolRegistry = request.app["registry"]
    return web.json_response({
        "status": "ok",
        "tools": len(registry),
        "server": MCPHandler.SERVER_INFO,
    })

###############################################################################
# App factory
###############################################################################

def build_app(config_path: str, runtime_host_override: str | None = None) -> web.Application:
    cfg = yaml.safe_load(Path(config_path).read_text())
    server_cfg = cfg.get("server", {})

    # Apply runtime IP override in memory — never write back to disk.
    if runtime_host_override:
        server_cfg = dict(server_cfg)
        server_cfg["coordinator_host"] = runtime_host_override
        server_cfg["head_node"] = runtime_host_override

    init_observability(cfg.get("observability", {}))
    auth = build_auth(server_cfg.get("auth", {}))
    registry = ToolRegistry(config_path)
    registry.load()

    app = web.Application()
    app["registry"] = registry
    app["config"] = cfg

    handler = MCPHandler(registry, auth, server_cfg)
    app["mcp_handler"] = handler

    app.router.add_get("/mcp", handler.handle_ws)
    app.router.add_post("/mcp", mcp_http_handler)
    app.router.add_get("/health", health_handler)

    async def on_startup(_app: web.Application) -> None:
        await registry.startup()
        logger.info("ZeroPoint MCP server ready.")

    async def on_shutdown(_app: web.Application) -> None:
        await registry.shutdown()
        logger.info("ZeroPoint MCP server stopped.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

###############################################################################
# stdio transport — reuses MCPHandler._dispatch() (no duplicate logic)
###############################################################################

async def run_stdio(config_path: str) -> None:
    registry = ToolRegistry(config_path)
    registry.load()
    await registry.startup()

    # No auth on stdio — the transport itself is the trust boundary.
    handler = MCPHandler(registry, auth=None, server_cfg={})

    def read_message() -> str | None:
        """Read newline-delimited or Content-Length-framed stdio JSON."""
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None

        if first_line.lower().startswith(b"content-length:"):
            headers = [first_line]
            while True:
                header = sys.stdin.buffer.readline()
                if not header or header in (b"\r\n", b"\n"):
                    break
                headers.append(header)
            length = next(
                int(h.split(b":", 1)[1].strip())
                for h in headers
                if h.lower().startswith(b"content-length:")
            )
            body = sys.stdin.buffer.read(length)
            return body.decode("utf-8")

        return first_line.decode("utf-8")

    try:
        while True:
            raw = await asyncio.to_thread(read_message)
            if not raw:
                break
            response = await handler._dispatch(raw)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
    finally:
        await registry.shutdown()

###############################################################################
# IP detection (runtime only — never writes to disk)
###############################################################################

def get_active_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

###############################################################################
# CLI
###############################################################################

@click.command()
@click.option("--config", default=_DEFAULT_CONFIG,
              show_default=True, help="Path to mcp_server_config.yaml")
@click.option("--host", default=None, help="Override listen host from config")
@click.option("--port", default=None, type=int, help="Override listen port from config")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              show_default=True)
@click.option("--transport", default="websocket",
              type=click.Choice(["websocket", "stdio"]), show_default=True)
def main(config: str, host: str | None, port: int | None, log_level: str, transport: str) -> None:
    """ZeroPoint MCP Server — start the selected MCP transport."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    if transport == "stdio":
        asyncio.run(run_stdio(config))
        return

    # Detect active IP at runtime for cluster config — in memory only, no disk writes.
    runtime_host: str | None = None
    try:
        detected = get_active_ip()
        if detected and detected != "127.0.0.1":
            runtime_host = detected
            logger.info("Runtime IP detected: %s (in-memory override, config unchanged)", detected)
    except Exception as exc:
        logger.warning("Could not detect runtime IP: %s", exc)

    cfg = yaml.safe_load(Path(config).read_text())
    server_cfg = cfg.get("server", {})

    # Default to loopback — explicit config or --host flag required for LAN exposure.
    listen_host = host or server_cfg.get("host", "127.0.0.1")
    listen_port = port or server_cfg.get("port", 8765)

    if listen_host in ("0.0.0.0", ""):
        logger.warning(
            "Server bound to 0.0.0.0 — MCP endpoint is reachable by ALL devices "
            "on this network. Ensure auth is enabled and firewall rules are in place."
        )

    app = build_app(config, runtime_host_override=runtime_host)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(app)

    async def _run() -> None:
        await runner.setup()
        site = web.TCPSite(runner, listen_host, listen_port)
        await site.start()
        logger.info("MCP (Streamable HTTP): http://%s:%d/mcp", listen_host, listen_port)
        logger.info("MCP (WebSocket, legacy): ws://%s:%d/mcp", listen_host, listen_port)
        logger.info("Health: http://%s:%d/health", listen_host, listen_port)

        stop = loop.create_future()
        if os.name == "nt":
            def handle_signal(sig, frame):
                loop.call_soon_threadsafe(
                    lambda: stop.set_result(None) if not stop.done() else None
                )
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    signal.signal(sig, handle_signal)
                except ValueError:
                    pass
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set_result, None)

        await stop
        await runner.cleanup()

    loop.run_until_complete(_run())


if __name__ == "__main__":
    main()
