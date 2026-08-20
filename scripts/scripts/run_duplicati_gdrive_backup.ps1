param(
    [string]$AuthId = $env:DUPLICATI_GDRIVE_AUTHID
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AuthId)) {
    throw "DUPLICATI_GDRIVE_AUTHID is not set. Get token from https://duplicati-oauth-handler.appspot.com?type=googledrive and set it with: setx DUPLICATI_GDRIVE_AUTHID ""<token>"""
}

$duplicatiExe = "C:\Program Files\Duplicati 2\Duplicati.CommandLine.exe"
if (-not (Test-Path $duplicatiExe)) {
    throw "Duplicati.CommandLine.exe not found at: $duplicatiExe"
}

$sourcePath = Split-Path -Parent $PSScriptRoot
$dbDir = "$env:USERPROFILE\DuplicatiBackups"
$dbPath = "$dbDir\zeropoint-mcp.sqlite"
$backupPassphrase = $env:DUPLICATI_BACKUP_PASSPHRASE

if (-not (Test-Path $sourcePath)) {
    throw "Backup source path not found: $sourcePath"
}

New-Item -ItemType Directory -Path $dbDir -Force | Out-Null

$args = @(
    "backup"
    "googledrive://ZeroPointMCPBackup"
    $sourcePath
    "--authid=$AuthId"
    "--dbpath=$dbPath"
    "--backup-name=ZeroPoint MCP Backup"
    "--retention-policy=1W:1D,4W:1W,12M:1M"
    "--auto-cleanup=true"
)

if ([string]::IsNullOrWhiteSpace($backupPassphrase)) {
    Write-Host "DUPLICATI_BACKUP_PASSPHRASE is not set; running backup without encryption."
    $args += "--no-encryption=true"
} else {
    Write-Host "Using AES-256 backup encryption with DUPLICATI_BACKUP_PASSPHRASE."
    $args += "--encryption-module=aes"
    $args += "--passphrase=$backupPassphrase"
}

& $duplicatiExe @args
