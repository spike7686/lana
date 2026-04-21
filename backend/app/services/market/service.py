from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple, Type

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models.kline import Kline1h, Kline15m, OI1h, OI15m

KLINE_MODEL_MAP = {
    "15m": Kline15m,
    "1h": Kline1h,
}

OI_MODEL_MAP = {
    "15m": OI15m,
    "1h": OI1h,
}


class MarketService:
    @staticmethod
    def _apply_time_order_and_limit(
        stmt: Select,
        time_col,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> Select:
        # No explicit time window: fetch latest N rows, then caller re-sorts asc for chart display.
        if start is None and end is None:
            return stmt.order_by(desc(time_col)).limit(limit)
        return stmt.order_by(time_col.asc()).limit(limit)

    @staticmethod
    def get_kline(
        db: Session,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> Sequence:
        model = KLINE_MODEL_MAP[interval]
        stmt: Select = select(model).where(model.symbol == symbol.upper().strip())

        if start is not None:
            stmt = stmt.where(model.open_time >= start)
        if end is not None:
            stmt = stmt.where(model.open_time <= end)

        stmt = MarketService._apply_time_order_and_limit(
            stmt=stmt,
            time_col=model.open_time,
            start=start,
            end=end,
            limit=limit,
        )
        rows = list(db.scalars(stmt))
        if start is None and end is None:
            rows.reverse()
        return rows

    @staticmethod
    def get_oi(
        db: Session,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> Sequence:
        model = OI_MODEL_MAP[interval]
        stmt: Select = select(model).where(model.symbol == symbol.upper().strip())

        if start is not None:
            stmt = stmt.where(model.ts >= start)
        if end is not None:
            stmt = stmt.where(model.ts <= end)

        stmt = MarketService._apply_time_order_and_limit(
            stmt=stmt,
            time_col=model.ts,
            start=start,
            end=end,
            limit=limit,
        )
        rows = list(db.scalars(stmt))
        if start is None and end is None:
            rows.reverse()
        return rows

    @staticmethod
    def get_kline_csv_rows(
        db: Session,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> Tuple[str, List[List[str]]]:
        rows = MarketService.get_kline(db, symbol, interval, start, end, limit)
        oi_map = MarketService._get_oi_map_for_kline_export(
            db=db,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            limit=limit,
        )
        header = (
            "symbol,open_time,open,high,low,close,volume,quote_volume,trades,"
            "sum_open_interest,sum_open_interest_value"
        )
        body: List[List[str]] = []
        for row in rows:
            oi_row = oi_map.get(row.open_time)
            body.append(
                [
                    row.symbol,
                    row.open_time.isoformat(),
                    str(row.open),
                    str(row.high),
                    str(row.low),
                    str(row.close),
                    str(row.volume),
                    "" if row.quote_volume is None else str(row.quote_volume),
                    "" if row.trades is None else str(row.trades),
                    ""
                    if oi_row is None or oi_row.sum_open_interest is None
                    else str(oi_row.sum_open_interest),
                    ""
                    if oi_row is None or oi_row.sum_open_interest_value is None
                    else str(oi_row.sum_open_interest_value),
                ]
            )
        return header, body

    @staticmethod
    def get_oi_csv_rows(
        db: Session,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> Tuple[str, List[List[str]]]:
        rows = MarketService.get_oi(db, symbol, interval, start, end, limit)
        header = "symbol,ts,sum_open_interest,sum_open_interest_value"
        body: List[List[str]] = []
        for row in rows:
            body.append(
                [
                    row.symbol,
                    row.ts.isoformat(),
                    "" if row.sum_open_interest is None else str(row.sum_open_interest),
                    ""
                    if row.sum_open_interest_value is None
                    else str(row.sum_open_interest_value),
                ]
            )
        return header, body

    @staticmethod
    def _get_oi_map_for_kline_export(
        db: Session,
        symbol: str,
        interval: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: int,
    ) -> dict:
        model = OI_MODEL_MAP[interval]
        stmt: Select = select(model).where(model.symbol == symbol.upper().strip())
        if start is not None:
            stmt = stmt.where(model.ts >= start)
        if end is not None:
            stmt = stmt.where(model.ts <= end)
        stmt = MarketService._apply_time_order_and_limit(
            stmt=stmt,
            time_col=model.ts,
            start=start,
            end=end,
            limit=limit,
        )
        rows = list(db.scalars(stmt))
        if start is None and end is None:
            rows.reverse()

        result = {}
        for row in rows:
            result[row.ts] = row
        return result
