"""
AndroidTool — high-level Android automation and CamNet orchestration.
Registered tool names: android_tap, android_swipe, android_input_text,
                       android_camera_capture, camnet_status, camnet_sync
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from zeropoint.tools.base import BaseTool, ToolError, ToolResult


class AndroidTool(BaseTool):
    name = "android"
    module = "android"
    description = "Android UI automation and CamNet multi-device orchestration."

    def _setup(self) -> None:
        self._cfg = self.config
        self._camnet_cfg = self.config.get("camnet", {})
        self._screenshot_dir = Path(self.config.get("screenshot_dir", "/data/camnet/screenshots"))
        self._video_dir = Path(self.config.get("video_dir", "/data/camnet/recordings"))
        self._controller = None  # lazy-init in startup()

    async def startup(self) -> None:
        try:
            from android.camnet_controller import CamNetController
            import yaml, os
            cfg_path = os.environ.get(
                "MCP_CONFIG", "/workspace/zeropoint/config/mcp_server_config.yaml"
            )
            if Path(cfg_path).exists():
                self._controller = CamNetController.from_config(cfg_path)
                await self._controller.connect_all()
                self._log.info("CamNet: %d devices registered.", len(self._controller.devices))
            else:
                self._log.warning("MCP_CONFIG not found — CamNet running in stub mode.")
        except ImportError as exc:
            self._log.warning("CamNetController unavailable (%s) — stub mode.", exc)

    async def shutdown(self) -> None:
        if self._controller:
            await self._controller.disconnect_all()

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        op = params.pop("_op", "tap")
        dispatch = {
            "tap":              self._tap,
            "swipe":            self._swipe,
            "input_text":       self._input_text,
            "camera_capture":   self._camera_capture,
            "camnet_status":    self._camnet_status,
            "camnet_sync":      self._camnet_sync,
        }
        handler = dispatch.get(op)
        if handler is None:
            raise ToolError(f"Unknown android operation: '{op}'", code="UNKNOWN_OP")
        return await handler(params)

    # ------------------------------------------------------------------
    # android_tap
    # ------------------------------------------------------------------

    async def _tap(self, params: dict) -> ToolResult:
        self._need_controller()
        device_id = params.get("device_id")
        result = await self._controller.tap(
            device_id=device_id,
            x=params.get("x"),
            y=params.get("y"),
            selector=params.get("selector"),
            wait_seconds=params.get("wait_seconds", 5.0),
        )
        return ToolResult(data=result)

    # ------------------------------------------------------------------
    # android_swipe
    # ------------------------------------------------------------------

    async def _swipe(self, params: dict) -> ToolResult:
        self.require(params, "start_x", "start_y", "end_x", "end_y")
        self._need_controller()
        result = await self._controller.swipe(
            device_id=params.get("device_id"),
            start_x=params["start_x"],
            start_y=params["start_y"],
            end_x=params["end_x"],
            end_y=params["end_y"],
            duration_ms=params.get("duration_ms", 300),
        )
        return ToolResult(data=result)

    # ------------------------------------------------------------------
    # android_input_text
    # ------------------------------------------------------------------

    async def _input_text(self, params: dict) -> ToolResult:
        self.require(params, "text")
        self._need_controller()
        result = await self._controller.input_text(
            device_id=params.get("device_id"),
            text=params["text"],
            clear_first=params.get("clear_first", True),
        )
        return ToolResult(data=result)

    # ------------------------------------------------------------------
    # android_camera_capture
    # ------------------------------------------------------------------

    async def _camera_capture(self, params: dict) -> ToolResult:
        self._need_controller()
        mode = params.get("mode", "photo")
        if mode not in ("photo", "screencap", "burst"):
            raise ToolError(f"Invalid mode '{mode}'. Use photo, screencap, or burst.", code="BAD_PARAM")

        results = await self._controller.capture_all(
            device_ids=params.get("device_ids"),
            mode="screencap" if mode == "screencap" else "photo",
            synchronized=params.get("synchronized", True),
        )
        return ToolResult(data={"captures": [r.to_dict() for r in results]})

    # ------------------------------------------------------------------
    # camnet_status
    # ------------------------------------------------------------------

    async def _camnet_status(self, params: dict) -> ToolResult:
        self._need_controller()
        result = await self._controller.status(device_ids=params.get("device_ids"))
        return ToolResult(data=result)

    # ------------------------------------------------------------------
    # camnet_sync
    # ------------------------------------------------------------------

    async def _camnet_sync(self, params: dict) -> ToolResult:
        self._need_controller()
        result = await self._controller.sync_media(
            device_ids=params.get("device_ids"),
            media_type=params.get("media_type", "all"),
            delete_after_sync=params.get("delete_after_sync", False),
            destination=params.get("destination"),
        )
        return ToolResult(data=result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _need_controller(self) -> None:
        if self._controller is None:
            raise ToolError(
                "CamNet controller is not available. Check device config and uiautomator2 install.",
                code="CONTROLLER_UNAVAILABLE",
            )

