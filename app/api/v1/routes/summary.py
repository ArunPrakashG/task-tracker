from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import Envelope, ok
from app.database import get_db
from app.schemas.summary import SummaryOut
from app.services import summary_service

router = APIRouter()


@router.get("/projects/{project_id}/summary", response_model=Envelope[SummaryOut])
async def get_summary(project_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]):
    return ok(await summary_service.get_project_summary(session, project_id))
