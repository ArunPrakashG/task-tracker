import uuid

from sqlalchemy import select

from app.models import Project, Task


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


async def test_delete_project_soft_deletes_project_and_its_tasks_only(
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

    # Rows are retained and marked deleted; only the doomed project's rows.
    db_session.expire_all()
    gone = (await db_session.execute(select(Task).where(Task.project_id == doomed_id))).scalars()
    kept_rows = (await db_session.execute(select(Task).where(Task.project_id == kept_id))).scalars()
    assert [t.deleted_at is not None for t in gone] == [True, True]
    assert [t.deleted_at is None for t in kept_rows] == [True, True]
    project_row = (
        await db_session.execute(select(Project).where(Project.id == doomed_id))
    ).scalar_one()
    assert project_row.deleted_at is not None


async def test_soft_deleted_project_is_hidden_everywhere(client, make_project, make_task):
    project = await make_project(name="hidden")
    task = await make_task(project, title="t")
    assert (await client.delete(f"/api/v1/projects/{project.id}")).status_code == 204

    listed = (await client.get("/api/v1/projects")).json()["data"]
    assert all(p["id"] != str(project.id) for p in listed)
    for method, url, body in [
        ("get", f"/api/v1/projects/{project.id}/tasks", None),
        ("get", f"/api/v1/projects/{project.id}/summary", None),
        ("post", f"/api/v1/projects/{project.id}/tasks", {"title": "x"}),
        ("delete", f"/api/v1/projects/{project.id}", None),
    ]:
        r = await client.request(method, url, json=body)
        assert r.status_code == 404, url
        assert r.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "in_progress"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TASK_NOT_FOUND"


async def test_name_can_be_reused_after_soft_delete_but_not_while_active(client):
    first = (await client.post("/api/v1/projects", json={"name": "reuse"})).json()["data"]
    dup = await client.post("/api/v1/projects", json={"name": "reuse"})
    assert dup.status_code == 409
    await client.delete(f"/api/v1/projects/{first['id']}")
    again = await client.post("/api/v1/projects", json={"name": "reuse"})
    assert again.status_code == 201
    assert again.json()["data"]["id"] != first["id"]


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
