# ZeroPoint MCP Server Autostart

ZeroPoint uses Windows Task Scheduler for automatic startup. The supported task is:

```text
\ZeroPoint\ZeroPoint-MCP-Autostart
```

The task launches `dev_start.ps1` from the repository root as the local system account.
The setup and removal scripts also delete legacy `ZeroPoint-MCP-Start.bat` launchers from
the current-user and all-users Startup folders so those entries do not remain visible or
start a stale copy from the old Downloads location.

## Check status

```powershell
.\manage_autostart.ps1 -Check
```

This reports the scheduled-task state, recent result, MCP health, and any legacy Startup-folder
launchers that still need cleanup.

## Enable or disable

```powershell
.\manage_autostart.ps1 -Enable
.\manage_autostart.ps1 -Disable
```

These commands enable or disable the scheduled task. They do not create Startup-folder files.

## Remove autostart

```powershell
.\manage_autostart.ps1 -Remove
```

This unregisters the scheduled task and removes legacy Startup-folder launchers.

## Install or repair the task

Run PowerShell as Administrator, then:

```powershell
.\setup_autostart.ps1
```

Verification without changing the task:

```powershell
.\setup_autostart.ps1 -Verify
```

## Manual server control

```powershell
.\dev_start.ps1
.\dev_start.ps1 -Stop
Get-Content .\server.log -Wait
```

## Endpoints

- WebSocket MCP: `ws://localhost:8765/mcp`
- Health check: `http://localhost:8765/health`
- Identity service: `http://localhost:8766`

**Status:** Scheduled-task autostart is the supported configuration.
