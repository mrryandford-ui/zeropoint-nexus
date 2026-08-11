################################################################################
# ZeroPoint AI Stack — Windows 10 Installer
# Run as Administrator in PowerShell
# Usage: powershell -ExecutionPolicy Bypass -File install_zeropoint_windows.ps1
################################################################################

#Requires -RunAsAdministrator
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT   = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$VENV   = "$ROOT\.venv"
$LOG    = "$ROOT\install_log.txt"
$PY_MIN = [Version]"3.11"

function Log   { param($m) $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] ✓ $m" -ForegroundColor Green;  Add-Content $LOG "[$ts] OK  $m" }
function Warn  { param($m) $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] ⚠ $m" -ForegroundColor Yellow; Add-Content $LOG "[$ts] WRN $m" }
function Info  { param($m) $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] → $m" -ForegroundColor Cyan;   Add-Content $LOG "[$ts] INF $m" }
function Abort { param($m) $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] ✗ $m" -ForegroundColor Red;    Add-Content $LOG "[$ts] ERR $m"; exit 1 }

"" | Set-Content $LOG
Write-Host ""
Write-Host "════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ZeroPoint AI Stack — Windows Installer"           -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"        -ForegroundColor DarkGray
Write-Host "  Target: $ROOT"                                     -ForegroundColor DarkGray
Write-Host "════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

################################################################################
# STEP 1 — Check / install Python 3.11+
################################################################################
Info "Step 1/7 — Checking Python..."

$pyCmd = $null
foreach ($candidate in @("python3.11","python3","python")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+\.\d+)") {
            if ([Version]$Matches[1] -ge $PY_MIN) {
                $pyCmd = $candidate
                Log "Found: $ver ($candidate)"
                break
            }
        }
    } catch {}
}

if (-not $pyCmd) {
    Info "Python $PY_MIN+ not found. Installing via winget..."
    try {
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        $env:PATH += ";C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
        $pyCmd = "python"
        Log "Python 3.11 installed via winget."
    } catch {
        Warn "winget failed. Trying chocolatey..."
        try {
            if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
                Set-ExecutionPolicy Bypass -Scope Process -Force
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
                iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
            }
            choco install python311 -y
            $pyCmd = "python"
            Log "Python 3.11 installed via Chocolatey."
        } catch {
            Abort "Cannot install Python automatically. Install Python 3.11+ from https://python.org and re-run."
        }
    }
}

################################################################################
# STEP 2 — Create virtual environment
################################################################################
Info "Step 2/7 — Creating Python virtual environment at $VENV..."

if (-not (Test-Path $VENV)) {
    & $pyCmd -m venv $VENV
    Log "Virtual environment created."
} else {
    Log "Virtual environment already exists — skipping."
}

$pip    = "$VENV\Scripts\pip.exe"
$python = "$VENV\Scripts\python.exe"

################################################################################
# STEP 3 — Upgrade pip + install core dependencies
################################################################################
Info "Step 3/7 — Installing Python packages (this takes 2-4 minutes)..."

& $pip install --upgrade pip wheel setuptools -q

$packages = @(
    # MCP server
    "mcp-server>=0.4.0",
    # Web / HTTP
    "aiohttp>=3.9",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "requests>=2.32",
    # Config / CLI
    "pyyaml>=6.0",
    "click>=8.1",
    "rich>=13.0",
    # Android
    "uiautomator2>=3.0",
    "appium-python-client>=3.1",
    # Observability
    "prometheus-client>=0.20",
    "opentelemetry-sdk>=1.25",
    "opentelemetry-exporter-otlp>=1.25",
    # Testing
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0"
)

foreach ($pkg in $packages) {
    Info "  Installing $pkg..."
    & $pip install $pkg -q
}
Log "Core packages installed."

################################################################################
# STEP 4 — Install Ray (large — separate step so failures are clear)
################################################################################
Info "Step 4/7 — Installing Ray 2.34 (largest package, ~500MB)..."
try {
    & $pip install "ray[default]==2.34.0" "ray[serve]==2.34.0" -q
    Log "Ray installed."
} catch {
    Warn "Ray install failed. You can retry later: $VENV\Scripts\pip install 'ray[default]==2.34.0'"
}

################################################################################
# STEP 5 — Install ADB (Android Debug Bridge)
################################################################################
Info "Step 5/7 — Checking ADB..."

$adbPath = $null
foreach ($candidate in @("adb", "C:\platform-tools\adb.exe")) {
    try {
        $v = & $candidate version 2>&1
        if ($v -match "Android Debug Bridge") {
            $adbPath = $candidate
            Log "ADB found: $v"
            break
        }
    } catch {}
}

