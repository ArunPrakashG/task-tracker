"""Project summary: task totals computed with one aggregate query."""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Project, Task, TaskStatus


async def run_summary_aggregate(session: AsyncSession, project_id: uuid.UUID, today: dt.date):
    """Execute the single aggregate statement for a project's task counts."""
    open_statuses = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
    stmt = select(
        func.count().label("total"),
        func.count().filter(Task.status == TaskStatus.PENDING).label("pending"),
        func.count().filter(Task.status == TaskStatus.IN_PROGRESS).label("in_progress"),
        func.count().filter(Task.status == TaskStatus.DONE).label("done"),
        func.count().filter(Task.status == TaskStatus.CANCELLED).label("cancelled"),
        func.count().filter(Task.due_date < today, Task.status.in_(open_statuses)).label("overdue"),
    ).where(Task.project_id == project_id)
    return (await session.execute(stmt)).one()


async def get_project_summary(session: AsyncSession, project_id: uuid.UUID) -> dict:
    if await session.get(Project, project_id) is None:
        raise AppError(404, "PROJECT_NOT_FOUND", "Project not found", field="project_id")
    today = dt.datetime.now(dt.UTC).date()
    row = await run_summary_aggregate(session, project_id, today)
    return {
        "total": row.total,
        "by_status": {
            "pending": row.pending,
            "in_progress": row.in_progress,
            "done": row.done,
            "cancelled": row.cancelled,
        },
        "overdue": row.overdue,
    }
