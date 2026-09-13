# ZeroPoint Nexus — Full System Breakdown

> A distributed AI relay grid for local systems work, security tooling, OSINT, IT automation, and device control — exposed to AI assistants via MCP.

---

## What It Actually Is

A private, multi-node Windows cluster that exposes a broad set of automation, security, and AI-agent tooling through the Model Context Protocol (MCP) — so tools like VS Code Copilot or Claude can directly control local systems, investigate OSINT targets, run pentest recon, manage Android devices, and orchestrate distributed compute across the cluster. MCP is the doorway; everything below is the house.

---

## Cluster Topology

| Node | Role | Notes |
|---|---|---|
| **ZERO-DEV** (HP Envy) | Frontend / workstation | Day-to-day dev machine, runs VS Code + Copilot |
| **ZERO-FLD** | Backend / head node | Runs the Ray cluster head; requires a **local** copy of the repo — network drives break the Python venv, Ray init, and PowerShell execution policy |

Nodes sync via network share, USB, or `robocopy` mirroring. Cluster topology is tracked in `cluster_registry.json`; policy rules live in `governance.json`.

---

## The MCP Server Layer (the "doorway")

| Component | Job |
|---|---|
| `zeropoint/server.py` | Main entrypoint — Streamable HTTP on `:8765/mcp` (used by VS Code), legacy WebSocket also available |
| `zeropoint/registry.py` | `ToolRegistry` — loads `tool_registration.json` + `mcp_server_config.yaml`, instantiates tool classes, routes every call |
| `zeropoint/auth.py` | `BearerTokenAuth` — SHA256 hash + constant-time comparison, IP-based rate limiting with periodic sweep + hard cap (bounded, leak-free as of this cleanup pass) |
| `zeropoint/observability.py` | Logging / metrics |
| Entry scripts | `zeropoint_mcp_main.py`, `zeropoint_mcp_server.py` |

Currently registers **18 tools**, confirmed live via smoke test (`{"status":"ok","tools":18}`).

---

## Tool Domains (the actual capabilities)

| Domain | Files | What it does |
|---|---|---|
| **Filesystem** | `tools/filesystem.py` | Read/write/list, bounded by an `allowed_roots` security whitelist |
| **Web tools** | `tools/webtools.py`, `ray_actors/webtools_actor.py` | Fetch, scrape, search — can run as a distributed Ray actor |
| **Android / ADB** | `tools/adb.py`, `tools/android/tool.py`, `android/camnet_controller.py`, `ray_actors/camnet_actor.py` | Shell access, push/pull, logcat, screencap, install, tap/swipe/text input, camera capture, "CamNet" camera-network sync |
| **IT Support** | `it_support/device_recovery.py`, `it_support_agent.py` | Ticketing system (`Severity`, `TicketStatus` enums), device online/offline state tracking |
| **OSINT** | `osint/investigations.py`, `pipeline.py` | Evidence collection (`EvidenceType` enum), async port scanning |
| **Pentest** | `pentest/credential_recovery.py`, `kali_runner.py`, `recon_orchestrator.py` | John the Ripper credential cracking (deliberately redacts plaintext from reports), Kali tool orchestration, recon automation |
| **Control Plane** | `control_plane/ai_orchestrator.py`, `cli.py`, `control_plane.py` | Coordinates AI agent tasks and cluster-wide orchestration |

---

## Distributed Compute

`ray_actors/` — `camnet_actor.py` and `webtools_actor.py` run as Ray actors, meaning camera-network and web-tool workloads can execute across cluster nodes rather than just locally on ZERO-DEV. `dev_start.ps1 -RayHead` starts the Ray head process.

---

## Automation & Ops

- **Scheduled tasks**: `ZeroPoint-MCP-Autostart`, `Autorun for ZeroPoint`, `ZeroPoint-Cluster-Healthcheck`, `Duplicati-ZeroPointMCP-GDrive-Backup`
- **Scripts**: `dev_start.ps1`, `manage_autostart.ps1`, `setup_autostart.ps1`, `activate_cluster_head.ps1`, `verify_cluster_connection.ps1`, `operator.ps1`, `supervisor_manual.ps1`, `install_zeropoint_windows.ps1`, `deploy_repo.ps1`

---

## Recent Hardening (September 2026 cleanup pass)

- Full test suite: **249 passing**, ruff/black/mypy all clean
- Fixed `BearerTokenAuth` rate-limit dict memory leak (unbounded growth under IP-spray attacks) — added periodic sweep + 10,000-entry hard cap, plus new `tests/test_auth.py` coverage
- Removed 3 fully duplicated nested tool directories (`it_support/it_support`, `osint/osint`, `pentest/pentest`) — 16 stale files including tracked `.pyc` bytecode
- Untracked 53 stale compiled bytecode files repo-wide, hardened `.gitignore` coverage
- Resolved all ruff violations (`UP042` StrEnum migration, `F401` unused import, `UP022` capture_output, `F841` reviewed individually — not blindly auto-fixed)
- Renamed project from `zeropoint-mcp` to **ZeroPoint Nexus** (outward title/description only — all internal MCP naming, package imports, and tool URIs unchanged)

---

## Open Items

| # | Item |
|---|---|
| 1 | Check `control_plane/control_plane/` and `ray_actors/ray_actors/` for the same duplicate-nested-folder bug found and fixed elsewhere |
| 2 | `zeropoint/tools/base.py` review |
| 3 | ZERO-FLD cluster health verification |
| 4 | README.md title/description rename (pending) |
