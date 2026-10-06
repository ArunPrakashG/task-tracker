from pydantic import BaseModel


class StatusCounts(BaseModel):
    pending: int
    in_progress: int
    done: int
    cancelled: int


class SummaryOut(BaseModel):
    total: int
    by_status: StatusCounts
    overdue: int
