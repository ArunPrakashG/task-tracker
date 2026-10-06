"""Background event dispatcher.

Handlers register with ``@on("event.name")`` and are looked up at emit time.
``emit`` schedules one background task per handler; handler exceptions are
logged and never propagate.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[None]]

_registry: dict[str, list[Handler]] = {}


def on(event: str) -> Callable[[Handler], Handler]:
    """Register an async handler for ``event``; returns the function unchanged."""

    def decorator(func: Handler) -> Handler:
        _registry.setdefault(event, []).append(func)
        return func

    return decorator


def unregister(event: str, handler: Handler) -> None:
    """Remove ``handler`` from ``event`` if registered."""
    handlers = _registry.get(event)
    if handlers and handler in handlers:
        handlers.remove(handler)
        if not handlers:
            del _registry[event]


async def _safe_call(handler: Handler, event: str, payload: dict) -> None:
    try:
        await handler(payload)
    except Exception:
        logger.exception("Event handler %r failed for event %r", handler, event)


def emit(background_tasks: BackgroundTasks, event: str, payload: dict[str, Any]) -> None:
    """Schedule every handler registered for ``event`` as a background task."""
    for handler in list(_registry.get(event, [])):
        background_tasks.add_task(_safe_call, handler, event, payload)
