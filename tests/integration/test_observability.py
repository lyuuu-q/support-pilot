from pathlib import Path

from fastapi.testclient import TestClient
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import UserAccount
from support_pilot.rag.ingestion import ingest_manifest
from support_pilot.rag.providers.deterministic import DeterministicEmbeddingProvider


def _headers(session: Session) -> dict[str, str]:
    user = session.scalar(select(UserAccount).where(UserAccount.role == "customer_developer"))
    assert user is not None
    return {"X-User-Id": str(user.id)}


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    if data is None:
        return set()
    return {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }


def test_agent_and_rag_emit_spans_and_metrics(
    client: TestClient,
    db_session: Session,
) -> None:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    reader = InMemoryMetricReader()
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    ingest_manifest(
        db_session,
        manifest_path=Path("data/knowledge/manifest.json"),
        embedding_provider=DeterministicEmbeddingProvider(),
    )

    response = client.post(
        "/api/v1/agent/resolve",
        headers=_headers(db_session),
        json={
            "message": "HTTP 429 响应里的 Retry-After 应该如何处理？",
            "context": {"product_version": "v2"},
        },
    )

    assert response.status_code == 200
    span_names = {span.name for span in span_exporter.get_finished_spans()}
    assert "agent.run" in span_names
    assert "rag.retrieval" in span_names
    metric_names = _metric_names(reader)
    assert "support_pilot.agent.runs" in metric_names
    assert "support_pilot.agent.duration_ms" in metric_names
    assert "support_pilot.rag.searches" in metric_names
