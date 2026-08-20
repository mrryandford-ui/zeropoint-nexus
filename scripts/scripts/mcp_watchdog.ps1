################################################################################
# ZeroPoint MCP Watchdog
# Checks the local MCP server health and restarts it if the service is down.
################################################################################

$ROOT = Split-Path -Parent $PSScriptRoot
$DEV_START = Join-Path $ROOT "dev_start.ps1"
$HEALTH_URL = "http://localhost:8765/health"

function Test-McpHealth {
    try {
        $resp = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing -TimeoutSec 5
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-McpServer {
    try {
        $conns = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
        if ($conns) {
            $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($pid in $pids) {
                try {
                    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                } catch {
                    Write-Host ("Could not stop process {0}: {1}" -f $pid, $_) -ForegroundColor Yellow
                }
            }
        }
    } catch {
        Write-Host "Unable to inspect MCP port listeners: $_" -ForegroundColor Yellow
    }
}

while ($true) {
    if (Test-McpHealth) {
        Write-Host "ZeroPoint MCP is healthy. Next health check in 5 minutes."
    } else {
        Write-Host "ZeroPoint MCP is not healthy. Restarting server..."
        Stop-McpServer
        Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$DEV_START" -WindowStyle Hidden
        Write-Host "Started dev_start.ps1 in the background."
    }
    Start-Sleep -Seconds 300
}
