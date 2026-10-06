import datetime as dt

BASE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def url(project) -> str:
    return f"/api/v1/projects/{project.id}/tasks"


async def walk(client, project, **params):
    """Follow next_cursor until exhausted; return (ids, pages)."""
    ids, pages, cursor = [], [], None
    while True:
        q = dict(params)
        if cursor:
            q["cursor"] = cursor
        r = await client.get(url(project), params=q)
        assert r.status_code == 200
        body = r.json()
        pages.append(body)
        ids.extend(t["id"] for t in body["data"])
        cursor = body["meta"]["next_cursor"]
        if not body["meta"]["has_more"]:
            return ids, pages


async def test_first_page_shape_and_default_limit(client, make_project, make_task):
    project = await make_project()
    for i in range(25):
        await make_task(project, created_at=BASE + dt.timedelta(minutes=i))
    r = await client.get(url(project))
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 20
    assert body["meta"]["limit"] == 20
    assert body["meta"]["has_more"] is True
    assert body["meta"]["next_cursor"]


async def test_walking_pages_returns_each_task_once_in_order(client, make_project, make_task):
    project = await make_project()
    tasks = [await make_task(project, created_at=BASE + dt.timedelta(minutes=i)) for i in range(11)]
    expected = [str(t.id) for t in reversed(tasks)]
    ids, pages = await walk(client, project, limit=3)
    assert ids == expected
    assert len(pages) == 4


async def test_identical_created_at_ties_are_stable(client, make_project, make_task):
    project = await make_project()
    tasks = [await make_task(project, created_at=BASE) for _ in range(7)]
    older = await make_task(project, created_at=BASE - dt.timedelta(days=1))
    expected = sorted((str(t.id) for t in tasks), reverse=True) + [str(older.id)]
    ids, _ = await walk(client, project, limit=3)
    assert ids == expected
    assert len(set(ids)) == 8


async def test_insert_during_walk_is_stable(client, make_project, make_task):
    project = await make_project()
    tasks = [await make_task(project, created_at=BASE + dt.timedelta(minutes=i)) for i in range(8)]
    expected = [str(t.id) for t in reversed(tasks)]
    r = await client.get(url(project), params={"limit": 3})
    body = r.json()
    ids = [t["id"] for t in body["data"]]
    await make_task(project, created_at=BASE + dt.timedelta(days=1))
    cursor = body["meta"]["next_cursor"]
    while cursor:
        r = await client.get(url(project), params={"limit": 3, "cursor": cursor})
        body = r.json()
        ids.extend(t["id"] for t in body["data"])
        cursor = body["meta"]["next_cursor"]
    assert ids == expected


async def test_filters_preserved_across_pages(client, make_project, make_task):
    project = await make_project()
    wanted = []
    for i in range(7):
        t = await make_task(
            project, status="done", priority="high", created_at=BASE + dt.timedelta(minutes=2 * i)
        )
        wanted.append(str(t.id))
        await make_task(
            project,
            status="pending",
            priority="high",
            created_at=BASE + dt.timedelta(minutes=2 * i + 1),
        )
        await make_task(
            project, status="done", priority="low", created_at=BASE + dt.timedelta(minutes=i)
        )
    ids, pages = await walk(client, project, limit=2, status="done", priority="high")
    assert ids == list(reversed(wanted))
    assert len(pages) == 4
    for page in pages:
        for t in page["data"]:
            assert t["status"] == "done"
            assert t["priority"] == "high"


async def test_last_page_has_no_next_cursor(client, make_project, make_task):
    project = await make_project()
    for i in range(4):
        await make_task(project, created_at=BASE + dt.timedelta(minutes=i))
    r = await client.get(url(project), params={"limit": 4})
    meta = r.json()["meta"]
    assert len(r.json()["data"]) == 4
    assert meta["has_more"] is False
    assert meta["next_cursor"] is None
    _, pages = await walk(client, project, limit=3)
    assert pages[-1]["meta"] == {"limit": 3, "has_more": False, "next_cursor": None}


async def test_invalid_cursor_and_limit_rejected(client, make_project):
    project = await make_project()
    for bad in ["not-a-cursor!!", "e30", "bm90LWpzb24", "eyJjIjoieCIsImkiOiJ5In0"]:
        r = await client.get(url(project), params={"cursor": bad})
        assert r.status_code == 422, bad
        err = r.json()["error"]
        assert err["code"] == "INVALID_CURSOR"
        assert err["field"] == "cursor"
    for bad in [0, 101, -1]:
        r = await client.get(url(project), params={"limit": bad})
        assert r.status_code == 422
        err = r.json()["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["field"] == "limit"
