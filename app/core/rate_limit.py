"""Rate limit decorator (STUB).

F8 replaces this implementation. Decorated routes must declare
``request: Request`` so the real implementation can read the client.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Any


def rate_limit(
    limit: int | None = None, window_seconds: int | None = None
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """No-op decorator preserving the wrapped route's signature."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        return wrapper

    return decorator
