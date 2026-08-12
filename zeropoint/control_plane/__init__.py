"""ZeroPoint Unified Control Plane sub-package."""

__all__ = ["ZeroPointControlPlane", "AIOrchestrator"]


def __getattr__(name):
    if name == "ZeroPointControlPlane":
        from zeropoint.control_plane.control_plane import ZeroPointControlPlane

        return ZeroPointControlPlane
    if name == "AIOrchestrator":
        from zeropoint.control_plane.ai_orchestrator import AIOrchestrator

        return AIOrchestrator
    raise AttributeError(name)
