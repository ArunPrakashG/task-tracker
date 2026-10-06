# task-tracker

FastAPI + async SQLAlchemy + Postgres task tracker (live coding test).

## Tooling
- Python 3.11+, managed with **uv** (`uv add`, `uv run`, `uv sync`) — never call `pip` directly.
- Lint/format with **ruff**: `uv run ruff check --fix . && uv run ruff format .`
- Tests: `uv run pytest tests/ -v`
- Migrations: Alembic, files in `alembic/versions/` must be committed.
- DB: `DATABASE_URL` from `.env` (gitignored). Postgres runs in Docker container `pg`.

## prompts.txt (mandatory submission requirement)
- Every user prompt is appended to `prompts.txt` **automatically** by the
  `UserPromptSubmit` hook (`.claude/hooks/log_prompt.py`). Do NOT log prompts manually.
- Never delete, reorder, or rewrite existing prompt entries.
- When you or the user hand-edit Claude's output, or a prompt is a fix/revision, append a
  comment line under the latest entry in `prompts.txt`, e.g.
  `# NOTE: edited app/models.py by hand — changed X to Y because Z`
- Don't commit `.env`, `.venv/`, `__pycache__/`, `*.pyc`.

## Architecture conventions
- Success envelope: `{success, data, meta}`. Error envelope:
  `{success: false, error: {detail, code, field?}}` (`field` omitted when not applicable).
- Error codes: VALIDATION_ERROR 422, NOT_FOUND 404, PROJECT_NOT_FOUND 404, TASK_NOT_FOUND 404,
  PROJECT_NAME_CONFLICT 409, INVALID_STATUS_TRANSITION 422, INVALID_CURSOR 422,
  RATE_LIMITED 429, INTERNAL_ERROR 500.
- Routes live in `app/api/v1/routes/<name>.py` exposing `router`; they are auto-discovered
  and mounted under `/api/v1`.
- Event handlers live in `app/handlers/<name>.py` using `@on("event")`, and are emitted with
  `emit(background_tasks, event, payload)`.
- POST routes use `@rate_limit()` and declare `request: Request`.
- `app/schemas` and `app/services` are namespace packages (no `__init__.py`).
- Functional tests only: drive the HTTP API; no unit tests per function.
- Never edit an existing migration and never change the database schema directly; every model change gets a new Alembic revision generated with `--autogenerate`.
