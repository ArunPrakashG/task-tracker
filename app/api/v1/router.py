"""Auto-discovering aggregate router for API v1 (mounted at /api/v1 by main)."""

import importlib
import pkgutil

from fastapi import APIRouter


def build_router(package: str = "app.api.v1.routes") -> APIRouter:
    """Include the ``router`` of every non-underscore submodule of ``package``."""
    api_router = APIRouter()
    pkg = importlib.import_module(package)
    names = sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_"))
    for name in names:
        module = importlib.import_module(f"{package}.{name}")
        router = getattr(module, "router", None)
        if router is not None:
            api_router.include_router(router)
    return api_router
