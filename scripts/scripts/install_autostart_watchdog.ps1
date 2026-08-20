################################################################################
# Install ZeroPoint MCP autostart and watchdog tasks
# Run this script as Administrator to register scheduled tasks.
################################################################################

$ROOT = Split-Path -Parent $PSScriptRoot
$DEV_START = Join-Path $ROOT "dev_start.ps1"
$WATCHDOG = Join-Path $ROOT "scripts\mcp_watchdog.ps1"

function Register-Task($taskName, $action, $trigger, $description) {
    try {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        }
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description $description -Force
        Write-Host "Registered task: $taskName"
    } catch {
        Write-Host "Failed to register task '$taskName': $_" -ForegroundColor Red
        exit 1
    }
}

$autoAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$DEV_START`""
$autoTrigger = New-ScheduledTaskTrigger -AtLogOn
$autoTrigger.Enabled = $true
Register-Task -taskName 'ZeroPoint MCP Autostart' -action $autoAction -trigger $autoTrigger -description 'Start the ZeroPoint MCP server at user logon.'

$watchdogAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WATCHDOG`""
$watchdogTrigger = New-ScheduledTaskTrigger -AtStartup
Register-Task -taskName 'ZeroPoint MCP Watchdog' -action $watchdogAction -trigger $watchdogTrigger -description 'Start the ZeroPoint MCP watchdog at boot and keep it running to monitor health.'

Write-Host "Installed ZeroPoint MCP autostart and watchdog tasks."
Write-Host "If this script fails with access denied, run it from an elevated Administrator PowerShell session."
