from fastapi import FastAPI

app = FastAPI(title="task-tracker")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
