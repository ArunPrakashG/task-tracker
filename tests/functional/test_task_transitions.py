import asyncio
import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.core.events import on, unregister
from app.models import Task, TaskStatus

ALLOWED = {
    ("pending", "in_progress"),
    ("in_progress", "done"),
    ("pending", "cancelled"),
    ("in_progress", "cancelled"),
}
ALL_STATUSES = [s.value for s in TaskStatus]
REJECTED = sorted(
    (src, dst) for src in ALL_STATUSES for dst in ALL_STATUSES if (src, dst) not in ALLOWED
)

# Factory rows get created_at/updated_at = now() on insert; pin them in the past so an
# advancing updated_at is unambiguous.
PAST = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)


async def _task(make_project, make_task, db_session, status: str) -> Task:
    project = await make_project()
    task = await make_task(project, status=status)
    task.updated_at = PAST
    await db_session.commit()
    return task


async def _reload(db_session, task_id) -> Task:
    db_session.expire_all()
    return (await db_session.execute(select(Task).where(Task.id == task_id))).scalar_one()


@pytest.mark.parametrize(("src", "dst"), sorted(ALLOWED))
async def test_valid_transitions(client, make_project, make_task, db_session, src, dst):
    task = await _task(make_project, make_task, db_session, src)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": dst})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["id"] == str(task.id)
    assert data["status"] == dst
    assert dt.datetime.fromisoformat(data["updated_at"]) > PAST

    stored = await _reload(db_session, task.id)
    assert stored.status == dst
    assert stored.updated_at > PAST


@pytest.mark.parametrize(("src", "dst"), REJECTED)
async def test_invalid_transitions_rejected(client, make_project, make_task, src, dst):
    project = await make_project()
    task = await make_task(project, status=src)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": dst})
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "INVALID_STATUS_TRANSITION"
    assert err["field"] == "status"
    assert f"'{src}'" in err["detail"]
    assert f"'{dst}'" in err["detail"]
    assert "Allowed:" in err["detail"]
    if src in ("done", "cancelled"):
        assert "Allowed: none" in err["detail"]


async def test_rejected_transition_does_not_mutate_task(
    client, make_project, make_task, db_session
):
    task = await _task(make_project, make_task, db_session, "done")
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "pending"})
    assert r.status_code == 422, r.text

    stored = await _reload(db_session, task.id)
    assert stored.status == "done"
    assert stored.updated_at == PAST


async def test_unknown_task_and_status(client, make_project, make_task):
    r = await client.patch(f"/api/v1/tasks/{uuid.uuid4()}/status", json={"status": "done"})
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "TASK_NOT_FOUND"

    project = await make_project()
    task = await make_task(project)
    r = await client.patch(f"/api/v1/tasks/{task.id}/status", json={"status": "bogus"})
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "status"


async def test_concurrent_conflicting_transitions_have_one_winner(
    client, make_project, make_task, db_session
):
    project = await make_project()
    task = await make_task(project, status="in_progress")
    url = f"/api/v1/tasks/{task.id}/status"

    # Hold the row lock from a separate connection while both requests start, so
    # they genuinely overlap: each must read the row before either can write. With
    # the service's SELECT ... FOR UPDATE they serialise behind this gate; without
    # it both would read 'in_progress' and both would succeed.
    await db_session.execute(select(Task).where(Task.id == task.id).with_for_update())
    both = asyncio.gather(
        client.patch(url, json={"status": "done"}),
        client.patch(url, json={"status": "cancelled"}),
    )
    await asyncio.sleep(0.3)
    await db_session.commit()
    r_done, r_cancel = await both
    codes = sorted([r_done.status_code, r_cancel.status_code])
    assert codes == [200, 422], (r_done.text, r_cancel.text)

    winner = r_done if r_done.status_code == 200 else r_cancel
    loser = r_cancel if winner is r_done else r_done
    assert loser.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    stored = await _reload(db_session, task.id)
    assert stored.status == winner.json()["data"]["status"]


async def test_status_change_event_emitted_only_on_success(client, make_project, make_task):
    received: list[dict] = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    on("task.status_changed")(handler)
    try:
        project = await make_project()
        task = await make_task(project, status="pending")
        url = f"/api/v1/tasks/{task.id}/status"

        r = await client.patch(url, json={"status": "in_progress"})
        assert r.status_code == 200, r.text
        assert len(received) == 1
        payload = received[0]
        assert payload == {
            "task_id": str(task.id),
            "project_id": str(project.id),
            "from_status": "pending",
            "to_status": "in_progress",
            "changed_at": payload["changed_at"],
        }
        assert dt.datetime.fromisoformat(payload["changed_at"]) == dt.datetime.fromisoformat(
            r.json()["data"]["updated_at"]
        )

        r = await client.patch(url, json={"status": "pending"})
        assert r.status_code == 422, r.text
        assert len(received) == 1
    finally:
        unregister("task.status_changed", handler)
