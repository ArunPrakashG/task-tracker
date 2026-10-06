import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import telemetry


@pytest.fixture
def span_exporter():
    telemetry.shutdown_tracing()
    exporter = InMemorySpanExporter()
    telemetry.configure_tracing(exporter=exporter)
    yield exporter
    telemetry.shutdown_tracing()


async def test_summary_emits_db_query_span(client, make_project, make_task, span_exporter):
    project = await make_project()
    await make_task(project, status="pending")
    r = await client.get(f"/api/v1/projects/{project.id}/summary")
    assert r.status_code == 200

    spans = {s.name: s for s in span_exporter.get_finished_spans()}
    assert "summary.db_query" in spans
    assert "projects.summary" in spans
    db_span = spans["summary.db_query"]
    duration = db_span.attributes["db.duration_ms"]
    assert isinstance(duration, float)
    assert duration >= 0
    assert db_span.parent is not None
    assert db_span.parent.span_id == spans["projects.summary"].context.span_id


async def test_disabled_telemetry_records_nothing(client, make_project, make_task):
    telemetry.shutdown_tracing()
    project = await make_project()
    await make_task(project, status="done")
    r = await client.get(f"/api/v1/projects/{project.id}/summary")
    assert r.status_code == 200
    assert r.json()["data"] == {
        "total": 1,
        "by_status": {"pending": 0, "in_progress": 0, "done": 1, "cancelled": 0},
        "overdue": 0,
    }

    # An exporter attached only afterwards sees nothing from the earlier call.
    exporter = InMemorySpanExporter()
    try:
        telemetry.configure_tracing(exporter=exporter)
        assert exporter.get_finished_spans() == ()
    finally:
        telemetry.shutdown_tracing()
