"""
FilesystemTool — sandboxed local filesystem read/write/list operations.
Registered tool names: filesystem_read, filesystem_write, filesystem_list
"""

from __future__ import annotations

import base64
import fnmatch
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from zeropoint.tools.base import BaseTool, ToolError, ToolResult


class FilesystemTool(BaseTool):
    name = "filesystem"
    module = "filesystem"
    description = "Read, write, and list sandboxed local filesystem paths."

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        raw_roots: list[str] = self.config.get("allowed_roots", [])
        if not raw_roots:
            raw_roots = [str(Path.cwd())]

        include_ollama_roots = self.config.get("include_ollama_model_roots", True)
        ollama_roots = self._detect_ollama_roots() if include_ollama_roots else []

        read_raw = self.config.get("read_allowed_roots", raw_roots + ollama_roots)
        write_raw = self.config.get("write_allowed_roots", raw_roots)
        list_raw = self.config.get("list_allowed_roots", read_raw)

        self._read_roots: list[Path] = [Path(r).resolve() for r in read_raw]
        self._write_roots: list[Path] = [Path(r).resolve() for r in write_raw]
        self._list_roots: list[Path] = [Path(r).resolve() for r in list_raw]

        self._deny: list[str] = self.config.get("deny_patterns", [])
        self._max_bytes: int = self.config.get("max_file_size_mb", 256) * 1024 * 1024
        self._allow_symlinks: bool = self.config.get("allow_symlinks", False)
        self._allow_write: bool = self.config.get("allow_write", True)

        access = self.config.get("access_control", {})
        if not access:
            access = self._load_access_from_governance()
        self._rbac_enabled: bool = access.get("enabled", False)
        self._default_role: str = str(access.get("default_role", "owner")).strip().lower()
        self._read_roles: set[str] = {str(x).strip().lower() for x in access.get("read_roles", [])}
        self._list_roles: set[str] = {str(x).strip().lower() for x in access.get("list_roles", [])}
        self._write_roles: set[str] = {str(x).strip().lower() for x in access.get("write_roles", [])}

        if not self._read_roots or not self._list_roots:
            raise RuntimeError("filesystem: read/list allowed roots must not be empty")

    def _detect_ollama_roots(self) -> list[str]:
        roots: list[str] = []
        from_env = os.environ.get("OLLAMA_MODELS")
        if from_env:
            roots.append(from_env)

        home = Path.home()
        roots.extend([
            str(home / ".ollama" / "models"),
            "/var/lib/ollama",
            "/usr/share/ollama/.ollama/models",
        ])

        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            roots.append(str(Path(user_profile) / ".ollama" / "models"))
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            roots.append(str(Path(local_app_data) / "Ollama" / "models"))
        return roots

    def _load_access_from_governance(self) -> dict[str, Any]:
        gov_path = Path(__file__).resolve().parents[2] / "governance.json"
        if not gov_path.exists():
            return {}
        try:
            payload = json.loads(gov_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        fs_roles = payload.get("access_control", {}).get("filesystem_roles", {})
        if not fs_roles:
            return {}
        return {
            "enabled": True,
            "default_role": "owner",
            "read_roles": fs_roles.get("read", []),
            "list_roles": fs_roles.get("list", []),
            "write_roles": fs_roles.get("write", []),
        }

    # ------------------------------------------------------------------
    # Guard
    # ------------------------------------------------------------------

    def _check_path(self, path_str: str, allowed_roots: list[Path]) -> Path:
        """Resolve and validate a path against allowed roots and deny list."""
        p = Path(path_str).resolve()

        in_root = any(p == root or p.is_relative_to(root) for root in allowed_roots)
        if not in_root:
            raise ToolError(
                f"Path '{p}' is outside allowed roots: {[str(r) for r in allowed_roots]}",
                code="PATH_DENIED",
            )

        # Symlink check
        if not self._allow_symlinks and p.is_symlink():
            raise ToolError(f"Symlinks are not allowed: '{p}'", code="SYMLINK_DENIED")

        # Deny-pattern check
        rel = str(p)
        for pat in self._deny:
            if fnmatch.fnmatch(rel, pat):
                raise ToolError(
                    f"Path '{p}' matches deny pattern '{pat}'",
                    code="PATH_DENIED",
                )
        return p

    def _check_role(self, params: dict[str, Any], op: str) -> None:
        if not self._rbac_enabled:
            return

        role = str(params.get("_requester_role", self._default_role)).strip().lower()
        if op == "read":
            allowed = self._read_roles
        elif op == "list":
            allowed = self._list_roles
        else:
            allowed = self._write_roles

        if allowed and role not in allowed:
            raise ToolError(
                f"Role '{role}' is not allowed to perform filesystem {op}. Allowed roles: {sorted(allowed)}",
                code="ROLE_DENIED",
            )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        # Dispatch on the registered tool name embedded by the registry
        op = params.pop("_op", "read")
        if op == "write":
            return await self._write(params)
        elif op == "list":
            return await self._list(params)
        else:
            return await self._read(params)

    # ------------------------------------------------------------------
    # filesystem_read
    # ------------------------------------------------------------------

    async def _read(self, params: dict) -> ToolResult:
        self.require(params, "path")
        self._check_role(params, "read")
        p = self._check_path(params["path"], self._read_roots)

        if not p.exists():
            raise ToolError(f"Path does not exist: '{p}'", code="NOT_FOUND")
        if not p.is_file():
            raise ToolError(f"Path is not a file: '{p}'", code="NOT_A_FILE")
        if p.stat().st_size > self._max_bytes:
            raise ToolError(
                f"File exceeds max size ({self._max_bytes // 1024 // 1024} MB): '{p}'",
                code="FILE_TOO_LARGE",
            )

        encoding: str = params.get("encoding", "auto")
        mime, _ = mimetypes.guess_type(str(p))
        is_text = (mime or "").startswith("text/") or p.suffix in {
            ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".sh",
            ".cfg", ".ini", ".toml", ".xml", ".html", ".css", ".txt", ".env",
        }

        if encoding == "base64" or (encoding == "auto" and not is_text):
            content = base64.b64encode(p.read_bytes()).decode()
            enc_used = "base64"
        else:
            raw = p.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            start = params.get("start_line")
            end = params.get("end_line")
            lines = text.splitlines(keepends=True)
            if start or end:
                s = (start or 1) - 1
                e = end or len(lines)
                lines = lines[s:e]
                text = "".join(lines)
            content = text
            enc_used = "utf-8"

        return ToolResult(data={
            "content": content,
            "size_bytes": p.stat().st_size,
            "mime_type": mime or "application/octet-stream",
            "encoding": enc_used,
            "line_count": content.count("\n") if enc_used == "utf-8" else None,
        })

    # ------------------------------------------------------------------
    # filesystem_write
    # ------------------------------------------------------------------

    async def _write(self, params: dict) -> ToolResult:
        self.require(params, "path", "content")
        self._check_role(params, "write")
        if not self._allow_write:
            raise ToolError("Filesystem writes are disabled by policy.", code="WRITE_DISABLED")
        p = self._check_path(params["path"], self._write_roots)
        mode: str = params.get("mode", "overwrite")
        encoding: str = params.get("encoding", "utf-8")

        p.parent.mkdir(parents=True, exist_ok=True)

        if mode == "create_new" and p.exists():
            raise ToolError(
                f"File already exists (mode=create_new): '{p}'",
                code="FILE_EXISTS",
            )

        content_str: str = params["content"]
        if encoding == "base64":
            raw = base64.b64decode(content_str)
        else:
            raw = content_str.encode("utf-8")

        if mode == "append":
            with open(p, "ab") as fh:
                fh.write(raw)
        else:
            p.write_bytes(raw)

        return ToolResult(data={"bytes_written": len(raw), "path": str(p)})

    # ------------------------------------------------------------------
    # filesystem_list
    # ------------------------------------------------------------------

    async def _list(self, params: dict) -> ToolResult:
        self.require(params, "path")
        self._check_role(params, "list")
        p = self._check_path(params["path"], self._list_roots)

        if not p.exists():
            raise ToolError(f"Path does not exist: '{p}'", code="NOT_FOUND")
        if not p.is_dir():
            raise ToolError(f"Path is not a directory: '{p}'", code="NOT_A_DIR")

        pattern: str = params.get("pattern", "*")
        recursive: bool = params.get("recursive", False)
        include_hidden: bool = params.get("include_hidden", False)

        entries = []
        glob_fn = p.rglob if recursive else p.glob
        for entry in sorted(glob_fn(pattern)):
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "dir" if entry.is_dir() else ("symlink" if entry.is_symlink() else "file"),
                    "size_bytes": stat.st_size if entry.is_file() else None,
                    "modified_at": __import__("datetime").datetime.fromtimestamp(
                        stat.st_mtime, tz=__import__("datetime").timezone.utc
                    ).isoformat(),
                })
            except OSError:
                continue

        return ToolResult(data={"entries": entries, "count": len(entries)})
