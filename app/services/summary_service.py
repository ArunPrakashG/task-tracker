"""Project summary: task totals computed with one aggregate query."""

import datetime as dt
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.telemetry import get_tracer
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
    ).where(Task.project_id == project_id, Task.deleted_at.is_(None))
    return (await session.execute(stmt)).one()


async def get_project_summary(session: AsyncSession, project_id: uuid.UUID) -> dict:
    tracer = get_tracer()
    with tracer.start_as_current_span("projects.summary"):
        project = await session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise AppError(404, "PROJECT_NOT_FOUND", "Project not found", field="project_id")
        today = dt.datetime.now(dt.UTC).date()
        with tracer.start_as_current_span("summary.db_query") as span:
            start = time.perf_counter()
            try:
                row = await run_summary_aggregate(session, project_id, today)
            finally:
                span.set_attribute("db.duration_ms", (time.perf_counter() - start) * 1000.0)
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
