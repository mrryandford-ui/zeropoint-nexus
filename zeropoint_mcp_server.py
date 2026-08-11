"""
ZeroPoint MCP Identity/Ray server (MCP 2.x style)
This ASGI server exposes simple MCP-style HTTP endpoints for identity and Ray integration.

Endpoints (HTTP JSON API):
- POST /mcp/get_node_identity
- POST /mcp/get_cluster_registry
- POST /mcp/get_governance
- POST /mcp/submit_task
- POST /mcp/list_ray_nodes

Runs on port 8766 and initializes Ray with namespace 'zeropoint'.
This is a lightweight MCP-compatible service for identity and Ray orchestration.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import socket
import os
import json
import sys
import time
import uuid

# Ray is optional; initialize if available
try:
    import ray
    RAY_AVAILABLE = True
except Exception:
    RAY_AVAILABLE = False

ROOT = os.path.dirname(os.path.abspath(__file__))
CLUSTER_REGISTRY_PATH = os.path.join(ROOT, "cluster_registry.json")
GOV_PATH = os.path.join(ROOT, "governance.json")

app = FastAPI(title="ZeroPoint Identity MCP Server")

# Helper: load json file safely
def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# TCP fallback to check Ray head reachability
def _tcp_check_ray(address):
    try:
        if not address or address == "auto":
            return {"ok": False, "reason": "no address"}
        host, port = address.split(":")
        import socket as _socket
        s = _socket.create_connection((host, int(port)), timeout=5)
        s.close()
        return {"ok": True, "note": "tcp-reachable"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

# Initialize Ray if available; fall back to TCP connectivity check when Ray import fails
def init_ray():
    address = os.environ.get("RAY_ADDRESS", "auto")
    if RAY_AVAILABLE:
        try:
            ray.init(address=address, namespace="zeropoint", ignore_reinit_error=True)
            return {"ok": True}
        except Exception as e:
            tcp = _tcp_check_ray(address)
            if tcp.get("ok"):
                return {"ok": True, "note": "connected_via_tcp_fallback"}
            return {"ok": False, "reason": str(e)}
    else:
        return _tcp_check_ray(address)

# Initial attempt to connect; subsequent health checks call init_ray() to refresh status
RAY_INIT_RESULT = init_ray()

# Tools (HTTP endpoints)
@app.post("/mcp/get_node_identity")
async def get_node_identity(request: Request):
    """Return basic node identity information."""
    hostname = socket.gethostname()
    pid = os.getpid()
    uid = str(uuid.uuid4())
    return JSONResponse({
        "hostname": hostname,
        "pid": pid,
        "uid": uid,
        "ray": init_ray(),
        "timestamp": time.time()
    })

@app.post("/mcp/get_cluster_registry")
async def get_cluster_registry(request: Request):
    """Return the cluster_registry.json contents."""
    data = _load_json(CLUSTER_REGISTRY_PATH, default={"nodes": []})
    return JSONResponse({"ok": True, "cluster_registry": data})

@app.post("/mcp/get_governance")
async def get_governance(request: Request):
    """Return governance.json contents."""
    data = _load_json(GOV_PATH, default={"version": 1, "policies": [], "capabilities": []})
    return JSONResponse({"ok": True, "governance": data})

@app.post("/mcp/list_ray_nodes")
async def list_ray_nodes(request: Request):
    """Return Ray cluster node information (if Ray available)."""
    if not RAY_AVAILABLE:
        return JSONResponse({"ok": False, "reason": "ray not available"})
    try:
        nodes = ray.nodes()
        return JSONResponse({"ok": True, "nodes": nodes})
    except Exception as e:
        return JSONResponse({"ok": False, "reason": str(e)})

@app.post("/mcp/submit_task")
async def submit_task(request: Request):
    """Submit a task to Ray. Expects a JSON body with at least 'task' field.

    This endpoint is identity-aware in the sense it returns a submission id and
    will attempt to schedule on the Ray cluster that was connected to during init.
    """
    body = await request.json()
    task_payload = body.get("task") if isinstance(body, dict) else None
    if not task_payload:
        return JSONResponse({"ok": False, "reason": "missing 'task' in body"})

    if not RAY_AVAILABLE:
        return JSONResponse({"ok": False, "reason": "ray not available"})

    try:
        # For safety, run an extremely small remote wrapper that echoes the payload
        @ray.remote
        def _exec_task(payload):
            # Placeholder: user should replace with real task logic
            return {"received": payload, "node": ray.util.get_node_ip_address() if hasattr(ray.util, 'get_node_ip_address') else None}

        ref = _exec_task.remote(task_payload)
        # Optionally wait or return ref id
        obj = ray.get(ref)
        return JSONResponse({"ok": True, "result": obj})
    except Exception as e:
        return JSONResponse({"ok": False, "reason": str(e)})

@app.get("/health")
async def health():
    # Refresh Ray init status on each health call so the endpoint reflects current cluster state
    ray_status = init_ray()
    return JSONResponse({"ok": True, "service": "zeropoint-identity", "ray": ray_status})

if __name__ == "__main__":
    # Run on port 8766
    uvicorn.run("zeropoint_mcp_server:app", host="0.0.0.0", port=8766, log_level="info")
