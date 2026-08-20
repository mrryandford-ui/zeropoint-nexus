param(
    [ValidateSet("verify", "translate", "embed", "custom")]
    [string]$Mode = "verify",

    [string]$Text = "hello from zeropoint",
    [string]$TargetLanguage = "Spanish",
    [string]$Model = "",
    [string]$TaskType = "",
    [string]$PayloadJson = "",
    [ValidateSet("auto", "ray-client", "ray-direct", "local")]
    [string]$ExecutionMode = "auto",
    [string]$HeadIp = "192.168.0.140",
    [string]$RayAddress = "",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$verifyScript = Join-Path $root "verify_cluster_connection.ps1"
$submitScript = Join-Path $root "scripts\ai_submit.ps1"

function Run-Verify {
    Write-Host "Step 1/2: Verifying cluster..." -ForegroundColor Cyan
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Full
    if ($LASTEXITCODE -ne 0) {
        throw "Cluster verification failed (exit code $LASTEXITCODE)."
    }
}

function Submit-Task {
    param(
        [string]$SubmitTaskType,
        [string]$SubmitPayload
    )
    Write-Host "Step 2/2: Submitting task ($SubmitTaskType)..." -ForegroundColor Cyan
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $submitScript `
        -TaskType $SubmitTaskType `
        -PayloadJson $SubmitPayload `
        -ExecutionMode $ExecutionMode `
        -HeadIp $HeadIp `
        -RayAddress $RayAddress
    if ($LASTEXITCODE -ne 0) {
        throw "Task submission failed (exit code $LASTEXITCODE)."
    }
}

if (-not $SkipVerify) {
    Run-Verify
}

switch ($Mode) {
    "verify" {
        Write-Host "Done. Cluster verify/connect completed." -ForegroundColor Green
    }
    "translate" {
        if (-not $Model) { $Model = "llama3.2:latest" }
        $payload = @{
            text = $Text
            target_language = $TargetLanguage
            model = $Model
        } | ConvertTo-Json -Compress
        Submit-Task -SubmitTaskType "translate_text" -SubmitPayload $payload
    }
    "embed" {
        if (-not $Model) { $Model = "nomic-embed-text" }
        $payload = @{
            text = $Text
            model = $Model
        } | ConvertTo-Json -Compress
        Submit-Task -SubmitTaskType "embed_text" -SubmitPayload $payload
    }
    "custom" {
        if (-not $TaskType) {
            throw "For custom mode, provide -TaskType."
        }
        if (-not $PayloadJson) {
            throw "For custom mode, provide -PayloadJson."
        }
        Submit-Task -SubmitTaskType $TaskType -SubmitPayload $PayloadJson
    }
}
