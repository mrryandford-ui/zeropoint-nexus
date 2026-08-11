"""
ZeroPoint Unified Control Plane
Single entry point that wires together all ZeroPoint subsystems:
MCP server, Ray cluster, IT support, OSINT, pentest, and CamNet.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("zeropoint.control_plane")


@dataclass
class SubsystemStatus:
    name: str
    healthy: bool
    details: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }


class ZeroPointControlPlane:
    """
    Unified Control Plane for the ZeroPoint stack.

    Coordinates:
      - MCP server lifecycle
      - Ray cluster health
      - CamNet device fleet
      - IT support agent
      - OSINT pipeline
      - Pentest runner
      - AI orchestrator

    Usage:
        cp = ZeroPointControlPlane.from_config("config/mcp_server_config.yaml")
        await cp.startup()
        status = await cp.health_check()
        await cp.shutdown()
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._subsystems: dict[str, Any] = {}
        self._status: dict[str, SubsystemStatus] = {}
        self._started_at: datetime | None = None

    @classmethod
    def from_config(cls, config_path: str | Path) -> "ZeroPointControlPlane":
        cfg = yaml.safe_load(Path(config_path).read_text())
        return cls(cfg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        logger.info("ZeroPoint Control Plane starting up...")
        self._started_at = datetime.now(timezone.utc)

        await asyncio.gather(
            self._init_ray(),
            self._init_mcp_registry(),
            self._init_it_support(),
            self._init_camnet(),
            self._init_osint(),
            self._init_ai_orchestrator(),
            return_exceptions=True,
        )

        healthy = sum(1 for s in self._status.values() if s.healthy)
        total = len(self._status)
        logger.info("Control Plane started: %d/%d subsystems healthy.", healthy, total)

    async def shutdown(self) -> None:
        logger.info("ZeroPoint Control Plane shutting down...")
        tasks = []
        for name, subsystem in self._subsystems.items():
            shutdown_fn = getattr(subsystem, "shutdown", None)
            if shutdown_fn:
                tasks.append(self._safe_shutdown(name, shutdown_fn))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Control Plane shutdown complete.")

    @staticmethod
    async def _safe_shutdown(name: str, fn) -> None:
        try:
            await fn()
        except Exception as exc:
            logger.warning("Error shutting down %s: %s", name, exc)

    # ------------------------------------------------------------------
    # Subsystem initializers
    # ------------------------------------------------------------------

    async def _init_ray(self) -> None:
        try:
            import ray
            ray_cfg = self.config.get("ray", {})
            address = ray_cfg.get("head_node", "auto")
            if not ray.is_initialized():
                ray.init(
                    address=address,
                    namespace=ray_cfg.get("namespace", "zeropoint"),
                    ignore_reinit_error=True,
                    logging_level=logging.WARNING,
                )
            self._subsystems["ray"] = ray
            self._status["ray"] = SubsystemStatus("ray", True, {
                "address": address,
                "nodes": len(ray.nodes()),
            })
            logger.info("Ray connected: %s", address)
        except Exception as exc:
            self._status["ray"] = SubsystemStatus("ray", False, {"error": str(exc)})
            logger.warning("Ray unavailable: %s", exc)

    async def _init_mcp_registry(self) -> None:
        try:
            from zeropoint.registry import ToolRegistry
            cfg_path = self.config.get("_config_path", "config/mcp_server_config.yaml")
            registry = ToolRegistry(cfg_path)
            registry.load()
            await registry.startup()
            self._subsystems["mcp_registry"] = registry
            self._status["mcp_registry"] = SubsystemStatus(
                "mcp_registry", True, {"tools": len(registry)}
            )
        except Exception as exc:
            self._status["mcp_registry"] = SubsystemStatus("mcp_registry", False, {"error": str(exc)})

    async def _init_it_support(self) -> None:
        try:
            from zeropoint.it_support import ITSupportAgent, DeviceRecoveryWorkflow
            agent = ITSupportAgent()
            recovery = DeviceRecoveryWorkflow()
            self._subsystems["it_support"] = agent
            self._subsystems["device_recovery"] = recovery
            self._status["it_support"] = SubsystemStatus("it_support", True)
        except Exception as exc:
            self._status["it_support"] = SubsystemStatus("it_support", False, {"error": str(exc)})

    async def _init_camnet(self) -> None:
        try:
            from android.camnet_controller import CamNetController
            cfg_path = self.config.get("_config_path", "config/mcp_server_config.yaml")
            ctrl = CamNetController.from_config(cfg_path)
            connected = await ctrl.connect_all()
            ok_count = sum(1 for v in connected.values() if v)
            self._subsystems["camnet"] = ctrl
            self._status["camnet"] = SubsystemStatus(
                "camnet", ok_count > 0,
                {"devices_connected": ok_count, "devices_total": len(connected)},
            )
        except Exception as exc:
            self._status["camnet"] = SubsystemStatus("camnet", False, {"error": str(exc)})

    async def _init_osint(self) -> None:
        try:
            from zeropoint.osint import OSINTPipeline, InvestigationsAgent
            inv = InvestigationsAgent(cases_dir="/data/zeropoint/investigations")
            loaded = inv.load_from_disk()
            self._subsystems["osint_pipeline"] = OSINTPipeline
            self._subsystems["investigations"] = inv
            self._status["osint"] = SubsystemStatus(
                "osint", True, {"cases_loaded": loaded}
            )
        except Exception as exc:
            self._status["osint"] = SubsystemStatus("osint", False, {"error": str(exc)})

    async def _init_ai_orchestrator(self) -> None:
        try:
            from zeropoint.control_plane.ai_orchestrator import AIOrchestrator
            orch = AIOrchestrator(self.config.get("ray", {}))
            await orch.startup()
            self._subsystems["ai_orchestrator"] = orch
            self._status["ai_orchestrator"] = SubsystemStatus("ai_orchestrator", True)
        except Exception as exc:
            self._status["ai_orchestrator"] = SubsystemStatus(
                "ai_orchestrator", False, {"error": str(exc)}
            )

    # ------------------------------------------------------------------
    # Health + status
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Re-check all subsystems and return full health report."""
        # Refresh Ray node count if available
        ray = self._subsystems.get("ray")
        if ray:
            try:
                import ray as _ray
                self._status["ray"].details["nodes"] = len(_ray.nodes())
                self._status["ray"].healthy = True
            except Exception:
                self._status["ray"].healthy = False

        # Refresh CamNet
        camnet = self._subsystems.get("camnet")
        if camnet:
            try:
                status = await camnet.status()
                self._status["camnet"].details["active_devices"] = status["active_count"]
            except Exception:
                pass

        healthy = [s for s in self._status.values() if s.healthy]
        return {
            "overall_healthy": len(healthy) == len(self._status),
            "healthy_count": len(healthy),
            "total_subsystems": len(self._status),
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self._started_at).total_seconds()
                if self._started_at else 0
            ),
            "subsystems": {k: v.to_dict() for k, v in self._status.items()},
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_subsystem(self, name: str) -> Any:
        return self._subsystems.get(name)

    # ------------------------------------------------------------------
    # High-level dispatch API
    # ------------------------------------------------------------------

    async def run_it_ticket(self, title: str, description: str, severity: str = "medium") -> dict:
        agent = self._subsystems.get("it_support")
        if not agent:
            return {"error": "IT Support subsystem not available"}
        ticket = agent.create_ticket(title, description, severity)
        diagnosis = await agent.triage(ticket)
        remediation = await agent.auto_remediate(ticket, diagnosis["issue_type"])
        return {
            "ticket": ticket.to_dict(),
            "diagnosis": diagnosis,
            "remediation": remediation,
        }

    async def run_osint(self, target: str, active: bool = False) -> dict:
        PipelineClass = self._subsystems.get("osint_pipeline")
        if not PipelineClass:
            return {"error": "OSINT subsystem not available"}
        async with PipelineClass() as pipeline:
            return await pipeline.run_all(target, active=active)

    async def camnet_capture(self, mode: str = "photo") -> dict:
        camnet = self._subsystems.get("camnet")
        if not camnet:
            return {"error": "CamNet not available"}
        results = await camnet.capture_all(mode=mode)
        return {"captures": [r.to_dict() for r in results]}

    async def ai_task(self, task_type: str, payload: dict) -> dict:
        orch = self._subsystems.get("ai_orchestrator")
        if not orch:
            return {"error": "AI Orchestrator not available"}
        return await orch.submit(task_type, payload)

