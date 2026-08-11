"""
ZeroPoint Observability — Prometheus metrics + OpenTelemetry tracing.
Call init_observability() once at server startup.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("zeropoint.observability")

# ---------------------------------------------------------------------------
# Prometheus metrics (optional — graceful fallback if not installed)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False

_tool_calls_total: Any = None
_tool_errors_total: Any = None
_tool_latency: Any = None
_active_connections: Any = None


def _init_prometheus(port: int, path: str) -> None:
    global _tool_calls_total, _tool_errors_total, _tool_latency, _active_connections
    if not _PROM_AVAILABLE:
        logger.warning("prometheus_client not installed — metrics disabled.")
        return

    _tool_calls_total = Counter(
        "zeropoint_tool_calls_total",
        "Total MCP tool invocations",
        ["tool_name", "status"],
    )
    _tool_errors_total = Counter(
        "zeropoint_tool_errors_total",
        "Total MCP tool errors",
        ["tool_name", "error_code"],
    )
    _tool_latency = Histogram(
        "zeropoint_tool_latency_seconds",
        "MCP tool execution latency",
        ["tool_name"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    _active_connections = Gauge(
        "zeropoint_active_connections",
        "Currently active WebSocket connections",
    )

    start_http_server(port)
    logger.info("Prometheus metrics serving on :%d%s", port, path)


# ---------------------------------------------------------------------------
# OpenTelemetry tracing (optional)
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

_tracer: Any = None


def _init_tracing(endpoint: str) -> None:
    global _tracer
    if not _OTEL_AVAILABLE:
        logger.warning("opentelemetry not installed — tracing disabled.")
        return

    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("zeropoint.mcp")
    logger.info("OpenTelemetry tracing → %s", endpoint)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_observability(cfg: dict[str, Any]) -> None:
    """Initialize metrics and tracing from the observability config block."""
    metrics_cfg = cfg.get("metrics", {})
    if metrics_cfg.get("enabled", False):
        _init_prometheus(
            port=metrics_cfg.get("port", 9090),
            path=metrics_cfg.get("path", "/metrics"),
        )

    tracing_cfg = cfg.get("tracing", {})
    if tracing_cfg.get("enabled", False):
        _init_tracing(endpoint=tracing_cfg.get("endpoint", "http://localhost:4317"))


def record_tool_call(tool_name: str, success: bool, latency_s: float = 0.0) -> None:
    """Record a completed tool call in Prometheus."""
    status = "success" if success else "error"
    if _tool_calls_total is not None:
        _tool_calls_total.labels(tool_name=tool_name, status=status).inc()
    if _tool_latency is not None and latency_s > 0:
        _tool_latency.labels(tool_name=tool_name).observe(latency_s)


def record_tool_error(tool_name: str, error_code: str) -> None:
    if _tool_errors_total is not None:
        _tool_errors_total.labels(tool_name=tool_name, error_code=error_code).inc()


def connection_opened() -> None:
    if _active_connections is not None:
        _active_connections.inc()


def connection_closed() -> None:
    if _active_connections is not None:
        _active_connections.dec()


class traced:
    """Context manager / decorator that wraps a block in an OTEL span."""

    def __init__(self, name: str, attributes: dict | None = None):
        self.name = name
        self.attributes = attributes or {}
        self._span = None

    def __enter__(self):
        if _tracer:
            self._span = _tracer.start_span(self.name)
            for k, v in self.attributes.items():
                self._span.set_attribute(k, str(v))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_type:
                self._span.record_exception(exc_val)
            self._span.end()
        return False

