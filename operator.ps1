################################################################################
# ZeroPoint Operator Runner - Phase B Unified UX
# Single entry point for all operator workflows (verify, pentest, recovery, etc.)
# Designed for copy/paste-only operation with built-in task presets.
#
# Usage:
#   # Verify cluster connectivity
#   .\operator.ps1 -Mode verify
#
#   # Run autonomous pentest on a network range
#   .\operator.ps1 -Mode pentest -TargetRange "192.168.0.0/24" -Scope "authorized-assessment-001"
#
#   # Run device recovery on connected Android device
#   .\operator.ps1 -Mode recovery -DeviceName "OnePlus-Test" -Scope "recovery-ticket-042"
#
#   # List available presets
#   .\operator.ps1 -Mode list-presets
#
################################################################################

param(
    [ValidateSet(
        "verify",
        "pentest",
        "recovery",
        "analytics",
        "translate",
        "embed",
        "analyze-image",
        "list-presets",
        "custom"
    )]
    [string]$Mode = "verify",

    # Pentest parameters
    [string]$TargetRange = "",
    [string]$Scope = "",
    [ValidateSet("phase1-recon", "phase2-exploit", "phase1-2-full")]
    [string]$PentestPhase = "phase1-recon",
    [string]$ActorRole = "operator",
    [switch]$UseMetasploit,
    [switch]$UseHashcat,
    [switch]$UseJohn,

    # Recovery parameters
    [string]$DeviceName = "",
    [ValidateSet("android", "ios")]
    [string]$DeviceType = "android",

    # Analytics parameters
    [string]$AnalysisType = "summarize_osint",
    [string]$InputFile = "",

    # Custom task
    [string]$TaskType = "",
    [string]$PayloadJson = "",

    # Generic cluster parameters
    [ValidateSet("auto", "ray-client", "ray-direct", "local")]
    [string]$ExecutionMode = "auto",
    [string]$HeadIp = "192.168.0.140",
    [string]$RayAddress = "",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
$VerifyScript = Join-Path $RootDir "verify_cluster_connection.ps1"
$SubmitScript = Join-Path $RootDir "scripts\ai_submit.ps1"

if (-not (Test-Path $PythonExe)) {
    throw "Python venv not found: $PythonExe"
}

# ============================================================================
# LOGGING & DISPLAY FUNCTIONS
# ============================================================================

function Write-Success {
    param([string]$Message)
    Write-Host "  [✓] $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "  [→] $Message" -ForegroundColor Cyan
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  [⚠] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "  [✗] $Message" -ForegroundColor Red
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  $($Title.PadRight(62))  ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

function Verify-Cluster {
    Write-Header "Cluster Connectivity Verification"
    Write-Info "Verifying connection to ZERO-FLD..."
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $VerifyScript -Full
    if ($LASTEXITCODE -ne 0) {
        throw "Cluster verification failed (exit code $LASTEXITCODE)."
    }
    Write-Success "Cluster is reachable and healthy."
}

function Validate-PentestScope {
    param([string]$Range, [string]$Scope)
    if (-not $Range) {
        throw "TargetRange is required for pentest mode. E.g., -TargetRange '192.168.0.0/24'"
    }
    if (-not $Scope) {
        throw "Scope is required for pentest mode (audit trail). E.g., -Scope 'authorized-assessment-001'"
    }
    Write-Info "Pentest scope validated: Range=$Range, Scope=$Scope"
}

function Validate-RecoveryScope {
    param([string]$Device)
    if (-not $Device) {
        throw "DeviceName is required for recovery mode. E.g., -DeviceName 'OnePlus-Test'"
    }
    Write-Info "Recovery scope validated: Device=$Device"
}

# ============================================================================
# TASK PRESET DEFINITIONS
# ============================================================================

$TaskPresets = @{
    pentest = @{
        "phase1-recon" = @{
            description = "Phase 1 - Reconnaissance (network discovery, port scan, service enumeration)"
            stages = @("nmap", "service-identify", "enum4linux", "whatweb")
        }
        "phase2-exploit" = @{
            description = "Phase 2 - Exploitation (metasploit modules, credential testing)"
            stages = @("metasploit-search", "credential-test", "privilege-escalation")
        }
        "phase1-2-full" = @{
            description = "Full Pipeline - Recon + Exploit (combined phase 1 & 2)"
            stages = @("nmap", "service-identify", "metasploit-search", "credential-test")
        }
    }
    recovery = @{
        "android-triage" = @{
            description = "Android Device Triage (detect, unlock attempt, data extraction)"
            stages = @("adb-detect", "device-state", "unlock-attempt", "data-extract")
        }
        "ios-triage" = @{
            description = "iOS Device Triage (detect, state check, backup)"
            stages = @("ios-detect", "device-state", "backup-attempt")
        }
    }
}

# ============================================================================
# SUBMIT TASK HELPER
# ============================================================================

function Submit-Task {
    param(
        [string]$TaskType,
        [string]$Payload
    )
    Write-Info "Submitting task: $TaskType"
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $SubmitScript `
        -TaskType $TaskType `
        -PayloadJson $Payload `
        -ExecutionMode $ExecutionMode `
        -HeadIp $HeadIp `
        -RayAddress $RayAddress
    
    if ($LASTEXITCODE -ne 0) {
        throw "Task submission failed (exit code $LASTEXITCODE)."
    }
}

# ============================================================================
# WORKFLOW: PENTEST
# ============================================================================

function Run-PentestWorkflow {
    Write-Header "Autonomous Pentest Workflow"
    
    Validate-PentestScope -Range $TargetRange -Scope $Scope
    
    $preset = $TaskPresets.pentest[$PentestPhase]
    if (-not $preset) {
        throw "Invalid pentest phase: $PentestPhase. Valid options: $($TaskPresets.pentest.Keys -join ', ')"
    }
    
    Write-Info "Pentest Phase: $PentestPhase"
    Write-Info "Description: $($preset.description)"
    Write-Info "Stages: $($preset.stages -join ' → ')"
    Write-Host ""
    
    $payload = @{
        target_range = $TargetRange
        scope_id = $Scope
        actor_role = $ActorRole
        phase = $PentestPhase
        stages = $preset.stages
        use_metasploit = $UseMetasploit
        use_hashcat = $UseHashcat
        use_john = $UseJohn
    } | ConvertTo-Json -Compress
    
    Write-Info "Payload: $payload"
    Write-Host ""
    
    Submit-Task -TaskType "auto_pentest_run" -Payload $payload
    Write-Success "Pentest workflow submitted successfully."
}

# ============================================================================
# WORKFLOW: RECOVERY
# ============================================================================

function Run-RecoveryWorkflow {
    Write-Header "Autonomous Device Recovery Workflow"
    
    Validate-RecoveryScope -Device $DeviceName
    
    $preset = if ($DeviceType -eq "android") { $TaskPresets.recovery["android-triage"] } else { $TaskPresets.recovery["ios-triage"] }
    
    Write-Info "Device: $DeviceName (Type: $DeviceType)"
    Write-Info "Description: $($preset.description)"
    Write-Info "Stages: $($preset.stages -join ' → ')"
    Write-Host ""
    
    $payload = @{
        device_name = $DeviceName
        device_type = $DeviceType
        actor_role = $ActorRole
        scope_id = $Scope
        stages = $preset.stages
    } | ConvertTo-Json -Compress
    
    Write-Info "Payload: $payload"
    Write-Host ""
    
    Submit-Task -TaskType "auto_recovery_run" -Payload $payload
    Write-Success "Recovery workflow submitted successfully."
}

# ============================================================================
# WORKFLOW: ANALYTICS (SIMPLE)
# ============================================================================

function Run-AnalyticsWorkflow {
    Write-Header "Analytics Workflow"
    
    if (-not $InputFile) {
        throw "InputFile is required for analytics mode. E.g., -InputFile 'path/to/osint_report.txt'"
    }
    if (-not (Test-Path $InputFile)) {
        throw "Input file not found: $InputFile"
    }
    
    Write-Info "Analysis Type: $AnalysisType"
    Write-Info "Input File: $InputFile"
    Write-Host ""
    
    $fileContent = Get-Content $InputFile -Raw
    $payload = @{
        content = $fileContent
        analysis_type = $AnalysisType
    } | ConvertTo-Json -Compress
    
    Submit-Task -TaskType $AnalysisType -Payload $payload
    Write-Success "Analytics workflow submitted successfully."
}

# ============================================================================
# SIMPLE TASKS: TRANSLATE, EMBED, IMAGE ANALYSIS
# ============================================================================

function Run-SimpleTask {
    param(
        [string]$Task,
        [string]$Text
    )
    Write-Header "Simple Task: $Task"
    
    switch ($Task) {
        "translate" {
            $model = "llama3.2:latest"
            $payload = @{
                text = $Text
                target_language = "Spanish"
                model = $model
            } | ConvertTo-Json -Compress
            Submit-Task -TaskType "translate_text" -Payload $payload
        }
        "embed" {
            $model = "nomic-embed-text"
            $payload = @{
                text = $Text
                model = $model
            } | ConvertTo-Json -Compress
            Submit-Task -TaskType "embed_text" -Payload $payload
        }
        default {
            throw "Unknown simple task: $Task"
        }
    }
    
    Write-Success "Task completed: $Task"
}

# ============================================================================
# LIST AVAILABLE PRESETS
# ============================================================================

function Show-Presets {
    Write-Header "Available Task Presets"
    
    Write-Host "PENTEST PRESETS:" -ForegroundColor Yellow
    foreach ($phase in $TaskPresets.pentest.Keys) {
        $desc = $TaskPresets.pentest[$phase].description
        $stages = $TaskPresets.pentest[$phase].stages -join " → "
        Write-Host "  $phase" -ForegroundColor Cyan
        Write-Host "    Description: $desc"
        Write-Host "    Stages: $stages"
        Write-Host ""
    }
    
    Write-Host "RECOVERY PRESETS:" -ForegroundColor Yellow
    foreach ($preset in $TaskPresets.recovery.Keys) {
        $desc = $TaskPresets.recovery[$preset].description
        $stages = $TaskPresets.recovery[$preset].stages -join " → "
        Write-Host "  $preset" -ForegroundColor Cyan
        Write-Host "    Description: $desc"
        Write-Host "    Stages: $stages"
        Write-Host ""
    }
}

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

Write-Host ""
Write-Host "ZeroPoint Operator Runner (Phase B - Unified UX)" -ForegroundColor Magenta
Write-Host "Mode: $Mode | ExecutionMode: $ExecutionMode" -ForegroundColor Gray
Write-Host ""

# Verify cluster unless skipped
if (-not $SkipVerify -and $Mode -ne "list-presets") {
    Verify-Cluster
    Write-Host ""
}

# Route to appropriate workflow
switch ($Mode) {
    "verify" {
        Write-Success "Cluster verification complete. All systems nominal."
    }
    
    "pentest" {
        Run-PentestWorkflow
    }
    
    "recovery" {
        Run-RecoveryWorkflow
    }
    
    "analytics" {
        Run-AnalyticsWorkflow
    }
    
    "translate" {
        Run-SimpleTask -Task "translate" -Text "hello from zeropoint"
    }
    
    "embed" {
        Run-SimpleTask -Task "embed" -Text "hello from zeropoint"
    }
    
    "list-presets" {
        Show-Presets
    }
    
    "custom" {
        if (-not $TaskType) {
            throw "Custom mode requires -TaskType parameter"
        }
        if (-not $PayloadJson) {
            throw "Custom mode requires -PayloadJson parameter"
        }
        Write-Header "Custom Task Submission"
        Submit-Task -TaskType $TaskType -Payload $PayloadJson
        Write-Success "Custom task submitted."
    }
    
    default {
        throw "Unknown mode: $Mode"
    }
}

Write-Host ""
Write-Success "Operator workflow completed successfully."
Write-Host ""
