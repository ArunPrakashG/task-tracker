# task-tracker

A FastAPI + async SQLAlchemy + Postgres + Redis task tracker with REST API under `/api/v1`. Supports cursor-based pagination, sliding-window rate limiting, and background audit logging of task status transitions.

## Run with Docker Compose

The entire stack (API, Postgres, Redis) runs with a single command:

```bash
docker compose up --build
```

Services:
- **app**: http://localhost:8000 (API and OpenAPI docs at `/docs`)
- **db**: postgresql://localhost:5433
- **redis**: redis://localhost:6380

The database migrations run automatically on startup. The API is ready once the health endpoint responds:

```bash
curl http://localhost:8000/health
```

## Run Locally with uv

Install dependencies and set up the environment:

```bash
uv sync
cp .env.example .env
```

Start Postgres in a container:

```bash
docker run -d --name pg \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=taskdb \
  -p 5432:5432 postgres:16-alpine
```

Start Redis in a container:

```bash
docker run -d --name redis \
  -p 6379:6379 redis:7-alpine
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Start the development server:

```bash
uv run fastapi dev app/main.py
```

Or with uvicorn:

```bash
uv run uvicorn app.main:app --reload
```

OpenAPI docs: http://localhost:8000/docs

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string, e.g. `postgresql+asyncpg://user:pass@localhost:5432/dbname` |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL |
| `RATE_LIMIT_REQUESTS` | No | `30` | Max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Rate limit window duration in seconds |
| `OTEL_ENABLED` | No | — | (optional) Enable OpenTelemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | — | (optional) OpenTelemetry exporter endpoint |

## API Endpoints

All endpoints are under `/api/v1`.

| Method | Path | Status | Query Params | Description |
|---|---|---|---|---|
| POST | `/api/v1/projects` | 201 | — | Create a project |
| GET | `/api/v1/projects` | 200 | — | List all projects |
| DELETE | `/api/v1/projects/{project_id}` | 204 | — | Soft-delete a project and its tasks (rows kept, `deleted_at` set; 404 afterwards) |
| POST | `/api/v1/projects/{project_id}/tasks` | 201 | — | Create a task in a project |
| GET | `/api/v1/projects/{project_id}/tasks` | 200 | `status`, `priority`, `limit` (1–100, default 20), `cursor` | List tasks in a project with cursor pagination |
| PATCH | `/api/v1/tasks/{task_id}/status` | 200 | — | Transition a task to a new status |
| GET | `/api/v1/projects/{project_id}/summary` | 200 | — | Get a project's task summary |

All requests and responses follow the envelope format below. POST endpoints are rate-limited and return HTTP 429 with a `Retry-After` header if the limit is exceeded.

## Response Format

### Success

All successful responses follow this envelope:

```json
{
  "success": true,
  "data": { /* response data */ },
  "meta": { /* optional metadata */ }
}
```

Example (list projects):

```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Project A",
      "created_at": "2026-10-06T10:00:00Z"
    }
  ]
}
```

Example (list tasks with pagination):

```json
{
  "success": true,
  "data": [
    {
      "id": "650e8400-e29b-41d4-a716-446655440001",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Implement feature",
      "priority": "high",
      "status": "in_progress",
      "due_date": "2026-10-15",
      "created_at": "2026-10-06T10:00:00Z",
      "updated_at": "2026-10-06T11:30:00Z"
    }
  ],
  "meta": {
    "limit": 20,
    "has_more": true,
    "next_cursor": "eyJjIjoiMjAyNi0xMC0wNlQxMTozMDowMFoiLCJpIjoiNjUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDAxIn0"
  }
}
```

### Errors

All error responses follow this envelope:

```json
{
  "success": false,
  "error": {
    "detail": "descriptive message",
    "code": "ERROR_CODE",
    "field": "field_name"
  }
}
```

The `field` field is omitted when not applicable.

Example (validation error):

```json
{
  "success": false,
  "error": {
    "detail": "Input should be a valid string",
    "code": "VALIDATION_ERROR",
    "field": "name"
  }
}
```

Example (invalid status transition):

```json
{
  "success": false,
  "error": {
    "detail": "Cannot transition task from 'done' to 'in_progress'. Allowed: none",
    "code": "INVALID_STATUS_TRANSITION",
    "field": "status"
  }
}
```

Example (rate limited):

```json
{
  "success": false,
  "error": {
    "detail": "Rate limit exceeded. Retry in 32 seconds.",
    "code": "RATE_LIMITED"
  }
}
```

### Error Codes

| Code | Status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request validation failed (missing/invalid field) |
| `NOT_FOUND` | 404 | General not-found (route does not exist) |
| `PROJECT_NOT_FOUND` | 404 | Project not found |
| `TASK_NOT_FOUND` | 404 | Task not found |
| `PROJECT_NAME_CONFLICT` | 409 | Project with this name already exists |
| `INVALID_STATUS_TRANSITION` | 422 | Task status cannot transition this way |
| `INVALID_CURSOR` | 422 | Cursor is malformed or invalid |
| `RATE_LIMITED` | 429 | Rate limit exceeded; see `Retry-After` header |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Task Status State Machine

