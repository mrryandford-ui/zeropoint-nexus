# ZeroPoint MCP Server Autostart Configuration

Your MCP servers are now configured to start automatically on system boot!

## ✓ What's Been Set Up

A batch file has been created in your Windows Startup folder:
```
C:\Users\ZeroPoint\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-MCP-Start.bat
```

This file automatically runs when Windows starts and launches the MCP servers in the background.

## How It Works

1. **System boots** → Windows loads all startup programs
2. **Startup folder runs** → ZeroPoint-MCP-Start.bat executes
3. **Batch file launches** → PowerShell runs `dev_start.ps1`
4. **MCP servers start** → WebSocket server (ws://localhost:8765/mcp) becomes available
5. **Logs are recorded** → `autostart.log` tracks startup events

## Management Commands

### Check Status
```powershell
.\manage_autostart.ps1 -Check
```
Shows if autostart is enabled and server status.

### Disable Autostart (Temporary)
```powershell
.\manage_autostart.ps1 -Disable
```
Temporarily disables autostart without deleting the file (can be re-enabled).

### Re-Enable Autostart
```powershell
.\manage_autostart.ps1 -Enable
```
Re-enables autostart after disabling it.

### Remove Autostart (Permanent)
```powershell
.\manage_autostart.ps1 -Remove
```
Permanently removes the autostart configuration.

## Manual Server Control

### Start MCP Server
```powershell
.\dev_start.ps1
```
Manually starts the MCP server in the current PowerShell window.

### Stop MCP Server
```powershell
.\dev_start.ps1 -Stop
```
Stops all running ZeroPoint MCP server processes.

### View Server Logs
```powershell
Get-Content server.log -Wait
```
Live view of server logs (press Ctrl+C to exit).

### View Autostart Logs
```powershell
Get-Content autostart.log -Wait
```
View logs from automatic startup events.

## Testing Autostart

1. **Reboot your computer**
   ```powershell
   Restart-Computer
   ```

2. **After restart, verify status:**
   ```powershell
   .\manage_autostart.ps1 -Check
   ```

3. **Expected output:**
   - ✓ Autostart ENABLED
   - ✓ MCP Server is RUNNING

## Files Created

| File | Purpose |
|------|---------|
| `setup_autostart.ps1` | Original setup script (for reference) |
| `manage_autostart.ps1` | Manage autostart settings |
| `ZeroPoint-MCP-Start.bat` | Startup batch file (in Startup folder) |
| `autostart.log` | Logs from automatic startup events |

## Troubleshooting

### Server not starting on boot?
1. Check autostart status: `.\manage_autostart.ps1 -Check`
2. Review autostart logs: `Get-Content autostart.log -Wait`
3. Try manual start: `.\dev_start.ps1`
4. Check server logs: `Get-Content server.log -Wait`

### Need to disable autostart temporarily?
```powershell
.\manage_autostart.ps1 -Disable
```
Then re-enable when ready:
```powershell
.\manage_autostart.ps1 -Enable
```

### Want to remove autostart completely?
```powershell
.\manage_autostart.ps1 -Remove
```

## Server Endpoints

Once running (either manually or via autostart):
- **WebSocket MCP**: `ws://localhost:8765/mcp`
- **Health Check**: `http://localhost:8765/health`
- **Metrics**: `http://localhost:9090/metrics`

## Quick Reference

```powershell
# Check if autostart works after restart
.\manage_autostart.ps1 -Check

# Manually start server
.\dev_start.ps1

# Manually stop server
.\dev_start.ps1 -Stop

# View real-time server logs
Get-Content server.log -Wait

# Disable/enable autostart
.\manage_autostart.ps1 -Disable
.\manage_autostart.ps1 -Enable

# Remove autostart completely
.\manage_autostart.ps1 -Remove
```

---
**Created:** 2026-08-10
**Status:** ✓ Autostart Configured and Ready
