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

# send initialize
init_msg = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"tester","version":"1.0"}}})
ws.send(init_msg)
resp = ws.recv()
print('INIT_RESP:', resp)

# send tools/list
list_msg = json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list"})
ws.send(list_msg)
resp2 = ws.recv()
print('TOOLS_LIST:', resp2)

# send filesystem_list call
call_msg = json.dumps({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"filesystem_list","arguments":{"path":"."}}})
ws.send(call_msg)
resp3 = ws.recv()
print('FS_LIST_RESP:', resp3)

# web fetch test via webtools_fetch
fetch_msg = json.dumps({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"webtools_fetch","arguments":{"url":"https://httpbin.org/get"}}})
ws.send(fetch_msg)
resp4 = ws.recv()
print('WEB_FETCH_RESP:', resp4)

ws.close()
