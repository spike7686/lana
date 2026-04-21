from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.asset_profile import AssetProfile
from app.schemas.pool import (
    ManualAddRequest,
    ManualRemoveRequest,
    PoolItem,
    PoolListResponse,
    RefreshAutoRequest,
    RefreshAutoResponse,
)
from app.services.collector.service import CollectorService
from app.services.pool.service import PoolService

router = APIRouter(prefix="/api/pool", tags=["pool"])


@router.get("", response_model=PoolListResponse)
def list_pool(
    status: Optional[str] = Query(default=None, pattern="^(active|inactive)$"),
    source: Optional[str] = Query(default=None, pattern="^(auto|manual)$"),
    db: Session = Depends(get_db),
) -> PoolListResponse:
    rows = PoolService.list_pool(db=db, status=status, source=source)
    symbols = [row.symbol for row in rows]
    sectors = {}
    if symbols:
        profiles = db.scalars(select(AssetProfile).where(AssetProfile.symbol.in_(symbols)))
        sectors = {p.symbol: p.sector for p in profiles}
    return PoolListResponse(
        items=[
            PoolItem(
                symbol=row.symbol,
                status=row.status,
                source=row.source,
                tier=(row.list_tags or {}).get("pool_tier"),
                sector=sectors.get(row.symbol),
                list_tags=row.list_tags,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    )


@router.post("/refresh-auto", response_model=RefreshAutoResponse)
def refresh_auto_pool(
    payload: RefreshAutoRequest,
    db: Session = Depends(get_db),
) -> RefreshAutoResponse:
    result = PoolService.refresh_auto_pool(
        db=db,
        binance_min_quote_volume=payload.binance_min_quote_volume,
        candidate_max_from_sources=payload.candidate_max_from_sources,
    )
    return RefreshAutoResponse(**result)


@router.post("/manual-add", response_model=PoolItem)
def manual_add(
    payload: ManualAddRequest,
    db: Session = Depends(get_db),
) -> PoolItem:
    row = PoolService.manual_add(db=db, symbol=payload.symbol)

    if payload.init_now:
        CollectorService.run_init_symbol(db=db, symbol=row.symbol, days=payload.days)

    return PoolItem(
        symbol=row.symbol,
        status=row.status,
        source=row.source,
        tier=(row.list_tags or {}).get("pool_tier"),
        sector=None,
        list_tags=row.list_tags,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/manual-remove", response_model=PoolItem)
def manual_remove(
    payload: ManualRemoveRequest,
    db: Session = Depends(get_db),
) -> PoolItem:
    row = PoolService.manual_remove(db=db, symbol=payload.symbol)
    return PoolItem(
        symbol=row.symbol,
        status=row.status,
        source=row.source,
        tier=(row.list_tags or {}).get("pool_tier"),
        sector=None,
        list_tags=row.list_tags,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
