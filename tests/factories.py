"""Data factories inserting through the ORM, bypassing API validation on purpose."""

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, TaskPriority, TaskStatus


async def make_project_impl(
    session: AsyncSession, name: str | None = None, description: str | None = None
) -> Project:
    project = Project(name=name or f"project-{uuid.uuid4().hex}", description=description)
    session.add(project)
    await session.commit()
    return project


async def make_task_impl(
    session: AsyncSession,
    project: Project | uuid.UUID,
    title: str | None = None,
    status: str = "pending",
    priority: str = "medium",
    due_date: dt.date | None = None,
    created_at: dt.datetime | None = None,
) -> Task:
    project_id = project.id if isinstance(project, Project) else project
    task = Task(
        project_id=project_id,
        title=title or f"task-{uuid.uuid4().hex[:12]}",
        status=TaskStatus(status),
        priority=TaskPriority(priority),
        due_date=due_date,
    )
    if created_at is not None:
        task.created_at = created_at
    session.add(task)
    await session.commit()
    return task
