from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import Engine

from support_pilot.config import Settings


def configure_telemetry(app: FastAPI, engine: Engine, settings: Settings) -> bool:
    """Configure OTLP tracing and metrics once per application when explicitly enabled."""
    if not settings.otel_enabled or getattr(app.state, "telemetry_configured", False):
        return False
    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_metrics_endpoint)
            )
        ],
    )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
    app.state.telemetry_configured = True
    return True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("support_pilot")


def get_meter() -> metrics.Meter:
    return metrics.get_meter("support_pilot")


def record_agent_run(
    *,
    duration_ms: float,
    outcome: str,
    intent: str,
    provider: str,
    risk_level: str,
) -> None:
    meter = get_meter()
    attributes = {
        "outcome": outcome,
        "intent": intent,
        "provider": provider,
        "risk_level": risk_level,
    }
    meter.create_counter("support_pilot.agent.runs", unit="1").add(1, attributes)
    meter.create_histogram("support_pilot.agent.duration_ms", unit="ms").record(
        duration_ms, attributes
    )


def record_agent_resume(*, result: str, duration_ms: float) -> None:
    meter = get_meter()
    attributes = {"result": result}
    meter.create_counter("support_pilot.agent.resumes", unit="1").add(1, attributes)
    meter.create_histogram("support_pilot.agent.resume_duration_ms", unit="ms").record(
        duration_ms, attributes
    )


def record_rag_search(
    *,
    duration_ms: float,
    answerable: bool,
    reason: str,
    hit_count: int,
) -> None:
    attributes: dict[str, str | bool | int | float] = {
        "answerable": answerable,
        "reason": reason,
    }
    meter = get_meter()
    meter.create_counter("support_pilot.rag.searches", unit="1").add(1, attributes)
    meter.create_histogram("support_pilot.rag.search_duration_ms", unit="ms").record(
        duration_ms, attributes
    )
    meter.create_histogram("support_pilot.rag.hit_count", unit="1").record(
        hit_count, attributes
    )


def record_retention_prune(
    *,
    deleted_events: int,
    deleted_runs: int,
    deleted_threads: int,
    dry_run: bool,
) -> None:
    attributes: dict[str, str | bool | int | float] = {"dry_run": dry_run}
    meter = get_meter()
    meter.create_counter("support_pilot.retention.deleted_events", unit="1").add(
        deleted_events, attributes
    )
    meter.create_counter("support_pilot.retention.deleted_runs", unit="1").add(
        deleted_runs, attributes
    )
    meter.create_counter("support_pilot.retention.deleted_threads", unit="1").add(
        deleted_threads, attributes
    )
