"""
ZeroPoint Investigations Agent
Case management, evidence collection, and link analysis
for structured OSINT investigations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger("zeropoint.osint.investigations")


class EvidenceType(str, Enum):
    DOMAIN = "domain"
    IP = "ip"
    EMAIL = "email"
    PERSON = "person"
    ORGANIZATION = "organization"
    PHONE = "phone"
    USERNAME = "username"
    URL = "url"
    HASH = "hash"
    FILE = "file"
    NOTE = "note"


@dataclass
class Evidence:
    evidence_id: str
    etype: EvidenceType
    value: str
    source: str
    confidence: float  # 0.0 – 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    added_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    linked_to: list[str] = field(default_factory=list)  # other evidence_ids

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "type": self.etype,
            "value": self.value,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "tags": self.tags,
            "metadata": self.metadata,
            "added_at": self.added_at.isoformat(),
            "linked_to": self.linked_to,
        }


@dataclass
class Case:
    case_id: str
    title: str
    description: str
    status: str = "open"  # open | active | closed | archived
    priority: str = "medium"  # low | medium | high | critical
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evidence: dict[str, Evidence] = field(default_factory=dict)
    timeline: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def add_event(self, actor: str, action: str, detail: str = "") -> None:
        self.timeline.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "actor": actor,
                "action": action,
                "detail": detail,
            }
        )
        self.updated_at = datetime.now(UTC)

    def to_dict(self, include_evidence: bool = True) -> dict:
        d = {
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "evidence_count": len(self.evidence),
            "timeline_entries": len(self.timeline),
            "tags": self.tags,
            "timeline": self.timeline[-20:],  # last 20 events
        }
        if include_evidence:
            d["evidence"] = {k: v.to_dict() for k, v in self.evidence.items()}
        return d


class InvestigationsAgent:
    """
    Manages investigation cases and evidence chains for ZeroPoint.

    Usage:
        agent = InvestigationsAgent()
        case = agent.create_case("Suspicious domain activity", "...")
        ev = agent.add_evidence(case.case_id, EvidenceType.DOMAIN, "evil.example.com", source="user_report")
        agent.link_evidence(case.case_id, ev.evidence_id, other_id)
        report = agent.generate_report(case.case_id)
    """

    def __init__(self, cases_dir: str | None = None):
        self._cases: dict[str, Case] = {}
        self._counter = 0
        self._ev_counter = 0
        self._cases_dir = Path(cases_dir) if cases_dir else None

    # ------------------------------------------------------------------
    # Case management
    # ------------------------------------------------------------------

    def create_case(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        tags: list[str] | None = None,
    ) -> Case:
        self._counter += 1
        cid = f"ZINV-{self._counter:04d}"
        case = Case(
            case_id=cid,
            title=title,
            description=description,
            priority=priority,
            tags=tags or [],
        )
        case.add_event("system", "case_created", title)
        self._cases[cid] = case
        logger.info("Created case %s: %s", cid, title)
        if self._cases_dir:
            self._persist(case)
        return case

    def get_case(self, case_id: str) -> Case | None:
        return self._cases.get(case_id)

    def update_case_status(self, case_id: str, status: str, actor: str = "system") -> bool:
        case = self._cases.get(case_id)
        if not case:
            return False
        case.status = status
        case.add_event(actor, "status_changed", status)
        return True

    def list_cases(self, status: str | None = None) -> list[dict]:
        cases = self._cases.values()
        if status:
            cases = [c for c in cases if c.status == status]
        return [
            c.to_dict(include_evidence=False)
            for c in sorted(cases, key=lambda c: c.updated_at, reverse=True)
        ]

    # ------------------------------------------------------------------
    # Evidence management
    # ------------------------------------------------------------------

    def add_evidence(
        self,
        case_id: str,
        etype: EvidenceType,
        value: str,
        source: str = "manual",
        confidence: float = 0.8,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Evidence | None:
        case = self._cases.get(case_id)
        if not case:
            logger.warning("Case %s not found", case_id)
            return None

        self._ev_counter += 1
        eid = f"EV-{self._ev_counter:05d}"
        # Fingerprint for deduplication
        fp = hashlib.sha256(f"{etype}:{value}".encode()).hexdigest()[:12]

        ev = Evidence(
            evidence_id=f"{eid}-{fp}",
            etype=etype,
            value=value,
            source=source,
            confidence=confidence,
            tags=tags or [],
            metadata=metadata or {},
        )
        case.evidence[ev.evidence_id] = ev
        case.add_event("system", "evidence_added", f"{etype}: {value[:60]}")
        logger.info("Evidence %s added to %s", ev.evidence_id, case_id)
        return ev

    def link_evidence(self, case_id: str, ev_id_a: str, ev_id_b: str) -> bool:
        case = self._cases.get(case_id)
        if not case:
            return False
        ev_a = case.evidence.get(ev_id_a)
        ev_b = case.evidence.get(ev_id_b)
        if not ev_a or not ev_b:
            return False
        if ev_id_b not in ev_a.linked_to:
            ev_a.linked_to.append(ev_id_b)
        if ev_id_a not in ev_b.linked_to:
            ev_b.linked_to.append(ev_id_a)
        case.add_event("system", "evidence_linked", f"{ev_id_a} ↔ {ev_id_b}")
        return True

    def search_evidence(self, case_id: str, query: str) -> list[dict]:
        case = self._cases.get(case_id)
        if not case:
            return []
        q = query.lower()
        return [
            ev.to_dict()
            for ev in case.evidence.values()
            if q in ev.value.lower()
            or q in ev.source.lower()
            or any(q in t.lower() for t in ev.tags)
        ]

    # ------------------------------------------------------------------
    # Link analysis
    # ------------------------------------------------------------------

    def build_graph(self, case_id: str) -> dict:
        """Return adjacency graph for evidence link analysis."""
        case = self._cases.get(case_id)
        if not case:
            return {}

        nodes = []
        edges = []
        seen_edges: set[frozenset] = set()

        for ev in case.evidence.values():
            nodes.append(
                {
                    "id": ev.evidence_id,
                    "type": ev.etype,
                    "label": ev.value[:40],
                    "confidence": ev.confidence,
                }
            )
            for linked in ev.linked_to:
                pair = frozenset([ev.evidence_id, linked])
                if pair not in seen_edges:
                    seen_edges.add(pair)
                    edges.append({"source": ev.evidence_id, "target": linked})

        return {
            "case_id": case_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(self, case_id: str) -> dict:
        case = self._cases.get(case_id)
        if not case:
            return {"error": f"Case {case_id} not found"}

        # Group evidence by type
        by_type: dict[str, list] = {}
        for ev in case.evidence.values():
            by_type.setdefault(ev.etype, []).append(ev.to_dict())

        # Stats
        total_links = sum(len(ev.linked_to) for ev in case.evidence.values()) // 2
        avg_confidence = (
            sum(ev.confidence for ev in case.evidence.values()) / len(case.evidence)
            if case.evidence
            else 0.0
        )

        report = {
            "report_generated": datetime.now(UTC).isoformat(),
            "case": case.to_dict(include_evidence=False),
            "summary": {
                "total_evidence": len(case.evidence),
                "evidence_types": {k: len(v) for k, v in by_type.items()},
                "total_links": total_links,
                "avg_confidence": round(avg_confidence, 2),
                "timeline_entries": len(case.timeline),
            },
            "evidence_by_type": by_type,
            "link_graph": self.build_graph(case_id),
            "timeline": case.timeline,
        }
        return report

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, case: Case) -> None:
        if not self._cases_dir:
            return
        self._cases_dir.mkdir(parents=True, exist_ok=True)
        path = self._cases_dir / f"{case.case_id}.json"
        path.write_text(json.dumps(case.to_dict(), indent=2, default=str))

    def load_from_disk(self) -> int:
        if not self._cases_dir or not self._cases_dir.exists():
            return 0
        loaded = 0
        for path in self._cases_dir.glob("ZINV-*.json"):
            try:
                data = json.loads(path.read_text())
                case = Case(
                    case_id=data["case_id"],
                    title=data["title"],
                    description=data["description"],
                    status=data.get("status", "open"),
                    priority=data.get("priority", "medium"),
                    tags=data.get("tags", []),
                )
                for ev_data in data.get("evidence", {}).values():
                    ev = Evidence(
                        evidence_id=ev_data["evidence_id"],
                        etype=EvidenceType(ev_data["type"]),
                        value=ev_data["value"],
                        source=ev_data["source"],
                        confidence=ev_data["confidence"],
                        tags=ev_data.get("tags", []),
                        metadata=ev_data.get("metadata", {}),
                        linked_to=ev_data.get("linked_to", []),
                    )
                    case.evidence[ev.evidence_id] = ev
                self._cases[case.case_id] = case
                loaded += 1
            except Exception as exc:
                logger.warning("Could not load %s: %s", path, exc)
        return loaded
