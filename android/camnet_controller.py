#!/usr/bin/env python3
"""
ZeroPoint CamNet — Android Multi-Device Automation Controller
Manages a fleet of Android devices (CamNet nodes) for synchronized
capture, monitoring, and media synchronization.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uiautomator2 as u2
import yaml

logger = logging.getLogger(__name__)

###############################################################################
# Data Models
###############################################################################

@dataclass
class DeviceInfo:
    device_id: str
    serial: str
    role: str
    label: str
    tags: list[str] = field(default_factory=list)
    # Live state (populated after connect)
    connected: bool = False
    battery_pct: int = -1
    storage_free_gb: float = -1.0
    android_version: str = ""
    last_seen: datetime | None = None
    _d: Any = field(default=None, repr=False)   # uiautomator2 Device handle

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "serial": self.serial,
            "role": self.role,
            "label": self.label,
            "tags": self.tags,
            "connected": self.connected,
            "battery_pct": self.battery_pct,
            "storage_free_gb": round(self.storage_free_gb, 2),
            "android_version": self.android_version,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


@dataclass
class CaptureResult:
    device_id: str
    local_path: str | None
    timestamp: datetime
    success: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "local_path": self.local_path,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }


###############################################################################
# CamNet Controller
###############################################################################

class CamNetController:
    """
    Orchestrates multiple Android devices as a synchronized camera network.

    Usage:
        ctrl = CamNetController.from_config("/workspace/zeropoint/config/mcp_server_config.yaml")
        asyncio.run(ctrl.connect_all())
        results = asyncio.run(ctrl.capture_all(mode="photo"))
    """

    def __init__(
        self,
        devices: list[DeviceInfo],
        screenshot_dir: Path,
        video_dir: Path,
        network_id: str = "camnet-0",
        coordinator_host: str = "192.168.100.1",
        coordinator_port: int = 9000,
        sync_interval_seconds: int = 5,
    ):
        self.devices: dict[str, DeviceInfo] = {d.device_id: d for d in devices}
        self.screenshot_dir = Path(screenshot_dir)
        self.video_dir = Path(video_dir)
        self.network_id = network_id
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        self.sync_interval_seconds = sync_interval_seconds
        self._lock = asyncio.Lock()

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config_path: str | Path) -> "CamNetController":
        """Instantiate from mcp_server_config.yaml."""
        cfg = yaml.safe_load(Path(config_path).read_text())
        android_cfg = cfg["tools"]["android"]["config"]
        camnet_cfg = android_cfg["camnet"]
        raw_devices = cfg.get("android_devices", [])

        devices = [
            DeviceInfo(
                device_id=d["id"],
                serial=d["serial"],
                role=d.get("role", "secondary"),
                label=d.get("label", d["id"]),
                tags=d.get("tags", []),
            )
            for d in raw_devices
        ]

        return cls(
            devices=devices,
            screenshot_dir=android_cfg["screenshot_dir"],
            video_dir=android_cfg["video_dir"],
            network_id=camnet_cfg["network_id"],
            coordinator_host=camnet_cfg["coordinator_host"],
            coordinator_port=camnet_cfg["coordinator_port"],
            sync_interval_seconds=camnet_cfg["sync_interval_seconds"],
        )

    # ------------------------------------------------------------------
    # Device Management
    # ------------------------------------------------------------------

    def _get_devices(self, device_ids: list[str] | None) -> list[DeviceInfo]:
        if not device_ids:
            return list(self.devices.values())
        return [self.devices[did] for did in device_ids if did in self.devices]

    async def connect_device(self, dev: DeviceInfo) -> bool:
        """Connect to a single device via uiautomator2 over network ADB."""
        loop = asyncio.get_event_loop()
        try:
            d = await loop.run_in_executor(None, u2.connect, dev.serial)
            dev._d = d
            dev.connected = True
            dev.last_seen = datetime.now(timezone.utc)

            info = await loop.run_in_executor(None, lambda: d.device_info)
            dev.android_version = info.get("sdkInt", "")
            batt = await loop.run_in_executor(None, lambda: d.battery.get_info())
            dev.battery_pct = batt.get("level", -1)

            logger.info("Connected to %s (%s)", dev.label, dev.serial)
            return True
        except Exception as exc:
            dev.connected = False
            logger.warning("Failed to connect %s: %s", dev.serial, exc)
            return False

    async def connect_all(self, device_ids: list[str] | None = None) -> dict[str, bool]:
        """Connect to all (or specified) devices concurrently."""
        targets = self._get_devices(device_ids)
        tasks = [self.connect_device(dev) for dev in targets]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return {dev.device_id: ok for dev, ok in zip(targets, results)}

    async def disconnect_all(self) -> None:
        for dev in self.devices.values():
            dev.connected = False
            dev._d = None
        logger.info("All devices disconnected.")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self, device_ids: list[str] | None = None) -> dict:
        """Return live status of all devices."""
        targets = self._get_devices(device_ids)
        loop = asyncio.get_event_loop()

        async def _refresh(dev: DeviceInfo):
            if dev._d and dev.connected:
                try:
                    batt = await loop.run_in_executor(None, lambda: dev._d.battery.get_info())
                    dev.battery_pct = batt.get("level", dev.battery_pct)
                    dev.last_seen = datetime.now(timezone.utc)
                except Exception:
                    dev.connected = False

        await asyncio.gather(*[_refresh(d) for d in targets])
        active = sum(1 for d in targets if d.connected)

        return {
            "network_id": self.network_id,
            "active_count": active,
            "devices": [d.to_dict() for d in targets],
        }

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    async def _capture_photo(self, dev: DeviceInfo, save_dir: Path) -> CaptureResult:
        ts = datetime.now(timezone.utc)
        loop = asyncio.get_event_loop()
        filename = f"{dev.device_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        local_path = save_dir / dev.device_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Launch camera, take photo, pull file
            d = dev._d
            await loop.run_in_executor(
                None,
                lambda: d.shell("am start -a android.media.action.STILL_IMAGE_CAMERA")
            )
            await asyncio.sleep(1.5)  # allow camera to open

            # Trigger shutter via keycode (KEYCODE_CAMERA = 27)
            await loop.run_in_executor(None, lambda: d.shell("input keyevent 27"))
            await asyncio.sleep(2.0)  # allow photo save

            # Find latest DCIM image and pull it
            result = await loop.run_in_executor(
                None,
                lambda: d.shell(
                    "ls -t /sdcard/DCIM/Camera/*.jpg 2>/dev/null | head -1"
                )
            )
            remote_path = result.output.strip()
            if not remote_path:
                raise RuntimeError("No photo found in DCIM/Camera/")

            await loop.run_in_executor(
                None, lambda: d.pull(remote_path, str(local_path))
            )
            dev.last_seen = datetime.now(timezone.utc)
            return CaptureResult(dev.device_id, str(local_path), ts, True)
        except Exception as exc:
            logger.error("Capture failed on %s: %s", dev.device_id, exc)
            return CaptureResult(dev.device_id, None, ts, False, str(exc))

    async def _capture_screencap(self, dev: DeviceInfo) -> CaptureResult:
        ts = datetime.now(timezone.utc)
        loop = asyncio.get_event_loop()
        filename = f"{dev.device_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.png"
        local_path = self.screenshot_dir / dev.device_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            img = await loop.run_in_executor(None, dev._d.screenshot)
            await loop.run_in_executor(None, lambda: img.save(str(local_path)))
            dev.last_seen = datetime.now(timezone.utc)
            return CaptureResult(dev.device_id, str(local_path), ts, True)
        except Exception as exc:
            logger.error("Screencap failed on %s: %s", dev.device_id, exc)
            return CaptureResult(dev.device_id, None, ts, False, str(exc))

    async def capture_all(
        self,
        device_ids: list[str] | None = None,
        mode: str = "photo",
        synchronized: bool = True,
    ) -> list[CaptureResult]:
        """
        Trigger capture on all (or specified) connected devices.

        mode: 'photo' | 'screencap'
        synchronized: if True, fire all devices simultaneously via gather()
        """
        targets = [d for d in self._get_devices(device_ids) if d.connected]
        if not targets:
            logger.warning("No connected devices to capture.")
            return []

        save_dir = self.screenshot_dir if mode == "screencap" else (
            self.screenshot_dir.parent / "photos"
        )
        save_dir.mkdir(parents=True, exist_ok=True)

        async def _one(dev: DeviceInfo) -> CaptureResult:
            if mode == "screencap":
                return await self._capture_screencap(dev)
            else:
                return await self._capture_photo(dev, save_dir)

        if synchronized:
            results = await asyncio.gather(*[_one(d) for d in targets])
        else:
            results = []
            for dev in targets:
                results.append(await _one(dev))

        ok = sum(1 for r in results if r.success)
        logger.info("Capture complete: %d/%d succeeded.", ok, len(results))
        return list(results)

    # ------------------------------------------------------------------
    # Media Sync
    # ------------------------------------------------------------------

    async def sync_media(
        self,
        device_ids: list[str] | None = None,
        media_type: str = "all",
        delete_after_sync: bool = False,
        destination: str | None = None,
    ) -> dict:
        """Pull media from devices to coordinator storage."""
        targets = [d for d in self._get_devices(device_ids) if d.connected]
        dest = Path(destination or self.screenshot_dir.parent / "sync")
        today = datetime.now().strftime("%Y-%m-%d")
        dest_day = dest / today
        dest_day.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_event_loop()
        total_files = 0
        total_bytes = 0
        errors: list[str] = []

        async def _sync_one(dev: DeviceInfo):
            nonlocal total_files, total_bytes
            try:
                patterns = []
                if media_type in ("all", "photo"):
                    patterns.append("/sdcard/DCIM/Camera/*.jpg")
                if media_type in ("all", "video"):
                    patterns.append("/sdcard/DCIM/Camera/*.mp4")

                for pattern in patterns:
                    ls = await loop.run_in_executor(
                        None,
                        lambda p=pattern: dev._d.shell(f"ls {p} 2>/dev/null").output
                    )
                    for remote_file in ls.strip().splitlines():
                        remote_file = remote_file.strip()
                        if not remote_file:
                            continue
                        fname = Path(remote_file).name
                        local_path = dest_day / dev.device_id / fname
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        await loop.run_in_executor(
                            None, lambda r=remote_file, l=local_path: dev._d.pull(r, str(l))
                        )
                        total_files += 1
                        total_bytes += local_path.stat().st_size
                        if delete_after_sync:
                            await loop.run_in_executor(
                                None,
                                lambda r=remote_file: dev._d.shell(f"rm -f {r}")
                            )
                dev.last_seen = datetime.now(timezone.utc)
            except Exception as exc:
                errors.append(f"{dev.device_id}: {exc}")
                logger.error("Sync error on %s: %s", dev.device_id, exc)

        await asyncio.gather(*[_sync_one(d) for d in targets])

        return {
            "synced_files": total_files,
            "bytes_transferred": total_bytes,
            "destination": str(dest_day),
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # UI Automation Helpers
    # ------------------------------------------------------------------

    async def tap(
        self,
        device_id: str,
        x: float | None = None,
        y: float | None = None,
        selector: dict | None = None,
        wait_seconds: float = 5.0,
    ) -> dict:
        dev = self.devices.get(device_id)
        if not dev or not dev.connected:
            return {"tapped": False, "element_found": False, "error": "Device not connected"}

        loop = asyncio.get_event_loop()
        try:
            d = dev._d
            if selector:
                el = d(**selector)
                found = await loop.run_in_executor(
                    None, lambda: el.wait(timeout=wait_seconds)
                )
                if found:
                    await loop.run_in_executor(None, el.click)
                return {"tapped": found, "element_found": found}
            elif x is not None and y is not None:
                await loop.run_in_executor(None, lambda: d.click(x, y))
                return {"tapped": True, "element_found": True}
        except Exception as exc:
            return {"tapped": False, "element_found": False, "error": str(exc)}

        return {"tapped": False, "element_found": False}

    async def input_text(
        self,
        device_id: str,
        text: str,
        clear_first: bool = True,
    ) -> dict:
        dev = self.devices.get(device_id)
        if not dev or not dev.connected:
            return {"success": False, "error": "Device not connected"}

        loop = asyncio.get_event_loop()
        try:
            d = dev._d
            if clear_first:
                await loop.run_in_executor(None, lambda: d.clear_text())
            await loop.run_in_executor(None, lambda: d.send_keys(text))
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def swipe(
        self,
        device_id: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration_ms: int = 300,
    ) -> dict:
        dev = self.devices.get(device_id)
        if not dev or not dev.connected:
            return {"success": False, "error": "Device not connected"}

        loop = asyncio.get_event_loop()
        try:
            d = dev._d
            await loop.run_in_executor(
                None,
                lambda: d.swipe(start_x, start_y, end_x, end_y, duration=duration_ms / 1000)
            )
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


###############################################################################
# CLI Entry Point
###############################################################################

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ZeroPoint CamNet Controller CLI")
    parser.add_argument("--config", default="/workspace/zeropoint/config/mcp_server_config.yaml")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Print device status")
    cap = sub.add_parser("capture", help="Trigger capture")
    cap.add_argument("--mode", choices=["photo", "screencap"], default="photo")
    cap.add_argument("--devices", nargs="*")

    syn = sub.add_parser("sync", help="Sync media from devices")
    syn.add_argument("--devices", nargs="*")
    syn.add_argument("--delete-after", action="store_true")

    args = parser.parse_args()

    async def main():
        ctrl = CamNetController.from_config(args.config)
        await ctrl.connect_all()

        if args.cmd == "status":
            result = await ctrl.status()
        elif args.cmd == "capture":
            results = await ctrl.capture_all(device_ids=args.devices, mode=args.mode)
            result = {"captures": [r.to_dict() for r in results]}
        elif args.cmd == "sync":
            result = await ctrl.sync_media(
                device_ids=args.devices,
                delete_after_sync=args.delete_after,
            )
        else:
            parser.print_help()
            return

        print(json.dumps(result, indent=2, default=str))

    asyncio.run(main())

