################################################################################
# ZeroPoint MCP Autostart Management
# Check and manage automatic startup
################################################################################

param(
    [switch]$Check,
    [switch]$Disable,
    [switch]$Enable,
    [switch]$Remove
)

$StartupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$BatFile = "$StartupPath\ZeroPoint-MCP-Start.bat"
$McpRoot = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$LogPath = "$McpRoot\autostart.log"

# Helper functions
function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ZeroPoint MCP Autostart Manager" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Default action if no switches provided
if (-not ($Check -or $Disable -or $Enable -or $Remove)) {
    $Check = $true
}

if ($Check) {
    INF "Checking autostart status..."
    Write-Host ""
    
    if (Test-Path $BatFile) {
        OK "Autostart ENABLED"
        Write-Host "  Location: $BatFile" -ForegroundColor Gray
        
        # Check if server is running
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8765/health" -TimeoutSec 1 -ErrorAction Stop
            OK "MCP Server is RUNNING"
        } catch {
            WRN "MCP Server is NOT running (may not have booted yet)"
        }
        
        # Show recent log
        if (Test-Path $LogPath) {
            Write-Host ""
            Write-Host "Recent autostart logs:" -ForegroundColor Cyan
            Get-Content $LogPath -Tail 5 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }
    } else {
        WRN "Autostart DISABLED"
        Write-Host "  Location: $BatFile (not found)"
    }
    
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  Check autostart : .\manage_autostart.ps1 -Check"
    Write-Host "  Enable autostart : .\manage_autostart.ps1 -Enable"
    Write-Host "  Disable autostart: .\manage_autostart.ps1 -Disable"
    Write-Host "  Remove autostart : .\manage_autostart.ps1 -Remove"
    Write-Host ""
    exit 0
}

if ($Disable) {
    if (Test-Path $BatFile) {
        Rename-Item -Path $BatFile -NewName "$($BatFile).disabled" -Force
        OK "Autostart DISABLED"
        Write-Host "  File: $BatFile -> $BatFile.disabled" -ForegroundColor Gray
    } else {
        WRN "Startup file not found"
    }
    exit 0
}

if ($Enable) {
    if (Test-Path "$BatFile.disabled") {
        Rename-Item -Path "$BatFile.disabled" -NewName $BatFile -Force
        OK "Autostart ENABLED"
        Write-Host "  File: $BatFile.disabled -> $BatFile" -ForegroundColor Gray
    } elseif (Test-Path $BatFile) {
        OK "Autostart already ENABLED"
    } else {
        ERR "Startup file not found"
        WRN "Run setup_autostart.ps1 first"
    }
    exit 0
}

if ($Remove) {
    $batToRemove = if (Test-Path $BatFile) { $BatFile } else { "$BatFile.disabled" }
    
    if (Test-Path $batToRemove) {
        Remove-Item -Path $batToRemove -Force -ErrorAction SilentlyContinue
        OK "Autostart removed"
        Write-Host "  Deleted: $batToRemove" -ForegroundColor Gray
    } else {
        WRN "Startup file not found"
    }
    exit 0
}

Write-Host ""
