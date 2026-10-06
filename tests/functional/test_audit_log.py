import asyncio
import time
import uuid
from types import SimpleNamespace

from sqlalchemy import select

from app.main import app
from app.models.audit import TaskAuditLog
from app.services import audit_service


async def _rows(db_session, task_id):
    result = await db_session.execute(
        select(TaskAuditLog)
        .where(TaskAuditLog.task_id == uuid.UUID(str(task_id)))
        .execution_options(populate_existing=True)
    )
    return list(result.scalars())


async def _wait_for_rows(db_session, task_id, wait=2.0):
    deadline = time.monotonic() + wait
    while True:
        rows = await _rows(db_session, task_id)
        if rows or time.monotonic() > deadline:
            return rows
        await asyncio.sleep(0.05)


async def _setup(make_project, make_task):
    project = await make_project()
    project_id = project.id
    task = await make_task(project)
    task_id = task.id
    return SimpleNamespace(id=project_id), SimpleNamespace(id=task_id)


async def test_status_change_writes_audit_row(client, db_session, make_project, make_task):
    project, task = await _setup(make_project, make_task)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "in_progress"})
    assert r.status_code == 200
    rows = await _wait_for_rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].from_status.value == "pending"
    assert rows[0].to_status.value == "in_progress"
    assert rows[0].project_id == project.id


async def test_rejected_transition_writes_no_audit_row(client, db_session, make_project, make_task):
    _, task = await _setup(make_project, make_task)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "done"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    await asyncio.sleep(0.3)
    assert await _rows(db_session, task.id) == []


async def test_response_does_not_wait_for_audit_write(
    client, db_session, make_project, make_task, monkeypatch
):
    """httpx's ASGITransport awaits the whole ASGI call, background tasks included, so
    client-side timing cannot show this. Drive the ASGI app directly and record the order
    of events: the final response body must be sent while the slowed write is unfinished."""
    _, task = await _setup(make_project, make_task)
    original = audit_service.record_status_change
    events: list[str] = []

    async def slow(session, payload):
        events.append("write_started")
        await asyncio.sleep(0.5)
        await original(session, payload)
        events.append("write_done")

    monkeypatch.setattr(audit_service, "record_status_change", slow)

    status = None
    body = b""

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b'{"status": "in_progress"}'}
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status, body
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")
            if not message.get("more_body", False):
                events.append("response_sent")

    sent_request = False
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PATCH",
        "scheme": "http",
        "path": f"/api/v1/tasks/{task.id}/status",
        "raw_path": f"/api/v1/tasks/{task.id}/status".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"host", b"test")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await app(scope, receive, send)

    assert status == 200
    assert events.index("response_sent") < events.index("write_done")
    assert "write_done" not in events[: events.index("response_sent")]
    rows = await _wait_for_rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].to_status.value == "in_progress"


async def test_audit_failure_does_not_fail_request(
    client, db_session, make_project, make_task, monkeypatch
):
    _, task = await _setup(make_project, make_task)

    async def boom(session, payload):
        raise RuntimeError("audit down")

    monkeypatch.setattr(audit_service, "record_status_change", boom)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "in_progress"
    await asyncio.sleep(0.2)
    assert await _rows(db_session, task.id) == []
    r = await client.get(f"/api/v1/tasks/{task.id}")
    if r.status_code == 200:
        assert r.json()["data"]["status"] == "in_progress"


async def test_audit_rows_survive_project_deletion(client, db_session, make_project, make_task):
    project, task = await _setup(make_project, make_task)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "in_progress"})
    assert r.status_code == 200
    assert len(await _wait_for_rows(db_session, task.id)) == 1
    r = await client.delete(f"/api/v1/projects/{project.id}")
    assert r.status_code == 204
    rows = await _rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].project_id == project.id
