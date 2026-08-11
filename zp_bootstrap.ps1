################################################################################
# ZeroPoint -- One-Paste Windows Bootstrap (ASCII-only, no encoding bugs)
# Run in PowerShell AS ADMINISTRATOR from any directory
################################################################################

$ROOT   = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$VENV   = "$ROOT\.venv"
$LOG    = "$ROOT\bootstrap_log.txt"

function Log  ($m) { $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] OK  $m" -ForegroundColor Green;  Add-Content $LOG "[$ts] OK  $m" }
function Warn ($m) { $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] WRN $m" -ForegroundColor Yellow; Add-Content $LOG "[$ts] WRN $m" }
function Info ($m) { $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] --> $m" -ForegroundColor Cyan;   Add-Content $LOG "[$ts] INF $m" }
function Err  ($m) { $ts = Get-Date -f "HH:mm:ss"; Write-Host "[$ts] ERR $m" -ForegroundColor Red;    Add-Content $LOG "[$ts] ERR $m"; throw $m }

New-Item -ItemType Directory -Force -Path $ROOT | Out-Null
"" | Set-Content $LOG

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ZeroPoint Bootstrap  --  $(Get-Date -Format 'yyyy-MM-dd HH:mm')" -ForegroundColor Cyan
Write-Host "  Target: $ROOT" -ForegroundColor DarkGray
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# STEP 1 -- Find or install Python 3.11+
# We already checked Python is installed on this machine, so this step will locate it.
Info "STEP 1/6 -- Locating Python 3.11+"

$pyExe = $null
$candidates = @(
    "python", "python3", "python3.11",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "C:\Program Files\Python311\python.exe",
    "C:\Python311\python.exe"
)

foreach ($c in $candidates) {
    try {
        $v = & $c --version 2>&1
        if ($v -match "Python (3\.\d+)") {
            $maj = [int]($Matches[1].Split(".")[0])
            $min = [int]($Matches[1].Split(".")[1])
            if ($maj -eq 3 -and $min -ge 11) { $pyExe = $c; Log "Found Python $($Matches[1]) at: $c"; break }
        }
    } catch {}
}

if (-not $pyExe) {
    Info "Python 3.11+ not found -- installing via winget..."
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements --silent
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python311","$env:LOCALAPPDATA\Programs\Python\Python311\Scripts","C:\Program Files\Python311","C:\Program Files\Python311\Scripts")) {
        if (Test-Path $p) { $env:PATH = "$p;$env:PATH" }
    }
    foreach ($c in @("python","python3.11")) {
        try {
            $v = & $c --version 2>&1
            if ($v -match "Python 3\.1[1-9]") { $pyExe = $c; Log "Python installed: $v"; break }
        } catch {}
    }
    if (-not $pyExe) { Err "Python 3.11 install failed. Install from https://python.org then re-run." }
}

# STEP 2 -- Create virtual environment
Info "STEP 2/6 -- Setting up virtual environment..."
if (Test-Path "$VENV\Scripts\python.exe") {
    Log "Venv already exists at $VENV"
} else {
    & $pyExe -m venv $VENV
    if ($LASTEXITCODE -ne 0) { Err "Failed to create venv." }
    Log "Venv created at $VENV"
}

$py  = "$VENV\Scripts\python.exe"

# STEP 3 -- Install packages
Info "STEP 3/6 -- Installing packages..."
# Heal pip if broken/missing, then upgrade core tools
& $py -m ensurepip --default-pip
& $py -m pip install --upgrade pip setuptools wheel -q
Log "pip/setuptools/wheel upgraded"

$pkgs = @(
    "aiohttp>=3.9","click>=8.1","pyyaml>=6.0","rich>=13.0",
    "beautifulsoup4>=4.12","lxml>=5.0","requests>=2.32",
    "prometheus-client>=0.20","opentelemetry-sdk>=1.25",
    "pytest>=8.0","pytest-asyncio>=0.23","pytest-cov>=5.0",
    "black>=24.0","ruff>=0.5","mypy>=1.10"
)
foreach ($pkg in $pkgs) {
    & $py -m pip install $pkg -q
    if ($LASTEXITCODE -eq 0) { Log "  Installed: $pkg" } else { Warn "  Failed:    $pkg (non-fatal)" }
}

