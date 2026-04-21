from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.base import get_db
from app.schemas.collect import (
    GapBackfillRequest,
    IncrementalRunResponse,
    InitSymbolRequest,
    TaskLogItem,
    TaskLogListResponse,
)
from app.services.collector.service import CollectorService

router = APIRouter(prefix="/api/collect", tags=["collect"])


@router.post("/init-symbol", response_model=IncrementalRunResponse)
def init_symbol(payload: InitSymbolRequest, db: Session = Depends(get_db)) -> IncrementalRunResponse:
    task = CollectorService.run_init_symbol(db=db, symbol=payload.symbol, days=payload.days)
    return IncrementalRunResponse(task_id=task.id, status=task.status)


@router.post("/incremental-run", response_model=IncrementalRunResponse)
def incremental_run(db: Session = Depends(get_db)) -> IncrementalRunResponse:
    task = CollectorService.run_incremental(db=db)
    return IncrementalRunResponse(task_id=task.id, status=task.status)


@router.post("/gap-inspect", response_model=IncrementalRunResponse)
def gap_inspect(
    hours: int = Query(default=24, ge=1, le=72),
    max_symbols: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> IncrementalRunResponse:
    task = CollectorService.run_gap_inspection(db=db, hours=hours, max_symbols=max_symbols)
    return IncrementalRunResponse(task_id=task.id, status=task.status)


@router.post("/gap-backfill", response_model=IncrementalRunResponse)
def gap_backfill(
    payload: GapBackfillRequest,
    db: Session = Depends(get_db),
) -> IncrementalRunResponse:
    task = CollectorService.run_gap_backfill(
        db=db,
        hours=payload.hours,
        max_symbols=payload.max_symbols,
        only_missing=payload.only_missing,
    )
    return IncrementalRunResponse(task_id=task.id, status=task.status)


@router.get("/tasks", response_model=TaskLogListResponse)
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    task_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, pattern="^(running|success|failed)$"),
    db: Session = Depends(get_db),
) -> TaskLogListResponse:
    records = CollectorService.list_tasks(db=db, limit=limit, task_type=task_type, status=status)
    items = [
        TaskLogItem(
            id=item.id,
            task_type=item.task_type,
            status=item.status,
            scope=item.scope,
            summary=item.summary,
            started_at=item.started_at,
            finished_at=item.finished_at,
            duration_seconds=(
                (item.finished_at - item.started_at).total_seconds()
                if item.finished_at and item.started_at
                else None
            ),
            error_message=item.error_message,
        )
        for item in records
    ]
    return TaskLogListResponse(items=items)
