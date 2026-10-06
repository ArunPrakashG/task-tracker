"""Redis sliding-window rate limiter used as a decorator on POST routes.

Decorated routes must declare ``request: Request``. Limits default to
``settings.rate_limit_requests`` / ``settings.rate_limit_window_seconds`` and are
read when the request arrives. If Redis is unavailable the request is allowed.
"""

import asyncio
import functools
import inspect
import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request

from app.config import settings
from app.core.errors import error_response

logger = logging.getLogger(__name__)

# Atomic sliding window using Redis server time (milliseconds).
# Returns {1, 0} when allowed, or {0, retry_after_ms} when blocked.
_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[3])
  redis.call('PEXPIRE', KEYS[1], window)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local retry = window
if oldest[2] then
  retry = tonumber(oldest[2]) + window - now
end
if retry < 1 then retry = 1 end
return {0, retry}
"""

_clients: dict[tuple[str, int], aioredis.Redis] = {}


def _get_client() -> aioredis.Redis:
    """Lazily create one client per (redis_url, event loop)."""
    key = (settings.redis_url, id(asyncio.get_running_loop()))
    client = _clients.get(key)
    if client is None:
        client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        _clients[key] = client
    return client


async def _check(key: str, limit: int, window_seconds: int) -> int | None:
    """Return None if allowed, else the retry-after in milliseconds."""
    client = _get_client()
    result = await client.eval(  # type: ignore[misc]
        _LUA, 1, key, window_seconds * 1000, limit, uuid.uuid4().hex
    )
    if int(result[0]) == 1:
        return None
    return int(result[1])


def rate_limit(
    limit: int | None = None, window_seconds: int | None = None
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Sliding-window rate limit decorator for async route functions."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if "request" not in inspect.signature(func).parameters:
            raise TypeError(f"@rate_limit requires {func.__name__} to declare `request: Request`")

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = kwargs.get("request")
            if not isinstance(request, Request):
                raise RuntimeError("@rate_limit could not find the Request in handler arguments")

            eff_limit = limit if limit is not None else settings.rate_limit_requests
            eff_window = (
                window_seconds if window_seconds is not None else settings.rate_limit_window_seconds
            )
            route = request.scope.get("route")
            template = getattr(route, "path", None) or request.url.path
            host = request.client.host if request.client else "unknown"
            key = f"ratelimit:{host}:{template}"

            try:
                retry_ms = await _check(key, eff_limit, eff_window)
            except Exception as exc:  # fail open on any Redis problem
                logger.warning("Rate limiter unavailable, allowing request: %s", exc)
                retry_ms = None

            if retry_ms is not None:
                seconds = max(1, math.ceil(retry_ms / 1000))
                response = error_response(
                    429, "RATE_LIMITED", f"Rate limit exceeded. Retry in {seconds} seconds."
                )
                response.headers["Retry-After"] = str(seconds)
                return response
            return await func(*args, **kwargs)

        wrapper.__rate_limited__ = True  # type: ignore[attr-defined]
        return wrapper

    return decorator
