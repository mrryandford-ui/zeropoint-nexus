################################################################################
# ZeroPoint Repository Deployment Tool
# Copies zeropoint-mcp from ZERO-DEV to ZERO-FLD or other destinations
################################################################################

param(
    [string]$Destination,
    [switch]$ToZeroFld,
    [switch]$Verify,
    [switch]$ShowHelp
)

$Source = "C:\Users\zeroi\Downloads\zeropoint-mcp"

# Helper functions
function OK  ($m) { Write-Host "  [OK]  $m" -ForegroundColor Green  }
function INF ($m) { Write-Host "  [-->] $m" -ForegroundColor Cyan   }
function WRN ($m) { Write-Host "  [WRN] $m" -ForegroundColor Yellow }
function ERR ($m) { Write-Host "  [ERR] $m" -ForegroundColor Red    }

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     ZeroPoint Repository Deployment Tool                      ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($ShowHelp -or (-not $Destination -and -not $ToZeroFld -and -not $Verify)) {
    Write-Host "Deploy zeropoint-mcp repository to another machine." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "USAGE:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Copy to ZERO-FLD:" -ForegroundColor White
    Write-Host "    .\deploy_repo.ps1 -ToZeroFld" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Copy to custom location:" -ForegroundColor White
    Write-Host "    .\deploy_repo.ps1 -Destination 'C:\path\to\destination'" -ForegroundColor Gray
    Write-Host "    .\deploy_repo.ps1 -Destination '\\\\SERVER\\Share\\zeropoint'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Verify existing installation:" -ForegroundColor White
    Write-Host "    .\deploy_repo.ps1 -Verify 'C:\path\to\check'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "OPTIONS:" -ForegroundColor Cyan
    Write-Host "  -ToZeroFld      : Deploy to ZERO-FLD (192.168.0.140)" -ForegroundColor Gray
    Write-Host "  -Destination    : Deploy to specific path" -ForegroundColor Gray
    Write-Host "  -Verify         : Verify existing installation" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

if ($Verify) {
    Write-Host "VERIFICATION MODE" -ForegroundColor Yellow
    Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host ""
    
    if (-not (Test-Path $Destination)) {
        ERR "Path not found: $Destination"
        exit 1
    }
    
    INF "Checking: $Destination"
    Write-Host ""
    
    $checks = @(
        @{file = "dev_start.ps1"; name = "Dev startup script" },
        @{file = "cluster_registry.json"; name = "Cluster registry" },
        @{file = "governance.json"; name = "Governance policy" },
        @{file = "config\mcp_server_config.yaml"; name = "MCP config" },
        @{file = ".venv\Scripts\python.exe"; name = "Python venv" }
    )
    
    $allOK = $true
    foreach ($check in $checks) {
        $fullPath = Join-Path $Destination $check.file
        if (Test-Path $fullPath) {
            OK "$($check.name)"
        } else {
            WRN "$($check.name) - NOT FOUND"
            $allOK = $false
        }
    }
    
    Write-Host ""
    if ($allOK) {
        OK "Installation verified - ready to use!"
    } else {
        WRN "Some files missing - may need reinstallation"
    }
    
    exit 0
}

# Determine destination
if ($ToZeroFld) {
    $Destination = "\\192.168.0.140\C$\Users\zeroi\Downloads\zeropoint-mcp"
    $MachineName = "ZERO-FLD"
}

Write-Host "SOURCE:" -ForegroundColor Yellow
Write-Host "  $Source" -ForegroundColor Cyan
Write-Host ""

Write-Host "DESTINATION:" -ForegroundColor Yellow
Write-Host "  $Destination" -ForegroundColor Cyan
Write-Host ""

# Verify source exists
if (-not (Test-Path $Source)) {
    ERR "Source directory not found: $Source"
    exit 1
}

OK "Source directory found"
Write-Host ""

# Create destination parent if needed
$DestParent = Split-Path $Destination -Parent
if (-not (Test-Path $DestParent)) {
    WRN "Destination parent doesn't exist: $DestParent"
    WRN "Attempting to create..."
    try {
        New-Item -ItemType Directory -Path $DestParent -Force | Out-Null
        OK "Created destination parent directory"
    } catch {
        ERR "Failed to create destination: $($_.Exception.Message)"
        exit 1
    }
}

# Copy with progress
Write-Host "Copying repository..." -ForegroundColor Yellow
Write-Host "(This may take a few minutes depending on network/speed)" -ForegroundColor Gray
Write-Host ""

try {
    # Use robocopy for reliable copying
    $robocopyArgs = @(
        $Source,
        $Destination,
        "/E",                          # Copy subdirectories including empty ones
        "/PURGE",                      # Remove files in dest not in source
        "/MIR",                        # Mirror (delete extra files)
        "/NFL",                        # No file list
        "/NDL",                        # No directory list
        "/NJH",                        # No job header
        "/NJS",                        # No job summary
        "/R:2",                        # 2 retries
        "/W:2"                         # 2 second wait between retries
    )
    
    $robocopyOutput = & robocopy @robocopyArgs
    
    # Robocopy returns 0 or 1 for success, higher for partial/errors
    if ($LASTEXITCODE -le 1) {
        OK "Repository copied successfully!"
    } else {
        WRN "Robocopy exited with code $LASTEXITCODE (may be partial success)"
        Write-Host "Output:" -ForegroundColor Yellow
        $robocopyOutput
    }
} catch {
    ERR "Copy failed: $($_.Exception.Message)"
    exit 1
}

Write-Host ""
Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

# Verify copy
INF "Verifying copy..."
Write-Host ""

$verifyChecks = @(
    "dev_start.ps1",
    "cluster_registry.json",
    "governance.json"
)

$copyOK = $true
foreach ($file in $verifyChecks) {
    $destFile = Join-Path $Destination $file
    if (Test-Path $destFile) {
        OK "$file"
    } else {
        ERR "$file - NOT FOUND"
        $copyOK = $false
    }
}

Write-Host ""

if ($copyOK) {
    Write-Host "✅ Deployment successful!" -ForegroundColor Green
    Write-Host ""
    
    if ($ToZeroFld) {
        Write-Host "Next steps on ZERO-FLD:" -ForegroundColor Cyan
        Write-Host "  1. Navigate to: C:\Users\zeroi\Downloads\zeropoint-mcp" -ForegroundColor Gray
        Write-Host "  2. Run: .\dev_start.ps1 -RayHead" -ForegroundColor Gray
        Write-Host "  3. Wait 15-20 seconds for startup" -ForegroundColor Gray
    } else {
        Write-Host "Repository is ready at: $Destination" -ForegroundColor Cyan
    }
} else {
    ERR "Deployment verification failed"
    ERR "Some files were not copied correctly"
    exit 1
}

Write-Host ""
Write-Host "═════════════════════════════════════════════════════════════════" -ForegroundColor Green
