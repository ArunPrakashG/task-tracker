import inspect
import sys
import textwrap

import httpx
from fastapi import APIRouter, BackgroundTasks, FastAPI, Request
from pydantic import BaseModel

from app.api.v1.router import build_router
from app.core.errors import AppError
from app.core.events import emit, on, unregister
from app.core.rate_limit import rate_limit
from app.main import create_app


def client(app: FastAPI, **kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, **kw), base_url="http://test")


async def test_health_returns_ok_envelope():
    async with client(create_app()) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"success": True, "data": {"status": "ok"}, "meta": None}


async def test_unknown_route_returns_error_envelope():
    async with client(create_app()) as c:
        r = await c.get("/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


async def test_validation_error_shape():
    app = create_app()

    class Body(BaseModel):
        name: str

    @app.post("/tmp-validate")
    async def tmp(body: Body):
        return {}

    async with client(app) as c:
        r = await c.post("/tmp-validate", json={"name": 123})
    assert r.status_code == 422
    err = r.json()["error"]
    assert r.json()["success"] is False
    assert err["code"] == "VALIDATION_ERROR"
    assert err["field"] == "name"


async def test_app_error_maps_to_envelope():
    app = create_app()

    @app.get("/tmp-err")
    async def with_field():
        raise AppError(409, "PROJECT_NAME_CONFLICT", "dup", "name")

    @app.get("/tmp-err-nofield")
    async def no_field():
        raise AppError(404, "NOT_FOUND", "missing")

    async with client(app) as c:
        r1 = await c.get("/tmp-err")
        r2 = await c.get("/tmp-err-nofield")
    assert r1.status_code == 409
    assert r1.json() == {
        "success": False,
        "error": {"detail": "dup", "code": "PROJECT_NAME_CONFLICT", "field": "name"},
    }
    assert r2.status_code == 404
    assert r2.json()["error"] == {"detail": "missing", "code": "NOT_FOUND"}
    assert "field" not in r2.json()["error"]


async def test_unhandled_exception_returns_500_envelope():
    app = create_app()

    @app.get("/tmp-boom")
    async def boom():
        raise RuntimeError("secret-internal-detail")

    async with client(app, raise_app_exceptions=False) as c:
        r = await c.get("/tmp-boom")
    assert r.status_code == 500
    assert r.json()["success"] is False
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in r.text
    assert "secret-internal-detail" not in r.text


async def test_emit_runs_handlers_in_background_and_isolates_failures():
    app = create_app()
    calls: list[dict] = []

    async def good(payload: dict) -> None:
        calls.append(payload)

    async def bad(payload: dict) -> None:
        raise RuntimeError("handler failure")

    on("test.foundation")(bad)
    on("test.foundation")(good)

    @app.post("/tmp-emit")
    async def route(background_tasks: BackgroundTasks):
        emit(background_tasks, "test.foundation", {"id": 1})
        return {"ok": True}

    try:
        async with client(app) as c:
            r = await c.post("/tmp-emit")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert calls == [{"id": 1}]
    finally:
        unregister("test.foundation", good)
        unregister("test.foundation", bad)


async def test_router_autodiscovery_mounts_under_prefix(tmp_path, monkeypatch):
    pkg = tmp_path / "tmp_routes_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "things.py").write_text(
        textwrap.dedent(
            """
            from fastapi import APIRouter

            router = APIRouter()


            @router.get("/things")
            async def things():
                return {"things": []}
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        app = FastAPI()
        app.include_router(build_router("tmp_routes_pkg"), prefix="/api/v1")
        async with client(app) as c:
            r = await c.get("/api/v1/things")
            r2 = await c.get("/things")
        assert r.status_code == 200
        assert r.json() == {"things": []}
        assert r2.status_code == 404
    finally:
        for name in [n for n in sys.modules if n.startswith("tmp_routes_pkg")]:
            del sys.modules[name]


async def test_rate_limit_stub_is_passthrough():
    app = create_app()
    router = APIRouter()

    @router.post("/tmp-rl")
    @rate_limit()
    async def route(request: Request):
        return {"method": request.method}

    assert "request" in inspect.signature(route).parameters
    app.include_router(router)
    async with client(app) as c:
        r = await c.post("/tmp-rl")
    assert r.status_code == 200
    assert r.json() == {"method": "POST"}
