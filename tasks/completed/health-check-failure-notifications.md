# Add Health-Check Failure Notifications

## Completed
- Health checks now record a durable state file at `logs/automation/health-notification-state.json`.
- Failure and recovery transitions write details to `logs/automation/health-alert.json`.
- State changes attempt a time-limited Windows `msg.exe` alert without opening a PowerShell window.
- Healthy checks remain silent, including the first successful baseline check.
- Health-only checks validate the local MCP server only; optional ZERO-FLD services do not create false alerts.

## Validation
- Direct health-only run completed with exit code `0`, healthy state, and no alert file.
- The deployed hidden scheduled task completed with `Last Result = 0` and healthy state.
- Windows Event Log and Windows Toast APIs were unavailable without elevation or additional components, so the implementation uses files plus `msg.exe` for state-change alerts.