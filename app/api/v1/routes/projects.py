import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.database import get_db
from app.schemas.project import ProjectCreate, ProjectOut
from app.services import project_service

router = APIRouter()
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/projects", status_code=201, response_model=Envelope[ProjectOut])
@rate_limit()
async def create_project(
    request: Request,
    payload: ProjectCreate,
    session: DbSession,
):
    project = await project_service.create_project(session, payload)
    return ok(ProjectOut.model_validate(project))


@router.get("/projects", response_model=Envelope[list[ProjectOut]])
async def list_projects(session: DbSession):
    projects = await project_service.list_projects(session)
    return ok([ProjectOut.model_validate(p) for p in projects])


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, session: DbSession):
    await project_service.delete_project(session, project_id)
    return Response(status_code=204)
