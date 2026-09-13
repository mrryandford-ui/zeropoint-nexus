"""Unit tests for bearer-token authentication and rate limiting."""

from __future__ import annotations

import time

from zeropoint.auth import AuthConfig, BearerTokenAuth


def _auth(monkeypatch, rate_limit_per_minute: int = 120) -> BearerTokenAuth:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
    cfg = AuthConfig(enabled=True, rate_limit_per_minute=rate_limit_per_minute)
    return BearerTokenAuth(cfg)


def test_rate_limit_triggers_after_threshold(monkeypatch):
    auth = _auth(monkeypatch, rate_limit_per_minute=20)

    assert auth.validate_header("Bearer wrong", "192.0.2.1") is False
    assert auth.validate_header("Bearer wrong", "192.0.2.1") is False
    assert auth.validate_header("Bearer test-token", "192.0.2.1") is False
    assert len(auth._failed_attempts["192.0.2.1"]) == 2


def test_stale_entry_removed_when_ip_revisited(monkeypatch):
    auth = _auth(monkeypatch)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    auth._record_failure("192.0.2.2")

    monkeypatch.setattr(time, "monotonic", lambda: 61.0)
    assert auth._is_rate_limited("192.0.2.2") is False
    assert "192.0.2.2" not in auth._failed_attempts


def test_sweep_triggers_after_interval(monkeypatch):
    auth = _auth(monkeypatch)
    monkeypatch.setattr(auth, "_SWEEP_INTERVAL", 3)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    auth._record_failure("192.0.2.3")
    auth._record_failure("192.0.2.4")

    monkeypatch.setattr(time, "monotonic", lambda: 61.0)
    auth._record_failure("192.0.2.5")

    assert "192.0.2.3" not in auth._failed_attempts
    assert "192.0.2.4" not in auth._failed_attempts
    assert "192.0.2.5" in auth._failed_attempts


def test_hard_cap_evicts_oldest(monkeypatch):
    auth = _auth(monkeypatch)
    monkeypatch.setattr(auth, "_MAX_TRACKED_IPS", 3)
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    auth._failed_attempts = {
        "192.0.2.10": [90.0],
        "192.0.2.11": [91.0],
        "192.0.2.12": [92.0],
        "192.0.2.13": [93.0],
    }

    auth._sweep_stale_entries()

    assert len(auth._failed_attempts) == 3
    assert "192.0.2.10" not in auth._failed_attempts
    assert set(auth._failed_attempts) == {
        "192.0.2.11",
        "192.0.2.12",
        "192.0.2.13",
    }


def test_valid_token_accepted(monkeypatch):
    auth = _auth(monkeypatch)

    assert auth.validate_header("Bearer test-token", "192.0.2.20") is True


def test_disabled_auth_always_passes():
    auth = BearerTokenAuth(AuthConfig(enabled=False))

    assert auth.validate_header(None, "192.0.2.21") is True
    assert auth.validate_header("not-a-token", "192.0.2.21") is True
