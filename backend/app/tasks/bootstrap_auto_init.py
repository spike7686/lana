from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from typing import Dict

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.services.collector.service import CollectorService
from app.services.pool.service import PoolService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="首批自动池分批初始化脚本（30天K线+OI）。"
    )
    parser.add_argument("--days", type=int, default=30, help="回补天数，默认30。")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="每批初始化币种数量，默认5。",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=2.0,
        help="每批之间休眠秒数，默认2秒。",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="最大批次数；0代表直到没有可初始化币种。",
    )
    parser.add_argument(
        "--refresh-auto-pool",
        action="store_true",
        help="启动时先刷新一次自动池。",
    )
    return parser.parse_args()


def _print_symbol_row(item: dict) -> None:
    summary = item.get("summary") or {}
    print(
        "  - {symbol}: k15={k15}, k1h={k1h}, oi15={oi15}, oi1h={oi1h}, task_id={task_id}, status={status}".format(
            symbol=item.get("symbol"),
            k15=summary.get("kline_15m", 0),
            k1h=summary.get("kline_1h", 0),
            oi15=summary.get("oi_15m", 0),
            oi1h=summary.get("oi_1h", 0),
            task_id=item.get("task_id"),
            status=item.get("status"),
        )
    )


def _sum_totals(acc: Dict[str, int], item: dict) -> None:
    summary = item.get("summary") or {}
    acc["kline_15m"] += int(summary.get("kline_15m", 0))
    acc["kline_1h"] += int(summary.get("kline_1h", 0))
    acc["oi_15m"] += int(summary.get("oi_15m", 0))
    acc["oi_1h"] += int(summary.get("oi_1h", 0))


def main() -> None:
    args = parse_args()
    settings = get_settings()
    start = datetime.now(timezone.utc)
    totals: Dict[str, int] = {
        "symbols": 0,
        "kline_15m": 0,
        "kline_1h": 0,
        "oi_15m": 0,
        "oi_1h": 0,
        "rounds": 0,
    }

    print(
        "[bootstrap] started",
        {
            "start_at": start.isoformat(),
            "days": args.days,
            "batch_size": args.batch_size,
            "sleep_seconds": args.sleep_seconds,
            "max_rounds": args.max_rounds,
        },
    )

    with SessionLocal() as db:
        if args.refresh_auto_pool:
            refresh = PoolService.refresh_auto_pool(
                db=db,
                binance_min_quote_volume=settings.auto_pool_binance_min_quote_volume,
                candidate_max_from_sources=settings.auto_pool_candidate_max_from_sources,
            )
            print("[bootstrap] refresh_auto_pool", refresh)

        round_idx = 0
        while True:
            if args.max_rounds > 0 and round_idx >= args.max_rounds:
                print("[bootstrap] reach max_rounds, stop")
                break

            round_idx += 1
            totals["rounds"] = round_idx

            summary = CollectorService.init_missing_history_for_auto_symbols(
                db=db,
                days=args.days,
                max_symbols=args.batch_size,
            )

            initialized_items = summary.get("initialized_items", [])
            initialized_count = int(summary.get("initialized", 0))
            totals["symbols"] += initialized_count

            print(
                "[bootstrap] round",
                round_idx,
                {
                    "candidates": summary.get("candidates", 0),
                    "initialized": initialized_count,
                    "skipped_with_history": summary.get("skipped_with_history", 0),
                },
            )
            for item in initialized_items:
                _print_symbol_row(item)
                _sum_totals(totals, item)

            if initialized_count == 0:
                print("[bootstrap] no pending symbols, done")
                break

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    end = datetime.now(timezone.utc)
    cost = (end - start).total_seconds()
    print(
        "[bootstrap] finished",
        {
            "finished_at": end.isoformat(),
            "elapsed_seconds": round(cost, 2),
            "rounds": totals["rounds"],
            "symbols_initialized": totals["symbols"],
            "kline_15m": totals["kline_15m"],
            "kline_1h": totals["kline_1h"],
            "oi_15m": totals["oi_15m"],
            "oi_1h": totals["oi_1h"],
        },
    )


if __name__ == "__main__":
    main()

