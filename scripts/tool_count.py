import json
from websocket import create_connection

token = None
with open('config/.env') as f:
    for line in f:
        if line.startswith('MCP_AUTH_TOKEN'):
            token = line.split('=',1)[1].strip()
            break
if not token:
    raise SystemExit('No MCP_AUTH_TOKEN')

url = 'ws://127.0.0.1:8765/mcp'
headers = [f'Authorization: Bearer {token}']
ws = create_connection(url, header=headers)

# initialize
ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"tool-counter","version":"1.0"}}}))
ws.recv()
# tools list
ws.send(json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list"}))
resp = ws.recv()
obj = json.loads(resp)
tools = obj.get('result', {}).get('tools', [])
print(len(tools))
ws.close()
