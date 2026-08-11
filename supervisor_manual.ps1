# Manual supervisor for ZeroPoint MCP on ZERO-DEV
# Sets environment and starts the dev_start.ps1 supervisor (manual start only)
param(
    [switch]$StartRayHead  # set if you want this node to run Ray head
)

$ROOT = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$env:PROJECT_DIR = $ROOT
$env:RAY_ADDRESS = "192.168.0.137:6379"   # Ray head address (cluster head node)
$env:NODE_ID = "dd7103b7feef4c86bba116544b94c408"
$env:NODE_NAME = "ZERO-DEV"
$env:HOSTNAME = $env:COMPUTERNAME

Write-Host "Starting ZeroPoint supervisor (manual). PROJECT_DIR=$env:PROJECT_DIR" -ForegroundColor Cyan
Write-Host "RAY_ADDRESS=$env:RAY_ADDRESS" -ForegroundColor Cyan

# Start MCP server (dev_start.ps1 will set PYTHONPATH and spawn the MCP job)
if ($StartRayHead) {
    & "$ROOT\dev_start.ps1" -RayHead
} else {
    & "$ROOT\dev_start.ps1"
}
