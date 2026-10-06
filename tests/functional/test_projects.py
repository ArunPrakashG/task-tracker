import uuid

from sqlalchemy import select

from app.models import Task


async def test_create_project_returns_201_envelope(client):
    r = await client.post("/api/v1/projects", json={"name": "  Alpha  ", "description": "d"})
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["meta"] is None
    data = body["data"]
    assert set(data) == {"id", "name", "description", "created_at"}
    assert data["name"] == "Alpha"
    assert data["description"] == "d"
    uuid.UUID(data["id"])


async def test_create_project_without_description(client):
    r = await client.post("/api/v1/projects", json={"name": "NoDesc"})
    assert r.status_code == 201
    assert r.json()["data"]["description"] is None


async def test_duplicate_name_returns_409(client):
    assert (await client.post("/api/v1/projects", json={"name": "Dup"})).status_code == 201
    r = await client.post("/api/v1/projects", json={"name": "Dup"})
    assert r.status_code == 409
    assert r.json() == {
        "success": False,
        "error": {
            "detail": r.json()["error"]["detail"],
            "code": "PROJECT_NAME_CONFLICT",
            "field": "name",
        },
    }


async def test_blank_name_returns_422(client):
    for payload in ({"name": "   "}, {"name": ""}, {}):
        r = await client.post("/api/v1/projects", json=payload)
        assert r.status_code == 422
        error = r.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["field"] == "name"


async def test_list_projects_newest_first(client):
    for name in ("first", "second", "third"):
        assert (await client.post("/api/v1/projects", json={"name": name})).status_code == 201
    r = await client.get("/api/v1/projects")
    assert r.status_code == 200
    assert [p["name"] for p in r.json()["data"]] == ["third", "second", "first"]


async def test_delete_project_returns_204(client):
    created = (await client.post("/api/v1/projects", json={"name": "gone"})).json()["data"]
    r = await client.delete(f"/api/v1/projects/{created['id']}")
    assert r.status_code == 204
    assert r.content == b""
    listed = (await client.get("/api/v1/projects")).json()["data"]
    assert all(p["id"] != created["id"] for p in listed)


async def test_delete_project_cascades_to_tasks_only_for_that_project(
    client, db_session, make_project, make_task
):
    doomed = await make_project(name="doomed")
    kept = await make_project(name="kept")
    for i in range(2):
        await make_task(doomed, title=f"d{i}")
        await make_task(kept, title=f"k{i}")
    doomed_id, kept_id = doomed.id, kept.id

    r = await client.delete(f"/api/v1/projects/{doomed_id}")
    assert r.status_code == 204

    db_session.expire_all()
    gone = (await db_session.execute(select(Task).where(Task.project_id == doomed_id))).all()
    remaining = (await db_session.execute(select(Task).where(Task.project_id == kept_id))).all()
    assert gone == []
    assert len(remaining) == 2


async def test_delete_unknown_project_returns_404(client):
    r = await client.delete(f"/api/v1/projects/{uuid.uuid4()}")
    assert r.status_code == 404
    error = r.json()["error"]
    assert error["code"] == "PROJECT_NOT_FOUND"
    assert error["field"] == "project_id"


async def test_malformed_project_id_returns_422(client):
    r = await client.delete("/api/v1/projects/not-a-uuid")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["field"] == "project_id"
