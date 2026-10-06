import datetime as dt
import uuid

import pytest


def _today_utc() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


async def test_create_task_defaults(client, make_project):
    project = await make_project()
    r = await client.post(f"/api/v1/projects/{project.id}/tasks", json={"title": "  Write spec  "})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert set(data) == {
        "id",
        "project_id",
        "title",
        "status",
        "priority",
        "due_date",
        "created_at",
        "updated_at",
    }
    assert data["project_id"] == str(project.id)
    assert data["title"] == "Write spec"
    assert data["status"] == "pending"
    assert data["priority"] == "medium"
    assert data["due_date"] is None
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    uuid.UUID(data["id"])


async def test_due_date_must_be_in_the_future(client, make_project):
    project = await make_project()
    url = f"/api/v1/projects/{project.id}/tasks"
    today = _today_utc()
    for bad in (today - dt.timedelta(days=1), today):
        r = await client.post(url, json={"title": "t", "due_date": bad.isoformat()})
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["field"] == "due_date"
        assert "future" in err["detail"]

    tomorrow = today + dt.timedelta(days=1)
    r = await client.post(url, json={"title": "t", "due_date": tomorrow.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["data"]["due_date"] == tomorrow.isoformat()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": "x" * 201}, "title"),
        ({}, "title"),
        ({"title": "ok", "priority": "urgent"}, "priority"),
    ],
)
async def test_invalid_title_and_priority_rejected(client, make_project, payload, field):
    project = await make_project()
    r = await client.post(f"/api/v1/projects/{project.id}/tasks", json=payload)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == field


async def test_unknown_project_returns_404(client):
    missing = uuid.uuid4()
    r = await client.post(f"/api/v1/projects/{missing}/tasks", json={"title": "t"})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "PROJECT_NOT_FOUND"

    r = await client.get(f"/api/v1/projects/{missing}/tasks")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "PROJECT_NOT_FOUND"


async def test_list_is_scoped_to_project(client, make_project, make_task):
    p1 = await make_project()
    p2 = await make_project()
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    t1 = await make_task(p1, created_at=base)
    t2 = await make_task(p1, created_at=base + dt.timedelta(minutes=1))
    await make_task(p2, created_at=base + dt.timedelta(minutes=2))

    r = await client.get(f"/api/v1/projects/{p1.id}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # Newest first.
    assert [t["id"] for t in data] == [str(t2.id), str(t1.id)]
    assert all(t["project_id"] == str(p1.id) for t in data)

    empty = await make_project()
    r = await client.get(f"/api/v1/projects/{empty.id}/tasks")
    assert r.status_code == 200
    assert r.json()["data"] == []


async def test_list_filters_combine(client, make_project, make_task):
    project = await make_project()
    a = await make_task(project, status="pending", priority="high")
    b = await make_task(project, status="pending", priority="low")
    c = await make_task(project, status="done", priority="high")
    await make_task(project, status="cancelled", priority="medium")
    url = f"/api/v1/projects/{project.id}/tasks"

    async def ids(params):
        r = await client.get(url, params=params)
        assert r.status_code == 200, r.text
        return {t["id"] for t in r.json()["data"]}

    assert await ids({"status": "pending"}) == {str(a.id), str(b.id)}
    assert await ids({"priority": "high"}) == {str(a.id), str(c.id)}
    assert await ids({"status": "pending", "priority": "high"}) == {str(a.id)}
    assert await ids({"status": "in_progress"}) == set()
    assert len(await ids({})) == 4


@pytest.mark.parametrize(
    ("params", "field"),
    [({"status": "bogus"}, "status"), ({"priority": "urgent"}, "priority")],
)
async def test_invalid_filter_value_rejected(client, make_project, params, field):
    project = await make_project()
    r = await client.get(f"/api/v1/projects/{project.id}/tasks", params=params)
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == field
