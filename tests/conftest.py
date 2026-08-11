"""
ZeroPoint pytest configuration — shared fixtures and settings.
"""
import pytest
import asyncio
import sys
from pathlib import Path

# Ensure the repo root is always on the path
sys.path.insert(0, str(Path(__file__).parents[1]))


# ── Event loop (required for pytest-asyncio) ───────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Shared tmp workspace ───────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def workspace(tmp_path):
    """A clean tmp directory pre-structured as a ZeroPoint workspace."""
    (tmp_path / "config").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "tasks" / "pending").mkdir(parents=True)
    (tmp_path / "tasks" / "running").mkdir(parents=True)
    (tmp_path / "tasks" / "completed").mkdir(parents=True)
    return tmp_path


# ── Minimal tool configs ───────────────────────────────────────────────────────
@pytest.fixture
def fs_config(tmp_path):
    return {
        "allowed_roots": [str(tmp_path)],
        "deny_patterns": ["**/*.key", "**/secrets/**"],
        "max_file_size_mb": 1,
        "allow_symlinks": False,
        "sandbox_mode": True,
    }


@pytest.fixture
def webtools_config():
    return {
        "allowed_domains": [],
        "blocked_domains": ["*.onion", "localhost", "127.0.0.1"],
        "timeout_seconds": 5,
        "max_response_size_mb": 1,
        "follow_redirects": True,
        "max_redirects": 3,
        "user_agent": "ZeroPoint-Test/1.0",
        "rate_limit": {"requests_per_minute": 120, "burst": 20},
    }


@pytest.fixture
def adb_config():
    return {
        "adb_binary": "adb",
        "adb_server_host": "127.0.0.1",
        "adb_server_port": 5037,
        "connection_timeout_seconds": 5,
        "command_timeout_seconds": 10,
        "max_log_lines": 200,
        "device_discovery": {"mode": "auto", "static_devices": []},
        "permissions": {
            "shell": True,
            "push_pull": True,
            "install_apk": True,
            "reboot": False,
            "root": False,
        },
    }
