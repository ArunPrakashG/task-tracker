import datetime as dt
import hashlib
import os

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from tests.conftest import REPO_ROOT, assert_test_database, test_database_name


async def test_schema_built_by_migrations(db_session):
    head = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini"))).get_current_head()
    versions = (await db_session.execute(text("SELECT version_num FROM alembic_version"))).all()
    assert [v[0] for v in versions] == [head]
    tables = {
        r[0]
        for r in await db_session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    }
    assert {"projects", "tasks"} <= tables


async def test_inserts_rows_for_leak_check(make_project, make_task):
    project = await make_project(name="leak-check")
    await make_task(project, title="leak-check-task")


async def test_tables_are_truncated_between_tests(db_session):
    for table in ("projects", "tasks"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count == 0


async def test_client_serves_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"] == {"status": "ok"}


async def test_factories_bypass_api_validation(make_project, make_task):
    project = await make_project()
    past = dt.date(2000, 1, 1)
    created = dt.datetime(2001, 2, 3, 4, 5, 6, tzinfo=dt.UTC)
    task = await make_task(project.id, status="done", due_date=past, created_at=created)
    assert task.due_date == past
    assert task.created_at == created
    assert task.status == "done"


def test_guard_rejects_non_test_database():
    with pytest.raises(RuntimeError):
        assert_test_database("postgresql+asyncpg://postgres:pass@localhost:5432/taskdb")
    assert_test_database("postgresql+asyncpg://postgres:pass@localhost:5432/taskdb_x_test")


def test_database_name_is_isolated_per_checkout():
    name = test_database_name()
    assert name.endswith("_test")
    db_id = os.environ.get("TEST_DB_ID") or hashlib.sha1(str(REPO_ROOT).encode()).hexdigest()[:8]
    assert db_id in name
