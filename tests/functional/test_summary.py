import datetime as dt
import uuid

from sqlalchemy import event

from app.database import engine


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


async def test_summary_counts_mixed_tasks(client, make_project, make_task):
    project = await make_project()
    for status in ("pending", "pending", "in_progress", "done", "done", "done", "cancelled"):
        await make_task(project, status=status)
    r = await client.get(f"/api/v1/projects/{project.id}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == {
        "total": 7,
        "by_status": {"pending": 2, "in_progress": 1, "done": 3, "cancelled": 1},
        "overdue": 0,
    }


async def test_empty_project_summary(client, make_project):
    project = await make_project()
    r = await client.get(f"/api/v1/projects/{project.id}/summary")
    assert r.status_code == 200
    assert r.json()["data"] == {
        "total": 0,
        "by_status": {"pending": 0, "in_progress": 0, "done": 0, "cancelled": 0},
        "overdue": 0,
    }


async def test_overdue_rules_and_boundaries(client, make_project, make_task):
    project = await make_project()
    today = _today()
    yesterday = today - dt.timedelta(days=1)
    await make_task(project, status="pending", due_date=yesterday)
    await make_task(project, status="in_progress", due_date=yesterday)
    await make_task(project, status="pending", due_date=today)
    await make_task(project, status="pending", due_date=today + dt.timedelta(days=1))
    await make_task(project, status="pending", due_date=None)
    await make_task(project, status="done", due_date=yesterday)
    await make_task(project, status="cancelled", due_date=yesterday)
    r = await client.get(f"/api/v1/projects/{project.id}/summary")
    data = r.json()["data"]
    assert data["total"] == 7
    assert data["overdue"] == 2


async def test_summary_is_scoped_to_project(client, make_project, make_task):
    mine = await make_project()
    other = await make_project()
    await make_task(mine, status="pending")
    await make_task(other, status="pending", due_date=_today() - dt.timedelta(days=3))
    await make_task(other, status="done")
    data = (await client.get(f"/api/v1/projects/{mine.id}/summary")).json()["data"]
    assert data["total"] == 1
    assert data["by_status"]["pending"] == 1
    assert data["by_status"]["done"] == 0
    assert data["overdue"] == 0


async def test_summary_unknown_project_returns_404(client):
    r = await client.get(f"/api/v1/projects/{uuid.uuid4()}/summary")
    assert r.status_code == 404
    error = r.json()["error"]
    assert error["code"] == "PROJECT_NOT_FOUND"
    assert error["field"] == "project_id"


async def test_summary_malformed_project_id_returns_422(client):
    r = await client.get("/api/v1/projects/not-a-uuid/summary")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["field"] == "project_id"


async def test_summary_uses_constant_number_of_queries(client, make_project, make_task):
    small = await make_project()
    large = await make_project()
    for _ in range(3):
        await make_task(small)
    for _ in range(30):
        await make_task(large)

    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        r_small = await client.get(f"/api/v1/projects/{small.id}/summary")
        small_count = len(statements)
        statements.clear()
        r_large = await client.get(f"/api/v1/projects/{large.id}/summary")
        large_count = len(statements)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)

    assert r_small.json()["data"]["total"] == 3
    assert r_large.json()["data"]["total"] == 30
    assert small_count <= 2
    assert large_count <= 2
    assert small_count == large_count
