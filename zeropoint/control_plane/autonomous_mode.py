"""
Phase 1 autonomous workflows for authorized pentest and device recovery.

This module provides:
  - strict scope validation for target ranges
  - explicit authorization gates
  - auditable execution records
  - safe-first recovery actions
"""
from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AutonomousModeError(RuntimeError):
    """Base autonomous workflow error."""


class ScopeValidationError(AutonomousModeError):
    """Raised when target scope is invalid or disallowed."""


class AuthorizationError(AutonomousModeError):
    """Raised when explicit authorization is not provided."""


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_private_target(target: str) -> bool:
    """
    Return True for clearly private/local targets:
      - private/loopback/link-local IP
      - private CIDR
      - localhost
      - RFC1918-like hostnames (*.local, *.lan, *.home)
    """
    t = target.strip().lower()
    if t in {"localhost"} or t.endswith(".local") or t.endswith(".lan") or t.endswith(".home"):
        return True

    try:
        ip = ipaddress.ip_address(t)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass

    try:
        net = ipaddress.ip_network(t, strict=False)
        return net.is_private
    except ValueError:
        return False


def validate_target_scope(target: str, allow_public: bool = False) -> dict[str, Any]:
    raw = (target or "").strip()
    if not raw:
        raise ScopeValidationError("Target scope is empty.")

    # Try single IP first
    try:
        ip = ipaddress.ip_address(raw)
        is_private = ip.is_private or ip.is_loopback or ip.is_link_local
        if not allow_public and not is_private:
            raise ScopeValidationError(
                f"Public IP scope is blocked by policy: {raw}. "
                "Pass allow_public=True only for explicitly authorized external testing."
            )
        return {
            "target": raw,
            "scope_type": "ip",
            "normalized": str(ip),
            "host_count_estimate": 1,
            "is_private": is_private,
        }
    except ValueError:
        pass

    # Try CIDR
    try:
        net = ipaddress.ip_network(raw, strict=False)
        is_private = net.is_private
        if not allow_public and not is_private:
            raise ScopeValidationError(
                f"Public network scope is blocked by policy: {raw}. "
                "Pass allow_public=True only for explicitly authorized external testing."
            )
        return {
            "target": raw,
            "scope_type": "cidr",
            "normalized": str(net),
            "host_count_estimate": int(net.num_addresses),
            "is_private": is_private,
        }
    except ValueError:
        pass

    # Domain/hostname
    is_private = _is_private_target(raw)
    if not allow_public and not is_private:
        raise ScopeValidationError(
            f"Public hostname scope is blocked by policy: {raw}. "
            "Pass allow_public=True only for explicitly authorized external testing."
        )
    return {
        "target": raw,
        "scope_type": "hostname",
        "normalized": raw,
        "host_count_estimate": None,
        "is_private": is_private,
    }


