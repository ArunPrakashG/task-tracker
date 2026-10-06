"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import build_router
from app.core.errors import register_exception_handlers
from app.core.responses import Envelope, ok
from app.core.telemetry import setup_telemetry
from app.database import engine
from app.handlers import discover_handlers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    discover_handlers()
    import app.models  # noqa: F401  (complete metadata)

    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(title="task-tracker", lifespan=lifespan)
    register_exception_handlers(application)
    setup_telemetry(application)
    application.include_router(build_router(), prefix="/api/v1")

    @application.get("/health", response_model=Envelope[dict[str, str]])
    async def health() -> dict:
        return ok({"status": "ok"})

    return application


app = create_app()
