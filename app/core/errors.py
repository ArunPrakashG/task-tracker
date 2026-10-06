"""Structured error handling."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        field: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.field = field


def error_response(
    status_code: int, code: str, detail: str, field: str | None = None
) -> JSONResponse:
    error: dict[str, str] = {"detail": detail, "code": code}
    if field is not None:
        error["field"] = field
    return JSONResponse(status_code=status_code, content={"success": False, "error": error})


def _field_from_loc(loc) -> str | None:
    for part in reversed(loc):
        if isinstance(part, str) and part not in _LOC_PREFIXES:
            return part
    return None


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.detail, exc.field)


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        detail = str(errors[0].get("msg", "Validation error"))
        field = _field_from_loc(errors[0].get("loc", ()))
    else:
        detail, field = "Validation error", None
    return error_response(422, "VALIDATION_ERROR", detail, field)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    else:
        code = f"HTTP_{exc.status_code}"
    response = error_response(exc.status_code, code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
