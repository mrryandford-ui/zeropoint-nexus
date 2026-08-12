# ZeroPoint MCP Project Scope & Handoff

Last updated: 2026-08-12

## 1) Mission

Build a **local-first, two-node AI operations platform** that can:

- run MCP-enabled tasks from one operator machine (ZERO-DEV),
- offload execution to a backend node (ZERO-FLD) when appropriate,
- support guided-to-autonomous workflows for:
  - authorized security assessment pipelines, and
  - device recovery/triage pipelines.

## 2) Current Reality (Authoritative)

### Working now
- Two-node topology exists and is reachable.
- Ray head and Ray Client ports are available on ZERO-FLD.
- AI task submission scripts work from ZERO-DEV.
- Ollama-backed task types (translate/embed/analyze_image) execute successfully.
- Worker/bootstrap automation scripts are present.

### Not fully complete yet
- Distributed execution can still fall back locally due import/cycle issues in control-plane package layout.
- Documentation across older markdown files is inconsistent with current runtime state.
- Autonomous "give target and run end-to-end" mode is not implemented yet.

## 3) Target End State

Operator provides one high-level intent:

- "Assess 192.168.0.0/24 (authorized scope X)"
- or "Recover attached Android device"

System then:
1. validates scope/authorization policy,
2. plans tool steps,
3. executes via MCP tools and cluster routing,
4. checkpoints evidence,
5. returns prioritized findings and a report.

## 4) Guardrails (Non-Negotiable)

- Authorized targets/devices only.
- Explicit scope declaration required for security workflows.
- Full audit trail of tool calls and decisions.
- High-risk actions require approval gates.
- No silent failures; errors must be surfaced and logged.

## 5) Phase Plan

## Phase A - Foundation Stabilization
Goal: make distributed execution reliable and observable.

Deliverables:
- eliminate control-plane import ambiguity/cycles,
- force deterministic package entrypoints,
- validate Ray remote execution path (no local fallback for healthy cluster),
- update core status docs.

Exit criteria:
- translate + embed tasks complete through Ray path in repeated runs,
- no circular import errors in orchestrator task execution.

## Phase B - Operator UX Simplification
Goal: one-command operational UX.

Deliverables:
- single runner script for verify + submit flows,
- standardized task payload presets,
- clear operator runbook for daily use and troubleshooting.

Exit criteria:
- operator can run verify + at least 2 task types from copy/paste commands only.

## Phase C - Autonomous Security Pipeline (Authorized)
Goal: controlled autonomous pentest orchestration.

Deliverables:
- target scope validator,
- recon workflow orchestration (tool adapters + planner loop),
- finding normalization + severity scoring,
- report generation with evidence references.

Exit criteria:
- scoped autonomous recon on a test lab range produces reproducible report.

## Phase D - Autonomous Device Recovery Pipeline
Goal: controlled autonomous device triage/recovery using connected-device tooling.

Deliverables:
- device discovery and state classifier,
- recovery action planner (safe first),
- artifact collection + summary + recommended next actions.

Exit criteria:
- connected test device workflow runs from detect -> triage -> report.

## 6) Active Backlog (Priority Order)

1. **P0:** fix distributed import-cycle path (unblocks true cluster mode).
2. **P0:** harmonize duplicate control-plane package structure.
3. **P1:** normalize/refresh docs to single source of truth.
4. **P1:** harden reboot automation verification and logs.
5. **P2:** implement autonomous mode phase 1 (security scope-gated planner).
6. **P2:** implement autonomous device recovery phase 1.

## 7) Handoff Notes for Next Work Session

- First focus: remove circular imports and validate Ray execution without `_execution_mode: "local_fallback"`.
- Keep [scripts/run_ai_workflow.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/scripts/run_ai_workflow.ps1) as the operator entrypoint.
- Treat [README.md](C:/Users/zeroi/Downloads/zeropoint-mcp/README.md) + this file as canonical docs; older status docs are historical unless updated.
- After each milestone, run practical verification from ZERO-DEV using:
  - [verify_cluster_connection.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/verify_cluster_connection.ps1)
  - [ai_submit.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/scripts/ai_submit.ps1)
  - [run_ai_workflow.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/scripts/run_ai_workflow.ps1)

## 8) Phase A Execution Status (Current)

Completed on ZERO-DEV:
- Added one-command workflow runner and mode-aware submit flow.
- Added execution mode selection (`auto`, `ray-client`, `ray-direct`, `local`) to [ai_submit.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/scripts/ai_submit.ps1).
- Improved [verify_cluster_connection.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/verify_cluster_connection.ps1) diagnostics to explicitly report Ray Client port state and connection mode.
- Normalized control-plane imports in CLI/package init files to reduce circular import risk.

Remaining to close Phase A:
- On ZERO-FLD, pull latest `main` and restart head services with Ray Client port open (`10001`).
- Re-run ZERO-DEV validation and confirm task output no longer shows local fallback for healthy Ray path.
