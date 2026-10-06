"""Read-side queries for tasks.

``build_task_query`` is kept separate from execution so cursor pagination can
be layered on top of the same filtered, ordered statement.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor
from app.models import Task, TaskPriority, TaskStatus


def build_task_query(
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> Select[tuple[Task]]:
    stmt = select(Task).where(Task.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Task.created_at, Task.id) < tuple_(cursor_created_at, cursor_id))
    stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


async def list_tasks(
    session: AsyncSession,
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
) -> Sequence[Task]:
    result = await session.execute(build_task_query(project_id, status, priority))
    return result.scalars().all()


async def list_tasks_page(
    session: AsyncSession,
    project_id: uuid.UUID,
    limit: int,
    cursor: str | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
) -> tuple[list[Task], str | None]:
    """Return one keyset page and the cursor for the next page (None on the last)."""
    stmt = build_task_query(project_id, status, priority, cursor=cursor, limit=limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return rows, next_cursor
