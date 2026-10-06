"""OpenAPI / Swagger customisation: metadata, tag docs and the shared error envelope."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

DESCRIPTION = """
Lightweight project and task tracker. Every response uses a common envelope:

* success: `{"success": true, "data": ..., "meta": ...}`
* error: `{"success": false, "error": {"detail": "...", "code": "...", "field": "..."}}`

`POST` endpoints are rate limited per client (Redis sliding window); exceeding the limit
returns `429` with a `Retry-After` header. Task lists use opaque cursor pagination
(`limit`, `cursor`; see `meta.next_cursor`). Deletes are soft deletes.
"""

TAGS = [
    {"name": "projects", "description": "Create, list and (soft) delete projects."},
    {
        "name": "tasks",
        "description": "Create and list tasks, and move them through the status state machine "
        "(`pending → in_progress → done`, `cancelled` from pending or in_progress).",
    },
    {"name": "meta", "description": "Service health."},
]


class ErrorBody(BaseModel):
    detail: str
    code: str
    field: str | None = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: ErrorBody


_ERROR_DOCS = {
    "404": "Resource not found (`PROJECT_NOT_FOUND`, `TASK_NOT_FOUND`)",
    "422": "Validation error (`VALIDATION_ERROR`, `INVALID_STATUS_TRANSITION`, `INVALID_CURSOR`)",
    "429": "Rate limit exceeded (`RATE_LIMITED`); see the `Retry-After` header",
    "500": "Unexpected server error (`INTERNAL_ERROR`)",
}


def _error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}},
    }


def install_openapi(app: FastAPI) -> None:
    """Replace ``app.openapi`` with a version documenting the shared error envelope."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        schema.setdefault("components", {}).setdefault("schemas", {})["ErrorEnvelope"] = (
            ErrorEnvelope.model_json_schema(ref_template="#/components/schemas/{model}")
        )
        for sub in schema["components"]["schemas"]["ErrorEnvelope"].pop("$defs", {}).items():
            schema["components"]["schemas"][sub[0]] = sub[1]
        for path, item in schema["paths"].items():
            if not path.startswith("/api/"):
                continue
            for method, op in item.items():
                responses = op.setdefault("responses", {})
                codes = ["422", "500"]
                if "{" in path:
                    codes.append("404")
                if method == "post":
                    codes.append("429")
                for code in codes:
                    responses[code] = _error_response(_ERROR_DOCS[code])
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
