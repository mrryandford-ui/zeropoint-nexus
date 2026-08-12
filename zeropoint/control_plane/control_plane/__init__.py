"""ZeroPoint Unified Control Plane sub-package."""

__all__ = ["ZeroPointControlPlane", "AIOrchestrator"]


def __getattr__(name):
    if name == "ZeroPointControlPlane":
        from .control_plane import ZeroPointControlPlane

        return ZeroPointControlPlane
    if name == "AIOrchestrator":
        from .ai_orchestrator import AIOrchestrator

        return AIOrchestrator
    raise AttributeError(name)
