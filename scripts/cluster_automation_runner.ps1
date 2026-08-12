param(
    [ValidateSet("Auto", "Head", "Worker")]
    [string]$Role = "Auto",
    [switch]$HealthCheckOnly
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$devStart = Join-Path $root "dev_start.ps1"
$verifyScript = Join-Path $root "verify_cluster_connection.ps1"
$logDir = Join-Path $root "logs\automation"
$headIp = "192.168.0.140"
$pwshPath = (Get-Command pwsh -ErrorAction Stop).Source

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ("cluster-automation-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-Log {
    param([string]$Message)
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $env:COMPUTERNAME, $Message
    Add-Content -Path $logFile -Value $line
    Write-Host $line
}

function Test-Port {
    param(
        [string]$ComputerName,
        [int]$Port
    )
    try {
        $result = Test-NetConnection -ComputerName $ComputerName -Port $Port -WarningAction SilentlyContinue
        return [bool]$result.TcpTestSucceeded
    } catch {
        return $false
    }
}

function Get-Role {
    param([string]$RequestedRole)
    if ($RequestedRole -ne "Auto") {
        return $RequestedRole
    }

    if ($env:COMPUTERNAME -eq "ZERO-FLD") {
        return "Head"
    }

    return "Worker"
}

function Get-RunningDevStartProcess {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -like "*dev_start.ps1*" } |
        Select-Object -First 1
}

function Start-DevStart {
    param([switch]$RayHead)

    $existing = Get-RunningDevStartProcess
    if ($null -ne $existing) {
        Write-Log "dev_start is already running (PID: $($existing.ProcessId)); skipping start."
        return
    }

    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$devStart`""
    )
    if ($RayHead) {
        $args += "-RayHead"
    }

    Start-Process -FilePath $pwshPath -ArgumentList $args -WindowStyle Hidden -WorkingDirectory $root | Out-Null
    if ($RayHead) {
        Write-Log "Started dev_start.ps1 -RayHead"
    } else {
        Write-Log "Started dev_start.ps1"
    }
}

$resolvedRole = Get-Role -RequestedRole $Role
Write-Log "Automation run started. Role=$resolvedRole HealthCheckOnly=$HealthCheckOnly"

if ($resolvedRole -eq "Head") {
    $localMcpUp = Test-Port -ComputerName "127.0.0.1" -Port 8765
    $localRayUp = Test-Port -ComputerName "127.0.0.1" -Port 6379

    if (-not $localMcpUp -or -not $localRayUp) {
        Write-Log "Head services not healthy (MCP=$localMcpUp, Ray=$localRayUp). Starting head stack."
        Start-DevStart -RayHead
    } else {
        Write-Log "Head services healthy (MCP and Ray reachable)."
    }

    Write-Log "Automation run completed."
    exit 0
}

# Worker behavior
$localMcpUp = Test-Port -ComputerName "127.0.0.1" -Port 8765
if (-not $localMcpUp) {
    Write-Log "Worker local MCP is down. Starting worker stack."
    Start-DevStart
    Start-Sleep -Seconds 10
} else {
    Write-Log "Worker local MCP is healthy."
}

$headRayUp = Test-Port -ComputerName $headIp -Port 6379
$headMcpUp = Test-Port -ComputerName $headIp -Port 8765
$headIdentityUp = Test-Port -ComputerName $headIp -Port 8766

Write-Log "Head reachability: Ray=$headRayUp MCP=$headMcpUp Identity=$headIdentityUp"

if ($headRayUp -and -not $HealthCheckOnly) {
    try {
        & $pwshPath -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Connect | Out-Null
        Write-Log "Cluster connect step completed."
    } catch {
        Write-Log "Cluster connect step failed: $($_.Exception.Message)"
    }
}

Write-Log "Automation run completed."
