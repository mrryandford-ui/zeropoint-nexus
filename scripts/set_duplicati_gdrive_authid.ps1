param(
    [Parameter(Mandatory = $true)]
    [string]$AuthId
)

$ErrorActionPreference = "Stop"

setx DUPLICATI_GDRIVE_AUTHID $AuthId | Out-Null
$env:DUPLICATI_GDRIVE_AUTHID = $AuthId

Write-Host "Saved DUPLICATI_GDRIVE_AUTHID for user profile."
Write-Host "Running first backup now..."
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\zeroi\Downloads\zeropoint-mcp\scripts\run_duplicati_gdrive_backup.ps1" -AuthId $AuthId
