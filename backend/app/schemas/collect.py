from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InitSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    days: int = Field(default=30, ge=1, le=30)


class IncrementalRunResponse(BaseModel):
    task_id: int
    status: str


class GapBackfillRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=72)
    max_symbols: int = Field(default=200, ge=1, le=1000)
    only_missing: bool = True


class TaskLogItem(BaseModel):
    id: int
    task_type: str
    status: str
    scope: dict
    summary: dict
    started_at: datetime
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    error_message: Optional[str]


class TaskLogListResponse(BaseModel):
    items: list[TaskLogItem]
