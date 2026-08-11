"""
Unit tests — AIOrchestrator (local execution path, no Ray required)
"""
import pytest
import sys
import pathlib
import asyncio

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.control_plane.ai_orchestrator import AIOrchestrator, AITask, _LRUCache


# ── LRUCache ───────────────────────────────────────────────────────────────────

class TestLRUCache:
    def test_set_and_get(self):
        c = _LRUCache(maxsize=3)
        c.set("k1", {"data": 1})
        assert c.get("k1") == {"data": 1}

    def test_miss_returns_none(self):
        c = _LRUCache()
        assert c.get("nonexistent") is None

    def test_eviction_on_overflow(self):
        c = _LRUCache(maxsize=2)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)   # should evict "a"
        assert c.get("a") is None
        assert c.get("b") == 2
        assert c.get("c") == 3

    def test_access_refreshes_lru(self):
        c = _LRUCache(maxsize=2)
        c.set("a", 1)
        c.set("b", 2)
        c.get("a")       # refresh "a"
        c.set("c", 3)    # should evict "b" not "a"
        assert c.get("a") == 1
        assert c.get("b") is None

    def test_key_for_deterministic(self):
        c = _LRUCache()
        k1 = c.key_for("classify_it_issue", {"description": "disk full"})
        k2 = c.key_for("classify_it_issue", {"description": "disk full"})
        assert k1 == k2

    def test_key_for_different_payload(self):
        c = _LRUCache()
        k1 = c.key_for("classify_it_issue", {"description": "disk full"})
        k2 = c.key_for("classify_it_issue", {"description": "network down"})
        assert k1 != k2


# ── AIOrchestrator ─────────────────────────────────────────────────────────────

@pytest.fixture
def orch():
    o = AIOrchestrator(ray_config={})
    o._ray_available = False  # force local path
    return o


class TestSubmit:
    @pytest.mark.asyncio
    async def test_unknown_task_type(self, orch):
        result = await orch.submit("nonexistent_task", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_result_has_task_id(self, orch):
        result = await orch.submit("classify_it_issue", {"description": "disk is full"})
        assert "task_id" in result
        assert result["task_id"].startswith("AIT-")

    @pytest.mark.asyncio
    async def test_caching_returns_cached(self, orch):
        payload = {"description": "no space on disk"}
        r1 = await orch.submit("classify_it_issue", payload)
        r2 = await orch.submit("classify_it_issue", payload)
        assert r2.get("_cached") is True

    @pytest.mark.asyncio
    async def test_no_cache_flag(self, orch):
        payload = {"description": "no space on disk"}
        r1 = await orch.submit("classify_it_issue", payload, use_cache=False)
        r2 = await orch.submit("classify_it_issue", payload, use_cache=False)
        assert not r2.get("_cached")

    @pytest.mark.asyncio
    async def test_task_recorded(self, orch):
        await orch.submit("classify_it_issue", {"description": "cpu high"})
        tasks = orch.list_tasks()
        assert len(tasks) >= 1


class TestClassifyIT:
    @pytest.mark.asyncio
    async def test_classify_disk(self, orch):
        r = await orch.submit("classify_it_issue", {"description": "disk is full no space left"})
        assert r["classification"] == "disk_full"

    @pytest.mark.asyncio
    async def test_classify_network(self, orch):
        r = await orch.submit("classify_it_issue", {"description": "network connectivity ping failed"})
        assert r["classification"] == "network"

    @pytest.mark.asyncio
    async def test_classify_unknown(self, orch):
        r = await orch.submit("classify_it_issue", {"description": "the weather is nice"})
        assert r["classification"] == "unknown"

    @pytest.mark.asyncio
    async def test_confidence_between_0_and_1(self, orch):
        r = await orch.submit("classify_it_issue", {"description": "disk space full storage"})
        assert 0.0 <= r["confidence"] <= 1.0


class TestExtractIOCs:
    @pytest.mark.asyncio
    async def test_extracts_ipv4(self, orch):
        r = await orch.submit("extract_iocs", {"text": "Attacker IP: 192.168.1.100 and 10.0.0.5"})
        assert "ipv4" in r["iocs"]
        assert "192.168.1.100" in r["iocs"]["ipv4"]

    @pytest.mark.asyncio
    async def test_extracts_cve(self, orch):
        r = await orch.submit("extract_iocs", {"text": "Vulnerable to CVE-2024-12345"})
        assert "cve" in r["iocs"]
        assert "CVE-2024-12345" in r["iocs"]["cve"]

    @pytest.mark.asyncio
    async def test_extracts_email(self, orch):
        r = await orch.submit("extract_iocs", {"text": "Contact attacker@evil.com for ransom"})
        assert "email" in r["iocs"]

    @pytest.mark.asyncio
    async def test_extracts_md5(self, orch):
        r = await orch.submit("extract_iocs", {"text": "Hash: d41d8cd98f00b204e9800998ecf8427e"})
        assert "md5" in r["iocs"]

    @pytest.mark.asyncio
    async def test_no_iocs_returns_empty(self, orch):
        r = await orch.submit("extract_iocs", {"text": "Nothing interesting here."})
        assert r["total"] == 0


class TestTriageAlert:
    @pytest.mark.asyncio
    async def test_critical_alert_auto_escalates(self, orch):
        r = await orch.submit("triage_alert", {
            "alert": {"severity": "critical", "source": "IDS", "message": "RCE detected"}
        })
        assert r["auto_escalate"] is True
        assert r["triage_priority"] == 1

    @pytest.mark.asyncio
    async def test_low_alert_no_escalation(self, orch):
        r = await orch.submit("triage_alert", {
            "alert": {"severity": "low", "source": "monitor"}
        })
        assert r["auto_escalate"] is False
        assert r["triage_priority"] > 2

    @pytest.mark.asyncio
    async def test_recommended_actions_present(self, orch):
        r = await orch.submit("triage_alert", {
            "alert": {"severity": "high", "source": "SIEM"}
        })
        assert isinstance(r["recommended_actions"], list)
        assert len(r["recommended_actions"]) > 0


class TestSummarizeOSINT:
    @pytest.mark.asyncio
    async def test_summarize_returns_summary_string(self, orch):
        results = [
            {"module": "dns", "data": {"A": ["1.2.3.4"]}},
            {"module": "port_scan_active", "data": {"open_ports": [80, 443], "scanned": 10}},
            {"module": "cert_transparency", "data": {"subdomains_found": ["www.evil.com"]}},
        ]
        r = await orch.submit("summarize_osint", {"target": "evil.com", "results": results})
        assert "evil.com" in r["summary"]
        assert 80 in r["open_ports"]


class TestAsyncSubmit:
    @pytest.mark.asyncio
    async def test_submit_async_returns_task_id(self, orch):
        tid = await orch.submit_async("extract_iocs", {"text": "CVE-2024-99999"})
        assert tid.startswith("AIT-")

    @pytest.mark.asyncio
    async def test_get_task(self, orch):
        r = await orch.submit("classify_it_issue", {"description": "disk full"})
        task = await orch.get_task(r["task_id"])
        assert task is not None
        assert task["done"] is True

    @pytest.mark.asyncio
    async def test_get_missing_task(self, orch):
        result = await orch.get_task("AIT-99999")
        assert result is None
