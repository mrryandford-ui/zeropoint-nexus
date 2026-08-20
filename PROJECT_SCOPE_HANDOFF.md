# ZeroPoint MCP Project Scope & Handoff

Last updated: 2026-08-12 (Phase C orchestrator integration complete)

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

### Operating Decision

- ZERO-DEV must remain fully usable as a single-machine local-first installation.
- ZERO-FLD is optional capacity for heavier or distributed workloads, not a prerequisite for normal operation.
- When ZERO-FLD is unavailable, the system should continue locally where supported and clearly report when a requested task requires remote capacity.

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

### Phase A - Foundation Stabilization ✅ COMPLETE (commit b4495e8)
Goal: make distributed execution reliable and observable.

Deliverables:
- ✅ eliminate control-plane import ambiguity/cycles,
- ✅ force deterministic package entrypoints,
- ✅ validate Ray remote execution path (no local fallback for healthy cluster),
- ✅ update core status docs.
- ✅ implement role-gated autonomous workflows with audit trail,
- ✅ add pentest tool wrappers (Metasploit, Hashcat, John),
- ✅ add Ollama filesystem access for abliterated models.

Exit criteria met:
- ✅ 30 unit tests passing; all tools accessible via autonomous_mode.py.

### Phase B - Operator UX Simplification ✅ COMPLETE (commit 5e586b2)
Goal: one-command operational UX.

Deliverables:
- ✅ unified runner script (operator.ps1) with built-in presets,
- ✅ standardized task payload presets for pentest/recovery/analytics,
- ✅ comprehensive operator runbook (OPERATOR_RUNBOOK.md) with copy/paste workflows.

Exit criteria met:
- ✅ operator can run verify + pentest + recovery + analytics from copy/paste commands only.

### Phase C - Autonomous Security Pipeline (Authorized) 🟡 PARTIAL (commit 4342c77)
Goal: controlled autonomous pentest orchestration with finding normalization.

Deliverables (In Progress):
- ✅ recon workflow orchestrator with tool adapters (Nmap, Enum4linux, Whatweb),
- ✅ finding normalization engine (NormalizedFinding dataclass + ToolAdapter pattern),
- ✅ severity/risk scoring (CVSS-like scale 0.1 INFO to 9.0 CRITICAL, capped at 100),
- ✅ report generation (JSON + markdown) with executive summary,
- ✅ integration into run_pentest() with auto-finding capture and export,
- ✅ 18 unit tests for orchestrator framework (all passing),
- 🟡 target scope validator (placeholder exists, needs full CIDR/IP validation),
- 🟡 additional tool adapters (Metasploit, John, Hashcat parsers not yet built).

Exit criteria (partial):
- ✅ recon on test range produces findings with normalized severity and report.
- 🟡 full workflow not yet end-to-end validated with actual pentest tools.

### Phase D - Autonomous Device Recovery Pipeline (Not Started)
Goal: controlled autonomous device triage/recovery using connected-device tooling.

Deliverables:
- device discovery and state classifier,
- recovery action planner (safe first),
- artifact collection + summary + recommended next actions.

Exit criteria:
- connected test device workflow runs from detect -> triage -> report.

## 6) Active Backlog (Priority Order)

1. **P0:** Complete Phase C scope validator (full CIDR range validation, approved scope enforcement).
2. **P0:** Wire backend task handlers for auto_pentest_run and auto_recovery_run in control_plane/cli.py.
3. **P1:** Build Metasploit, John, and Hashcat output parsers/adapters.
4. **P1:** End-to-end integration test for pentest workflow (test tools → findings → report).
5. **P2:** Move repo from Downloads to C:\Zeropoint (path updates in 8 PowerShell scripts).
6. **P2:** Native Ollama GUI + MCP filesystem integration (requires Claude/LLM orchestrator layer).
7. **P3:** Phase D autonomous device recovery implementation.

## 7) Handoff Notes for Next Work Session - Phase C Continuation

