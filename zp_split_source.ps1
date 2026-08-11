################################################################################
# ZeroPoint — Split zeropoint-all-python-source.txt into individual files
# Run from: C:\Users\zeroi\Downloads\zeropoint-mcp
# Usage: powershell -ExecutionPolicy Bypass -File zp_split_source.ps1
################################################################################

$ROOT   = "C:\Users\zeroi\Downloads\zeropoint-mcp"
$SOURCE = "$ROOT\zeropoint-all-python-source.txt"

if (-not (Test-Path $SOURCE)) {
    Write-Host "[ERR] Not found: $SOURCE" -ForegroundColor Red
    Write-Host "      Make sure zeropoint-all-python-source.txt is in $ROOT" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"; exit 1
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ZeroPoint Source Splitter" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$lines   = Get-Content $SOURCE -Encoding UTF8
$current = @()
$relPath = $null
$written = 0
$skipped = 0

foreach ($line in $lines) {
    if ($line -match "^={40,}\s*$") {
        # separator line — ignore
        continue
    }
    if ($line -match "^FILE:\s*(.+?)\s*$") {
        # flush previous file
        if ($relPath -and $current.Count -gt 0) {
            $dest = Join-Path $ROOT $relPath.Replace("/", "\")
            $dir  = Split-Path $dest -Parent
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            ($current | Where-Object { $_ -ne $null }) -join "`n" | Set-Content $dest -Encoding UTF8 -NoNewline
            Write-Host "  [OK] $relPath" -ForegroundColor Green
            $written++
        }
        $relPath = $Matches[1].Trim()
        $current = @()
    } else {
        $current += $line
    }
}

# flush last file
if ($relPath -and $current.Count -gt 0) {
    $dest = Join-Path $ROOT $relPath.Replace("/", "\")
    $dir  = Split-Path $dest -Parent
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    ($current | Where-Object { $_ -ne $null }) -join "`n" | Set-Content $dest -Encoding UTF8 -NoNewline
    Write-Host "  [OK] $relPath" -ForegroundColor Green
    $written++
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Done!  $written files written to $ROOT" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""

# Also copy loose files from Downloads into correct project locations
$dl = "C:\Users\zeroi\Downloads"
$moves = @{
    "$dl\mcp.json"                  = "$ROOT\.vscode\mcp.json"
    "$dl\conftest.py"               = "$ROOT\tests\conftest.py"
    "$dl\test_base_tool.py"         = "$ROOT\tests\unit\test_base_tool.py"
    "$dl\test_filesystem.py"        = "$ROOT\tests\unit\test_filesystem.py"
    "$dl\test_webtools.py"          = "$ROOT\tests\unit\test_webtools.py"
    "$dl\test_adb.py"               = "$ROOT\tests\unit\test_adb.py"
    "$dl\test_it_support.py"        = "$ROOT\tests\unit\test_it_support.py"
    "$dl\test_osint.py"             = "$ROOT\tests\unit\test_osint.py"
    "$dl\test_ai_orchestrator.py"   = "$ROOT\tests\unit\test_ai_orchestrator.py"
    "$dl\test_registry.py"          = "$ROOT\tests\unit\test_registry.py"
    "$dl\test_mcp_server.py"        = "$ROOT\tests\integration\test_mcp_server.py"
    "$dl\test_ray_cluster.py"       = "$ROOT\tests\integration\test_ray_cluster.py"
    "$dl\webtools_actor.py"         = "$ROOT\zeropoint\ray_actors\webtools_actor.py"
    "$dl\camnet_actor.py"           = "$ROOT\zeropoint\ray_actors\camnet_actor.py"
    "$dl\cli.py"                    = "$ROOT\zeropoint\control_plane\cli.py"
    "$dl\tools_registry.json"       = "$ROOT\config\tools_registry.json"
    "$dl\tool_registration.json"    = "$ROOT\config\tool_registration.json"
    "$dl\mcp_server_config.yaml"    = "$ROOT\config\mcp_server_config.yaml"
}

Write-Host "  Moving loose Downloads files into project..." -ForegroundColor Cyan
foreach ($src in $moves.Keys) {
    $dst = $moves[$src]
    if (Test-Path $src) {
        $dstDir = Split-Path $dst -Parent
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        Copy-Item $src $dst -Force
        Write-Host "  [OK] $(Split-Path $src -Leaf)  ->  $(($dst).Replace($ROOT,''))" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "  All done! Run zp_bootstrap.ps1 next if you haven't already." -ForegroundColor Yellow
Write-Host ""
Read-Host "Press Enter to exit"
