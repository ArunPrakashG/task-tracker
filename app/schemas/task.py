"""Task request/response schemas."""

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.models.enums import TaskPriority, TaskStatus

TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TaskCreate(BaseModel):
    title: TaskTitle
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: dt.date | None = None

    @field_validator("due_date")
    @classmethod
    def _due_date_in_future(cls, value: dt.date | None) -> dt.date | None:
        if value is not None and value <= dt.datetime.now(dt.UTC).date():
            raise ValueError("due_date must be in the future")
        return value


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_date: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime
