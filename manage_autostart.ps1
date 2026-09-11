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

$TaskName = "ZeroPoint-MCP-Autostart"
$TaskPath = "\ZeroPoint\"
$FullTaskName = "$TaskPath$TaskName"
$StartupFiles = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-MCP-Start.bat",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-MCP-Start.bat",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Start ZeroPoint MCP.lnk",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\Start ZeroPoint MCP.lnk",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-Cluster-Autostart.lnk",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-Cluster-Autostart.lnk"
)
$McpRoot = $PSScriptRoot
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

    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        OK "Autostart ENABLED"
        Write-Host "  Task: $FullTaskName" -ForegroundColor Gray

        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
        Write-Host "  State: $($task.State); Last result: $($taskInfo.LastTaskResult)" -ForegroundColor Gray
        
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
        Write-Host "  Task: $FullTaskName (not found)"
    }

    $legacyFiles = $StartupFiles | Where-Object { Test-Path $_ }
    if ($legacyFiles) {
        WRN "Legacy Startup-folder launcher(s) found:"
        $legacyFiles | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
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
    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
        OK "Autostart DISABLED"
        Write-Host "  Task: $FullTaskName" -ForegroundColor Gray
    } else {
        WRN "Scheduled task not found"
    }
    exit 0
}

if ($Enable) {
    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        Enable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
        OK "Autostart ENABLED"
        Write-Host "  Task: $FullTaskName" -ForegroundColor Gray
    } else {
        ERR "Scheduled task not found"
        WRN "Run setup_autostart.ps1 first"
    }
    exit 0
}

if ($Remove) {
    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        OK "Scheduled-task autostart removed"
    } else {
        WRN "Scheduled task not found"
    }

    foreach ($startupFile in $StartupFiles) {
        if (Test-Path $startupFile) {
            Remove-Item -Path $startupFile -Force -ErrorAction SilentlyContinue
            OK "Removed legacy Startup-folder launcher: $startupFile"
        }
    }
    exit 0
}

Write-Host ""
