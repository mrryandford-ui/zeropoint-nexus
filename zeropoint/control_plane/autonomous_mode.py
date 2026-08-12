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
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def _log(self, phase: str, action: str, status: str, **details: Any) -> None:
        self._events.append(AuditEvent(phase=phase, action=action, status=status, details=details))

    def _clear(self) -> None:
        self._events = []

    def _require_authorized(self, authorized: bool, scope_id: str) -> None:
        if not authorized:
            raise AuthorizationError("authorized=True is required.")
        if not scope_id.strip():
            raise AuthorizationError("scope_id is required for auditability.")

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
                "public_scope_blocked_by_default": True,
            },
        }

    async def run_pentest(
        self,
        target: str,
        scope_id: str,
        authorized: bool,
        active: bool = False,
        use_kali: bool = False,
        allow_public: bool = False,
    ) -> dict[str, Any]:
        self._clear()
        self._require_authorized(authorized, scope_id)
        scope = validate_target_scope(target, allow_public=allow_public)
        self._log("scope", "validate_target_scope", "ok", scope=scope, scope_id=scope_id)

        from zeropoint.osint.pipeline import OSINTPipeline

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
        if use_kali:
            from zeropoint.pentest.kali_runner import KaliRunner

            self._log("kali", "nmap", "started")
            runner = KaliRunner()
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
            self._log("kali", "nmap", "ok" if nmap_result.success else "failed", returncode=nmap_result.returncode)

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
        }
        self._log("report", "summary", "ok", summary=summary)

        return {
            "workflow": "autonomous_pentest_phase1",
            "authorized": True,
            "scope_id": scope_id,
            "target_scope": scope,
            "summary": summary,
            "osint": osint_result,
            "kali": kali_summary,
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
                "factory_reset_requires_separate_confirmed_path": True,
            },
        }

    async def run_device_recovery(
        self,
        device_serial: str,
        authorized: bool,
        scope_id: str,
        attempt_reconnect: bool = True,
    ) -> dict[str, Any]:
        self._clear()
        self._require_authorized(authorized, scope_id)
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
