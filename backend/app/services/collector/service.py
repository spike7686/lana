from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Type

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.asset_pool import AssetPool
from app.models.collector_task_log import CollectorTaskLog
from app.models.kline import Kline1h, Kline15m, OI1h, OI15m
from app.services.binance.client import (
    BinanceFuturesClient,
    paginate_klines,
    paginate_open_interest,
)
from app.services.profile.service import ProfileService

INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
}

KLINE_MODEL_MAP = {
    "15m": Kline15m,
    "1h": Kline1h,
}

OI_MODEL_MAP = {
    "15m": OI15m,
    "1h": OI1h,
}


class CollectorService:
    @staticmethod
    def run_init_symbol(db: Session, symbol: str, days: int) -> CollectorTaskLog:
        normalized_symbol = symbol.upper().strip()
        task = CollectorService._create_task(
            db=db,
            task_type="init_symbol",
            scope={"symbol": normalized_symbol, "days": days},
        )

        try:
            CollectorService._ensure_symbol_active(db=db, symbol=normalized_symbol)

            now = datetime.now(timezone.utc)
            start_dt = now - timedelta(days=days)
            start_ms = _to_ms(start_dt)
            end_ms = _last_closed_ms(now_ms=_to_ms(now), interval_ms=INTERVAL_MS["15m"])
            end_ms_1h = _last_closed_ms(now_ms=_to_ms(now), interval_ms=INTERVAL_MS["1h"])

            summary = CollectorService._collect_symbol_range(
                db=db,
                symbol=normalized_symbol,
                kline_start_ms_map={"15m": start_ms, "1h": start_ms},
                oi_start_ms_map={"15m": start_ms, "1h": start_ms},
                end_ms=end_ms,
                end_ms_1h=end_ms_1h,
            )
            try:
                profile_row = ProfileService.get_profile(db=db, symbol=normalized_symbol, refresh=False)
                summary["profile_cached"] = bool(profile_row and profile_row.extra is not None)
                summary["profile_error"] = None
            except Exception as profile_exc:
                # Profile metadata is non-critical for bootstrap data collection.
                summary["profile_cached"] = False
                summary["profile_error"] = str(profile_exc)

            CollectorService._finalize_task(db=db, task=task, status="success", summary=summary)
            return task
        except Exception as exc:
            CollectorService._finalize_task(
                db=db,
                task=task,
                status="failed",
                summary={"note": "init_symbol failed"},
                error_message=str(exc),
            )
            raise

    @staticmethod
    def run_incremental(db: Session) -> CollectorTaskLog:
        task = CollectorService._create_task(
            db=db,
            task_type="incremental_run",
            scope={"trigger": "manual"},
        )

        try:
            symbols = CollectorService._list_active_symbols(db=db)
            now_ms = _to_ms(datetime.now(timezone.utc))
            end_ms_15m = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["15m"])
            end_ms_1h = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["1h"])

            symbol_summaries = []
            for symbol in symbols:
                start_map = {
                    "15m": CollectorService._next_start_ms(db, Kline15m, symbol, INTERVAL_MS["15m"]),
                    "1h": CollectorService._next_start_ms(db, Kline1h, symbol, INTERVAL_MS["1h"]),
                }

                # OI timeline should follow its own last timestamp.
                oi_start_map = {
                    "15m": CollectorService._next_start_ms(db, OI15m, symbol, INTERVAL_MS["15m"]),
                    "1h": CollectorService._next_start_ms(db, OI1h, symbol, INTERVAL_MS["1h"]),
                }

                symbol_summary = CollectorService._collect_symbol_range(
                    db=db,
                    symbol=symbol,
                    kline_start_ms_map=start_map,
                    oi_start_ms_map=oi_start_map,
                    end_ms=end_ms_15m,
                    end_ms_1h=end_ms_1h,
                )
                symbol_summaries.append(symbol_summary)

            summary = {
                "active_symbols": len(symbols),
                "processed_symbols": len(symbol_summaries),
                "symbols": symbol_summaries,
            }
            CollectorService._finalize_task(db=db, task=task, status="success", summary=summary)
            return task
        except Exception as exc:
            CollectorService._finalize_task(
                db=db,
                task=task,
                status="failed",
                summary={"note": "incremental_run failed"},
                error_message=str(exc),
            )
            raise

    @staticmethod
    def run_gap_inspection(db: Session, hours: int, max_symbols: int) -> CollectorTaskLog:
        task = CollectorService._create_task(
            db=db,
            task_type="gap_inspect",
            scope={"hours": hours, "max_symbols": max_symbols},
        )

        try:
            summary = CollectorService.inspect_recent_gaps(
                db=db,
                hours=hours,
                max_symbols=max_symbols,
            )
            CollectorService._finalize_task(db=db, task=task, status="success", summary=summary)
            return task
        except Exception as exc:
            CollectorService._finalize_task(
                db=db,
                task=task,
                status="failed",
                summary={"note": "gap_inspect failed"},
                error_message=str(exc),
            )
            raise

    @staticmethod
    def run_gap_backfill(
        db: Session,
        hours: int,
        max_symbols: int,
        only_missing: bool = True,
    ) -> CollectorTaskLog:
        task = CollectorService._create_task(
            db=db,
            task_type="gap_backfill",
            scope={"hours": hours, "max_symbols": max_symbols, "only_missing": only_missing},
        )

        try:
            inspect_summary = CollectorService.inspect_recent_gaps(
                db=db,
                hours=hours,
                max_symbols=max_symbols,
            )
            symbols_report = inspect_summary.get("symbols", [])
            if only_missing:
                target_symbols = [
                    item["symbol"] for item in symbols_report if int(item.get("missing_total", 0)) > 0
                ]
            else:
                target_symbols = [item["symbol"] for item in symbols_report]

            now_ms = _to_ms(datetime.now(timezone.utc))
            end_ms_15m = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["15m"])
            end_ms_1h = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["1h"])
            start_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
            start_ms_raw = _to_ms(start_dt)
            start_ms_15m = _align_floor_ms(start_ms_raw, INTERVAL_MS["15m"])
            start_ms_1h = _align_floor_ms(start_ms_raw, INTERVAL_MS["1h"])

            repaired_symbols: List[dict] = []
            for symbol in target_symbols:
                data_summary = CollectorService._collect_symbol_range(
                    db=db,
                    symbol=symbol,
                    kline_start_ms_map={"15m": start_ms_15m, "1h": start_ms_1h},
                    oi_start_ms_map={"15m": start_ms_15m, "1h": start_ms_1h},
                    end_ms=end_ms_15m,
                    end_ms_1h=end_ms_1h,
                )
                repaired_symbols.append(data_summary)

            after_summary = CollectorService.inspect_recent_gaps(
                db=db,
                hours=hours,
                max_symbols=max_symbols,
            )

            summary = {
                "hours": hours,
                "max_symbols": max_symbols,
                "only_missing": only_missing,
                "targets": len(target_symbols),
                "target_symbols": target_symbols,
                "repaired_symbols": repaired_symbols,
                "before": inspect_summary,
                "after": after_summary,
            }
            CollectorService._finalize_task(db=db, task=task, status="success", summary=summary)
            return task
        except Exception as exc:
            CollectorService._finalize_task(
                db=db,
                task=task,
                status="failed",
                summary={"note": "gap_backfill failed"},
                error_message=str(exc),
            )
            raise

    @staticmethod
    def inspect_recent_gaps(db: Session, hours: int, max_symbols: int) -> dict:
        symbols = CollectorService._list_active_symbols(db=db)[:max_symbols]

        now_ms = _to_ms(datetime.now(timezone.utc))
        end_ms_15m = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["15m"])
        end_ms_1h = _last_closed_ms(now_ms=now_ms, interval_ms=INTERVAL_MS["1h"])
        start_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        start_ms_raw = _to_ms(start_dt)
        start_ms_15m = _align_floor_ms(start_ms_raw, INTERVAL_MS["15m"])
        start_ms_1h = _align_floor_ms(start_ms_raw, INTERVAL_MS["1h"])

        expected_15m = _expected_points(start_ms_15m, end_ms_15m, INTERVAL_MS["15m"])
        expected_1h = _expected_points(start_ms_1h, end_ms_1h, INTERVAL_MS["1h"])

        items: List[dict] = []
        total_missing = 0
        missing_symbols = 0

        for symbol in symbols:
            kline_15m_count = CollectorService._count_points(
                db=db, model=Kline15m, symbol=symbol, start_ms=start_ms_15m, end_ms=end_ms_15m
            )
            oi_15m_count = CollectorService._count_points(
                db=db, model=OI15m, symbol=symbol, start_ms=start_ms_15m, end_ms=end_ms_15m
            )
            kline_1h_count = CollectorService._count_points(
                db=db, model=Kline1h, symbol=symbol, start_ms=start_ms_1h, end_ms=end_ms_1h
            )
            oi_1h_count = CollectorService._count_points(
                db=db, model=OI1h, symbol=symbol, start_ms=start_ms_1h, end_ms=end_ms_1h
            )

            miss_k15 = max(0, expected_15m - kline_15m_count)
            miss_o15 = max(0, expected_15m - oi_15m_count)
            miss_k1h = max(0, expected_1h - kline_1h_count)
            miss_o1h = max(0, expected_1h - oi_1h_count)
            miss_total = miss_k15 + miss_o15 + miss_k1h + miss_o1h

            if miss_total > 0:
                missing_symbols += 1
                total_missing += miss_total

            items.append(
                {
                    "symbol": symbol,
                    "expected": {
                        "kline_15m": expected_15m,
                        "oi_15m": expected_15m,
                        "kline_1h": expected_1h,
                        "oi_1h": expected_1h,
                    },
                    "actual": {
                        "kline_15m": kline_15m_count,
                        "oi_15m": oi_15m_count,
                        "kline_1h": kline_1h_count,
                        "oi_1h": oi_1h_count,
                    },
                    "missing": {
                        "kline_15m": miss_k15,
                        "oi_15m": miss_o15,
                        "kline_1h": miss_k1h,
                        "oi_1h": miss_o1h,
                    },
                    "missing_total": miss_total,
                }
            )

        return {
            "hours": hours,
            "inspected_symbols": len(symbols),
            "missing_symbols": missing_symbols,
            "missing_points_total": total_missing,
            "window": {
                "start_15m": _from_ms(start_ms_15m).isoformat(),
                "end_15m": _from_ms(end_ms_15m).isoformat(),
                "start_1h": _from_ms(start_ms_1h).isoformat(),
                "end_1h": _from_ms(end_ms_1h).isoformat(),
            },
            "symbols": items,
        }

    @staticmethod
    def list_tasks(
        db: Session,
        limit: int,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[CollectorTaskLog]:
        stmt = select(CollectorTaskLog)
        if task_type:
            stmt = stmt.where(CollectorTaskLog.task_type == task_type)
        if status:
            stmt = stmt.where(CollectorTaskLog.status == status)
        stmt = stmt.order_by(CollectorTaskLog.started_at.desc(), CollectorTaskLog.id.desc()).limit(limit)
        return list(db.scalars(stmt))

    @staticmethod
    def init_missing_history_for_auto_symbols(
        db: Session,
        days: int,
        max_symbols: int,
    ) -> dict:
        stmt = (
            select(AssetPool.symbol)
            .where(AssetPool.source == "auto", AssetPool.status == "active")
            .order_by(AssetPool.symbol.asc())
        )
        candidates = list(db.scalars(stmt))

        initialized: List[str] = []
        initialized_items: List[dict] = []
        skipped_with_history = 0

        for symbol in candidates:
            if len(initialized) >= max_symbols:
                break

            has_kline_15m = db.scalar(select(Kline15m.symbol).where(Kline15m.symbol == symbol).limit(1))
            if has_kline_15m:
                skipped_with_history += 1
                continue

            task = CollectorService.run_init_symbol(db=db, symbol=symbol, days=days)
            initialized.append(symbol)
            initialized_items.append(
                {
                    "symbol": symbol,
                    "task_id": task.id,
                    "status": task.status,
                    "summary": task.summary,
                }
            )

        return {
            "candidates": len(candidates),
            "initialized": len(initialized),
            "initialized_symbols": initialized,
            "initialized_items": initialized_items,
            "skipped_with_history": skipped_with_history,
        }

    @staticmethod
    def _collect_symbol_range(
        db: Session,
        symbol: str,
        kline_start_ms_map: Dict[str, int],
        oi_start_ms_map: Dict[str, int],
        end_ms: int,
        end_ms_1h: Optional[int] = None,
    ) -> dict:
        client = BinanceFuturesClient()
        result = {
            "symbol": symbol,
            "kline_15m": 0,
            "kline_1h": 0,
            "oi_15m": 0,
            "oi_1h": 0,
        }

        # 15m data
        if kline_start_ms_map["15m"] <= end_ms:
            k15_rows = paginate_klines(
                client=client,
                symbol=symbol,
                interval="15m",
                interval_ms=INTERVAL_MS["15m"],
                start_ms=kline_start_ms_map["15m"],
                end_ms=end_ms,
            )
            parsed_k15 = _parse_kline_rows(symbol=symbol, rows=k15_rows)
            result["kline_15m"] = CollectorService._upsert_kline(db, "15m", parsed_k15)

        if oi_start_ms_map["15m"] <= end_ms:
            oi15_rows = paginate_open_interest(
                client=client,
                symbol=symbol,
                period="15m",
                period_ms=INTERVAL_MS["15m"],
                start_ms=oi_start_ms_map["15m"],
                end_ms=end_ms,
            )
            parsed_oi15 = _parse_oi_rows(symbol=symbol, rows=oi15_rows)
            result["oi_15m"] = CollectorService._upsert_oi(db, "15m", parsed_oi15)

        # 1h data
        end_1h = end_ms if end_ms_1h is None else end_ms_1h
        if kline_start_ms_map["1h"] <= end_1h:
            k1h_rows = paginate_klines(
                client=client,
                symbol=symbol,
                interval="1h",
                interval_ms=INTERVAL_MS["1h"],
                start_ms=kline_start_ms_map["1h"],
                end_ms=end_1h,
            )
            parsed_k1h = _parse_kline_rows(symbol=symbol, rows=k1h_rows)
            result["kline_1h"] = CollectorService._upsert_kline(db, "1h", parsed_k1h)

        if oi_start_ms_map["1h"] <= end_1h:
            oi1h_rows = paginate_open_interest(
                client=client,
                symbol=symbol,
                period="1h",
                period_ms=INTERVAL_MS["1h"],
                start_ms=oi_start_ms_map["1h"],
                end_ms=end_1h,
            )
            parsed_oi1h = _parse_oi_rows(symbol=symbol, rows=oi1h_rows)
            result["oi_1h"] = CollectorService._upsert_oi(db, "1h", parsed_oi1h)

        return result

    @staticmethod
    def _create_task(db: Session, task_type: str, scope: dict) -> CollectorTaskLog:
        task = CollectorTaskLog(
            task_type=task_type,
            status="running",
            scope=scope,
            summary={},
            started_at=datetime.now(timezone.utc),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def _finalize_task(
        db: Session,
        task: CollectorTaskLog,
        status: str,
        summary: dict,
        error_message: Optional[str] = None,
    ) -> None:
        task.status = status
        task.summary = summary
        task.error_message = error_message
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)

    @staticmethod
    def _ensure_symbol_active(db: Session, symbol: str) -> None:
        stmt: Select[tuple[AssetPool]] = select(AssetPool).where(AssetPool.symbol == symbol)
        existing = db.scalar(stmt)

        if existing is None:
            existing = AssetPool(symbol=symbol, status="active", source="manual", list_tags={})
            db.add(existing)
        else:
            existing.status = "active"
            if not existing.source:
                existing.source = "manual"
        db.commit()

    @staticmethod
    def _list_active_symbols(db: Session) -> List[str]:
        stmt = select(AssetPool.symbol).where(AssetPool.status == "active").order_by(AssetPool.symbol)
        return list(db.scalars(stmt))

    @staticmethod
    def _next_start_ms(
        db: Session,
        model: Type,
        symbol: str,
        interval_ms: int,
    ) -> int:
        ts_col = getattr(model, "open_time", None)
        if ts_col is None:
            ts_col = getattr(model, "ts")

        stmt = select(func.max(ts_col)).where(model.symbol == symbol)
        last_ts = db.scalar(stmt)

        if last_ts is None:
            return _to_ms(datetime.now(timezone.utc) - timedelta(days=30))

        return _to_ms(last_ts) + interval_ms

    @staticmethod
    def _upsert_kline(db: Session, interval: str, rows: List[dict]) -> int:
        if not rows:
            return 0

        model = KLINE_MODEL_MAP[interval]
        stmt = insert(model).values(rows)
        update_set = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "quote_volume": stmt.excluded.quote_volume,
            "trades": stmt.excluded.trades,
        }
        stmt = stmt.on_conflict_do_update(index_elements=["symbol", "open_time"], set_=update_set)
        db.execute(stmt)
        db.commit()
        return len(rows)

    @staticmethod
    def _count_points(
        db: Session,
        model: Type,
        symbol: str,
        start_ms: int,
        end_ms: int,
    ) -> int:
        ts_col = getattr(model, "open_time", None)
        if ts_col is None:
            ts_col = getattr(model, "ts")
        stmt = (
            select(func.count())
            .select_from(model)
            .where(
                model.symbol == symbol,
                ts_col >= _from_ms(start_ms),
                ts_col <= _from_ms(end_ms),
            )
        )
        result = db.scalar(stmt)
        return int(result or 0)

    @staticmethod
    def _upsert_oi(db: Session, interval: str, rows: List[dict]) -> int:
        if not rows:
            return 0

        model = OI_MODEL_MAP[interval]
        stmt = insert(model).values(rows)
        update_set = {
            "sum_open_interest": stmt.excluded.sum_open_interest,
            "sum_open_interest_value": stmt.excluded.sum_open_interest_value,
        }
        stmt = stmt.on_conflict_do_update(index_elements=["symbol", "ts"], set_=update_set)
        db.execute(stmt)
        db.commit()
        return len(rows)


