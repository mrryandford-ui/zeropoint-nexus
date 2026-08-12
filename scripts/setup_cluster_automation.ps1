param(
    [switch]$Remove,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$runner = Join-Path $root "scripts\cluster_automation_runner.ps1"
$startupCmd = Join-Path $root "scripts\run_cluster_autostart.cmd"
$healthCmdFile = Join-Path $root "scripts\run_cluster_healthcheck.cmd"
$startupTask = "ZeroPoint-Cluster-Autostart"
$healthTask = "ZeroPoint-Cluster-Healthcheck"
$startupShortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "ZeroPoint-Cluster-Autostart.lnk"

if (-not (Test-Path $runner) -or -not (Test-Path $startupCmd) -or -not (Test-Path $healthCmdFile)) {
    throw "Runner script not found: $runner"
}

function Show-Task {
    param([string]$Name)
    $output = cmd /c "schtasks /Query /TN `"$Name`" /FO LIST /V 2>nul"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Task not found: $Name"
        return
    }
    $output
}

if ($Remove) {
    schtasks /Delete /TN $startupTask /F 2>$null | Out-Null
    schtasks /Delete /TN $healthTask /F 2>$null | Out-Null
    if (Test-Path $startupShortcut) {
        Remove-Item -Path $startupShortcut -Force
    }
    Write-Host "Removed automation tasks (if present)."
    exit 0
}

if ($Verify) {
    Write-Host "=== $startupTask ==="
    Show-Task -Name $startupTask
    Write-Host ""
    Write-Host "=== $healthTask ==="
    Show-Task -Name $healthTask
    Write-Host ""
    Write-Host "Startup shortcut present: $(Test-Path $startupShortcut)"
    exit 0
}

$startCmd = "`"$startupCmd`""
$healthCmd = "`"$healthCmdFile`""

& schtasks /Create /TN $startupTask /SC ONLOGON /RL LIMITED /TR $startCmd /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    # Fallback for environments where on-logon task registration is blocked.
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($startupShortcut)
    $shortcut.TargetPath = $startupCmd
    $shortcut.Arguments = ""
    $shortcut.WorkingDirectory = $root
    $shortcut.Save()
    Write-Host "Could not create ONLOGON task. Created Startup shortcut fallback instead."
} else {
    Write-Host "Created/updated task: $startupTask (runs at logon)"
}

& schtasks /Create /TN $healthTask /SC MINUTE /MO 15 /RL LIMITED /TR $healthCmd /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create task: $healthTask"
}

Write-Host "Created/updated automation:"
Write-Host "  - $healthTask (runs every 15 minutes)"

# Run once now so automation state is initialized
& schtasks /Run /TN $startupTask | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Triggered startup task once."
} else {
    Write-Host "Could not trigger startup task immediately; it will run at next logon via task or Startup shortcut."
}
