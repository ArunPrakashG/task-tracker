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
