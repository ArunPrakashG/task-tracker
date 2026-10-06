"""Tasks nested under a project: create and list."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.database import get_db
from app.models import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskRead
from app.services import task_query, task_service

router = APIRouter(tags=["tasks"])


@router.post(
    "/projects/{project_id}/tasks",
    status_code=201,
    summary="Create a task in a project",
    response_model=Envelope[TaskRead],
)
@rate_limit()
async def create_task(
    request: Request,
    project_id: uuid.UUID,
    body: TaskCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task = await task_service.create_task(session, project_id, body)
    return ok(TaskRead.model_validate(task))


@router.get(
    "/projects/{project_id}/tasks",
    summary="List a project's tasks (cursor-paginated, filterable by status and priority)",
    response_model=Envelope[list[TaskRead]],
)
async def list_project_tasks(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[TaskStatus | None, Query()] = None,
    priority: Annotated[TaskPriority | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    await task_service.ensure_project_exists(session, project_id)
    tasks, next_cursor = await task_query.list_tasks_page(
        session, project_id, limit, cursor=cursor, status=status, priority=priority
    )
    meta = {"limit": limit, "has_more": next_cursor is not None, "next_cursor": next_cursor}
    return ok([TaskRead.model_validate(t) for t in tasks], meta=meta)
