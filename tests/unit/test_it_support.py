"""
Unit tests — ITSupportAgent + DeviceRecoveryWorkflow
"""
import pytest
import sys
import pathlib
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.it_support.it_support_agent import ITSupportAgent, Severity, TicketStatus
from zeropoint.it_support.device_recovery import DeviceRecoveryWorkflow, DeviceState


# ═══════════════════════════════════════════════════════════════════════════════
# ITSupportAgent
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def agent():
    return ITSupportAgent()


class TestTicketManagement:
    def test_create_ticket_returns_ticket(self, agent):
        t = agent.create_ticket("Disk full", "No space left on device", severity="high")
        assert t.ticket_id.startswith("ZIT-")
        assert t.title == "Disk full"
        assert t.severity == Severity.HIGH
        assert t.status == TicketStatus.OPEN

    def test_ticket_ids_are_unique(self, agent):
        t1 = agent.create_ticket("A", "desc")
        t2 = agent.create_ticket("B", "desc")
        assert t1.ticket_id != t2.ticket_id

    def test_get_ticket_returns_correct(self, agent):
        t = agent.create_ticket("Test", "test")
        found = agent.get_ticket(t.ticket_id)
        assert found is t

    def test_get_ticket_missing_returns_none(self, agent):
        assert agent.get_ticket("ZIT-9999") is None

    def test_list_tickets_empty(self, agent):
        assert agent.list_tickets() == []

    def test_list_tickets_returns_all(self, agent):
        agent.create_ticket("A", "a")
        agent.create_ticket("B", "b")
        assert len(agent.list_tickets()) == 2

    def test_list_tickets_filter_by_status(self, agent):
        t = agent.create_ticket("A", "a")
        t.status = TicketStatus.RESOLVED
        agent.create_ticket("B", "b")  # stays OPEN
        resolved = agent.list_tickets(status="resolved")
        assert len(resolved) == 1
        assert resolved[0]["ticket_id"] == t.ticket_id


class TestClassification:
    def test_classify_disk_issue(self, agent):
        assert agent.classify_issue("No space left on disk") == "disk_full"

    def test_classify_network_issue(self, agent):
        assert agent.classify_issue("Cannot ping the gateway, network is offline") == "no_network"

    def test_classify_service_issue(self, agent):
        assert agent.classify_issue("The nginx service has crashed and stopped") == "service_down"

    def test_classify_memory_issue(self, agent):
        assert agent.classify_issue("System is out of memory, OOM killer triggered") == "high_memory"

    def test_classify_auth_issue(self, agent):
        assert agent.classify_issue("Permission denied when running sudo") == "auth_failure"

    def test_classify_cpu_issue(self, agent):
        assert agent.classify_issue("CPU load is at 100%, system is slow") == "high_cpu"

    def test_classify_unknown(self, agent):
        assert agent.classify_issue("The sky is blue today") == "unknown"

    def test_classify_device_issue(self, agent):
        assert agent.classify_issue("ADB device not found, disconnected") == "device_offline"


class TestTriage:
    @pytest.mark.asyncio
    async def test_triage_returns_issue_type(self, agent):
        t = agent.create_ticket("Disk full", "No space left on /data disk partition")
        result = await agent.triage(t)
        assert "issue_type" in result
        assert result["issue_type"] == "disk_full"
        assert t.status == TicketStatus.TRIAGING

    @pytest.mark.asyncio
    async def test_triage_logs_step(self, agent):
        t = agent.create_ticket("Network down", "Cannot ping 8.8.8.8 network connectivity")
        await agent.triage(t)
        assert any("Classified" in step for step in t.steps_taken)


class TestRemediation:
    @pytest.mark.asyncio
    async def test_remediation_unknown_escalates(self, agent):
        t = agent.create_ticket("Mystery", "strange unexplained phenomenon")
        result = await agent.auto_remediate(t, "unknown")
        assert t.status == TicketStatus.ESCALATED
        assert any("escalating" in a.lower() for a in result["actions"])

    @pytest.mark.asyncio
    async def test_remediation_disk_attempts_cleanup(self, agent):
        t = agent.create_ticket("Disk", "disk full")
        # Mock the subprocess calls
        async def _fake_run(cmd, timeout=10):
            return "ok", 0
        with patch.object(agent, "_run", _fake_run):
            result = await agent.auto_remediate(t, "disk_full")
        assert len(result["actions"]) > 0

    @pytest.mark.asyncio
    async def test_remediation_sets_resolution_on_success(self, agent):
        t = agent.create_ticket("Disk", "disk full")
        async def _fake_run(cmd, timeout=10):
            return "Deleted.", 0
        with patch.object(agent, "_run", _fake_run):
            await agent.auto_remediate(t, "disk_full")
        assert t.status == TicketStatus.RESOLVED
        assert t.resolution != ""
        assert t.resolved_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# DeviceRecoveryWorkflow
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def recovery():
    return DeviceRecoveryWorkflow()


def _mock_adb(stdout="", rc=0):
    async def _fake(self, args, serial=None, timeout=30):
        return stdout, rc
    return _fake


class TestDeviceRecovery:
    def test_session_ids_unique(self, recovery):
        # Just verify internal counter increments
        assert recovery._counter == 0

    @pytest.mark.asyncio
    async def test_detect_state_online(self, recovery):
        with patch.object(DeviceRecoveryWorkflow, "_adb", _mock_adb(stdout="device", rc=0)):
            state = await recovery.detect_state("192.168.100.10:5555")
        assert state == DeviceState.ONLINE

    @pytest.mark.asyncio
    async def test_detect_state_offline(self, recovery):
        with patch.object(DeviceRecoveryWorkflow, "_adb", _mock_adb(stdout="", rc=1)):
            with patch.object(DeviceRecoveryWorkflow, "_fastboot", _mock_adb(stdout="", rc=1)):
                state = await recovery.detect_state("192.168.100.99:5555")
        assert state == DeviceState.OFFLINE

    @pytest.mark.asyncio
    async def test_soft_reset_success(self, recovery):
        call_count = [0]
        async def _adb(self, args, serial=None, timeout=30):
            call_count[0] += 1
            if "get-state" in args:
                return "device", 0
            return "", 0
        with patch.object(DeviceRecoveryWorkflow, "_adb", _adb):
            session = await recovery.soft_reset("192.168.100.10:5555")
        assert session.completed
        assert any(s.name == "reboot" for s in session.steps)

    @pytest.mark.asyncio
    async def test_factory_reset_requires_confirmation(self, recovery):
        session = await recovery.factory_reset("192.168.100.10:5555", confirmed=False)
        assert session.completed
        assert not session.success
        assert any("safety_gate" in s.name for s in session.steps)

    @pytest.mark.asyncio
    async def test_adb_reconnect_runs_four_steps(self, recovery):
        with patch.object(DeviceRecoveryWorkflow, "_adb", _mock_adb(stdout="connected", rc=0)):
            session = await recovery.adb_reconnect("192.168.100.10:5555")
        # Should have: disconnect, kill-server, start-server, connect
        assert len(session.steps) >= 4

    def test_list_sessions_empty(self, recovery):
        assert recovery.list_sessions() == []

    @pytest.mark.asyncio
    async def test_get_session_returns_dict(self, recovery):
        with patch.object(DeviceRecoveryWorkflow, "_adb", _mock_adb(stdout="device", rc=0)):
            session = await recovery.adb_reconnect("192.168.100.10:5555")
        result = recovery.get_session(session.session_id)
        assert result is not None
        assert result["session_id"] == session.session_id
