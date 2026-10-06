"""OpenTelemetry setup. Off by default; when disabled no spans are recorded."""

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

logger = logging.getLogger(__name__)

_TRACER_NAME = "task-tracker"
_provider: TracerProvider | None = None
_NOOP_TRACER = trace.NoOpTracer()


def _is_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "false").strip().lower() in {"true", "1", "yes"}


def _default_exporter() -> SpanExporter:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            return OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            logger.warning("OTLP exporter package not installed; falling back to console exporter")
    return ConsoleSpanExporter()


def configure_tracing(exporter: SpanExporter | None = None) -> TracerProvider:
    """Build a tracer provider kept in module state (not the OTel global)."""
    global _provider
    shutdown_tracing()
    provider = TracerProvider()
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(_default_exporter()))
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush and drop the configured provider; tracing becomes a no-op."""
    global _provider
    provider, _provider = _provider, None
    if provider is not None:
        provider.shutdown()


def get_tracer() -> trace.Tracer:
    if _provider is None:
        return _NOOP_TRACER
    return _provider.get_tracer(_TRACER_NAME)


def setup_telemetry(app) -> None:
    if _is_enabled():
        configure_tracing()
