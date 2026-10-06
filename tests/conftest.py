"""Shared functional test harness: isolated test DB built by migrations, client, cleanup."""

import asyncio
import hashlib
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_database_name() -> str:
    db_id = os.environ.get("TEST_DB_ID") or hashlib.sha1(str(REPO_ROOT).encode()).hexdigest()[:8]
    return f"taskdb_{db_id}_test"


test_database_name.__test__ = False  # type: ignore[attr-defined]  # not a pytest test


def _build_test_env() -> str:
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    dev_url = os.environ.get("DATABASE_URL") or dotenv_values(REPO_ROOT / ".env").get(
        "DATABASE_URL"
    )
    if not dev_url:
        raise RuntimeError("DATABASE_URL is not set; define it in the environment or .env")
    test_url = make_url(dev_url).set(database=test_database_name())
    rendered = test_url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = rendered
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"
    os.environ["RATE_LIMIT_REQUESTS"] = "1000"
    return rendered


# Must run before anything imports `app` (settings and engine read env at import time).
TEST_DATABASE_URL = _build_test_env()

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.database import async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402

from .factories import make_project_impl, make_task_impl  # noqa: E402


def assert_test_database(url: str) -> None:
    """Refuse destructive operations unless the database name ends with `_test`."""
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(f"Refusing destructive operation on non-test database {name!r}")


def _asyncpg_dsn(url: str, database: str) -> str:
    u = make_url(url).set(drivername="postgresql", database=database)
    return u.render_as_string(hide_password=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _test_database() -> AsyncIterator[None]:
    assert_test_database(TEST_DATABASE_URL)
    name = make_url(TEST_DATABASE_URL).database
    conn = await asyncpg.connect(_asyncpg_dsn(TEST_DATABASE_URL, "postgres"))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{proc.stdout}\n{proc.stderr}")
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_state(_test_database: None) -> AsyncIterator[None]:
    assert_test_database(str(engine.url.render_as_string(hide_password=False)))
    async with engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        tables = [r[0] for r in rows]
        if tables:
            quoted = ", ".join('"' + t.replace('"', '""') + '"' for t in tables)
            await conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    try:
        r = aioredis.from_url(os.environ["REDIS_URL"])
        try:
            await r.flushdb()
        finally:
            await r.aclose()
    except Exception:
        pass
    yield


ClientFactory = Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]


@pytest.fixture
def client_factory() -> ClientFactory:
    @asynccontextmanager
    async def factory(address: tuple[str, int] = ("127.0.0.1", 12345)):
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=address)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                yield c

    return factory


@pytest_asyncio.fixture
async def client(client_factory: ClientFactory) -> AsyncIterator[httpx.AsyncClient]:
    async with client_factory() as c:
        yield c


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def make_project(db_session: AsyncSession):
    async def _make(name: str | None = None, description: str | None = None):
        return await make_project_impl(db_session, name=name, description=description)

    return _make


@pytest_asyncio.fixture
async def make_task(db_session: AsyncSession):
    async def _make(
        project,
        title: str | None = None,
        status: str = "pending",
        priority: str = "medium",
        due_date=None,
        created_at=None,
    ):
        return await make_task_impl(
            db_session,
            project,
            title=title,
            status=status,
            priority=priority,
            due_date=due_date,
            created_at=created_at,
        )

    return _make
