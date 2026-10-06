import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import TaskAuditLog
from app.models.enums import TaskStatus


async def record_status_change(session: AsyncSession, payload: dict) -> None:
    """Add an audit row for a ``task.status_changed`` payload. Does not commit."""
    session.add(
        TaskAuditLog(
            task_id=uuid.UUID(str(payload["task_id"])),
            project_id=uuid.UUID(str(payload["project_id"])),
            from_status=TaskStatus(payload["from_status"]),
            to_status=TaskStatus(payload["to_status"]),
            changed_at=dt.datetime.fromisoformat(payload["changed_at"]),
        )
    )