@dataclass
class AuditEvent:
    phase: str
    action: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "action": self.action,
            "status": self.status,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class AutonomousWorkflowManager:
    """Phase 1 autonomous planner/executor."""

    def __init__(self, governance_path: str | Path | None = None) -> None:
        self._events: list[AuditEvent] = []
        self._governance = _load_governance(governance_path)
        self._authorized_ranges: dict[str, Any] = self._governance.get("authorized_scope_ranges", {})

    def _log(self, phase: str, action: str, status: str, **details: Any) -> None:
        self._events.append(AuditEvent(phase=phase, action=action, status=status, details=details))

    def _clear(self) -> None:
        self._events = []

    def _allowed_roles(self, workflow_key: str) -> set[str]:
        access = self._governance.get("access_control", {})
        workflow_roles = access.get("workflow_roles", {})
        configured = workflow_roles.get(workflow_key, [])
        if configured:
            return {str(r).strip().lower() for r in configured}

        defaults = {
            "pentest_phase1": {"owner", "security_lead", "security_analyst"},
            "recovery_phase1": {"owner", "security_lead", "recovery_tech"},
        }
        return defaults.get(workflow_key, {"owner"})

    def _is_target_in_approved_scope(self, target: str, workflow_key: str = "pentest_phase1") -> bool:
        """
        Check if target (single IP or CIDR) falls within approved scope ranges for the workflow.
        Returns True if target is within any approved range.
        """
        if not self._authorized_ranges:
            return True  # No restrictions if not configured

        workflow_ranges_key = "pentest" if workflow_key == "pentest_phase1" else "recovery"
        approved_ranges = self._authorized_ranges.get(workflow_ranges_key, [])
        
        if not approved_ranges:
            return True  # No restrictions if workflow not listed

        target = (target or "").strip()
        if not target:
            return False

        try:
            # Try parsing target as IP or CIDR
            target_net = ipaddress.ip_network(target, strict=False)
        except ValueError:
            # If it's a hostname, we can't check it against CIDR ranges
            # Default to allowing hostnames (assumed to be private/approved)
            return True

        for range_str in approved_ranges:
            try:
                approved_net = ipaddress.ip_network(range_str, strict=False)
                # Check if target_net is completely within approved_net
                if target_net.subnet_of(approved_net):
                    return True
            except ValueError:
                continue

        return False

    def _require_authorized(
        self,
        authorized: bool,
        scope_id: str,
        actor_role: str,
        workflow_key: str,
        target: str | None = None,
    ) -> None:
        if not authorized:
            raise AuthorizationError("authorized=True is required.")
        if not scope_id.strip():
            raise AuthorizationError("scope_id is required for auditability.")
        role = (actor_role or "").strip().lower()
        if not role:
            raise AuthorizationError("actor_role is required.")
        allowed = self._allowed_roles(workflow_key)
        if role not in allowed:
            raise AuthorizationError(
                f"Role '{actor_role}' is not allowed for {workflow_key}. Allowed: {sorted(allowed)}"
            )
        
        # Check if target is within approved scope ranges
        if target:
            if not self._is_target_in_approved_scope(target, workflow_key):
                raise ScopeValidationError(
                    f"Target '{target}' is not within approved scope ranges for {workflow_key}. "
                    "Contact security_lead for scope expansion."
                )

    def plan_pentest(self, target: str, allow_public: bool = False) -> dict[str, Any]:
        scope = validate_target_scope(target, allow_public=allow_public)
        plan = [
            "Validate target scope and authorization metadata",
            "Run passive OSINT modules (DNS/WHOIS/headers/cert transparency)",
            "Optionally run active recon modules (subdomain + TCP connect scan)",
            "Optionally run Kali nmap quick scan if tool exists",
            "Normalize findings and generate summary report",
        ]
        return {
            "workflow": "autonomous_pentest_phase1",
            "target_scope": scope,
            "steps": plan,
            "safety": {
                "requires_authorized_flag": True,
                "requires_scope_id": True,
                "requires_actor_role": True,
                "allowed_roles": sorted(self._allowed_roles("pentest_phase1")),
                "public_scope_blocked_by_default": True,
            },
        }

    async def run_pentest(
        self,
        target: str,
        scope_id: str,
        authorized: bool,
        actor_role: str = "owner",
        active: bool = False,
        use_kali: bool = False,
        use_metasploit: bool = False,
        use_hashcat: bool = False,
        use_john: bool = False,
        hash_file: str | None = None,
        hash_mode: int = 0,
        wordlist: str | None = None,
        allow_public: bool = False,
        export_findings: bool = True,
    ) -> dict[str, Any]:
        self._clear()
        self._require_authorized(authorized, scope_id, actor_role, "pentest_phase1", target=target)
        scope = validate_target_scope(target, allow_public=allow_public)
        self._log(
            "scope",
            "validate_target_scope",
            "ok",
            scope=scope,
            scope_id=scope_id,
            actor_role=actor_role,
        )

        from zeropoint.osint.pipeline import OSINTPipeline
        from zeropoint.pentest.recon_orchestrator import ReconOrchestrator

        # Initialize orchestrator for finding normalization
        orchestrator = ReconOrchestrator(target, scope_id, actor_role)

        self._log("osint", "run_all", "started", active=active)
        async with OSINTPipeline() as pipeline:
            osint_result = await pipeline.run_all(target, active=active)
        self._log(
            "osint",
            "run_all",
            "ok",
            module_count=osint_result.get("module_count", 0),
            active_mode=osint_result.get("active_mode", False),
        )

        kali_summary: dict[str, Any] = {"executed": False}
        metasploit_summary: dict[str, Any] = {"executed": False}
        hashcat_summary: dict[str, Any] = {"executed": False}
        john_summary: dict[str, Any] = {"executed": False}

        if use_kali or use_metasploit or use_hashcat or use_john:
            from zeropoint.pentest.kali_runner import KaliRunner

            runner = KaliRunner()

            if use_kali:
                self._log("kali", "nmap", "started")
                nmap_result = await runner.nmap(
                    target=target,
                    ports="1-1024",
                    flags="-sV",
                    authorized=True,
                )
                kali_summary = {
                    "executed": True,
                    "tool": "nmap",
                    "success": nmap_result.success,
                    "returncode": nmap_result.returncode,
                    "duration_seconds": nmap_result.duration_seconds,
                    "parsed": nmap_result.parsed,
                    "stderr": nmap_result.stderr[:500],
                }
                self._log(
                    "kali",
                    "nmap",
                    "ok" if nmap_result.success else "failed",
                    returncode=nmap_result.returncode,
                )

                # Normalize nmap findings
                if nmap_result.success and nmap_result.stdout:
                    from zeropoint.pentest.recon_orchestrator import NmapAdapter
                    adapter = NmapAdapter()
                    nmap_findings = adapter.parse_output(nmap_result.stdout, target)
                    orchestrator.all_findings.extend(nmap_findings)
                    self._log("finding_normalization", "nmap", "ok", finding_count=len(nmap_findings))

            if use_metasploit:
                self._log("metasploit", "modules_search", "started")
                msf_result = await runner.metasploit_modules(
                    query="type:exploit",
                    authorized=True,
                )
                metasploit_summary = {
                    "executed": True,
                    "success": msf_result.success,
                    "returncode": msf_result.returncode,
                    "matches": msf_result.parsed.get("count", 0),
                    "sample": msf_result.parsed.get("matches", [])[:10],
                    "stderr": msf_result.stderr[:500],
                }
                self._log(
                    "metasploit",
                    "modules_search",
                    "ok" if msf_result.success else "failed",
                    returncode=msf_result.returncode,
                )

            if (use_hashcat or use_john) and not hash_file:
                self._log("credential", "hash_input", "failed", reason="hash_file_missing")
                raise ScopeValidationError("hash_file is required when use_hashcat/use_john is enabled.")

            if use_hashcat:
                self._log("credential", "hashcat", "started")
                hashcat_result = await runner.hashcat_crack(
                    hash_file=hash_file or "",
                    mode=hash_mode,
                    wordlist=wordlist,
                    authorized=True,
                )
                hashcat_summary = {
                    "executed": True,
                    "success": hashcat_result.success,
                    "returncode": hashcat_result.returncode,
                    "cracked_count": hashcat_result.parsed.get("count", 0),
                    "stderr": hashcat_result.stderr[:500],
                }
                self._log(
                    "credential",
                    "hashcat",
                    "ok" if hashcat_result.success else "failed",
                    returncode=hashcat_result.returncode,
                )

            if use_john:
                self._log("credential", "john", "started")
                john_result = await runner.john_crack(
                    hash_file=hash_file or "",
                    wordlist=wordlist,
                    authorized=True,
                )
                john_summary = {
                    "executed": True,
                    "success": john_result.success,
                    "returncode": john_result.returncode,
                    "cracked_count": john_result.parsed.get("count", 0),
                    "stderr": john_result.stderr[:500],
                }
                self._log(
                    "credential",
                    "john",
                    "ok" if john_result.success else "failed",
                    returncode=john_result.returncode,
                )

        open_ports = []
        for item in osint_result.get("results", []):
            if item.get("module") == "port_scan_active":
                open_ports = item.get("data", {}).get("open_ports", [])
                break

        summary = {
            "target": target,
            "scope_type": scope["scope_type"],
            "active_mode": active,
            "open_ports_detected": open_ports,
            "kali_executed": kali_summary.get("executed", False),
            "metasploit_executed": metasploit_summary.get("executed", False),
            "hashcat_executed": hashcat_summary.get("executed", False),
            "john_executed": john_summary.get("executed", False),
            "total_findings": len(orchestrator.all_findings),
            "risk_score": orchestrator._calculate_risk_score(),
        }
        self._log("report", "summary", "ok", summary=summary)

        # Export findings if requested
        findings_path = None
        report_path = None
        if export_findings and orchestrator.all_findings:
            findings_dir = Path(__file__).parent.parent.parent / "logs" / "findings"
            findings_dir.mkdir(parents=True, exist_ok=True)
            findings_path = findings_dir / f"{scope_id}-findings.json"
            report_path = findings_dir / f"{scope_id}-report.md"
            orchestrator.export_findings(findings_path)
            orchestrator.export_report_markdown(report_path)
            self._log("export", "findings", "ok", path=str(findings_path))

        return {
            "workflow": "autonomous_pentest_phase1",
            "authorized": True,
            "actor_role": actor_role,
            "scope_id": scope_id,
            "target_scope": scope,
            "summary": summary,
            "osint": osint_result,
            "kali": kali_summary,
            "metasploit": metasploit_summary,
            "hashcat": hashcat_summary,
            "john": john_summary,
            "findings": [f.to_dict() for f in orchestrator.all_findings],
            "findings_file": str(findings_path) if findings_path else None,
            "report_file": str(report_path) if report_path else None,
            "audit_trail": [e.to_dict() for e in self._events],
            "completed_at": _ts(),
        }

    def plan_device_recovery(self, device_serial: str) -> dict[str, Any]:
        serial = (device_serial or "").strip()
        if not serial:
            raise ScopeValidationError("device_serial is required.")
        return {
            "workflow": "autonomous_device_recovery_phase1",
            "device_serial": serial,
            "steps": [
                "Detect current device state",
                "Run safe reconnect workflow (adb disconnect/kill-server/start-server/connect)",
                "Re-detect state and report recommendation",
            ],
            "safety": {
                "destructive_actions_not_included": True,
                "requires_actor_role": True,
                "allowed_roles": sorted(self._allowed_roles("recovery_phase1")),
                "factory_reset_requires_separate_confirmed_path": True,
            },
        }

    async def run_device_recovery(
        self,
        device_serial: str,
        authorized: bool,
        scope_id: str,
        actor_role: str = "owner",
        attempt_reconnect: bool = True,
    ) -> dict[str, Any]:
        self._clear()
        self._require_authorized(authorized, scope_id, actor_role, "recovery_phase1")
        serial = (device_serial or "").strip()
        if not serial:
            raise ScopeValidationError("device_serial is required.")

        from zeropoint.it_support.device_recovery import DeviceRecoveryWorkflow

        workflow = DeviceRecoveryWorkflow()
        self._log("device", "detect_state", "started", serial=serial)
        before = await workflow.detect_state(serial)
        self._log("device", "detect_state", "ok", initial_state=str(before))

        reconnect = None
        if attempt_reconnect:
            self._log("device", "adb_reconnect", "started")
            reconnect = await workflow.adb_reconnect(serial)
            self._log("device", "adb_reconnect", "ok" if reconnect.success else "failed", success=reconnect.success)

        self._log("device", "detect_state_post", "started")
        after = await workflow.detect_state(serial)
        self._log("device", "detect_state_post", "ok", final_state=str(after))

        recommendation = (
            "device_online"
            if str(after).endswith("online")
            else "escalate_manual_recovery"
        )
        self._log("report", "recommendation", "ok", recommendation=recommendation)

        return {
            "workflow": "autonomous_device_recovery_phase1",
            "authorized": True,
            "actor_role": actor_role,
            "scope_id": scope_id,
            "device_serial": serial,
            "initial_state": str(before),
            "final_state": str(after),
            "attempt_reconnect": attempt_reconnect,
            "reconnect_session": reconnect.to_dict() if reconnect else None,
            "recommendation": recommendation,
            "audit_trail": [e.to_dict() for e in self._events],
            "completed_at": _ts(),
        }


def _load_governance(governance_path: str | Path | None) -> dict[str, Any]:
    if governance_path:
        path = Path(governance_path)
    else:
        path = Path(__file__).resolve().parents[2] / "governance.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
