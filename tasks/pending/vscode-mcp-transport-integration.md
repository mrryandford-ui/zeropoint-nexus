# Integrate ZeroPoint with VS Code MCP transport

## Goal
Expose the running ZeroPoint filesystem and web tools to VS Code without OAuth prompts or incompatible transport errors.

## Current finding
- `.vscode/mcp.json` previously configured `zeropoint` as HTTP.
- The ZeroPoint server currently exposes `/mcp` as WebSocket-only.
- HTTP POST to `/mcp` returns `405`.
- `MCP_AUTH_TOKEN` is not present in the VS Code environment.
- Setting `"enabled": false` on the HTTP server entry did NOT stop VS Code
  from attempting to connect and triggering OAuth dynamic client
  registration prompts (confirmed via MCP output log timestamps after the
  edit). The entries were removed entirely instead (`"servers": {}`).
- The previously defined `zeropoint-fs-stdio` entry used
  `--transport stdio` and `--tools filesystem` CLI flags that
  `zeropoint/server.py` does not implement (`build_app()` only accepts a
  config path). That entry was never functional and was removed too.

## Required work
- Implement an actual VS Code-compatible transport in the ZeroPoint server:
  either a stdio mode or a Streamable HTTP endpoint (not raw WebSocket).
- Pass the local bearer token securely without printing or hard-coding it.
- Test initialize, tools/list, and a harmless filesystem read through the
  real VS Code MCP client (not just curl/Invoke-WebRequest).
- Re-add the workspace registration in `.vscode/mcp.json` only after the
  handshake succeeds end-to-end.
- Keep the local server usable when ZERO-FLD is unavailable.