if (-not $adbPath) {
    Info "ADB not found. Downloading Android Platform Tools..."
    $ptUrl  = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    $ptZip  = "$env:TEMP\platform-tools.zip"
    $ptDest = "C:\platform-tools"
    try {
        Invoke-WebRequest -Uri $ptUrl -OutFile $ptZip -UseBasicParsing
        Expand-Archive -Path $ptZip -DestinationPath "C:\" -Force
        $env:PATH += ";$ptDest"
        [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$ptDest", [EnvironmentVariableTarget]::Machine)
        Log "ADB installed to $ptDest and added to system PATH."
    } catch {
        Warn "ADB download failed. Download manually from: https://developer.android.com/tools/releases/platform-tools"
    }
}

################################################################################
# STEP 6 — Install ZeroPoint package in editable mode
################################################################################
Info "Step 6/7 — Installing ZeroPoint package..."

if (Test-Path "$ROOT\pyproject.toml") {
    & $pip install -e $ROOT -q
    Log "ZeroPoint package installed (editable mode)."
} else {
    Warn "pyproject.toml not found at $ROOT — skipping package install."
}

################################################################################
# STEP 7 — Create config directories + generate auth token
################################################################################
Info "Step 7/7 — Creating runtime directories and config..."

$dirs = @(
    "$ROOT\config",
    "$ROOT\logs",
    "$ROOT\tasks\pending",
    "$ROOT\tasks\running",
    "$ROOT\tasks\completed",
    "C:\data\camnet\screenshots",
    "C:\data\camnet\recordings",
    "C:\data\camnet\sync",
    "C:\tmp\mcp_scratch",
    "C:\var\log\zeropoint-mcp"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}
Log "Directories created."

# Generate auth token if not already set
$envFile = "$ROOT\config\.env"
if (-not (Test-Path $envFile)) {
    $token = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
    @"
# ZeroPoint Environment — DO NOT COMMIT THIS FILE
MCP_AUTH_TOKEN=$token
RAY_REDIS_PASSWORD=zeropoint-ray-secret
WEBTOOLS_PROXY=
"@ | Set-Content $envFile
    Log "Auth token generated → $envFile"
} else {
    $envLines = Get-Content $envFile -ErrorAction SilentlyContinue
    $tokenLine = $envLines | Where-Object { $_ -match "^\s*MCP_AUTH_TOKEN\s*=\s*(.*)$" } | Select-Object -First 1
    $tokenValue = $null
    if ($tokenLine -and $tokenLine -match "^\s*MCP_AUTH_TOKEN\s*=\s*(.*)$") {
        $tokenValue = $Matches[1].Trim('"').Trim("'")
    }

    if (-not $tokenValue) {
        $token = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
        if ($tokenLine) {
            $envLines = $envLines | ForEach-Object {
                if ($_ -match "^\s*MCP_AUTH_TOKEN\s*=\s*(.*)$") { "MCP_AUTH_TOKEN=$token" } else { $_ }
            }
        } else {
            $envLines += "MCP_AUTH_TOKEN=$token"
        }
        $envLines | Set-Content $envFile
        Log ".env existed but had no valid MCP_AUTH_TOKEN. Generated and updated token in $envFile"
    } else {
        Log ".env already exists — keeping existing token."
    }
}

# Update mcp_server_config.yaml paths for Windows
$cfgSrc = "$ROOT\config\mcp_server_config.yaml"
if (Test-Path $cfgSrc) {
    (Get-Content $cfgSrc) `
        -replace "/workspace/zeropoint", $ROOT.Replace("\","/") `
        -replace "/data/camnet",         "C:/data/camnet" `
        -replace "/tmp/mcp_scratch",     "C:/tmp/mcp_scratch" `
        -replace "/var/log",             "C:/var/log" `
        -replace "/usr/local/bin/adb",   "adb" |
    Set-Content $cfgSrc
    Log "mcp_server_config.yaml paths updated for Windows."
}

################################################################################
# SUMMARY
################################################################################
Write-Host ""
Write-Host "════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ZeroPoint Install Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Python venv : $VENV" -ForegroundColor White
Write-Host "  Config      : $ROOT\config\mcp_server_config.yaml" -ForegroundColor White
Write-Host "  Auth token  : $ROOT\config\.env" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run dev_start.ps1 to start the MCP server" -ForegroundColor White
Write-Host "  2. Open VS Code → install the MCP config" -ForegroundColor White
Write-Host "  3. Ask Copilot in VS Code to use ZeroPoint tools" -ForegroundColor White
Write-Host "════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Pause
