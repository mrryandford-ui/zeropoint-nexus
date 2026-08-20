# Add health-check failure notifications

## Goal
Notify the operator when the scheduled ZeroPoint health check fails, hangs, or detects that a local or cluster service is unavailable, while keeping normal checks silent and non-interactive.

## Requirements
- Preserve hidden/background execution so the active application is not interrupted.
- Record structured failure details in `logs/automation/`.
- Surface a failure-only notification through an appropriate Windows or VS Code-compatible channel.
- Avoid interactive prompts, credential requests, and notification spam.
- Include recovery/healthy-state information so an operator knows when the issue clears.
- Add focused validation for success, failure, and notification suppression during healthy runs.
