from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import TaskStatus


def _values(e: type) -> list[str]:
    return [m.value for m in e]  # type: ignore[attr-defined]


def _in_list(e: type) -> str:
    return ", ".join(f"'{v}'" for v in _values(e))


def _status_enum(name: str) -> Enum:
    return Enum(
        TaskStatus,
        native_enum=False,
        create_constraint=False,
        length=20,
        name=name,
        values_callable=_values,
    )


class TaskAuditLog(Base):
    """Append-only history of task status changes. No FKs: survives task/project deletion."""

    __tablename__ = "task_audit_logs"
    __table_args__ = (
        CheckConstraint(f"from_status IN ({_in_list(TaskStatus)})", name="from_status"),
        CheckConstraint(f"to_status IN ({_in_list(TaskStatus)})", name="to_status"),
        Index("ix_task_audit_logs_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    from_status: Mapped[TaskStatus] = mapped_column(_status_enum("from_status"), nullable=False)
    to_status: Mapped[TaskStatus] = mapped_column(_status_enum("to_status"), nullable=False)
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
