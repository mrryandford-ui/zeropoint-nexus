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


class TestScopeRangeValidation:
    """Test approved scope range enforcement."""

    def test_target_within_approved_range(self):
        """Target within approved range should pass validation."""
        mgr = AutonomousWorkflowManager()
        # This should not raise an exception since governance has approved ranges
        is_in_scope = mgr._is_target_in_approved_scope("192.168.1.10", "pentest_phase1")
        assert is_in_scope is True

    def test_target_within_approved_cidr_range(self):
        """CIDR range within approved range should pass validation."""
        mgr = AutonomousWorkflowManager()
        is_in_scope = mgr._is_target_in_approved_scope("192.168.1.0/25", "pentest_phase1")
        assert is_in_scope is True

    def test_target_outside_approved_range(self):
        """Target outside approved ranges should fail validation."""
        mgr = AutonomousWorkflowManager()
        is_in_scope = mgr._is_target_in_approved_scope("8.8.8.8", "pentest_phase1")
        assert is_in_scope is False

    def test_target_outside_approved_cidr_range(self):
        """CIDR range outside approved ranges should fail validation."""
        mgr = AutonomousWorkflowManager()
        is_in_scope = mgr._is_target_in_approved_scope("8.0.0.0/8", "pentest_phase1")
        assert is_in_scope is False

    def test_hostname_allowed_by_default(self):
        """Hostnames should be allowed since we can't validate CIDR against DNS names."""
        mgr = AutonomousWorkflowManager()
        is_in_scope = mgr._is_target_in_approved_scope("internal.example.com", "pentest_phase1")
        assert is_in_scope is True

    def test_recovery_workflow_range_validation(self):
        """Recovery workflow should use recovery scope ranges."""
        mgr = AutonomousWorkflowManager()
        # 127.0.0.0/8 is in recovery approved ranges
        is_in_scope = mgr._is_target_in_approved_scope("127.0.0.1", "recovery_phase1")
        assert is_in_scope is True
        # 192.168.0.0/16 is NOT in recovery approved ranges (only pentest)
        is_in_scope = mgr._is_target_in_approved_scope("192.168.1.10", "recovery_phase1")
        assert is_in_scope is False

    @pytest.mark.asyncio
    async def test_authorization_checks_scope_range(self):
        """Authorization should reject out-of-scope targets."""
        mgr = AutonomousWorkflowManager()
        with pytest.raises(ScopeValidationError, match="not within approved scope ranges"):
            mgr._require_authorized(
                authorized=True,
                scope_id="AUTH-001",
                actor_role="security_analyst",
                workflow_key="pentest_phase1",
                target="8.8.8.8",
            )

    @pytest.mark.asyncio
    async def test_authorization_allows_in_scope_targets(self):
        """Authorization should accept in-scope targets."""
        mgr = AutonomousWorkflowManager()
        # This should not raise an exception
        mgr._require_authorized(
            authorized=True,
            scope_id="AUTH-001",
            actor_role="security_analyst",
            workflow_key="pentest_phase1",
            target="192.168.1.10",
        )
