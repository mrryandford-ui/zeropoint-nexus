################################################################################
# ZeroPoint MCP Stack -- dev_start.ps1
# Usage:
#   .\dev_start.ps1              # MCP server only
#   .\dev_start.ps1 -RayHead     # MCP server + Ray head node
#   .\dev_start.ps1 -Stop        # Kill all ZeroPoint processes
################################################################################
param(
    [switch]$RayHead,
    [switch]$Stop
)

$ROOT   = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$VENV   = "$ROOT\.venv"
$PY     = "$VENV\Scripts\python.exe"
$ENV    = "$ROOT\config\.env"
$CFG    = "$ROOT\config\mcp_server_config.yaml"
$LOG    = "$ROOT\server.log"

Set-Location $ROOT

function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ZeroPoint MCP Stack  --  dev_start.ps1" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

if ($Stop) {
    INF "Stopping ZeroPoint processes..."
    Get-Job | Where-Object { $_.Name -like "ZP_*" } | ForEach-Object {
        Stop-Job $_; Remove-Job $_
        OK "Stopped job: $($_.Name)"
    }
    OK "Done."; exit 0
}

# Load .env
$token = $null
if (Test-Path $ENV) {
    $envLines = Get-Content $ENV -ErrorAction SilentlyContinue
    $updatedLines = @()
    $foundTokenLine = $false
    foreach ($line in $envLines) {
        if ($line -match "^\s*#") {
            $updatedLines += $line
            continue
        }

        if ($line -match "^\s*MCP_AUTH_TOKEN\s*=\s*(.*)$") {
            $foundTokenLine = $true
            $current = $Matches[1].Trim('"').Trim("'")
            if ($current) {
                $token = $current
            }
            $updatedLines += $line
            continue
        }

        $updatedLines += $line
    }

    if (-not $foundTokenLine -or -not $token) {
        WRN "config\.env has no valid MCP_AUTH_TOKEN -- generating a new token..."
        $token = ([System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))) -replace "[^A-Za-z0-9]", ""
        if (-not $foundTokenLine) {
            $updatedLines += "MCP_AUTH_TOKEN=$token"
        } else {
            $updatedLines = $updatedLines | ForEach-Object {
                if ($_ -match "^\s*MCP_AUTH_TOKEN\s*=\s*(.*)$") { "MCP_AUTH_TOKEN=$token" } else { $_ }
            }
        }
        New-Item -ItemType Directory -Force -Path "$ROOT\config" | Out-Null
        $updatedLines | Set-Content $ENV -Encoding UTF8
        foreach ($line in $updatedLines | Where-Object { $_ -match "^\s*[^#].+=." }) {
            $parts = $line -split "=", 2
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
        }
        OK "Generated token -> config\.env"
        Write-Host "  Token: $token" -ForegroundColor Magenta
    } else {
        foreach ($line in $envLines | Where-Object { $_ -match "^\s*[^#].+=." }) {
            $parts = $line -split "=", 2
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
        }
        OK "Loaded config\.env"
    }
} else {
    WRN "config\.env not found -- generating default token..."
    $token = ([System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))) -replace "[^A-Za-z0-9]", ""
    New-Item -ItemType Directory -Force -Path "$ROOT\config" | Out-Null
    "MCP_AUTH_TOKEN=$token" | Set-Content $ENV -Encoding UTF8
    $env:MCP_AUTH_TOKEN = $token
    OK "Generated token -> config\.env"
    Write-Host "  Token: $token" -ForegroundColor Magenta
}

# Check Python venv
if (-not (Test-Path $PY)) {
    ERR "Virtual environment not found at $VENV"
    Write-Host ""
    Write-Host "  Run these commands first:" -ForegroundColor Yellow
    Write-Host "    winget install -e --id Python.Python.3.11" -ForegroundColor White
    Write-Host "    (reopen PowerShell, then cd to project root)" -ForegroundColor White
    Write-Host "    python -m venv .venv" -ForegroundColor White
    Write-Host "    .venv\Scripts\pip install -e .[dev]" -ForegroundColor White
    exit 1
}

$env:PYTHONPATH = $ROOT
OK "PYTHONPATH = $ROOT"

