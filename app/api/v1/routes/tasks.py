"""Task status transitions."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import emit
from app.core.responses import Envelope, ok
from app.database import get_db
from app.schemas.task import TaskRead, TaskStatusUpdate
from app.services import task_service

router = APIRouter(tags=["tasks"])


@router.patch(
    "/tasks/{task_id}/status",
    summary="Change a task's status (validated against the state machine)",
    response_model=Envelope[TaskRead],
)
async def update_task_status(
    task_id: uuid.UUID,
    body: TaskStatusUpdate,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task, previous = await task_service.transition_status(session, task_id, body.status)
    # Emitted only after a successful commit; handlers run after the response.
    emit(
        background_tasks,
        "task.status_changed",
        {
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "from_status": previous.value,
            "to_status": task.status.value,
            "changed_at": task.updated_at.isoformat(),
        },
    )
    return ok(TaskRead.model_validate(task))
