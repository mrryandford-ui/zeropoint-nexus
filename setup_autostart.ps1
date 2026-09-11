################################################################################
# ZeroPoint MCP Server Autostart Setup
# Sets up Windows Task Scheduler to launch MCP server on system boot
################################################################################

param(
    [switch]$Remove,
    [switch]$Verify
)

$TaskName = "ZeroPoint-MCP-Autostart"
$TaskPath = "\ZeroPoint\"
$FullTaskName = "$TaskPath$TaskName"
$ScriptPath = Join-Path $PSScriptRoot "dev_start.ps1"
$LogPath = Join-Path $PSScriptRoot "autostart.log"
$LegacyStartupFiles = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-MCP-Start.bat",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-MCP-Start.bat",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Start ZeroPoint MCP.lnk",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\Start ZeroPoint MCP.lnk",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-Cluster-Autostart.lnk",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\ZeroPoint-Cluster-Autostart.lnk"
)

# Helper functions
function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ZeroPoint MCP Server Autostart Setup" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    ERR "This script requires Administrator privileges!"
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}
OK "Running with Administrator privileges"

if ($Verify) {
    Write-Host "Checking scheduled task status..." -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        OK "Task exists: $FullTaskName"
        Write-Host "Status: $($task.State)"
        Write-Host "Last Run: $($task.LastRunTime)"
        Write-Host "Last Result: $($task.LastTaskResult)"
        if (Test-Path $LogPath) {
            Write-Host ""
            Write-Host "Recent log entries:" -ForegroundColor Cyan
            Get-Content $LogPath -Tail 10
        }
    } else {
        WRN "Task not found. Run setup_autostart.ps1 without -Verify to create it."
    }
    exit 0
}

if ($Remove) {
    INF "Removing scheduled task..."
    $task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        OK "Task removed: $FullTaskName"
    } else {
        WRN "Task not found"
    }
    exit 0
}

# Create new task
INF "Setting up automatic startup task..."

# Create XML action for task
$TaskAction = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"& '$ScriptPath' >> '$LogPath' 2>&1`""

# Create trigger for system startup
$TaskTrigger = New-ScheduledTaskTrigger -AtStartup

# Create principal to run as SYSTEM with highest privileges
$TaskPrincipal = New-ScheduledTaskPrincipal `
    -UserID "NT AUTHORITY\SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Create task settings
$TaskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

# Register the task
$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
if ($task) {
    INF "Task already exists. Updating..."
    Set-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $TaskAction -Trigger $TaskTrigger -Principal $TaskPrincipal -Settings $TaskSettings | Out-Null
} else {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath $TaskPath `
        -Action $TaskAction `
        -Trigger $TaskTrigger `
        -Principal $TaskPrincipal `
        -Settings $TaskSettings `
        -Description "Automatically starts ZeroPoint MCP servers on system boot" | Out-Null
}

OK "Task created/updated: $FullTaskName"

foreach ($legacyStartupFile in $LegacyStartupFiles) {
    if (Test-Path $legacyStartupFile) {
        Remove-Item -Path $legacyStartupFile -Force -ErrorAction SilentlyContinue
        OK "Removed legacy Startup-folder launcher: $legacyStartupFile"
    }
}

Write-Host ""
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Trigger: At System Startup"
Write-Host "  Action: PowerShell.exe"
Write-Host "  Script: $ScriptPath"
Write-Host "  Log: $LogPath"
Write-Host "  Run As: SYSTEM (Highest Privileges)"
Write-Host "  Auto-Restart: Enabled (3 retries, 1 min interval)"
Write-Host ""

# Run manually to test
INF "Testing immediate launch..."
$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Start-ScheduledTask -InputObject $task
Start-Sleep -Seconds 3
$taskInfo = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Write-Host "Task State: $($taskInfo.State)" -ForegroundColor Cyan
Write-Host "Last Run Time: $($taskInfo.LastRunTime)" -ForegroundColor Cyan

Start-Sleep -Seconds 5

# Verify server started
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8765/health" -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        OK "MCP server is responding - autostart verified!"
    }
} catch {
    WRN "Server health check failed, but may still be starting..."
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Autostart configured successfully!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  Verify status : .\setup_autostart.ps1 -Verify"
Write-Host "  Remove task   : .\setup_autostart.ps1 -Remove"
Write-Host "  Manual start  : .\dev_start.ps1"
Write-Host "  Manual stop   : .\dev_start.ps1 -Stop"
Write-Host "  View logs     : Get-Content .\autostart.log -Wait"
Write-Host ""
