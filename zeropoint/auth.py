"""
Bearer-token authentication middleware for the ZeroPoint MCP WebSocket server.

Flow:
  1. Client connects and sends an MCP `initialize` request.
  2. Server validates the `Authorization: Bearer <token>` header before
     upgrading to WebSocket.  Connections without a valid token are
     rejected with HTTP 401.
  3. After the handshake the connection is trusted for its lifetime.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


###############################################################################
# Config
###############################################################################

@dataclass
class AuthConfig:
    enabled: bool = True
    method: str = "bearer_token"    # bearer_token | none
    token_env: str = "MCP_AUTH_TOKEN"
    rate_limit_per_minute: int = 120


###############################################################################
# BearerTokenAuth
###############################################################################

class BearerTokenAuth:
    """
    Validates bearer tokens for incoming MCP connections.

    Token is read once from the environment variable named in `token_env`.
    Comparison is constant-time to prevent timing attacks.
    """

    def __init__(self, cfg: AuthConfig):
        self.cfg = cfg
        self._token: str | None = None
        self._token_hash: bytes | None = None
        self._failed_attempts: dict[str, list[float]] = {}  # ip -> timestamps
        if cfg.enabled:
            self._load_token()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_token(self) -> None:
        raw = os.environ.get(self.cfg.token_env, "").strip()
        if not raw:
            logger.critical(
                "Auth is ENABLED but %s is not set. "
                "Set the env var or disable auth in config.",
                self.cfg.token_env,
            )
            raise RuntimeError(
                f"Missing required env var: {self.cfg.token_env}"
            )
        # Store hash only — never keep the plaintext in memory longer than needed
        self._token_hash = hashlib.sha256(raw.encode()).digest()
        logger.info("Auth token loaded from env var '%s'.", self.cfg.token_env)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_header(self, authorization: str | None, peer_ip: str = "unknown") -> bool:
        """
        Validate an HTTP `Authorization` header value.

        Args:
            authorization: Raw header value, e.g. "Bearer abc123".
            peer_ip:       Client IP for rate-limit tracking.

        Returns:
            True if the token is valid (or auth is disabled).
        """
        if not self.cfg.enabled:
            return True

        if not authorization:
            logger.warning("Auth: missing Authorization header from %s", peer_ip)
            return False

        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning("Auth: malformed Authorization header from %s", peer_ip)
            return False

        candidate = parts[1].strip()

        if self._is_rate_limited(peer_ip):
            logger.warning("Auth: rate limit exceeded for %s", peer_ip)
            return False

        candidate_hash = hashlib.sha256(candidate.encode()).digest()
        valid = hmac.compare_digest(candidate_hash, self._token_hash)  # type: ignore[arg-type]

        if not valid:
            self._record_failure(peer_ip)
            logger.warning("Auth: invalid token from %s", peer_ip)
        else:
            logger.debug("Auth: accepted connection from %s", peer_ip)

        return valid

    # ------------------------------------------------------------------
    # Rate limiting (simple sliding window)
    # ------------------------------------------------------------------

    def _is_rate_limited(self, ip: str) -> bool:
        now = time.monotonic()
        window = 60.0
        attempts = self._failed_attempts.get(ip, [])
        recent = [t for t in attempts if now - t < window]
        self._failed_attempts[ip] = recent
        limit = self.cfg.rate_limit_per_minute // 10  # 10% of normal limit for failures
        return len(recent) >= limit

    def _record_failure(self, ip: str) -> None:
        self._failed_attempts.setdefault(ip, []).append(time.monotonic())

    # ------------------------------------------------------------------
    # Token generation helper (used in dev_start.sh / first-run)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_token(length: int = 48) -> str:
        """Generate a cryptographically strong random bearer token."""
        return secrets.token_urlsafe(length)


###############################################################################
# Factory
###############################################################################

def build_auth(config: dict[str, Any]) -> BearerTokenAuth | None:
    """
    Build an auth handler from the server config dict.

    config: the `server.auth` block from mcp_server_config.yaml
    """
    auth_cfg = AuthConfig(
        enabled=config.get("enabled", True),
        method=config.get("method", "bearer_token"),
        token_env=config.get("token_env", "MCP_AUTH_TOKEN"),
    )
    if not auth_cfg.enabled:
        logger.info("Auth is DISABLED — all connections accepted.")
        return None
    return BearerTokenAuth(auth_cfg)

