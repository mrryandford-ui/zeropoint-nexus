"""
Unit tests — OSINTPipeline + InvestigationsAgent
"""
import pytest
import sys
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.osint.pipeline import OSINTPipeline, OSINTResult
from zeropoint.osint.investigations import (
    InvestigationsAgent, EvidenceType, Case, Evidence
)


# ═══════════════════════════════════════════════════════════════════════════════
# OSINTPipeline
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pipeline():
    p = OSINTPipeline(timeout=5)
    p._session = MagicMock()
    return p


class TestOSINTResult:
    def test_to_dict(self):
        r = OSINTResult("example.com", "dns", {"A": ["1.2.3.4"]})
        d = r.to_dict()
        assert d["target"] == "example.com"
        assert d["module"] == "dns"
        assert d["data"]["A"] == ["1.2.3.4"]
        assert d["error"] is None

    def test_error_result(self):
        r = OSINTResult("example.com", "dns", {}, error="timeout")
        assert r.to_dict()["error"] == "timeout"


class TestHTTPHeaders:
    @pytest.mark.asyncio
    async def test_gather_http_headers_success(self, pipeline):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.url = MagicMock(__str__=lambda _: "https://example.com")
        mock_resp.headers = {
            "Server": "nginx/1.24",
            "X-Powered-By": "PHP/8.2",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "default-src 'self'",
            "Strict-Transport-Security": "max-age=31536000",
        }
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        pipeline._session.head = MagicMock(return_value=mock_resp)

        result = await pipeline.gather_http_headers("example.com")
        assert result.module == "http_headers"
        assert result.error is None
        assert result.data.get("https", {}).get("server") == "nginx/1.24"


class TestSubdomains:
    @pytest.mark.asyncio
    async def test_gather_subdomains_returns_result(self, pipeline):
        import socket
        async def _fake_resolve(executor, fn, *args):
            # Only "www" resolves
            fqdn = args[0] if args else ""
            if "www" in str(fn):
                return "1.2.3.4"
            raise socket.gaierror("not found")

        def _mock_gethostbyname(h):
            if "www" in h:
                return "1.2.3.4"
            raise socket.gaierror(-2, "Name or service not known")

        with patch("socket.gethostbyname", side_effect=_mock_gethostbyname):
            result = await pipeline.gather_subdomains(
                "example.com", wordlist=["www", "mail", "ftp"]
            )
        assert result.module == "subdomains_active"
        assert isinstance(result.data.get("found"), list)
        assert isinstance(result.data.get("tested"), int)


class TestPortScan:
    @pytest.mark.asyncio
    async def test_port_scan_open_port(self, pipeline):
        async def _fake_conn(host, port):
            if port == 80:
                writer = MagicMock()
                writer.close = MagicMock()
                writer.wait_closed = AsyncMock()
                return MagicMock(), writer
            raise ConnectionRefusedError()

        with patch("asyncio.open_connection", side_effect=_fake_conn):
            result = await pipeline.gather_port_scan("example.com", ports=[80, 443, 22])
        assert 80 in result.data["open_ports"]
        assert 443 not in result.data["open_ports"]

    @pytest.mark.asyncio
    async def test_port_scan_all_closed(self, pipeline):
        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError()):
            result = await pipeline.gather_port_scan("example.com", ports=[9999])
        assert result.data["open_ports"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# InvestigationsAgent
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def agent():
    return InvestigationsAgent()


class TestCaseManagement:
    def test_create_case(self, agent):
        case = agent.create_case("Suspicious domain", priority="high")
        assert case.case_id.startswith("ZINV-")
        assert case.title == "Suspicious domain"
        assert case.priority == "high"
        assert case.status == "open"

    def test_case_ids_unique(self, agent):
        c1 = agent.create_case("A")
        c2 = agent.create_case("B")
        assert c1.case_id != c2.case_id

    def test_get_case_found(self, agent):
        c = agent.create_case("Test")
        assert agent.get_case(c.case_id) is c

    def test_get_case_not_found(self, agent):
        assert agent.get_case("ZINV-9999") is None

    def test_update_case_status(self, agent):
        c = agent.create_case("Test")
        result = agent.update_case_status(c.case_id, "active")
        assert result is True
        assert c.status == "active"

    def test_update_missing_case(self, agent):
        assert agent.update_case_status("ZINV-9999", "closed") is False

    def test_list_cases(self, agent):
        agent.create_case("A")
        agent.create_case("B")
        assert len(agent.list_cases()) == 2

    def test_list_cases_filter_status(self, agent):
        c = agent.create_case("A")
        agent.update_case_status(c.case_id, "closed")
        agent.create_case("B")  # stays open
        assert len(agent.list_cases(status="closed")) == 1
        assert len(agent.list_cases(status="open")) == 1


class TestEvidenceManagement:
    def test_add_evidence(self, agent):
        c = agent.create_case("Test")
        ev = agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.com", source="user")
        assert ev is not None
        assert ev.value == "evil.com"
        assert ev.etype == EvidenceType.DOMAIN
        assert ev.evidence_id in c.evidence

    def test_add_evidence_missing_case(self, agent):
        ev = agent.add_evidence("ZINV-9999", EvidenceType.IP, "1.2.3.4")
        assert ev is None

    def test_link_evidence(self, agent):
        c = agent.create_case("Test")
        ev1 = agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.com")
        ev2 = agent.add_evidence(c.case_id, EvidenceType.IP, "1.2.3.4")
        result = agent.link_evidence(c.case_id, ev1.evidence_id, ev2.evidence_id)
        assert result is True
        assert ev2.evidence_id in ev1.linked_to
        assert ev1.evidence_id in ev2.linked_to

    def test_link_evidence_idempotent(self, agent):
        c = agent.create_case("Test")
        ev1 = agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.com")
        ev2 = agent.add_evidence(c.case_id, EvidenceType.IP, "1.2.3.4")
        agent.link_evidence(c.case_id, ev1.evidence_id, ev2.evidence_id)
        agent.link_evidence(c.case_id, ev1.evidence_id, ev2.evidence_id)
        assert ev1.linked_to.count(ev2.evidence_id) == 1

    def test_search_evidence(self, agent):
        c = agent.create_case("Test")
        agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.example.com")
        agent.add_evidence(c.case_id, EvidenceType.IP, "1.2.3.4")
        results = agent.search_evidence(c.case_id, "evil")
        assert len(results) == 1
        assert results[0]["value"] == "evil.example.com"


class TestReportAndGraph:
    def test_build_graph_structure(self, agent):
        c = agent.create_case("Test")
        ev1 = agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.com")
        ev2 = agent.add_evidence(c.case_id, EvidenceType.IP, "1.2.3.4")
        agent.link_evidence(c.case_id, ev1.evidence_id, ev2.evidence_id)
        graph = agent.build_graph(c.case_id)
        assert graph["node_count"] == 2
        assert graph["edge_count"] == 1

    def test_generate_report(self, agent):
        c = agent.create_case("Test Report")
        agent.add_evidence(c.case_id, EvidenceType.DOMAIN, "evil.com")
        report = agent.generate_report(c.case_id)
        assert report["summary"]["total_evidence"] == 1
        assert "evidence_by_type" in report
        assert "link_graph" in report
        assert "timeline" in report

    def test_generate_report_missing_case(self, agent):
        result = agent.generate_report("ZINV-9999")
        assert "error" in result
