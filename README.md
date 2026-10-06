# task-tracker

FastAPI + async SQLAlchemy + Alembic + Postgres.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync
docker run -d --name pg \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=taskdb \
  -p 5432:5432 postgres:16-alpine
echo 'DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/taskdb' > .env
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Migrations

```bash
uv run alembic upgrade head
```

## Test and lint

```bash
uv run pytest tests/ -v
uv run ruff check --fix . && uv run ruff format .
```
