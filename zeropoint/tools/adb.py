"""
AdbTool — Android Debug Bridge operations over TCP/USB.
Registered tool names: adb_shell, adb_push, adb_pull, adb_logcat,
                       adb_screencap, adb_install
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import time
from pathlib import Path
from typing import Any

from zeropoint.tools.base import BaseTool, ToolError, ToolResult


class AdbTool(BaseTool):
    name = "adb"
    module = "adb"
    description = "ADB shell, push/pull, logcat, screencap, and APK install."

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        self._adb_bin: str = self.config.get("adb_binary", "adb")
        self._server_host: str = self.config.get("adb_server_host", "127.0.0.1")
        self._server_port: int = self.config.get("adb_server_port", 5037)
        self._conn_timeout: int = self.config.get("connection_timeout_seconds", 10)
        self._cmd_timeout: int = self.config.get("command_timeout_seconds", 30)
        self._max_log: int = self.config.get("max_log_lines", 2000)
        self._perms: dict = self.config.get("permissions", {})

        # Static devices from config
        discovery = self.config.get("device_discovery", {})
        self._static_devices: list[str] = discovery.get("static_devices", [])

    async def startup(self) -> None:
        # Start ADB server if not running
        await self._run_adb(["start-server"], timeout=15, device=None)
        self._log.info("ADB server started at %s:%d", self._server_host, self._server_port)

    async def shutdown(self) -> None:
        pass  # Leave ADB server running between sessions

    # ------------------------------------------------------------------
    # ADB runner
    # ------------------------------------------------------------------

    async def _run_adb(
        self,
        args: list[str],
        device: str | None = None,
        timeout: int | None = None,
        stdin_data: bytes | None = None,
    ) -> tuple[str, str, int]:
        """
        Run an adb command asynchronously.
        Returns (stdout, stderr, returncode).
        """
        cmd = [self._adb_bin]
        if device:
            cmd += ["-s", device]
        cmd += ["-P", str(self._server_port)]
        cmd += args

        timeout_s = timeout or self._cmd_timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=timeout_s,
            )
            return (
                stdout_b.decode("utf-8", errors="replace").strip(),
                stderr_b.decode("utf-8", errors="replace").strip(),
                proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            raise ToolError(
                f"ADB command timed out after {timeout_s}s: {' '.join(args)}",
                code="ADB_TIMEOUT",
            )
        except FileNotFoundError:
            raise ToolError(
                f"ADB binary not found at '{self._adb_bin}'. Is it installed?",
                code="ADB_NOT_FOUND",
            )

    def _require_perm(self, perm: str) -> None:
        if not self._perms.get(perm, True):
            raise ToolError(
                f"Permission '{perm}' is disabled in config.",
                code="PERMISSION_DENIED",
            )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        op = params.pop("_op", "shell")
        dispatch = {
            "shell": self._shell,
            "push": self._push,
            "pull": self._pull,
            "logcat": self._logcat,
            "screencap": self._screencap,
            "install": self._install,
        }
        handler = dispatch.get(op)
        if handler is None:
            raise ToolError(f"Unknown ADB operation: '{op}'", code="UNKNOWN_OP")
        return await handler(params)

    # ------------------------------------------------------------------
    # adb_shell
    # ------------------------------------------------------------------

    async def _shell(self, params: dict) -> ToolResult:
        self.require(params, "command")
        self._require_perm("shell")
        device = params.get("device_id")
        command: str = params["command"]
        as_root: bool = params.get("as_root", False)

        if as_root:
            self._require_perm("root")
            command = f"su -c '{command}'"

        stdout, stderr, rc = await self._run_adb(
            ["shell", command],
            device=device,
            timeout=params.get("timeout_seconds", self._cmd_timeout),
        )
        return ToolResult(data={
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": rc,
            "device_serial": device or "auto",
        })

    # ------------------------------------------------------------------
    # adb_push
    # ------------------------------------------------------------------

    async def _push(self, params: dict) -> ToolResult:
        self.require(params, "local_path", "remote_path")
        self._require_perm("push_pull")
        device = params.get("device_id")
        local = params["local_path"]
        remote = params["remote_path"]

        if not Path(local).exists():
            raise ToolError(f"Local file not found: '{local}'", code="NOT_FOUND")

        stdout, stderr, rc = await self._run_adb(
            ["push", local, remote], device=device
        )
        if rc != 0:
            raise ToolError(f"ADB push failed: {stderr}", code="ADB_ERROR")

        # Parse bytes from adb output (e.g. "1 file pushed, 0 skipped. 45.1 MB/s (102400 bytes in 0.002s)")
        bytes_tx = _parse_bytes_transferred(stdout)
        return ToolResult(data={"bytes_transferred": bytes_tx, "remote_path": remote})

    # ------------------------------------------------------------------
    # adb_pull
    # ------------------------------------------------------------------

    async def _pull(self, params: dict) -> ToolResult:
        self.require(params, "remote_path", "local_path")
        self._require_perm("push_pull")
        device = params.get("device_id")
        remote = params["remote_path"]
        local = params["local_path"]

        Path(local).parent.mkdir(parents=True, exist_ok=True)
        stdout, stderr, rc = await self._run_adb(
            ["pull", remote, local], device=device
        )
        if rc != 0:
            raise ToolError(f"ADB pull failed: {stderr}", code="ADB_ERROR")

        bytes_tx = _parse_bytes_transferred(stdout)
        return ToolResult(data={"bytes_transferred": bytes_tx, "local_path": local})

    # ------------------------------------------------------------------
    # adb_logcat
    # ------------------------------------------------------------------

    async def _logcat(self, params: dict) -> ToolResult:
        device = params.get("device_id")
        filt: str = params.get("filter", "*:D")
        lines: int = min(params.get("lines", 500), self._max_log)
        timeout: int = params.get("timeout_seconds", 10)

        stdout, stderr, rc = await self._run_adb(
            ["logcat", "-d", "-t", str(lines), filt],
            device=device,
            timeout=timeout + 5,
        )
        log_lines = stdout.splitlines()
        return ToolResult(data={
            "log": stdout,
            "line_count": len(log_lines),
            "device_serial": device or "auto",
        })

    # ------------------------------------------------------------------
    # adb_screencap
    # ------------------------------------------------------------------

    async def _screencap(self, params: dict) -> ToolResult:
        device = params.get("device_id")
        ts = int(time.time())
        save_path: str = params.get(
            "save_path",
            f"/tmp/mcp_scratch/screencap_{device or 'device'}_{ts}.png",
        )
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        # Pull raw PNG bytes via exec-out for speed
        cmd = [self._adb_bin]
        if device:
            cmd += ["-s", device]
        cmd += ["-P", str(self._server_port), "exec-out", "screencap", "-p"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            raw, err = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            raise ToolError("Screencap timed out.", code="ADB_TIMEOUT")

        if proc.returncode != 0 or not raw:
            raise ToolError(
                f"Screencap failed: {err.decode(errors='replace')}",
                code="ADB_ERROR",
            )

        Path(save_path).write_bytes(raw)

        # Detect dimensions from PNG header
        width = height = 0
        if raw[:4] == b"\x89PNG" and len(raw) >= 24:
            import struct
            width = struct.unpack(">I", raw[16:20])[0]
            height = struct.unpack(">I", raw[20:24])[0]

        return ToolResult(data={
            "local_path": save_path,
            "width": width,
            "height": height,
            "size_bytes": len(raw),
        })

    # ------------------------------------------------------------------
    # adb_install
    # ------------------------------------------------------------------

    async def _install(self, params: dict) -> ToolResult:
        self.require(params, "apk_path")
        self._require_perm("install_apk")
        device = params.get("device_id")
        apk = params["apk_path"]
        grant: bool = params.get("grant_permissions", True)
        replace: bool = params.get("replace_existing", True)

        if not Path(apk).exists():
            raise ToolError(f"APK not found: '{apk}'", code="NOT_FOUND")

        args = ["install"]
        if grant:
            args.append("-g")
        if replace:
            args.append("-r")
        args.append(apk)

        stdout, stderr, rc = await self._run_adb(args, device=device, timeout=120)
        success = rc == 0 and "Success" in stdout

        # Extract package name from aapt if available
        pkg = ""
        try:
            aapt = await asyncio.create_subprocess_exec(
                "aapt", "dump", "badging", apk,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await aapt.communicate()
            for line in out.decode(errors="replace").splitlines():
                if line.startswith("package:"):
                    import re
                    m = re.search(r"name='([^']+)'", line)
                    if m:
                        pkg = m.group(1)
                    break
        except Exception:
            pkg = Path(apk).stem

        return ToolResult(data={
            "success": success,
            "package_name": pkg,
            "output": stdout,
            "device_serial": device or "auto",
        })


###############################################################################
# Helpers
###############################################################################

def _parse_bytes_transferred(adb_output: str) -> int:
    import re
    m = re.search(r"\((\d+)\s+bytes", adb_output)
    return int(m.group(1)) if m else 0

