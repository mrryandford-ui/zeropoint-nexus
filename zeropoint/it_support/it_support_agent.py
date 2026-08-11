"""
ZeroPoint IT Support Agent
Automated triage, diagnosis, and remediation for common IT issues.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("zeropoint.it_support")


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    TRIAGING = "triaging"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass
class Ticket:
    ticket_id: str
    title: str
    description: str
    severity: Severity = Severity.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    steps_taken: list[str] = field(default_factory=list)
    resolution: str = ""
    device_id: str = ""
    assigned_to: str = "zeropoint-auto"

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "steps_taken": self.steps_taken,
            "resolution": self.resolution,
            "device_id": self.device_id,
            "assigned_to": self.assigned_to,
        }


class ITSupportAgent:
    """
    Automated IT support agent for ZeroPoint infrastructure.

    Handles: connectivity issues, disk space alerts, service restarts,
    log analysis, user account issues, and device health checks.
    """

    KNOWN_ISSUES = {
        "no_network": ["ping", "dns", "gateway", "network", "connectivity", "offline"],
        "disk_full":  ["disk", "space", "full", "storage", "no space left"],
        "service_down": ["service", "daemon", "crash", "stopped", "failed", "dead"],
        "high_cpu": ["cpu", "load", "slow", "hung", "freeze", "100%"],
        "high_memory": ["memory", "ram", "oom", "out of memory", "swap"],
        "auth_failure": ["login", "auth", "password", "permission denied", "sudo"],
        "device_offline": ["device", "offline", "adb", "disconnected", "not found"],
    }

    def __init__(self):
        self._tickets: dict[str, Ticket] = {}
        self._counter = 0

    # ------------------------------------------------------------------
    # Ticket Management
    # ------------------------------------------------------------------

    def create_ticket(
        self,
        title: str,
        description: str,
        severity: str = "medium",
        device_id: str = "",
    ) -> Ticket:
        self._counter += 1
        tid = f"ZIT-{self._counter:04d}"
        ticket = Ticket(
            ticket_id=tid,
            title=title,
            description=description,
            severity=Severity(severity),
            device_id=device_id,
        )
        self._tickets[tid] = ticket
        logger.info("Created ticket %s: %s", tid, title)
        return ticket

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def list_tickets(self, status: str | None = None) -> list[dict]:
        tickets = self._tickets.values()
        if status:
            tickets = [t for t in tickets if t.status == status]
        return [t.to_dict() for t in sorted(tickets, key=lambda t: t.created_at, reverse=True)]

    # ------------------------------------------------------------------
    # Triage
    # ------------------------------------------------------------------

    def classify_issue(self, description: str) -> str:
        """Classify issue type from description keywords."""
        desc_lower = description.lower()
        for issue_type, keywords in self.KNOWN_ISSUES.items():
            if any(kw in desc_lower for kw in keywords):
                return issue_type
        return "unknown"

    async def triage(self, ticket: Ticket) -> dict:
        """Run automated triage and return diagnosis."""
        ticket.status = TicketStatus.TRIAGING
        issue_type = self.classify_issue(ticket.description)
        ticket.steps_taken.append(f"Classified as: {issue_type}")
        diagnosis = await self._diagnose(issue_type, ticket.device_id)
        return {"issue_type": issue_type, "diagnosis": diagnosis}

    async def _diagnose(self, issue_type: str, device_id: str) -> dict:
        handlers = {
            "no_network":   self._diag_network,
            "disk_full":    self._diag_disk,
            "service_down": self._diag_services,
            "high_cpu":     self._diag_cpu,
            "high_memory":  self._diag_memory,
            "auth_failure": self._diag_auth,
            "device_offline": self._diag_device,
        }
        handler = handlers.get(issue_type, self._diag_generic)
        return await handler(device_id)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    async def _run(self, cmd: list[str], timeout: int = 10) -> tuple[str, int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return out.decode(errors="replace").strip(), proc.returncode or 0
        except Exception as exc:
            return str(exc), -1

    async def _diag_network(self, _: str) -> dict:
        results = {}
        out, rc = await self._run(["ping", "-c", "3", "-W", "2", "8.8.8.8"])
        results["internet_ping"] = {"output": out, "reachable": rc == 0}
        out, rc = await self._run(["ip", "route", "show"])
        results["routing_table"] = out
        out, rc = await self._run(["cat", "/etc/resolv.conf"])
        results["dns_config"] = out
        return results

    async def _diag_disk(self, _: str) -> dict:
        out, _ = await self._run(["df", "-h"])
        du_out, _ = await self._run(["du", "-sh", "/var/log", "/tmp", "/data"])
        return {"disk_usage": out, "large_dirs": du_out}

    async def _diag_services(self, _: str) -> dict:
        out, _ = await self._run(["systemctl", "list-units", "--state=failed", "--no-pager"])
        return {"failed_services": out}

    async def _diag_cpu(self, _: str) -> dict:
        out, _ = await self._run(["ps", "aux", "--sort=-%cpu"])
        top_out, _ = await self._run(["uptime"])
        return {"top_processes": "\n".join(out.splitlines()[:20]), "load_average": top_out}

    async def _diag_memory(self, _: str) -> dict:
        out, _ = await self._run(["free", "-h"])
        ps_out, _ = await self._run(["ps", "aux", "--sort=-%mem"])
        return {"memory_usage": out, "top_processes": "\n".join(ps_out.splitlines()[:10])}

    async def _diag_auth(self, _: str) -> dict:
        out, _ = await self._run(["tail", "-n", "50", "/var/log/auth.log"])
        return {"auth_log_tail": out}

    async def _diag_device(self, device_id: str) -> dict:
        out, rc = await self._run(["adb", "devices", "-l"])
        return {"adb_devices": out, "target_device": device_id}

    async def _diag_generic(self, _: str) -> dict:
        out, _ = await self._run(["uptime"])
        mem, _ = await self._run(["free", "-h"])
        df, _  = await self._run(["df", "-h", "/"])
        return {"uptime": out, "memory": mem, "disk_root": df}

    # ------------------------------------------------------------------
    # Remediation
    # ------------------------------------------------------------------

    async def auto_remediate(self, ticket: Ticket, issue_type: str) -> dict:
        """Attempt automatic remediation. Returns action taken."""
        ticket.status = TicketStatus.IN_PROGRESS
        actions = []

        if issue_type == "disk_full":
            out, rc = await self._run(["journalctl", "--vacuum-size=500M"])
            actions.append(f"Vacuumed journal logs: {out[:200]}")
            out, rc = await self._run(["find", "/tmp", "-mtime", "+7", "-delete"])
            actions.append("Deleted /tmp files older than 7 days.")

        elif issue_type == "service_down":
            # Restart failed systemd services
            svc_out, _ = await self._run(
                ["systemctl", "list-units", "--state=failed", "--no-pager", "--plain"]
            )
            for line in svc_out.splitlines():
                parts = line.split()
                if parts and parts[0].endswith(".service"):
                    svc = parts[0]
                    out, rc = await self._run(["systemctl", "restart", svc])
                    actions.append(f"Restarted {svc}: {'ok' if rc == 0 else 'failed'}")

        elif issue_type == "high_memory":
            out, rc = await self._run(["sync"])
            out2, _ = await self._run(
                ["bash", "-c", "echo 3 > /proc/sys/vm/drop_caches"]
            )
            actions.append("Synced and dropped caches.")

        if not actions:
            actions.append(f"No automatic remediation available for '{issue_type}' — escalating.")
            ticket.status = TicketStatus.ESCALATED
        else:
            ticket.status = TicketStatus.RESOLVED
            ticket.resolved_at = datetime.now(timezone.utc)
            ticket.resolution = "; ".join(actions)

        ticket.steps_taken.extend(actions)
        return {"actions": actions, "status": ticket.status}

