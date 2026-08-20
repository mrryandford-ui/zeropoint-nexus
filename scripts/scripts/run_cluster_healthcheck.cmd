@echo off
pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cluster_automation_runner.ps1" -HealthCheckOnly
