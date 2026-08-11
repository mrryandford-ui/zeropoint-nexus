"""
ZeroPoint Core MCP Server (MCP 2.x style)

- FastAPI server listening on port 8765
- Exposes a single /mcp POST endpoint for handshake and tool calls
- Exposes /health GET endpoint

Tools implemented (MCP 2.x style):
- filesystem_read
- filesystem_list
- filesystem_search
- filesystem_write
- filesystem_delete
- webtools_fetch
- webtools_scrape
- adb_devices
- adb_screenshot

Security: filesystem operations are sandboxed to the project root.
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import io
import json
import time
import socket
import base64
import subprocess
import shlex
from typing import Optional

# Optional dependencies: requests, bs4
try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_SEARCH_RESULTS = 200
MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB max read

app = FastAPI(title="ZeroPoint Core MCP Server")

# Helpers
def safe_join(root: str, path: str) -> str:
    # Prevent path traversal outside of root
    joined = os.path.normpath(os.path.join(root, path))
    if not joined.startswith(os.path.normpath(root) + os.sep) and os.path.normpath(joined) != os.path.normpath(root):
        raise ValueError("Path escapes allowed root")
    return joined

def read_file_text(path: str, max_bytes: int = MAX_READ_BYTES):
    with open(path, 'rb') as f:
        data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        # Return base64 to avoid truncation confusion
        return {"binary": True, "content": base64.b64encode(data).decode('utf-8'), "encoding": "base64"}
    try:
        text = data.decode('utf-8')
        return {"binary": False, "content": text}
    except Exception:
        return {"binary": True, "content": base64.b64encode(data).decode('utf-8'), "encoding": "base64"}

# Tool implementations
async def tool_filesystem_read(args: dict):
    path = args.get('path')
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")
    fp = safe_join(ROOT, path)
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="file not found")
    return {"ok": True, "path": path, "result": read_file_text(fp)}

async def tool_filesystem_list(args: dict):
    path = args.get('path', '.')
    fp = safe_join(ROOT, path)
    if not os.path.exists(fp):
        raise HTTPException(status_code=404, detail="path not found")
    if os.path.isfile(fp):
        return {"ok": True, "path": path, "type": "file", "size": os.path.getsize(fp)}
    items = []
    for name in os.listdir(fp):
        p = os.path.join(fp, name)
        items.append({"name": name, "is_dir": os.path.isdir(p), "size": os.path.getsize(p) if os.path.isfile(p) else None})
    return {"ok": True, "path": path, "items": items}

async def tool_filesystem_search(args: dict):
    query = args.get('query')
    path = args.get('path', '.')
    if not query:
        raise HTTPException(status_code=400, detail="'query' is required")
    fp = safe_join(ROOT, path)
    results = []
    qlower = query.lower()
    for dirpath, dirnames, filenames in os.walk(fp):
        # search filenames
        for fn in filenames:
            if qlower in fn.lower():
                rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
                results.append({"path": rel, "match": "filename"})
                if len(results) >= MAX_SEARCH_RESULTS:
                    return {"ok": True, "results": results}
        # search file contents (small files only)
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 256 * 1024:
                    continue
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    txt = f.read()
                if qlower in txt.lower():
                    rel = os.path.relpath(p, ROOT)
                    results.append({"path": rel, "match": "content"})
                    if len(results) >= MAX_SEARCH_RESULTS:
                        return {"ok": True, "results": results}
            except Exception:
                continue
    return {"ok": True, "results": results}

async def tool_filesystem_write(args: dict):
    path = args.get('path')
    content = args.get('content')
    mode = args.get('mode', 'w')
    if not path or content is None:
        raise HTTPException(status_code=400, detail="'path' and 'content' are required")
    fp = safe_join(ROOT, path)
    d = os.path.dirname(fp)
    os.makedirs(d, exist_ok=True)
    # Support writing base64 binary if provided as dict
    if isinstance(content, dict) and content.get('encoding') == 'base64':
        data = base64.b64decode(content.get('content', ''))
        with open(fp, 'wb') as f:
            f.write(data)
        return {"ok": True, "path": path, "written": len(data), "binary": True}
    else:
        with open(fp, mode, encoding='utf-8') as f:
            f.write(str(content))
        return {"ok": True, "path": path, "written": len(str(content)), "binary": False}

async def tool_filesystem_delete(args: dict):
    path = args.get('path')
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")
    fp = safe_join(ROOT, path)
    if not os.path.exists(fp):
        raise HTTPException(status_code=404, detail="path not found")
    try:
        if os.path.isfile(fp):
            os.remove(fp)
            return {"ok": True, "deleted": path}
        else:
            # remove directory tree
            import shutil
            shutil.rmtree(fp)
            return {"ok": True, "deleted": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def tool_webtools_fetch(args: dict):
    url = args.get('url')
    timeout = float(args.get('timeout', 10))
    if not url:
        raise HTTPException(status_code=400, detail="'url' is required")
    if requests is None:
        return {"ok": False, "reason": "requests library not available"}
    try:
        r = requests.get(url, timeout=timeout)
        text = r.text
        # truncate large responses
        if len(text) > 100_000:
            text = text[:100_000] + '\n...truncated...'
        return {"ok": True, "status_code": r.status_code, "headers": dict(r.headers), "text": text}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

async def tool_webtools_scrape(args: dict):
    url = args.get('url')
    selector = args.get('selector')
    if not url:
        raise HTTPException(status_code=400, detail="'url' is required")
    if requests is None:
        return {"ok": False, "reason": "requests library not available"}
    if BeautifulSoup is None:
        return {"ok": False, "reason": "bs4 (BeautifulSoup) not available"}
    try:
        r = requests.get(url, timeout=float(args.get('timeout', 10)))
        soup = BeautifulSoup(r.text, 'html.parser')
        if selector:
            nodes = soup.select(selector)
        else:
            nodes = [soup]
        out = []
        for n in nodes:
            out.append({"text": n.get_text(strip=True), "html": str(n)})
        return {"ok": True, "results": out}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

async def tool_adb_devices(args: dict):
    # Uses system adb command if available
    adb = args.get('adb_path', 'adb')
    try:
        proc = subprocess.run([adb, 'devices', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        out = proc.stdout.decode('utf-8', errors='ignore')
        # parse lines
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith('List of devices'):
                continue
            parts = line.split()
            serial = parts[0]
            state = parts[1] if len(parts) > 1 else ''
            devices.append({'serial': serial, 'state': state, 'raw': line})
        return {"ok": True, "devices": devices}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

async def tool_adb_screenshot(args: dict):
    adb = args.get('adb_path', 'adb')
    serial = args.get('serial')
    target_tmp = os.path.join(ROOT, 'tmp')
    os.makedirs(target_tmp, exist_ok=True)
    try:
        # Using adb exec-out screencap -p
        cmd = [adb]
        if serial:
            cmd.extend(['-s', serial])
        cmd.extend(['exec-out', 'screencap', '-p'])
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
        if proc.returncode != 0:
            return {"ok": False, "reason": proc.stderr.decode('utf-8', errors='ignore')}
        data = proc.stdout
        b64 = base64.b64encode(data).decode('utf-8')
        return {"ok": True, "image_base64": b64}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

# Tool registry
TOOL_REGISTRY = {
    'filesystem_read': {
        'description': 'Read a file under workspace root',
        'schema': {'path': 'relative path to file'}
    },
    'filesystem_list': {
        'description': 'List directory contents under workspace root',
        'schema': {'path': 'relative path (optional)'}
    },
    'filesystem_search': {
        'description': 'Search filenames and small file contents',
        'schema': {'query': 'search string', 'path': 'relative root (optional)'}
    },
    'filesystem_write': {
        'description': 'Write file; supports plain text or {encoding: base64, content: ...}',
        'schema': {'path': 'relative path', 'content': 'string or base64 dict'}
    },
    'filesystem_delete': {
        'description': 'Delete file or directory',
        'schema': {'path': 'relative path'}
    },
    'webtools_fetch': {'description': 'HTTP GET fetch', 'schema': {'url': 'http://...'}},
    'webtools_scrape': {'description': 'Fetch and scrape HTML via CSS selector', 'schema': {'url': 'http://...', 'selector': 'CSS selector (optional)'}},
    'adb_devices': {'description': 'List adb devices using system adb', 'schema': {}},
    'adb_screenshot': {'description': 'Capture device screenshot via adb exec-out screencap -p', 'schema': {'serial': '(optional) device serial'}}
}

# Dispatcher
TOOL_HANDLERS = {
    'filesystem_read': tool_filesystem_read,
    'filesystem_list': tool_filesystem_list,
    'filesystem_search': tool_filesystem_search,
    'filesystem_write': tool_filesystem_write,
    'filesystem_delete': tool_filesystem_delete,
    'webtools_fetch': tool_webtools_fetch,
    'webtools_scrape': tool_webtools_scrape,
    'adb_devices': tool_adb_devices,
    'adb_screenshot': tool_adb_screenshot
}

@app.post('/mcp')
async def mcp_entry(request: Request):
    """MCP 2.x single endpoint API.

    Expected JSON body examples:
    - Handshake: {"method": "handshake"}
    - Call tool: {"method": "call", "tool": "filesystem_read", "args": {"path": "file.txt"}}
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    method = body.get('method')
    if not method:
        raise HTTPException(status_code=400, detail="'method' is required")

    if method == 'handshake':
        return JSONResponse({
            'ok': True,
            'service': 'zeropoint-core',
            'host': socket.gethostname(),
            'tools': TOOL_REGISTRY,
            'timestamp': time.time()
        })

    if method == 'call':
        tool = body.get('tool')
        args = body.get('args', {}) or {}
        if not tool:
            raise HTTPException(status_code=400, detail="'tool' is required for call")
        handler = TOOL_HANDLERS.get(tool)
        if not handler:
            raise HTTPException(status_code=404, detail=f"tool not found: {tool}")
        # Call the handler
        try:
            result = await handler(args)
            return JSONResponse(result)
        except HTTPException as he:
            raise he
        except Exception as e:
            return JSONResponse({'ok': False, 'reason': str(e)})

    raise HTTPException(status_code=400, detail='unknown method')

@app.get('/health')
async def health():
    return JSONResponse({'status': 'ok'})

if __name__ == '__main__':
    # Run the ASGI app on port 8765
    uvicorn.run('zeropoint_mcp_main:app', host='0.0.0.0', port=8765, log_level='info')
