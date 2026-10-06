import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Project, Task
from app.schemas.project import ProjectCreate

_UNIQUE_VIOLATION = "23505"


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return code == _UNIQUE_VIOLATION


async def create_project(session: AsyncSession, payload: ProjectCreate) -> Project:
    project = Project(name=payload.name, description=payload.description)
    session.add(project)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_unique_violation(exc):
            raise AppError(
                409,
                "PROJECT_NAME_CONFLICT",
                f"A project named '{payload.name}' already exists",
                field="name",
            ) from exc
        raise
    return project


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.execute(
        select(Project)
        .where(Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return list(result.scalars().all())


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> None:
    """Soft-delete a project and its tasks; rows stay in the database with ``deleted_at`` set."""
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError(404, "PROJECT_NOT_FOUND", "Project not found", field="project_id")
    now = dt.datetime.now(dt.UTC)
    project.deleted_at = now
    await session.execute(
        update(Task)
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await session.commit()
