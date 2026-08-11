"""
ZeroPoint Distributed AI Orchestrator
Routes AI workloads across the Ray cluster:
  - Text inference (local model or API)
  - Embedding generation
  - Async task queuing with priority
  - Result caching
  - CamNet image analysis
  - OSINT summarization
  - IT triage classification
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("zeropoint.ai_orchestrator")


###############################################################################
# Task types
###############################################################################

TASK_TYPES = {
    "classify_it_issue":    "Classify an IT issue description into a category.",
    "summarize_osint":      "Summarize OSINT findings for a target.",
    "analyze_image":        "Analyze a CamNet screenshot or capture.",
    "generate_report":      "Generate a structured report from raw data.",
    "extract_iocs":         "Extract indicators of compromise from text.",
    "triage_alert":         "Triage a security alert and suggest response.",
    "translate_text":       "Translate text to a target language.",
    "embed_text":           "Generate a text embedding vector.",
}


###############################################################################
# Result + Task dataclasses
###############################################################################

@dataclass
class AITask:
    task_id: str
    task_type: str
    payload: dict[str, Any]
    priority: int = 5              # 1 (highest) – 10 (lowest)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: dict | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "done": self.done,
            "result": self.result,
            "error": self.error,
        }


###############################################################################
# LRU cache
###############################################################################

class _LRUCache:
    def __init__(self, maxsize: int = 256):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def key_for(self, task_type: str, payload: dict) -> str:
        blob = json.dumps({"type": task_type, "payload": payload}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


###############################################################################
# AIOrchestrator
###############################################################################

class AIOrchestrator:
    """
    Distributed AI task orchestrator backed by Ray.

    If Ray is unavailable, falls back to local async execution.
    Results are cached with an LRU cache to avoid redundant inference.

    Supported backends (in priority order):
      1. Ray remote actors   — distributed cluster execution
      2. Local async         — single-node fallback
    """

    def __init__(self, ray_config: dict[str, Any] | None = None):
        self._ray_cfg = ray_config or {}
        self._cache = _LRUCache(maxsize=512)
        self._tasks: dict[str, AITask] = {}
        self._counter = 0
        self._ray_available = False
        self._semaphore = asyncio.Semaphore(8)   # max 8 concurrent local AI tasks

    async def startup(self) -> None:
        try:
            import ray
            if not ray.is_initialized():
                ray.init(
                    address=self._ray_cfg.get("head_node", "auto"),
                    namespace=self._ray_cfg.get("namespace", "zeropoint"),
                    ignore_reinit_error=True,
                    logging_level=logging.WARNING,
                )
            self._ray_available = True
            logger.info("AI Orchestrator: Ray backend active.")
        except Exception as exc:
            logger.warning("AI Orchestrator: Ray unavailable (%s) — using local fallback.", exc)
            self._ray_available = False

    async def shutdown(self) -> None:
        logger.info("AI Orchestrator shutdown.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 5,
        use_cache: bool = True,
    ) -> dict:
        """
        Submit an AI task. Returns result dict immediately (awaits completion).
        For fire-and-forget, use submit_async().
        """
        if task_type not in TASK_TYPES:
            return {"error": f"Unknown task_type '{task_type}'. Options: {list(TASK_TYPES)}"}

        # Cache check
        cache_key = self._cache.key_for(task_type, payload)
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit for %s", task_type)
                return {**cached, "_cached": True}

        self._counter += 1
        task = AITask(
            task_id=f"AIT-{self._counter:05d}",
            task_type=task_type,
            payload=payload,
            priority=priority,
        )
        self._tasks[task.task_id] = task

        try:
            async with self._semaphore:
                if self._ray_available:
                    result = await self._execute_ray(task)
                else:
                    result = await self._execute_local(task)
        except Exception as exc:
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            return {"task_id": task.task_id, "error": str(exc)}

        task.result = result
        task.completed_at = datetime.now(timezone.utc)

        if use_cache and not task.error:
            self._cache.set(cache_key, result)

        return {"task_id": task.task_id, **result}

    async def submit_async(self, task_type: str, payload: dict, priority: int = 5) -> str:
        """Fire-and-forget — returns task_id immediately."""
        self._counter += 1
        task = AITask(f"AIT-{self._counter:05d}", task_type, payload, priority)
        self._tasks[task.task_id] = task
        asyncio.create_task(self._run_task(task))
        return task.task_id

    async def get_task(self, task_id: str) -> dict | None:
        t = self._tasks.get(task_id)
        return t.to_dict() if t else None

    def list_tasks(self, done: bool | None = None) -> list[dict]:
        tasks = self._tasks.values()
        if done is not None:
            tasks = [t for t in tasks if t.done == done]
        return [t.to_dict() for t in sorted(tasks, key=lambda t: t.created_at, reverse=True)]

    # ------------------------------------------------------------------
    # Ray execution
    # ------------------------------------------------------------------

    async def _execute_ray(self, task: AITask) -> dict:
        """Offload task to Ray cluster via remote function."""
        import ray

        @ray.remote
        def _ray_task(task_type: str, payload: dict) -> dict:
            # Runs inside Ray worker — import here to avoid pickling issues
            import asyncio
            orchestrator = AIOrchestrator.__new__(AIOrchestrator)
            orchestrator._ray_available = False
            orchestrator._semaphore = asyncio.Semaphore(1)
            orchestrator._cache = _LRUCache()
            orchestrator._tasks = {}
            orchestrator._counter = 0
            loop = asyncio.new_event_loop()
            return loop.run_until_complete(orchestrator._execute_local(
                AITask(task_id="ray-sub", task_type=task_type, payload=payload)
            ))

        loop = asyncio.get_event_loop()
        ref = _ray_task.remote(task.task_type, task.payload)
        result = await loop.run_in_executor(None, ray.get, ref)
        return result

    async def _run_task(self, task: AITask) -> None:
        try:
            async with self._semaphore:
                result = await self._execute_local(task)
            task.result = result
        except Exception as exc:
            task.error = str(exc)
        task.completed_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Local execution — task handlers
    # ------------------------------------------------------------------

    async def _execute_local(self, task: AITask) -> dict:
        handlers = {
            "classify_it_issue":  self._handle_classify_it,
            "summarize_osint":    self._handle_summarize_osint,
            "analyze_image":      self._handle_analyze_image,
            "generate_report":    self._handle_generate_report,
            "extract_iocs":       self._handle_extract_iocs,
            "triage_alert":       self._handle_triage_alert,
            "translate_text":     self._handle_translate,
            "embed_text":         self._handle_embed,
        }
        handler = handlers.get(task.task_type, self._handle_unknown)
        return await handler(task.payload)

    async def _handle_classify_it(self, payload: dict) -> dict:
        description = payload.get("description", "")
        keywords = {
            "network":   ["network", "ping", "dns", "internet", "connectivity", "offline"],
            "disk_full": ["disk", "space", "full", "storage"],
            "memory":    ["memory", "ram", "oom", "slow"],
            "service":   ["service", "crash", "stopped", "failed", "daemon"],
            "security":  ["breach", "unauthorized", "malware", "virus", "attack"],
            "device":    ["device", "android", "adb", "disconnected", "phone"],
            "auth":      ["login", "password", "auth", "permission", "access denied"],
        }
        desc_lower = description.lower()
        scores = {
            cat: sum(1 for kw in kws if kw in desc_lower)
            for cat, kws in keywords.items()
        }
        best = max(scores, key=scores.get) if any(scores.values()) else "unknown"
        return {
            "classification": best,
            "confidence": min(scores.get(best, 0) / 3.0, 1.0),
            "all_scores": scores,
            "method": "keyword_heuristic",
        }

    async def _handle_summarize_osint(self, payload: dict) -> dict:
        results = payload.get("results", [])
        target = payload.get("target", "unknown")

        modules_run = [r.get("module", "?") for r in results]
        errors = [r for r in results if r.get("error")]
        open_ports = []
        subdomains = []

        for r in results:
            data = r.get("data", {})
            if r.get("module") == "port_scan_active":
                open_ports = data.get("open_ports", [])
            if r.get("module") in ("cert_transparency", "subdomains_active"):
                subdomains.extend(data.get("subdomains_found", data.get("found", [])))

        summary = (
            f"OSINT scan of '{target}' completed {len(modules_run)} modules. "
            f"Found {len(set(subdomains))} unique subdomains, "
            f"{len(open_ports)} open ports. "
            f"{len(errors)} module(s) encountered errors."
        )
        return {
            "target": target,
            "summary": summary,
            "modules_run": modules_run,
            "open_ports": open_ports,
            "subdomains_sample": sorted(set(subdomains))[:20],
            "error_count": len(errors),
        }

    async def _handle_analyze_image(self, payload: dict) -> dict:
        """
        Placeholder for CamNet image analysis.
        In production, swap the body for a call to a vision model
        (e.g. LLaVA via llama.cpp, or a cloud vision API).
        """
        image_path = payload.get("image_path", "")
        return {
            "image_path": image_path,
            "analysis": "Vision model not configured — plug in LLaVA or cloud vision API.",
            "status": "stub",
        }

    async def _handle_generate_report(self, payload: dict) -> dict:
        data = payload.get("data", {})
        report_type = payload.get("report_type", "generic")
        lines = [
            f"# ZeroPoint Report — {report_type.upper()}",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for key, val in data.items():
            lines.append(f"## {key.replace('_', ' ').title()}")
            lines.append(str(val))
            lines.append("")
        return {"report": "\n".join(lines), "report_type": report_type}

    async def _handle_extract_iocs(self, payload: dict) -> dict:
        import re
        text = payload.get("text", "")
        patterns = {
            "ipv4":   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "domain": r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b",
            "md5":    r"\b[a-fA-F0-9]{32}\b",
            "sha256": r"\b[a-fA-F0-9]{64}\b",
            "email":  r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "url":    r"https?://[^\s<>\"{}|\\^`\[\]]+",
            "cve":    r"CVE-\d{4}-\d{4,7}",
        }
        iocs: dict[str, list] = {}
        for ioc_type, pattern in patterns.items():
            found = list(set(re.findall(pattern, text)))
            if found:
                iocs[ioc_type] = found
        return {"iocs": iocs, "total": sum(len(v) for v in iocs.values())}

    async def _handle_triage_alert(self, payload: dict) -> dict:
        alert = payload.get("alert", {})
        severity = alert.get("severity", "medium")
        source = alert.get("source", "unknown")

        priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
        priority = priority_map.get(severity, 3)

        actions = []
        if severity in ("critical", "high"):
            actions += ["isolate_affected_system", "notify_security_team", "preserve_logs"]
        elif severity == "medium":
            actions += ["investigate_source", "monitor_for_recurrence"]
        else:
            actions += ["log_and_monitor"]

        return {
            "triage_priority": priority,
            "recommended_actions": actions,
            "source": source,
            "severity": severity,
            "auto_escalate": severity in ("critical", "high"),
        }

    async def _handle_translate(self, payload: dict) -> dict:
        return {
            "note": "Translation model not configured — integrate with local or cloud NMT.",
            "source_text": payload.get("text", "")[:100],
            "target_language": payload.get("target_language", "en"),
            "status": "stub",
        }

    async def _handle_embed(self, payload: dict) -> dict:
        text = payload.get("text", "")
        # Deterministic stub — replace with sentence-transformers in production
        h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        vec = [(((h >> i) & 0xFF) / 255.0 - 0.5) for i in range(0, 384 * 8, 8)]
        return {
            "embedding": vec[:384],
            "dimensions": 384,
            "model": "stub_sha256_384d",
            "note": "Replace with sentence-transformers or text-embedding-ada-002 in production.",
        }

    async def _handle_unknown(self, payload: dict) -> dict:
        return {"error": "No handler for this task type.", "payload_keys": list(payload.keys())}

