# ZeroPoint MCP

ZeroPoint MCP is a private two-node AI/tooling cluster for local system work, analysis, and automation.

## Goal

- **ZERO-DEV (HP Envy)**: frontend/workstation for day-to-day use
- **ZERO-FLD (Lenovo IdeaPad 5)**: backend/head node for orchestration and heavier work

The cluster is intended to:

- run local MCP tools quickly on the workstation
- route heavier jobs to the backend
- share settings, MCP servers, and identity through VS Code sync and cluster config

## Main components

- **MCP core** on port **8765**
- **Identity service** on port **8766**
- **Ray** for distributed execution on port **6379**
- **Prometheus** on port **9090**
- **OTEL collector** on port **4317** when enabled

## What is included

- filesystem tools
- web tools
- ADB tools
- Android tooling
- control-plane orchestration
- OSINT helpers
- pentest helpers
- IT support helpers
- Ray actors for distributed work

## Important files

- [PROJECT_SCOPE_HANDOFF.md](PROJECT_SCOPE_HANDOFF.md)
- [PROJECT_STATUS.txt](PROJECT_STATUS.txt)
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)
- [CLUSTER_STATUS.md](CLUSTER_STATUS.md)
- [CLUSTER_SETUP_GUIDE.md](CLUSTER_SETUP_GUIDE.md)
- [CLUSTER_STARTUP_NOW.md](CLUSTER_STARTUP_NOW.md)
- [dev_start.ps1](dev_start.ps1)
- [verify_cluster_connection.ps1](verify_cluster_connection.ps1)
- [activate_cluster_head.ps1](activate_cluster_head.ps1)
- [cluster_registry.json](cluster_registry.json)
- [governance.json](governance.json)

## Quick start

### On ZERO-FLD

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1 -RayHead
```

### On ZERO-DEV

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp
.\dev_start.ps1
```

### Verify

```powershell
.\verify_cluster_connection.ps1 -Connect
```

## Phase B: Operator UX Simplification (Unified Runner)

**👉 START HERE FOR DAILY USE**

The new **operator.ps1** provides a single, copy/paste-only interface for all workflows:

```powershell
cd C:\Users\zeroi\Downloads\zeropoint-mcp

# Verify cluster is healthy
.\operator.ps1 -Mode verify

# Run autonomous pentest (Phase 1: Recon)
.\operator.ps1 -Mode pentest -TargetRange "192.168.0.0/24" -Scope "authorized-assessment-001" -PentestPhase phase1-recon

# Run autonomous pentest (Phase 1 + 2: Full Pipeline, with Metasploit)
.\operator.ps1 -Mode pentest `
  -TargetRange "192.168.0.0/24" `
  -Scope "authorized-assessment-001" `
  -PentestPhase phase1-2-full `
  -UseMetasploit `
  -ActorRole "security-lead"

# Run device recovery (Android)
.\operator.ps1 -Mode recovery -DeviceName "OnePlus-Test" -Scope "recovery-ticket-042"

# List available presets
.\operator.ps1 -Mode list-presets
```

**For complete copy/paste workflows and troubleshooting, see [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md)**

### Key features:

- ✅ **No manual JSON.** Built-in task presets for all workflows.
- ✅ **Copy/paste only.** Every command is ready to copy from runbook.
- ✅ **Role-gated.** Specify `-ActorRole` to control access to restricted tools (Metasploit, Hashcat, John).
- ✅ **Audit trail.** All submissions logged with scope ID, actor, and timestamp.
- ✅ **Auto-retry.** Execution mode auto-detects Ray Client/Direct/Local.

---

## Autonomous workflows (Phase 1) - Direct CLI

For advanced users who prefer direct CLI access:

```powershell
# build an autonomous pentest plan
zeropoint-control auto pentest-plan 192.168.0.0/24

# run autonomous pentest phase 1 (authorized flag + scope id required)
zeropoint-control auto pentest-run 192.168.0.0/24 --scope-id AUTH-001 --authorized --active

# build autonomous device recovery plan
zeropoint-control auto recovery-plan 192.168.100.10:5555

# run autonomous device recovery phase 1 (safe reconnect flow)
zeropoint-control auto recovery-run 192.168.100.10:5555 --scope-id AUTH-DR-001 --authorized
```

Role-based execution is enforced for autonomous runs. Set role explicitly when needed:

```powershell
zeropoint-control auto pentest-run 192.168.0.0/24 --scope-id AUTH-001 --authorized --actor-role security_analyst --active --use-kali --use-metasploit
```

## Filesystem + Ollama model access policy

- The filesystem tool now supports role-aware read/list/write controls.
- Ollama model directories are included in **read/list** roots by default.
- Writes should remain restricted to operator/workspace paths (not model stores).
- Role policy is defined in [governance.json](governance.json) under `access_control`.

## Notes

- `pyproject.toml` expects this file as the project README.
- [PROJECT_SCOPE_HANDOFF.md](PROJECT_SCOPE_HANDOFF.md) is the current canonical scope/handoff plan.
- Settings Sync should be enabled in VS Code on both machines.
- The backend should remain the cluster head; the workstation should remain the interactive front end.
