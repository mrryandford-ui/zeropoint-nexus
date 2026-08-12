"""
Unit tests for Phase C recon orchestrator and finding normalization.
"""

import pytest
from zeropoint.pentest.recon_orchestrator import (
    NormalizedFinding,
    FindingType,
    Severity,
    NmapAdapter,
    Enum4linuxAdapter,
    WhatwebAdapter,
    ReconOrchestrator,
)


class TestNormalizedFinding:
    """Tests for NormalizedFinding data structure."""

    def test_finding_creation(self):
        """Test basic finding creation."""
        finding = NormalizedFinding(
            id="test-001",
            type=FindingType.OPEN_PORT,
            severity=Severity.INFO,
            title="Test Finding",
            description="This is a test finding",
            affected_target="192.168.1.1",
            affected_port=22,
            affected_service="ssh",
        )
        assert finding.id == "test-001"
        assert finding.type == FindingType.OPEN_PORT
        assert finding.severity == Severity.INFO
        assert finding.affected_port == 22

    def test_finding_to_dict(self):
        """Test converting finding to dictionary."""
        finding = NormalizedFinding(
            id="test-002",
            type=FindingType.SERVICE_DETECTED,
            severity=Severity.LOW,
            title="Service Found",
            description="HTTP service detected",
            affected_target="192.168.1.1",
            affected_service="http",
        )
        d = finding.to_dict()
        assert d["id"] == "test-002"
        assert d["type"] == "service_detected"
        assert d["severity"] == 0.1
        assert "timestamp" in d


class TestNmapAdapter:
    """Tests for Nmap output normalization."""

    def test_parse_nmap_text_output(self):
        """Test parsing standard Nmap text output."""
        adapter = NmapAdapter()
        output = """
        22/tcp open ssh OpenSSH 7.4
        80/tcp open http Apache httpd 2.4.6
        443/tcp open https Apache httpd 2.4.6
        """
        findings = adapter.parse_output(output, "192.168.1.1")
        assert len(findings) == 3
        assert findings[0].affected_port == 22
        assert findings[0].affected_service == "ssh"
        assert findings[1].affected_port == 80
        assert findings[1].affected_service == "http"

    def test_parse_nmap_empty_output(self):
        """Test parsing empty Nmap output."""
        adapter = NmapAdapter()
        findings = adapter.parse_output("", "192.168.1.1")
        assert len(findings) == 0

    def test_nmap_finding_severity(self):
        """Test that Nmap open ports are marked as INFO severity."""
        adapter = NmapAdapter()
        output = "22/tcp open ssh OpenSSH 7.4\n"
        findings = adapter.parse_output(output, "192.168.1.1")
        assert findings[0].severity == Severity.INFO


class TestEnum4linuxAdapter:
    """Tests for enum4linux output normalization."""

    def test_parse_enum4linux_output(self):
        """Test parsing enum4linux share enumeration."""
        adapter = Enum4linuxAdapter()
        output = """
        Shares on target
        ===============
        \\\\target\\shared
        \\\\target\\users
        \\\\target\\admin$
        """
        findings = adapter.parse_output(output, "192.168.1.1")
        assert len(findings) == 3
        assert any("shared" in f.evidence.get("share_name", "") for f in findings)
        assert findings[0].type == FindingType.INFORMATION_DISCLOSURE

    def test_enum4linux_empty_output(self):
        """Test parsing empty enum4linux output."""
        adapter = Enum4linuxAdapter()
        findings = adapter.parse_output("", "192.168.1.1")
        assert len(findings) == 0


class TestWhatwebAdapter:
    """Tests for Whatweb output normalization."""

    def test_parse_whatweb_output(self):
        """Test parsing whatweb fingerprint output."""
        adapter = WhatwebAdapter()
        output = "http://192.168.1.1 [Apache:2.4.6,OpenSSL:1.0.2] text"
        findings = adapter.parse_output(output, "192.168.1.1")
        assert len(findings) == 1
        assert findings[0].type == FindingType.SERVICE_DETECTED
        assert findings[0].severity == Severity.INFO

    def test_whatweb_empty_output(self):
        """Test parsing empty whatweb output."""
        adapter = WhatwebAdapter()
        findings = adapter.parse_output("", "192.168.1.1")
        assert len(findings) == 0


