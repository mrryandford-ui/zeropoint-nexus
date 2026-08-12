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
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$rayExe = Join-Path $root ".venv\Scripts\ray.exe"

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

function Get-PrimaryIPv4 {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -like "192.168.*" -or
            $_.IPAddress -like "10.*" -or
            $_.IPAddress -like "172.1[6-9].*" -or
            $_.IPAddress -like "172.2[0-9].*" -or
            $_.IPAddress -like "172.3[0-1].*"
        } |
        Select-Object -First 1).IPAddress
    if (-not $ip) {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.InterfaceAlias -notlike "*Loopback*"
            } |
            Select-Object -First 1).IPAddress
    }
    return $ip
}

function Test-WorkerJoinedCluster {
    param(
        [string]$LocalIp,
        [string]$HeadIp,
        [string]$PythonPath,
        [string]$RayCliPath
    )
    if (-not (Test-Path $RayCliPath)) {
        return $false
    }

    $raylet = Get-Process -Name "raylet" -ErrorAction SilentlyContinue
    if ($raylet) {
        return $true
    }

    $statusOutput = @(& $RayCliPath status --address "$HeadIp`:6379" 2>&1) -join "`n"
    return $statusOutput -match "Active:"
}

function Ensure-RayWorker {
    param(
        [string]$LocalIp,
        [string]$HeadIp,
        [string]$RayCliPath,
        [string]$PythonPath
    )

    if (-not (Test-Path $RayCliPath)) {
        Write-Log "ray.exe not found at $RayCliPath; cannot auto-join worker."
        return
    }

    if (Test-WorkerJoinedCluster -LocalIp $LocalIp -HeadIp $HeadIp -PythonPath $PythonPath -RayCliPath $RayCliPath) {
        Write-Log "Worker already joined Ray cluster (node IP: $LocalIp)."
        return
    }

    Write-Log "Worker not joined to Ray cluster; starting worker at $LocalIp."
    $env:RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER = "1"
    $rayTempDir = Join-Path $env:LOCALAPPDATA "Temp\ray-worker"
    New-Item -ItemType Directory -Path $rayTempDir -Force | Out-Null
    & $RayCliPath stop --force | Out-Null
    & $RayCliPath start --address "$HeadIp`:6379" --num-cpus=4 --temp-dir "$rayTempDir" | Out-Null

    Start-Sleep -Seconds 3
    if (Test-WorkerJoinedCluster -LocalIp $LocalIp -HeadIp $HeadIp -PythonPath $PythonPath -RayCliPath $RayCliPath) {
        Write-Log "Worker joined Ray cluster successfully."
    } else {
        Write-Log "Worker join attempt completed, but local node is still not visible in cluster."
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
$localIp = Get-PrimaryIPv4
if ($localIp) {
    Write-Log "Detected worker local IP: $localIp"
}

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

if ($headRayUp) {
    Ensure-RayWorker -LocalIp $localIp -HeadIp $headIp -RayCliPath $rayExe -PythonPath $venvPython
}

if ($headRayUp -and -not $HealthCheckOnly) {
    try {
        & $pwshPath -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Connect | Out-Null
        Write-Log "Cluster connect step completed."
    } catch {
        Write-Log "Cluster connect step failed: $($_.Exception.Message)"
    }
}

Write-Log "Automation run completed."
