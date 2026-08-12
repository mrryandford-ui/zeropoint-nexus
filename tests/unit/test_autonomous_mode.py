"""
Unit tests — AutonomousWorkflowManager phase-1 scaffolding.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from zeropoint.control_plane.autonomous_mode import (
    AutonomousWorkflowManager,
    AuthorizationError,
    ScopeValidationError,
    validate_target_scope,
)


class TestValidateTargetScope:
    def test_private_ip_allowed(self):
        out = validate_target_scope("192.168.0.10")
        assert out["scope_type"] == "ip"
        assert out["is_private"] is True

    def test_private_cidr_allowed(self):
        out = validate_target_scope("10.0.0.0/24")
        assert out["scope_type"] == "cidr"
        assert out["is_private"] is True

    def test_public_ip_blocked_by_default(self):
        with pytest.raises(ScopeValidationError):
            validate_target_scope("8.8.8.8")

    def test_public_ip_allowed_with_override(self):
        out = validate_target_scope("8.8.8.8", allow_public=True)
        assert out["scope_type"] == "ip"
        assert out["is_private"] is False


class TestAutonomousWorkflowManager:
    def test_plan_pentest(self):
        mgr = AutonomousWorkflowManager()
        plan = mgr.plan_pentest("192.168.1.0/24")
        assert plan["workflow"] == "autonomous_pentest_phase1"
        assert len(plan["steps"]) >= 4

    def test_plan_recovery(self):
        mgr = AutonomousWorkflowManager()
        plan = mgr.plan_device_recovery("192.168.100.10:5555")
        assert plan["workflow"] == "autonomous_device_recovery_phase1"
        assert plan["device_serial"] == "192.168.100.10:5555"

    @pytest.mark.asyncio
    async def test_run_pentest_requires_authorization(self):
        mgr = AutonomousWorkflowManager()
        with pytest.raises(AuthorizationError):
            await mgr.run_pentest(
                target="192.168.1.10",
                scope_id="",
                authorized=False,
            )

    @pytest.mark.asyncio
    async def test_run_pentest_happy_path_with_mocked_osint(self, monkeypatch):
        mgr = AutonomousWorkflowManager()

        class FakePipeline:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def run_all(self, target, active=False):
                return {
                    "target": target,
                    "active_mode": active,
                    "module_count": 1,
                    "results": [
                        {
                            "module": "port_scan_active",
                            "data": {"open_ports": [80, 443], "scanned": 10},
                        }
                    ],
                }

        monkeypatch.setattr("zeropoint.osint.pipeline.OSINTPipeline", FakePipeline)
        result = await mgr.run_pentest(
            target="192.168.1.10",
            scope_id="AUTH-123",
            authorized=True,
            active=True,
            use_kali=False,
        )
        assert result["authorized"] is True
        assert result["summary"]["open_ports_detected"] == [80, 443]
        assert len(result["audit_trail"]) >= 3

    @pytest.mark.asyncio
    async def test_run_recovery_happy_path_with_mocked_workflow(self, monkeypatch):
        mgr = AutonomousWorkflowManager()

        class FakeSession:
            success = True

            def to_dict(self):
                return {"session_id": "REC-0001", "success": True}

        class FakeRecoveryWorkflow:
            async def detect_state(self, serial):
                return "online"

            async def adb_reconnect(self, serial):
                return FakeSession()

        monkeypatch.setattr(
            "zeropoint.it_support.device_recovery.DeviceRecoveryWorkflow",
            FakeRecoveryWorkflow,
        )
        result = await mgr.run_device_recovery(
            device_serial="192.168.100.10:5555",
            authorized=True,
            scope_id="AUTH-456",
            attempt_reconnect=True,
        )
        assert result["authorized"] is True
        assert result["recommendation"] == "device_online"
        assert result["reconnect_session"]["success"] is True