**Current State (Commit 4342c77):**
- ReconOrchestrator framework complete with NormalizedFinding dataclass and ToolAdapter pattern.
- Nmap, Enum4linux, Whatweb adapters functional with smart parsing (UNC paths, JSON output support).
- Integration into run_pentest() auto-generates findings.json + report.md on completion.
- 18 unit tests passing; all 192 full test suite passing.
- Finding export includes JSON (with summary/findings/execution_log) and markdown (with severity grouping + remediation).

**What's Next:**
1. **Scope Validator:** Enhance validate_target_scope() to accept full CIDR ranges, validate against governance.json approved_scope_ranges, reject out-of-scope targets.
2. **Backend Task Handlers:** Add handlers in control_plane/cli.py to route auto_pentest_run/auto_recovery_run task types to autonomous_mode methods.
3. **Tool Output Parsers:** Build adapters for Metasploit JSON output (module info + exploitation attempts), John cracked passwords, Hashcat output formats.
4. **Testing:** Create integration tests that:
   - Run pentest against mock tools or lab targets,
   - validate finding count and severity distribution,
   - confirm report format and evidence archival.
5. **Optional Enhancements:** HTML report generation, CVSS v3.1 scoring, automated remediation suggestions.

**Key Files for Phase C Continuation:**
- [zeropoint/pentest/recon_orchestrator.py](C:/Users/zeroi/Downloads/zeropoint-mcp/zeropoint/pentest/recon_orchestrator.py) — Core orchestrator (17KB, 18 tests, fully documented).
- [zeropoint/control_plane/autonomous_mode.py](C:/Users/zeroi/Downloads/zeropoint-mcp/zeropoint/control_plane/autonomous_mode.py) — Orchestrator integration point (run_pentest method line 206+).
- [tests/unit/test_recon_orchestrator.py](C:/Users/zeroi/Downloads/zeropoint-mcp/tests/unit/test_recon_orchestrator.py) — Full test suite for orchestrator.

**Testing Phase C Locally:**
```powershell
# Run orchestrator tests only
python -m pytest tests/unit/test_recon_orchestrator.py -v

# Run full test suite
python -m pytest tests/ -q

# Test via CLI (once task handlers wired):
zeropoint-control auto pentest-run --target 192.168.1.0/24 --scope-id test-001 --actor-role operator
```

**Notes on Design Decisions:**
- **Finding Normalization:** Used adapter pattern (base ToolAdapter class + specific adapters) to isolate tool parsing logic and make adding new tools trivial.
- **Risk Scoring:** Simple additive severity values (capped at 100) chosen for operator clarity; can be enhanced with CVSS weighting later.
- **Report Format:** Markdown chosen for human readability; JSON export preserves machine-readable structure for downstream processing.
- **Parity Namespace:** Both zeropoint/pentest/ and zeropoint/pentest/pentest/ maintained to handle Ray worker import ambiguities; consolidate in future refactor.

## 8) Phase A/B Execution Status (Historical)

Completed on ZERO-DEV:
- Added one-command workflow runner and mode-aware submit flow.
- Added execution mode selection (`auto`, `ray-client`, `ray-direct`, `local`) to [ai_submit.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/scripts/ai_submit.ps1).
- Improved [verify_cluster_connection.ps1](C:/Users/zeroi/Downloads/zeropoint-mcp/verify_cluster_connection.ps1) diagnostics to explicitly report Ray Client port state and connection mode.
- Normalized control-plane imports in CLI/package init files to reduce circular import risk.

Remaining to close Phase A:
- On ZERO-FLD, pull latest `main` and restart head services with Ray Client port open (`10001`).
- Re-run ZERO-DEV validation and confirm task output no longer shows local fallback for healthy Ray path.

Phase C early progress:
- Added phase-1 autonomous workflow manager in [autonomous_mode.py](C:/Users/zeroi/Downloads/zeropoint-mcp/zeropoint/control_plane/autonomous_mode.py).
- Added CLI entrypoints for plan/run flows:
  - `zeropoint-control auto pentest-plan`
  - `zeropoint-control auto pentest-run`
  - `zeropoint-control auto recovery-plan`
  - `zeropoint-control auto recovery-run`
- Added unit coverage in [test_autonomous_mode.py](C:/Users/zeroi/Downloads/zeropoint-mcp/tests/unit/test_autonomous_mode.py).
