from app import database
from app.core.events import on
from app.services import audit_service


# Both collaborators are referenced through their modules at call time
# (``database.async_session_factory`` and ``audit_service.record_status_change``)
# so tests can monkeypatch either one.
@on("task.status_changed")
async def handle_task_status_changed(payload: dict) -> None:
    async with database.async_session_factory() as session:
        await audit_service.record_status_change(session, payload)
        await session.commit()
