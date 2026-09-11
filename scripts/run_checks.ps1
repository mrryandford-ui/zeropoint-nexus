<#
.SYNOPSIS
    ZeroPoint MCP — Full validation sequence.
    Runs: pytest, ruff, black, mypy, smoke test.
    Stops at first failure and reports clearly.

.USAGE
    cd C:\ZeroPoint
    .\scripts\run_checks.ps1

    # Skip smoke test (faster, CI-safe):
    .\scripts\run_checks.ps1 -SkipSmoke
#>

param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'
$repo = 'C:\ZeroPoint'
Set-Location $repo

$pass  = [char]0x2705  # checkmark
$fail  = [char]0x274C  # cross
$skip  = [char]0x23ED  # skip

$results = [ordered]@{}

function Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    try {
        & $Block
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Exit code $LASTEXITCODE" }
        $results[$Name] = "$pass Pass"
    } catch {
        $results[$Name] = "$fail FAILED: $_"
        Write-Host "`nFAILED at: $Name" -ForegroundColor Red
        Write-Host $_ -ForegroundColor Red
        Report-Summary
        exit 1
    }
}

function Report-Summary {
    Write-Host "`n=== SUMMARY ==" -ForegroundColor Yellow
    foreach ($key in $results.Keys) {
        Write-Host "  $key : $($results[$key])"
    }
}

# ---------------------------------------------------------------------------
# STEP 1 — git pull
# ---------------------------------------------------------------------------
Step 'git pull' {
    git pull origin main
}

# ---------------------------------------------------------------------------
# STEP 2 — Activate venv
# ---------------------------------------------------------------------------
Step 'venv activate' {
    $activate = Join-Path $repo '.venv\Scripts\Activate.ps1'
    if (-not (Test-Path $activate)) {
        throw ".venv not found at $activate. Rebuild with: py -3.14 -m venv .venv"
    }
    & $activate
    $v = python --version 2>&1
    Write-Host "Python: $v"
}

# ---------------------------------------------------------------------------
# STEP 3 — pip install dev deps
# ---------------------------------------------------------------------------
Step 'pip install' {
    pip install -e ".[dev]" --quiet
}

# ---------------------------------------------------------------------------
# STEP 4 — pytest
# ---------------------------------------------------------------------------
$null = New-Item -ItemType Directory -Force -Path (Join-Path $repo 'tasks')
Step 'pytest' {
    pytest tests/ -v --tb=short --cov=zeropoint --cov-report=term-missing 2>&1 |
        Tee-Object -FilePath (Join-Path $repo 'tasks\test_run.log')
    if ($LASTEXITCODE -ne 0) { throw "pytest exited $LASTEXITCODE" }
}

# ---------------------------------------------------------------------------
# STEP 5 — ruff
# ---------------------------------------------------------------------------
Step 'ruff' {
    ruff check zeropoint/ zeropoint_mcp_main.py zeropoint_mcp_server.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nAuto-fixable issues found. Run: ruff check --fix zeropoint/" -ForegroundColor Yellow
        throw "ruff exited $LASTEXITCODE"
    }
}

# ---------------------------------------------------------------------------
# STEP 6 — black
# ---------------------------------------------------------------------------
Step 'black' {
    black --check --diff zeropoint/ zeropoint_mcp_main.py zeropoint_mcp_server.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFormatting needed. Run: black zeropoint/" -ForegroundColor Yellow
        throw "black exited $LASTEXITCODE"
    }
}

# ---------------------------------------------------------------------------
# STEP 7 — mypy
# ---------------------------------------------------------------------------
Step 'mypy' {
    mypy zeropoint/server.py zeropoint/registry.py zeropoint/auth.py --ignore-missing-imports
    if ($LASTEXITCODE -ne 0) { throw "mypy exited $LASTEXITCODE" }
}

# ---------------------------------------------------------------------------
# STEP 8 — smoke test (skippable)
# ---------------------------------------------------------------------------
if ($SkipSmoke) {
    $results['smoke test /health'] = "$skip Skipped"
} else {
    Step 'smoke test /health' {
        $env:MCP_AUTH_TOKEN = 'test-token-dev'

        # Start server as a background job (no & operator needed)
        $job = Start-Job -ScriptBlock {
            Set-Location $using:repo
            & '.venv\Scripts\python.exe' -m zeropoint.server `
                --transport websocket --log-level DEBUG
        }

        Write-Host "Server starting (job $($job.Id))…" -ForegroundColor DarkGray
        Start-Sleep -Seconds 4

        try {
            $resp = Invoke-WebRequest `
                -Uri 'http://127.0.0.1:8765/health' `
                -Headers @{ Authorization = 'Bearer test-token-dev' } `
                -UseBasicParsing `
                -TimeoutSec 5
            Write-Host "STATUS : $($resp.StatusCode)"
            Write-Host "CONTENT: $($resp.Content)"
            if ($resp.StatusCode -ne 200) {
                throw "Expected HTTP 200, got $($resp.StatusCode)"
            }
        } finally {
            Stop-Job  -Job $job -ErrorAction SilentlyContinue
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Report-Summary
Write-Host "`nAll checks passed." -ForegroundColor Green