class TestReconOrchestrator:
    """Tests for orchestrator coordination."""

    def test_orchestrator_creation(self):
        """Test creating orchestrator instance."""
        orchestrator = ReconOrchestrator("192.168.1.0/24", "scope-001", "operator")
        assert orchestrator.target == "192.168.1.0/24"
        assert orchestrator.scope_id == "scope-001"
        assert orchestrator.actor_role == "operator"
        assert len(orchestrator.all_findings) == 0

    def test_add_findings(self):
        """Test adding findings to orchestrator."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")
        finding1 = NormalizedFinding(
            id="f1",
            type=FindingType.OPEN_PORT,
            severity=Severity.INFO,
            title="Port 22",
            description="SSH open",
            affected_target="192.168.1.1",
            affected_port=22,
        )
        finding2 = NormalizedFinding(
            id="f2",
            type=FindingType.SERVICE_DETECTED,
            severity=Severity.LOW,
            title="HTTP Service",
            description="HTTP detected",
            affected_target="192.168.1.1",
        )
        orchestrator.all_findings.extend([finding1, finding2])
        assert len(orchestrator.all_findings) == 2

    def test_get_findings_by_severity(self):
        """Test grouping findings by severity."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")
        for i in range(3):
            finding = NormalizedFinding(
                id=f"f{i}",
                type=FindingType.OPEN_PORT,
                severity=Severity.INFO if i < 2 else Severity.LOW,
                title=f"Port {i}",
                description=f"Port {i} open",
                affected_target="192.168.1.1",
                affected_port=22 + i,
            )
            orchestrator.all_findings.append(finding)

        grouped = orchestrator.get_findings_by_severity()
        assert "INFO" in grouped
        assert len(grouped["INFO"]) == 2
        assert len(grouped["LOW"]) == 1

    def test_executive_summary(self):
        """Test generating executive summary."""
        orchestrator = ReconOrchestrator("192.168.1.0/24", "scope-001", "operator")
        finding = NormalizedFinding(
            id="f1",
            type=FindingType.OPEN_PORT,
            severity=Severity.HIGH,
            title="High Risk Port",
            description="Dangerous port open",
            affected_target="192.168.1.1",
            affected_port=22,
        )
        orchestrator.all_findings.append(finding)

        summary = orchestrator.get_executive_summary()
        assert summary["scope_id"] == "scope-001"
        assert summary["target"] == "192.168.1.0/24"
        assert summary["total_findings"] == 1
        assert summary["findings_by_severity"]["HIGH"] == 1
        assert summary["risk_score"] == 7.0  # HIGH severity = 7.0

    def test_risk_score_calculation(self):
        """Test risk score is capped at 100."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")
        # Add 20 critical findings (9.0 each = 180 total, should cap at 100)
        for i in range(20):
            finding = NormalizedFinding(
                id=f"f{i}",
                type=FindingType.VULNERABLE_SERVICE,
                severity=Severity.CRITICAL,
                title=f"Critical {i}",
                description="Critical vulnerability",
                affected_target="192.168.1.1",
            )
            orchestrator.all_findings.append(finding)

        risk_score = orchestrator._calculate_risk_score()
        assert risk_score == 100.0

    @pytest.mark.asyncio
    async def test_run_stage_success(self):
        """Test running a recon stage successfully."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")

        async def mock_executor():
            return [
                NormalizedFinding(
                    id="mock-1",
                    type=FindingType.OPEN_PORT,
                    severity=Severity.INFO,
                    title="Mock Finding",
                    description="Mock finding from executor",
                    affected_target="192.168.1.1",
                    affected_port=22,
                )
            ]

        findings = await orchestrator.run_stage("mock_stage", mock_executor)
        assert len(findings) == 1
        assert len(orchestrator.all_findings) == 1
        assert len(orchestrator.execution_log) == 2  # started + ok

    @pytest.mark.asyncio
    async def test_run_stage_failure(self):
        """Test handling stage failures gracefully."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")

        async def failing_executor():
            raise RuntimeError("Simulated failure")

        findings = await orchestrator.run_stage("failing_stage", failing_executor)
        assert findings == []
        assert len(orchestrator.execution_log) == 2  # started + error
        assert orchestrator.execution_log[-1]["status"] == "error"

    def test_export_findings_json(self, tmp_path):
        """Test exporting findings to JSON."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")
        finding = NormalizedFinding(
            id="f1",
            type=FindingType.OPEN_PORT,
            severity=Severity.INFO,
            title="Port 22",
            description="SSH open",
            affected_target="192.168.1.1",
            affected_port=22,
        )
        orchestrator.all_findings.append(finding)

        output_file = tmp_path / "findings.json"
        orchestrator.export_findings(output_file)
        assert output_file.exists()

        import json
        with open(output_file) as f:
            data = json.load(f)
        assert data["target"] == "192.168.1.1"
        assert data["summary"]["total_findings"] == 1
        assert len(data["findings"]) == 1

    def test_export_report_markdown(self, tmp_path):
        """Test generating markdown report."""
        orchestrator = ReconOrchestrator("192.168.1.1", "scope-001", "operator")
        for i in range(3):
            severity = [Severity.CRITICAL, Severity.HIGH, Severity.LOW][i]
            finding = NormalizedFinding(
                id=f"f{i}",
                type=FindingType.OPEN_PORT,
                severity=severity,
                title=f"Finding {i}",
                description=f"Description {i}",
                affected_target="192.168.1.1",
                affected_port=22 + i,
                remediation="Apply security patch",
            )
            orchestrator.all_findings.append(finding)

        output_file = tmp_path / "report.md"
        orchestrator.export_report_markdown(output_file)
        assert output_file.exists()

        content = output_file.read_text()
        assert "Autonomous Reconnaissance Report" in content
        assert "CRITICAL" in content
        assert "HIGH" in content
        assert "192.168.1.1" in content
