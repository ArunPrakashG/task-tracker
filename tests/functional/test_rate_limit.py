"""Functional tests for the Redis sliding-window rate limiter."""

import asyncio
import uuid

from fastapi.routing import APIRoute

from app.config import settings
from app.main import app


def _name() -> str:
    return f"proj-{uuid.uuid4().hex[:12]}"


async def _post(client):
    return await client.post("/api/v1/projects", json={"name": _name()})


async def test_over_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 3)
    statuses = [(await _post(client)).status_code for _ in range(3)]
    assert statuses == [201, 201, 201]

    resp = await _post(client)
    assert resp.status_code == 429
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RATE_LIMITED"
    assert "detail" in body["error"]
    assert int(resp.headers["Retry-After"]) >= 1


async def test_window_expiry_allows_requests_again(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 1)
    assert (await _post(client)).status_code == 201
    assert (await _post(client)).status_code == 201
    assert (await _post(client)).status_code == 429
    await asyncio.sleep(1.2)
    assert (await _post(client)).status_code == 201


async def test_limits_are_per_client(client_factory, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    async with client_factory(address=("10.0.0.1", 1111)) as a:
        async with client_factory(address=("10.0.0.2", 2222)) as b:
            assert (await _post(a)).status_code == 201
            assert (await _post(a)).status_code == 201
            assert (await _post(a)).status_code == 429
            assert (await _post(b)).status_code == 201
            assert (await _post(b)).status_code == 201
            assert (await _post(b)).status_code == 429


async def test_non_post_endpoints_unlimited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    for _ in range(10):
        assert (await client.get("/api/v1/projects")).status_code != 429
        resp = await client.delete(f"/api/v1/projects/{uuid.uuid4()}")
        assert resp.status_code != 429


async def test_fails_open_when_redis_is_down(client, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    for _ in range(3):
        assert (await _post(client)).status_code == 201


async def test_concurrent_requests_respect_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 10)
    responses = await asyncio.gather(*[_post(client) for _ in range(20)])
    statuses = [r.status_code for r in responses]
    assert statuses.count(201) == 10
    assert statuses.count(429) == 10


def _iter_api_routes(routes, prefix=""):
    """Yield (full_path, APIRoute), expanding FastAPI's included-router wrappers."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            ctx_prefix = route.include_context.prefix or ""
            yield from _iter_api_routes(original.routes, prefix + ctx_prefix)
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route


def test_every_post_route_is_rate_limited():
    checked = 0
    for path, route in _iter_api_routes(app.routes):
        if path.startswith("/api/v1") and "POST" in route.methods:
            checked += 1
            assert getattr(route.endpoint, "__rate_limited__", False), path
    assert checked > 0
