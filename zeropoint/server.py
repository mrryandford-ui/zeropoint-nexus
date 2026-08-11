"""
ZeroPoint MCP Server — WebSocket entrypoint.

Implements the Model Context Protocol (MCP) 1.0 over WebSocket + JSON-RPC 2.0.
Handles: initialize, tools/list, tools/call, ping, shutdown.
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
# MCP WebSocket handler
###############################################################################

class MCPHandler:
    """Stateful WebSocket session handler — one instance per connection."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_INFO = {"name": "zeropoint-mcp", "version": "1.0.0"}

    def __init__(self, registry: ToolRegistry, auth: Any, server_cfg: dict):
        self.registry = registry
        self.auth = auth
        self.cfg = server_cfg
        self._initialized = False

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        # Auth check before upgrade
        if self.auth:
            auth_header = request.headers.get("Authorization")
            peer = request.remote or "unknown"
            if not self.auth.validate_header(auth_header, peer):
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

    async def _dispatch(self, raw: str) -> dict | None:
        """Parse JSON-RPC, route to method handler, return response."""
        try:
            req = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _err(None, -32700, f"Parse error: {exc}")

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
            logger.error("Unhandled error in method '%s': %s", method, exc, exc_info=True)
            return _err(req_id, -32603, "Internal error", str(exc))

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
# HTTP health endpoint
###############################################################################

async def health_handler(request: web.Request) -> web.Response:
    registry: ToolRegistry = request.app["registry"]
    return web.json_response({
        "status": "ok",
        "tools": len(registry),
        "server": MCPHandler.SERVER_INFO,
    })

###############################################################################
# App factory
###############################################################################

def build_app(config_path: str) -> web.Application:
    cfg = yaml.safe_load(Path(config_path).read_text())
    server_cfg = cfg.get("server", {})

    # Observability
    init_observability(cfg.get("observability", {}))

    # Auth
    auth = build_auth(server_cfg.get("auth", {}))

    # Registry
    registry = ToolRegistry(config_path)
    registry.load()

    # aiohttp app
    app = web.Application()
    app["registry"] = registry
    app["config"] = cfg

    handler = MCPHandler(registry, auth, server_cfg)

    app.router.add_get("/mcp", handler.handle_ws)
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
# CLI
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

@click.command()
@click.option("--config", default="/workspace/zeropoint/config/mcp_server_config.yaml",
              show_default=True, help="Path to mcp_server_config.yaml")
@click.option("--host", default=None, help="Override listen host from config")
@click.option("--port", default=None, type=int, help="Override listen port from config")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              show_default=True)
def main(config: str, host: str | None, port: int | None, log_level: str) -> None:
    """ZeroPoint MCP Server — start the WebSocket MCP endpoint."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    # Dynamic IP detection and update in config
    try:
        active_ip = get_active_ip()
        if active_ip and active_ip != "127.0.0.1":
            config_path = Path(config)
            content = config_path.read_text(encoding="utf-8")
            import re
            new_content = re.sub(r'(coordinator_host:\s*")[^"]+', f'\\g<1>{active_ip}', content)
            new_content = re.sub(r'(head_node:\s*")[^":]+', f'\\g<1>{active_ip}', new_content)
            if new_content != content:
                config_path.write_text(new_content, encoding="utf-8")
                logging.info(f"Dynamically updated server config with local IP: {active_ip}")
    except Exception as e:
        logging.warning(f"Could not dynamically update config IP: {e}")

    cfg = yaml.safe_load(Path(config).read_text())
    server_cfg = cfg.get("server", {})
    listen_host = host or server_cfg.get("host", "0.0.0.0")
    listen_port = port or server_cfg.get("port", 8765)

    app = build_app(config)

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    runner = web.AppRunner(app)

    async def _run() -> None:
        await runner.setup()
        site = web.TCPSite(runner, listen_host, listen_port)
        await site.start()
        logger.info("Listening on ws://%s:%d/mcp", listen_host, listen_port)
        logger.info("Health:   http://%s:%d/health", listen_host, listen_port)

        stop = loop.create_future()
        if os.name == "nt":
            def handle_signal(sig, frame):
                loop.call_soon_threadsafe(lambda: stop.set_result(None) if not stop.done() else None)
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

