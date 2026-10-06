import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Project
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
        select(Project).order_by(Project.created_at.desc(), Project.id.desc())
    )
    return list(result.scalars().all())


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> None:
    project = await session.get(Project, project_id)
    if project is None:
        raise AppError(404, "PROJECT_NOT_FOUND", "Project not found", field="project_id")
    await session.delete(project)
    await session.commit()
