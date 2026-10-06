"""Common response envelope."""

from typing import Any

from pydantic import BaseModel


def ok(data: Any, meta: dict | None = None) -> dict:
    """Build a success envelope."""
    return {"success": True, "data": data, "meta": meta}


class Envelope[T](BaseModel):
    """Generic success envelope for use as ``response_model``."""

    success: bool = True
    data: T
    meta: dict | None = None


class ErrorBody(BaseModel):
    detail: str
    code: str
    field: str | None = None


class ErrorEnvelope(BaseModel):
    """Error envelope, for OpenAPI documentation."""

    success: bool = False
    error: ErrorBody
