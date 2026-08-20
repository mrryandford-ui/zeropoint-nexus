param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "classify_it_issue",
        "summarize_osint",
        "extract_iocs",
        "triage_alert",
        "generate_report",
        "translate_text",
        "embed_text",
        "analyze_image",
        "auto_pentest_plan",
        "auto_pentest_run",
        "auto_recovery_plan",
        "auto_recovery_run"
    )]
    [string]$TaskType,

    [Parameter(Mandatory = $true)]
    [string]$PayloadJson,

    [ValidateSet("auto", "ray-client", "ray-direct", "local")]
    [string]$ExecutionMode = "auto",

    [string]$HeadIp = "192.168.0.140",
    [int]$RayPort = 6379,
    [int]$RayClientPort = 10001,
    [string]$RayAddress = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
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

$resolvedMode = $ExecutionMode
$resolvedRayAddress = $null

if ($ExecutionMode -eq "auto") {
    if ($RayAddress) {
        $resolvedMode = "ray-client"
        $resolvedRayAddress = $RayAddress
    } else {
        $rayClientReachable = Test-Port -ComputerName $HeadIp -Port $RayClientPort
        if ($rayClientReachable) {
            $resolvedMode = "ray-client"
            $resolvedRayAddress = "ray://$HeadIp`:$RayClientPort"
        } else {
            $resolvedMode = "local"
        }
    }
} elseif ($ExecutionMode -eq "ray-client") {
    $resolvedRayAddress = if ($RayAddress) { $RayAddress } else { "ray://$HeadIp`:$RayClientPort" }
} elseif ($ExecutionMode -eq "ray-direct") {
    $resolvedRayAddress = if ($RayAddress) { $RayAddress } else { "$HeadIp`:$RayPort" }
}

if ($resolvedMode -eq "local") {
    Write-Host "[INFO] Running in local mode (Ray client not selected/reachable)." -ForegroundColor Yellow
} else {
    Write-Host "[INFO] Running in $resolvedMode mode using $resolvedRayAddress" -ForegroundColor Cyan
}

@'
import asyncio
import json
import sys

task_type = sys.argv[1]
payload_raw = sys.argv[2]
execution_mode = sys.argv[3]
ray_address = sys.argv[4]

payload = json.loads(payload_raw)

from zeropoint.control_plane.ai_orchestrator import AIOrchestrator


async def main():
    orch = AIOrchestrator(
        ray_config={"head_node": ray_address, "namespace": "zeropoint"} if ray_address else {}
    )
    if execution_mode != "local":
        await orch.startup()
    result = await orch.submit(task_type, payload, use_cache=False)
    if isinstance(result, dict):
        result.setdefault("_submission_mode", execution_mode)
        if ray_address:
            result.setdefault("_submission_ray_address", ray_address)
    print(json.dumps(result, indent=2))

asyncio.run(main())
'@ | & $python - $TaskType $PayloadJson $resolvedMode ($resolvedRayAddress ?? "")
