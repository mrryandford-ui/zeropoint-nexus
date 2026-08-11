# ZeroPoint MCP

ZeroPoint MCP is a private two-node AI/tooling cluster for local system work, analysis, and automation.

## Goal

- **ZERO-DEV (HP Envy)**: frontend/workstation for day-to-day use
- **ZERO-FLD (Lenovo IdeaPad 5)**: backend/head node for orchestration and heavier work

The cluster is intended to:

- run local MCP tools quickly on the workstation
- route heavier jobs to the backend
- share settings, MCP servers, and identity through VS Code sync and cluster config

## Main components

- **MCP core** on port **8765**
- **Identity service** on port **8766**
- **Ray** for distributed execution on port **6379**
- **Prometheus** on port **9090**
- **OTEL collector** on port **4317** when enabled

## What is included

- filesystem tools
- web tools
- ADB tools
- Android tooling
- control-plane orchestration
- OSINT helpers
- pentest helpers
- IT support helpers
- Ray actors for distributed work

## Important files

- [PROJECT_STATUS.txt](PROJECT_STATUS.txt)
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)
- [CLUSTER_STATUS.md](CLUSTER_STATUS.md)
- [CLUSTER_SETUP_GUIDE.md](CLUSTER_SETUP_GUIDE.md)
- [CLUSTER_STARTUP_NOW.md](CLUSTER_STARTUP_NOW.md)
- [dev_start.ps1](dev_start.ps1)
- [verify_cluster_connection.ps1](verify_cluster_connection.ps1)
- [activate_cluster_head.ps1](activate_cluster_head.ps1)
- [cluster_registry.json](cluster_registry.json)
- [governance.json](governance.json)

## Quick start

### On ZERO-FLD

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1 -RayHead
```

### On ZERO-DEV

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1
```

### Verify

```powershell
.\verify_cluster_connection.ps1 -Connect
```

## Notes

- `pyproject.toml` expects this file as the project README.
- Settings Sync should be enabled in VS Code on both machines.
- The backend should remain the cluster head; the workstation should remain the interactive front end.
