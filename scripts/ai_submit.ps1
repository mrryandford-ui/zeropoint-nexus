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
        "analyze_image"
    )]
    [string]$TaskType,

    [Parameter(Mandatory = $true)]
    [string]$PayloadJson,

    [string]$RayAddress = "ray://192.168.0.140:10001"
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
}

@'
import asyncio
import json
import sys

task_type = sys.argv[1]
payload_raw = sys.argv[2]
ray_address = sys.argv[3]

payload = json.loads(payload_raw)

from zeropoint.control_plane.ai_orchestrator import AIOrchestrator


async def main():
    orch = AIOrchestrator(ray_config={"head_node": ray_address, "namespace": "zeropoint"})
    await orch.startup()
    result = await orch.submit(task_type, payload, use_cache=False)
    print(json.dumps(result, indent=2))

asyncio.run(main())
'@ | & $python - $TaskType $PayloadJson $RayAddress
