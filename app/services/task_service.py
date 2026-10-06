"""Task creation and the task status state machine."""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Project, Task, TaskStatus
from app.schemas.task import TaskCreate

# The whole state machine: each status maps to the statuses it may move to.
# Terminal statuses map to an empty set. Anything not listed is rejected.
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def _describe_allowed(current: TaskStatus) -> str:
    allowed = [s for s in TaskStatus if s in TRANSITIONS[current]]
    return ", ".join(f"'{s.value}'" for s in allowed) if allowed else "none"


async def ensure_project_exists(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError(404, "PROJECT_NOT_FOUND", "Project not found", field="project_id")
    return project


async def create_task(session: AsyncSession, project_id: uuid.UUID, data: TaskCreate) -> Task:
    await ensure_project_exists(session, project_id)
    task = Task(
        project_id=project_id,
        title=data.title,
        priority=data.priority,
        due_date=data.due_date,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def transition_status(
    session: AsyncSession, task_id: uuid.UUID, new_status: TaskStatus
) -> tuple[Task, TaskStatus]:
    """Move a task to ``new_status`` under a row lock.

    Returns the updated task and its previous status. Raises ``AppError`` (and
    rolls back, releasing the lock) for an unknown task or a disallowed move.
    """
    stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update()
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        await session.rollback()
        raise AppError(404, "TASK_NOT_FOUND", "Task not found", field="task_id")

    current = TaskStatus(task.status)
    if new_status not in TRANSITIONS[current]:
        await session.rollback()
        raise AppError(
            422,
            "INVALID_STATUS_TRANSITION",
            f"Cannot transition task from '{current.value}' to '{new_status.value}'. "
            f"Allowed: {_describe_allowed(current)}",
            field="status",
        )

    task.status = new_status
    task.updated_at = dt.datetime.now(dt.UTC)
    await session.commit()
    return task, current
