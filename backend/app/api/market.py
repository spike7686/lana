from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.market import KlineListResponse, KlinePoint, OIListResponse, OIPoint
from app.schemas.profile import AssetProfileResponse
from app.services.market.service import MarketService
from app.services.profile.service import ProfileService

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/market/{symbol}/kline", response_model=KlineListResponse)
def get_kline(
    symbol: str,
    interval: str = Query(pattern="^(15m|1h)$"),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> KlineListResponse:
    try:
        ProfileService.get_profile(db=db, symbol=symbol, refresh=False)
    except Exception:
        # Profile fetch should not block market data query.
        pass

    rows = MarketService.get_kline(
        db=db,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
    )
    items = [
        KlinePoint(
            symbol=row.symbol,
            open_time=row.open_time,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            quote_volume=None if row.quote_volume is None else float(row.quote_volume),
            trades=row.trades,
        )
        for row in rows
    ]
    return KlineListResponse(items=items)


@router.get("/market/{symbol}/oi", response_model=OIListResponse)
def get_oi(
    symbol: str,
    interval: str = Query(pattern="^(15m|1h)$"),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> OIListResponse:
    try:
        ProfileService.get_profile(db=db, symbol=symbol, refresh=False)
    except Exception:
        # Profile fetch should not block market data query.
        pass

    rows = MarketService.get_oi(
        db=db,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
    )
    items = [
        OIPoint(
            symbol=row.symbol,
            ts=row.ts,
            sum_open_interest=None
            if row.sum_open_interest is None
            else float(row.sum_open_interest),
            sum_open_interest_value=None
            if row.sum_open_interest_value is None
            else float(row.sum_open_interest_value),
        )
        for row in rows
    ]
    return OIListResponse(items=items)


@router.get("/market/{symbol}/profile", response_model=AssetProfileResponse)
def get_profile(
    symbol: str,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> AssetProfileResponse:
    row = ProfileService.get_profile(db=db, symbol=symbol, refresh=refresh)
    return AssetProfileResponse(
        symbol=row.symbol,
        name=row.name,
        sector=row.sector,
        description=row.description,
        website=row.website,
        twitter=row.twitter,
        extra=row.extra,
        updated_at=row.updated_at,
    )


@router.get("/export/{symbol}")
def export_symbol(
    symbol: str,
    interval: str = Query(pattern="^(15m|1h)$"),
    data_type: str = Query(alias="type", pattern="^(kline|oi)$"),
    format: str = Query(default="csv", pattern="^(csv)$"),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    if format != "csv":
        raise HTTPException(status_code=400, detail="Only csv format is supported")

    if data_type == "kline":
        header, rows = MarketService.get_kline_csv_rows(
            db=db,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
        )
    else:
        header, rows = MarketService.get_oi_csv_rows(
            db=db,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
        )

    csv_lines = [header] + [",".join(r) for r in rows]
    filename = f"{symbol.upper()}_{data_type}_{interval}.csv"
    return PlainTextResponse(
        "\n".join(csv_lines),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
