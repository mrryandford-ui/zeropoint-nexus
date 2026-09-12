"""
ZeroPoint Device Recovery Workflow
Automated Android device recovery: bootloop, bricked state, factory reset,
ADB recovery mode, and sideload operations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger("zeropoint.device_recovery")


class DeviceState(str, Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    BOOTLOOP = "bootloop"
    FASTBOOT = "fastboot"
    RECOVERY = "recovery"
    SIDELOAD = "sideload"
    BRICKED = "bricked"


@dataclass
class RecoveryStep:
    name: str
    description: str
    success: bool = False
    output: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RecoverySession:
    session_id: str
    device_serial: str
    initial_state: DeviceState
    target_state: DeviceState
    steps: list[RecoveryStep] = field(default_factory=list)
    completed: bool = False
    success: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    def add_step(
        self, name: str, description: str, success: bool, output: str = ""
    ) -> RecoveryStep:
        step = RecoveryStep(name=name, description=description, success=success, output=output)
        self.steps.append(step)
        logger.info("[%s] Step '%s': %s", self.session_id, name, "✓" if success else "✗")
        return step

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "device_serial": self.device_serial,
            "initial_state": self.initial_state,
            "target_state": self.target_state,
            "completed": self.completed,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "success": s.success,
                    "output": s.output[:500],
                    "timestamp": s.timestamp.isoformat(),
                }
                for s in self.steps
            ],
        }


class DeviceRecoveryWorkflow:
    """
    Orchestrates Android device recovery workflows via ADB + fastboot.

    Supported workflows:
      - soft_reset:       Reboot device normally
      - recovery_mode:    Boot to recovery, optionally wipe + reformat
      - fastboot_mode:    Boot to fastboot for image flashing
      - sideload_ota:     Sideload an OTA zip via ADB sideload
      - factory_reset:    Wipe data via recovery
      - adb_reconnect:    Disconnect, kill-server, restart, reconnect
    """

    def __init__(self):
        self._sessions: dict[str, RecoverySession] = {}
        self._counter = 0

    # ------------------------------------------------------------------
    # ADB / fastboot runners
    # ------------------------------------------------------------------

    async def _adb(
        self, args: list[str], serial: str | None = None, timeout: int = 30
    ) -> tuple[str, int]:
        cmd = ["adb"]
        if serial:
            cmd += ["-s", serial]
        cmd += args
        return await self._run(cmd, timeout)

    async def _fastboot(
        self, args: list[str], serial: str | None = None, timeout: int = 60
    ) -> tuple[str, int]:
        cmd = ["fastboot"]
        if serial:
            cmd += ["-s", serial]
        cmd += args
        return await self._run(cmd, timeout)

    @staticmethod
    async def _run(cmd: list[str], timeout: int) -> tuple[str, int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return out.decode(errors="replace").strip(), proc.returncode or 0
        except TimeoutError:
            return f"Command timed out after {timeout}s: {' '.join(cmd)}", -1
        except Exception as exc:
            return str(exc), -1

    # ------------------------------------------------------------------
    # Device state detection
    # ------------------------------------------------------------------

    async def detect_state(self, serial: str) -> DeviceState:
        # Check ADB
        out, rc = await self._adb(["get-state"], serial=serial, timeout=5)
        if rc == 0:
            state_map = {
                "device": DeviceState.ONLINE,
                "recovery": DeviceState.RECOVERY,
                "sideload": DeviceState.SIDELOAD,
                "bootloader": DeviceState.FASTBOOT,
            }
            return state_map.get(out.strip(), DeviceState.UNKNOWN)

        # Check fastboot
        out, rc = await self._fastboot(["devices"], timeout=5)
        if serial in out:
            return DeviceState.FASTBOOT

        return DeviceState.OFFLINE

    # ------------------------------------------------------------------
    # Session factory
    # ------------------------------------------------------------------

    def _new_session(
        self, serial: str, initial: DeviceState, target: DeviceState
    ) -> RecoverySession:
        self._counter += 1
        sid = f"REC-{self._counter:04d}"
        session = RecoverySession(sid, serial, initial, target)
        self._sessions[sid] = session
        return session

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    async def soft_reset(self, serial: str) -> RecoverySession:
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.ONLINE)

        out, rc = await self._adb(["reboot"], serial=serial)
        session.add_step("reboot", "Soft reboot via ADB", rc == 0, out)

        await asyncio.sleep(5)
        for _ in range(12):  # wait up to 60s
            new_state = await self.detect_state(serial)
            if new_state == DeviceState.ONLINE:
                break
            await asyncio.sleep(5)

        session.success = (await self.detect_state(serial)) == DeviceState.ONLINE
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    async def reboot_to_recovery(self, serial: str) -> RecoverySession:
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.RECOVERY)

        out, rc = await self._adb(["reboot", "recovery"], serial=serial)
        session.add_step("reboot_recovery", "Rebooting to recovery mode", rc == 0, out)

        await asyncio.sleep(8)
        new_state = await self.detect_state(serial)
        session.add_step(
            "verify_recovery",
            "Verifying recovery mode",
            new_state == DeviceState.RECOVERY,
            f"State: {new_state}",
        )
        session.success = new_state == DeviceState.RECOVERY
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    async def reboot_to_fastboot(self, serial: str) -> RecoverySession:
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.FASTBOOT)

        if state == DeviceState.ONLINE:
            out, rc = await self._adb(["reboot", "bootloader"], serial=serial)
            session.add_step("reboot_bootloader", "Rebooting to bootloader via ADB", rc == 0, out)
        else:
            # Try fastboot reboot-bootloader
            out, rc = await self._fastboot(["reboot-bootloader"], serial=serial)
            session.add_step("fastboot_reboot", "Fastboot reboot to bootloader", rc == 0, out)

        await asyncio.sleep(6)
        new_state = await self.detect_state(serial)
        session.success = new_state == DeviceState.FASTBOOT
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    async def sideload_ota(self, serial: str, ota_zip_path: str) -> RecoverySession:
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.ONLINE)

        if not Path(ota_zip_path).exists():
            session.add_step(
                "check_ota", "Verify OTA zip exists", False, f"Not found: {ota_zip_path}"
            )
            session.completed = True
            return session

        # Get to sideload mode
        if state != DeviceState.SIDELOAD:
            out, rc = await self._adb(["reboot", "sideload"], serial=serial)
            session.add_step("enter_sideload", "Entering ADB sideload mode", rc == 0, out)
            await asyncio.sleep(8)

        out, rc = await self._adb(["sideload", ota_zip_path], serial=serial, timeout=300)
        session.add_step("sideload_ota", f"Sideloading {Path(ota_zip_path).name}", rc == 0, out)

        await asyncio.sleep(5)
        out, rc = await self._adb(["reboot"], serial=serial)
        session.add_step("reboot_after_ota", "Rebooting after OTA", rc == 0, out)

        session.success = rc == 0
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    async def factory_reset(self, serial: str, confirmed: bool = False) -> RecoverySession:
        """⚠ DESTRUCTIVE — wipes all user data. confirmed=True required."""
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.ONLINE)

        if not confirmed:
            session.add_step(
                "safety_gate",
                "Factory reset requires confirmed=True",
                False,
                "Aborted — confirmation not given.",
            )
            session.completed = True
            return session

        # Boot to recovery first
        if state != DeviceState.RECOVERY:
            out, rc = await self._adb(["reboot", "recovery"], serial=serial)
            session.add_step("reboot_recovery", "Boot to recovery", rc == 0, out)
            await asyncio.sleep(10)

        # Issue wipe commands via ADB in recovery
        for cmd_args, label in [
            (["shell", "recovery", "--wipe_data"], "Wipe data partition"),
            (["shell", "recovery", "--wipe_cache"], "Wipe cache partition"),
        ]:
            out, rc = await self._adb(cmd_args, serial=serial, timeout=120)
            session.add_step(label.lower().replace(" ", "_"), label, rc == 0, out)

        out, rc = await self._adb(["reboot"], serial=serial)
        session.add_step("reboot_final", "Final reboot after wipe", rc == 0, out)

        session.success = rc == 0
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    async def adb_reconnect(self, serial: str) -> RecoverySession:
        """Full ADB reconnect: disconnect, kill-server, start-server, connect."""
        state = await self.detect_state(serial)
        session = self._new_session(serial, state, DeviceState.ONLINE)

        steps = [
            (["disconnect", serial], "Disconnect device"),
            (["kill-server"], "Kill ADB server"),
            (["start-server"], "Start ADB server"),
            (["connect", serial], "Reconnect device"),
        ]
        for args, label in steps:
            out, rc = await self._adb(args, timeout=15)
            session.add_step(label.lower().replace(" ", "_"), label, rc == 0, out)
            await asyncio.sleep(1)

        await asyncio.sleep(3)
        final_state = await self.detect_state(serial)
        session.success = final_state == DeviceState.ONLINE
        session.completed = True
        session.finished_at = datetime.now(UTC)
        return session

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> dict | None:
        s = self._sessions.get(session_id)
        return s.to_dict() if s else None

    def list_sessions(self) -> list[dict]:
        return [
            s.to_dict()
            for s in sorted(self._sessions.values(), key=lambda s: s.started_at, reverse=True)
        ]
