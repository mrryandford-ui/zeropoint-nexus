################################################################################
# ZeroPoint Cluster Activation Toolkit
# Run this on ZERO-FLD to establish cluster connection
################################################################################

param(
    [switch]$Activate,
    [switch]$Status
)

$ScriptPath = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$RayHeadAddress = "192.168.0.140:6379"
$McpPort = 8765
$RayPort = 6379
$IdentityPort = 8766

# Helper functions
function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     ZeroPoint Cluster Activation - Head Node Launcher         ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($Status) {
    INF "Checking head node status..."
    Write-Host ""
    
    $ports = @($RayPort, $McpPort, $IdentityPort)
    $portNames = @("Ray Head (6379)", "MCP Server (8765)", "Identity (8766)")
    
    $allRunning = $true
    for ($i = 0; $i -lt $ports.Length; $i++) {
        try {
            $socket = New-Object System.Net.Sockets.TcpClient
            $socket.Connect("localhost", $ports[$i])
            OK "$($portNames[$i]) - LISTENING"
            $socket.Close()
        } catch {
            WRN "$($portNames[$i]) - NOT LISTENING"
            $allRunning = $false
        }
    }
    
    Write-Host ""
    if ($allRunning) {
        OK "All services running - Cluster is ACTIVE"
    } else {
        WRN "Some services not running - Start with: .\activate_cluster_head.ps1 -Activate"
    }
    
    exit 0
}

if ($Activate) {
    Write-Host "This script will start the Ray head node and MCP services." -ForegroundColor Cyan
    Write-Host "Run this on: ZERO-FLD (192.168.0.140)" -ForegroundColor Yellow
    Write-Host ""
    
    # Change to zeropoint directory
    if (-not (Test-Path $ScriptPath)) {
        ERR "ZeroPoint MCP directory not found: $ScriptPath"
        ERR "Please ensure zeropoint-mcp is installed in this location"
        exit 1
    }
    
    Set-Location $ScriptPath
    OK "Changed directory to: $ScriptPath"
    Write-Host ""
    
    # Check for dev_start.ps1
    if (-not (Test-Path ".\dev_start.ps1")) {
        ERR "dev_start.ps1 not found in $ScriptPath"
        exit 1
    }
    
    INF "Starting Ray head node with MCP services..."
    Write-Host ""
    
    # Start the head node
    & ".\dev_start.ps1" -RayHead
    
    # Wait a bit for services to start
    Start-Sleep -Seconds 5
    
    # Verify services
    Write-Host ""
    INF "Verifying services..."
    Write-Host ""
    
    $allRunning = $true
    for ($i = 0; $i -lt $ports.Length; $i++) {
        try {
            $socket = New-Object System.Net.Sockets.TcpClient
            $socket.Connect("localhost", $ports[$i])
            OK "$($portNames[$i]) - LISTENING"
            $socket.Close()
        } catch {
            WRN "$($portNames[$i]) - NOT YET"
            $allRunning = $false
        }
    }
    
    Write-Host ""
    if ($allRunning) {
        Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
        Write-Host "✓ Head Node Activated Successfully!" -ForegroundColor Green
        Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps on ZERO-DEV:" -ForegroundColor Cyan
        Write-Host "  1. Test connectivity:" -ForegroundColor White
        Write-Host "     Test-NetConnection -ComputerName 192.168.0.140 -Port 6379" -ForegroundColor Gray
        Write-Host ""
        Write-Host "  2. Should show: TcpTestSucceeded: True ✓" -ForegroundColor White
        Write-Host ""
        Write-Host "  3. If successful, cluster is connected!" -ForegroundColor Green
    } else {
        WRN "Some services may still be starting..."
        WRN "Wait 10-15 seconds and run: .\activate_cluster_head.ps1 -Status"
    }
    
    exit 0
}

# Default: Show help
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Activate head node:" -ForegroundColor White
Write-Host "    .\activate_cluster_head.ps1 -Activate" -ForegroundColor Gray
Write-Host ""
Write-Host "  Check status:" -ForegroundColor White
Write-Host "    .\activate_cluster_head.ps1 -Status" -ForegroundColor Gray
Write-Host ""
Write-Host "Important: Run this on ZERO-FLD machine (192.168.0.140)" -ForegroundColor Yellow
Write-Host ""