Tasks flow through these states based on the TRANSITIONS rule below. Arrows indicate allowed moves:

```
       ┌─────────────────────────────────┐
       │                                 │
       ▼                                 ▼
   PENDING ────────────────────────▶ CANCELLED
       │
       │
       ▼
   IN_PROGRESS ───────────────────▶ CANCELLED
       │
       │
       ▼
     DONE
```

Valid transitions:
- **PENDING**: can move to `IN_PROGRESS` or `CANCELLED`
- **IN_PROGRESS**: can move to `DONE` or `CANCELLED`
- **DONE**: terminal (no transitions)
- **CANCELLED**: terminal (no transitions)

Any other transition is rejected with an `INVALID_STATUS_TRANSITION` error (422).

## Pagination and Rate Limiting

### Cursor Pagination

Task listing supports opaque keyset cursor pagination:

- Query with `limit` (1–100, default 20) and optional `cursor` to fetch a page.
- Each page includes a `next_cursor` in the response metadata (null if no more pages).
- Cursor encodes the `created_at` timestamp and `id` of the last item; you must pass the exact cursor from the previous response to get the next page.

### Rate Limiting

POST endpoints (`/api/v1/projects`, `/api/v1/projects/{project_id}/tasks`) are rate-limited to **30 requests per 60 seconds** per client IP (configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`). Limits use a sliding-window algorithm backed by Redis.

When the limit is exceeded:
- The API responds with HTTP 429.
- The error code is `RATE_LIMITED`.
- The `Retry-After` header indicates how many seconds to wait before retrying.
- If Redis is unavailable, the request is allowed (fail-open).

## Background Audit Logging

When a task's status is updated via `PATCH /api/v1/tasks/{task_id}/status`, the endpoint returns immediately. A background event handler then records the transition in the database:

1. **Event emitted**: After a successful status transition, the event `task.status_changed` is emitted with:
   - `task_id`: UUID of the task
   - `project_id`: UUID of the project
   - `from_status`: previous task status
   - `to_status`: new task status
   - `changed_at`: ISO 8601 timestamp

2. **Handler**: The handler (in `app/handlers/audit.py`) listens for `task.status_changed` and inserts a record into the `task_audit_logs` table.

3. **Result**: Each status change is logged for audit, compliance and debugging purposes. The audit log is not part of the task update response; it is recorded asynchronously after the response is sent.

## Migrations

Alembic manages the database schema. Never edit an existing migration file, and never alter the database schema directly.

To make a model change:

1. Edit the model in `app/models/`.
2. Generate a new migration:
   ```bash
   uv run alembic revision --autogenerate -m "describe the change"
   ```
3. Review the generated file in `alembic/versions/`.
4. Apply it:
   ```bash
   uv run alembic upgrade head
   ```
5. Commit the migration file to git.

To check for uncommitted schema changes:

```bash
uv run alembic check
```

## Tests and Lint

### Tests

Run the test suite against a dedicated test database (created via Alembic) and test Redis instance (db 15):

```bash
uv run pytest tests/ -v
```

Tests are functional and drive the HTTP API; there are no unit tests per function.

### Lint and Format

Check code style with ruff:

```bash
uv run ruff check .
uv run ruff format --check .
```

Auto-fix style issues:

```bash
uv run ruff check --fix .
uv run ruff format .
```

## Project Layout

```
task-tracker/
├── app/
│   ├── api/v1/
│   │   ├── routes/          # Endpoint handlers (mounted under /api/v1)
│   │   └── router.py        # Route discovery and registration
│   ├── core/
│   │   ├── errors.py        # Error envelope and exception handlers
│   │   ├── responses.py     # Response envelope (success/error)
│   │   ├── pagination.py    # Cursor pagination helpers
│   │   ├── rate_limit.py    # Redis rate limiter decorator
│   │   ├── events.py        # Event emission
│   │   └── telemetry.py     # OpenTelemetry setup
│   ├── handlers/            # Event handlers (@on("event"))
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas (namespace package)
│   ├── services/            # Business logic (namespace package)
│   ├── config.py            # Settings from environment
│   ├── database.py          # SQLAlchemy async engine and session factory
│   └── main.py              # Application factory
├── alembic/
│   ├── versions/            # Migration files (auto-generated, must be committed)
│   └── env.py               # Alembic configuration
├── tests/                   # Functional tests (HTTP API only)
├── Dockerfile              # Python 3.12 slim, uv frozen install, non-root
├── docker-compose.yml      # Services: app, db (postgres:16), redis:7
├── .env.example            # Template for environment variables
├── .dockerignore           # Exclude .venv, __pycache__, etc.
├── pyproject.toml          # uv project metadata and dependencies
├── alembic.ini             # Alembic settings
└── CLAUDE.md               # Architecture conventions and tooling

## AI Usage

Every user prompt is logged automatically in `prompts.txt` by the `UserPromptSubmit` hook (`.claude/hooks/log_prompt.py`). Do not log prompts manually. When editing Claude's output by hand or submitting a revised prompt, append a comment line under the latest entry, e.g.:

```
# NOTE: edited app/models.py by hand — changed X to Y because Z
```

Never delete, reorder, or rewrite existing prompt entries.
