import json, uuid

node_id = uuid.uuid4().hex

identity = {
    "node_id": node_id,
    "machine": "HP Envy x360",
    "path": r"C:\Users\zeroi\Downloads\zeropoint-mcp"
}

with open(r"C:\Users\zeroi\Downloads\zeropoint-mcp\node\\identity.json", "w") as f:
    json.dump(identity, f, indent=2)

with open(r"C:\Users\zeroi\Downloads\zeropoint-mcp\node\\node_id.txt", "w") as f:
    f.write(node_id)
