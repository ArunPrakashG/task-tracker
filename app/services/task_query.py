"""Read-side queries for tasks.

``build_task_query`` is kept separate from execution so cursor pagination can
be layered on top of the same filtered, ordered statement.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskPriority, TaskStatus


def build_task_query(
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
) -> Select[tuple[Task]]:
    stmt = select(Task).where(Task.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    return stmt.order_by(Task.created_at.desc(), Task.id.desc())


async def list_tasks(
    session: AsyncSession,
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
) -> Sequence[Task]:
    result = await session.execute(build_task_query(project_id, status, priority))
    return result.scalars().all()