if (-not (Test-Path $CFG)) { ERR "Config not found: $CFG"; exit 1 }
OK "Config: $CFG"

# Dynamic IP detection and config update
INF "Detecting active network IP address..."
$activeIp = $null
$activeIp = (Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress
if (-not $activeIp) {
    $activeIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notlike "*Loopback*" } | Select-Object -First 1).IPAddress
}
if ($activeIp) {
    OK "Detected active local IP: $activeIp"
    $cfgContent = Get-Content $CFG -Raw
    $cfgContent = $cfgContent -replace '(?<=coordinator_host:\s*")[^"]+', $activeIp
    $cfgContent = $cfgContent -replace '(?<=head_node:\s*")[^":]+', $activeIp
    $cfgContent | Set-Content $CFG -NoNewline
    OK "Dynamically updated config with active IP $activeIp"
} else {
    WRN "Could not detect active IP address. Keeping default configuration."
}

# Start MCP server
INF "Starting MCP server on ws://localhost:8765 ..."
$mcpJob = Start-Job -Name "ZP_MCP" -ScriptBlock {
    param($py, $cfg, $root, $log)
    $env:PYTHONPATH = $root
    & $py -m zeropoint.server --config $cfg 2>&1 | Tee-Object -FilePath $log
} -ArgumentList $PY, $CFG, $ROOT, $LOG

Start-Sleep 2

if ($mcpJob.State -eq "Running") {
    OK "MCP server started (Job ID: $($mcpJob.Id))"
    OK "WebSocket : ws://localhost:8765/mcp"
    OK "Log       : $LOG"
} else {
    ERR "MCP server failed! Check $LOG"
    Receive-Job $mcpJob; exit 1
}

# Identity service (port 8766)
INF "Starting Identity service on port 8766..."
$identityJob = Start-Job -Name "ZP_IDENTITY" -ScriptBlock {
    param($py, $root)
    $env:PYTHONPATH = $root
    & $py $root\zeropoint_mcp_server.py
} -ArgumentList $PY, $ROOT
Start-Sleep 2
if ($identityJob.State -eq "Running") {
    OK "Identity service started on port 8766"
} else {
    WRN "Identity service failed -- cluster identity checks will fail"
    Receive-Job $identityJob
}

# Optional Ray head
if ($RayHead) {
    $rayExe = "$VENV\Scripts\ray.exe"
    if (Test-Path $rayExe) {
        INF "Starting Ray head node on port 6379 with advertised IP $activeIp..."
        $rayJob = Start-Job -Name "ZP_RAY" -ScriptBlock {
            param($ray, $ip)
            $env:RAY_BIND_ADDRESS = "0.0.0.0"
            & $ray start --head --port=6379 --dashboard-port=8265 --dashboard-host=0.0.0.0 --num-cpus=4 --node-ip-address=$ip
        } -ArgumentList $rayExe, $activeIp
        Start-Sleep 3
        if ($rayJob.State -eq "Running") {
            OK "Ray head running -- dashboard: http://localhost:8265"
        } else {
            WRN "Ray failed -- server runs in local mode (that is fine)"
        }
    } else {
        WRN "ray.exe not in venv -- skip (.venv\Scripts\pip install 'ray[default]' to add it)"
    }
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  ZeroPoint is running!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  MCP      : ws://localhost:8765/mcp" -ForegroundColor White
Write-Host "  Identity : http://localhost:8766" -ForegroundColor White
Write-Host "  Token    : $env:MCP_AUTH_TOKEN" -ForegroundColor White
Write-Host "  Log      : $LOG" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Stop : .\dev_start.ps1 -Stop" -ForegroundColor Yellow
Write-Host "  Tail : Get-Content $LOG -Wait" -ForegroundColor Yellow
Write-Host ""

try {
    while ($true) {
        $failed = Get-Job -Name "ZP_MCP" -ErrorAction SilentlyContinue | Where-Object { $_.State -ne "Running" }
        if ($failed) { ERR "MCP server stopped!"; Receive-Job -Name "ZP_MCP"; break }
        Start-Sleep 5
    }
} catch {
    INF "Watching stopped. Server still running in background. Use -Stop to terminate."
}