# Ray -- large download ~200MB
Info "Installing ray[default] (large download ~200MB -- please wait)..."
& $py -m pip install "ray[default]>=2.34.0"
if ($LASTEXITCODE -eq 0) { Log "Ray installed" } else { Warn "Ray failed -- will run in local mode (that is OK)" }

# Android
Info "Installing Android automation packages..."
& $py -m pip install "uiautomator2>=3.0" "appium-python-client>=3.1"
if ($LASTEXITCODE -eq 0) { Log "Android packages installed" } else { Warn "Android packages optional -- skipped" }

# Editable install
if (Test-Path "$ROOT\pyproject.toml") {
    Info "Installing zeropoint-mcp in editable mode..."
    & $py -m pip install -e "$ROOT[dev]" -q
    if ($LASTEXITCODE -eq 0) { Log "zeropoint-mcp installed (editable)" } else { Warn "Editable install failed -- PYTHONPATH fallback will work" }
}

# STEP 4 -- Install ADB
Info "STEP 4/6 -- Checking ADB..."
$adbFound = $false
foreach ($loc in @("adb","C:\adb\adb.exe","$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe")) {
    try { $v = & $loc version 2>&1; if ($v -match "Android Debug Bridge") { $adbFound = $true; Log "ADB found at: $loc"; break } } catch {}
}

if (-not $adbFound) {
    Info "Downloading Android Platform Tools..."
    $adbDir = "C:\adb"
    $adbZip = "$env:TEMP\platform-tools.zip"
    try {
        Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $adbZip -UseBasicParsing
        Expand-Archive -Path $adbZip -DestinationPath $env:TEMP -Force
        New-Item -ItemType Directory -Force -Path $adbDir | Out-Null
        Copy-Item "$env:TEMP\platform-tools\*" $adbDir -Recurse -Force
        $env:PATH = "$adbDir;$env:PATH"
        $sysPath = [System.Environment]::GetEnvironmentVariable("PATH","Machine")
        if ($sysPath -notlike "*$adbDir*") { [System.Environment]::SetEnvironmentVariable("PATH","$adbDir;$sysPath","Machine") }
        Log "ADB installed at C:\adb"
    } catch { Warn "ADB download failed -- install manually later" }
}

# STEP 5 -- Generate auth token
Info "STEP 5/6 -- Generating auth token..."
$envDir  = "$ROOT\config"
$envFile = "$envDir\.env"
New-Item -ItemType Directory -Force -Path $envDir | Out-Null

if (Test-Path $envFile) {
    $content = Get-Content $envFile -ErrorAction SilentlyContinue
    if ($content -match "MCP_AUTH_TOKEN=[A-Za-z0-9]+") {
        Log "config\.env already exists with valid token -- skipping"
        $null = $content -match "MCP_AUTH_TOKEN=(.+)"
        $token = $Matches[1].Trim()
    } else {
        $token = [Guid]::NewGuid().ToString("N")
        "# ZeroPoint MCP Auth Token`nMCP_AUTH_TOKEN=$token" | Set-Content $envFile -Encoding UTF8
        Log "Auth token regenerated (previous was empty/invalid) -> $envFile"
    }
} else {
    $token = [Guid]::NewGuid().ToString("N")
    "# ZeroPoint MCP Auth Token`nMCP_AUTH_TOKEN=$token" | Set-Content $envFile -Encoding UTF8
    Log "Auth token generated -> $envFile"
}
Write-Host "  Token: $token" -ForegroundColor Magenta

# STEP 6 -- Copy dev_start.ps1 from Downloads if present
Info "STEP 6/6 -- Checking dev_start.ps1..."
$devStart = "$ROOT\dev_start.ps1"
$devSrc   = "$env:USERPROFILE\Downloads\dev_start.ps1"

if (Test-Path $devStart) {
    Log "dev_start.ps1 already in project root"
} elseif (Test-Path $devSrc) {
    Copy-Item $devSrc $devStart -Force
    Log "dev_start.ps1 copied from Downloads"
} else {
    Warn "dev_start.ps1 not found -- download it from the project files"
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Bootstrap complete!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next: cd $ROOT" -ForegroundColor Cyan
Write-Host "        .\dev_start.ps1" -ForegroundColor White
Write-Host "        .\dev_start.ps1 -RayHead   (with Ray cluster)" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Press Enter to exit"