def _to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _last_closed_ms(now_ms: int, interval_ms: int) -> int:
    return now_ms - (now_ms % interval_ms) - interval_ms


def _align_floor_ms(value_ms: int, interval_ms: int) -> int:
    return value_ms - (value_ms % interval_ms)


def _expected_points(start_ms: int, end_ms: int, interval_ms: int) -> int:
    if end_ms < start_ms:
        return 0
    return ((end_ms - start_ms) // interval_ms) + 1


def _parse_kline_rows(symbol: str, rows: List[list]) -> List[dict]:
    parsed = []
    for row in rows:
        parsed.append(
            {
                "symbol": symbol,
                "open_time": _from_ms(int(row[0])),
                "open": Decimal(str(row[1])),
                "high": Decimal(str(row[2])),
                "low": Decimal(str(row[3])),
                "close": Decimal(str(row[4])),
                "volume": Decimal(str(row[5])),
                "quote_volume": Decimal(str(row[7])) if row[7] is not None else None,
                "trades": int(row[8]) if row[8] is not None else None,
            }
        )
    return parsed


def _parse_oi_rows(symbol: str, rows: List[dict]) -> List[dict]:
    parsed = []
    for row in rows:
        parsed.append(
            {
                "symbol": symbol,
                "ts": _from_ms(int(row["timestamp"])),
                "sum_open_interest": Decimal(str(row.get("sumOpenInterest")))
                if row.get("sumOpenInterest") is not None
                else None,
                "sum_open_interest_value": Decimal(str(row.get("sumOpenInterestValue")))
                if row.get("sumOpenInterestValue") is not None
                else None,
            }
        )
    return parsed
