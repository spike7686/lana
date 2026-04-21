from __future__ import annotations

import time
from threading import Lock
from typing import Any, Callable, Dict, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.db.base import SessionLocal
from app.services.collector.service import CollectorService
from app.services.pool.service import PoolService

_scheduler: Optional[BackgroundScheduler] = None
_cycle_lock = Lock()
_stats_lock = Lock()
_failure_stats: Dict[str, Dict[str, Any]] = {
    "refresh_auto_pool": {"total_failures": 0, "consecutive_failures": 0, "last_error": None},
    "auto_init_missing_history": {"total_failures": 0, "consecutive_failures": 0, "last_error": None},
    "incremental_run": {"total_failures": 0, "consecutive_failures": 0, "last_error": None},
    "daily_gap_inspect": {"total_failures": 0, "consecutive_failures": 0, "last_error": None},
}


def _mark_success(step_name: str) -> None:
    with _stats_lock:
        if step_name in _failure_stats:
            _failure_stats[step_name]["consecutive_failures"] = 0
            _failure_stats[step_name]["last_error"] = None


def _mark_failure(step_name: str, error: str) -> None:
    with _stats_lock:
        if step_name not in _failure_stats:
            return
        _failure_stats[step_name]["total_failures"] += 1
        _failure_stats[step_name]["consecutive_failures"] += 1
        _failure_stats[step_name]["last_error"] = error


def _snapshot_failure_stats() -> Dict[str, Dict[str, Any]]:
    with _stats_lock:
        return {
            key: {
                "total_failures": value["total_failures"],
                "consecutive_failures": value["consecutive_failures"],
                "last_error": value["last_error"],
            }
            for key, value in _failure_stats.items()
        }


def _run_with_retry(
    step_name: str,
    fn: Callable[[], Any],
    retry_count: int,
    retry_delay_seconds: float,
) -> Tuple[bool, Any, Optional[str], int]:
    attempts = 0
    last_error: Optional[str] = None
    max_attempts = max(1, retry_count + 1)

    while attempts < max_attempts:
        attempts += 1
        try:
            result = fn()
            _mark_success(step_name)
            return True, result, None, attempts
        except Exception as exc:
            last_error = str(exc)
            _mark_failure(step_name, last_error)
            is_last = attempts >= max_attempts
            print(
                "[scheduler] step failed",
                {
                    "step": step_name,
                    "attempt": attempts,
                    "max_attempts": max_attempts,
                    "error": last_error,
                    "will_retry": not is_last,
                },
            )
            if not is_last and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)

    return False, None, last_error, attempts


def run_pool_collect_cycle() -> None:
    locked = _cycle_lock.acquire(blocking=False)
    if not locked:
        print("[scheduler] skip cycle: previous cycle still running")
        return

    try:
        settings = get_settings()
        with SessionLocal() as db:
            refresh_summary: dict = {}
            init_summary: dict = {
                "candidates": 0,
                "initialized": 0,
                "initialized_symbols": [],
                "initialized_items": [],
                "skipped_with_history": 0,
            }
            incremental_task = None

            refresh_ok, refresh_result, refresh_error, refresh_attempts = _run_with_retry(
                step_name="refresh_auto_pool",
                fn=lambda: PoolService.refresh_auto_pool(
                    db=db,
                    binance_min_quote_volume=settings.auto_pool_binance_min_quote_volume,
                    candidate_max_from_sources=settings.auto_pool_candidate_max_from_sources,
                ),
                retry_count=settings.scheduler_step_retry_count,
                retry_delay_seconds=settings.scheduler_step_retry_delay_seconds,
            )
            if refresh_ok:
                refresh_summary = refresh_result
            else:
                refresh_summary = {"error": refresh_error}

            if settings.auto_init_new_symbols:
                init_ok, init_result, init_error, init_attempts = _run_with_retry(
                    step_name="auto_init_missing_history",
                    fn=lambda: CollectorService.init_missing_history_for_auto_symbols(
                        db=db,
                        days=settings.auto_init_days,
                        max_symbols=settings.auto_init_max_symbols_per_cycle,
                    ),
                    retry_count=settings.scheduler_step_retry_count,
                    retry_delay_seconds=settings.scheduler_step_retry_delay_seconds,
                )
                if init_ok:
                    init_summary = init_result
                else:
                    init_summary = {"error": init_error}
            else:
                init_attempts = 0

            # Must run regardless of refresh/init outcome.
            inc_ok, inc_result, inc_error, inc_attempts = _run_with_retry(
                step_name="incremental_run",
                fn=lambda: CollectorService.run_incremental(db=db),
                retry_count=settings.scheduler_step_retry_count,
                retry_delay_seconds=settings.scheduler_step_retry_delay_seconds,
            )
            if inc_ok:
                incremental_task = inc_result

            print(
                "[scheduler] cycle done",
                {
                    "refresh": {
                        "ok": refresh_ok,
                        "attempts": refresh_attempts,
                        "summary": refresh_summary,
                    },
                    "auto_init": {
                        "enabled": settings.auto_init_new_symbols,
                        "ok": True if not settings.auto_init_new_symbols else init_ok,
                        "attempts": init_attempts,
                        "summary": init_summary,
                    },
                    "incremental": {
                        "ok": inc_ok,
                        "attempts": inc_attempts,
                        "task_id": incremental_task.id if incremental_task else None,
                        "status": incremental_task.status if incremental_task else "failed",
                        "error": inc_error,
                    },
                    "failure_stats": _snapshot_failure_stats(),
                },
            )
    except Exception as exc:
        print("[scheduler] cycle fatal", {"error": str(exc), "failure_stats": _snapshot_failure_stats()})
    finally:
        _cycle_lock.release()


def run_daily_gap_inspection() -> None:
    locked = _cycle_lock.acquire(blocking=False)
    if not locked:
        print("[scheduler] skip daily gap inspection: previous cycle still running")
        return

    try:
        settings = get_settings()
        with SessionLocal() as db:
            ok, task, error, attempts = _run_with_retry(
                step_name="daily_gap_inspect",
                fn=lambda: CollectorService.run_gap_inspection(
                    db=db,
                    hours=settings.gap_check_hours,
                    max_symbols=settings.gap_check_max_symbols,
                ),
                retry_count=settings.scheduler_step_retry_count,
                retry_delay_seconds=settings.scheduler_step_retry_delay_seconds,
            )
            print(
                "[scheduler] daily gap inspection done",
                {
                    "ok": ok,
                    "attempts": attempts,
                    "task_id": task.id if ok and task else None,
                    "status": task.status if ok and task else "failed",
                    "error": error,
                    "failure_stats": _snapshot_failure_stats(),
                },
            )
    except Exception as exc:
        print(
            "[scheduler] daily gap inspection fatal",
            {"error": str(exc), "failure_stats": _snapshot_failure_stats()},
        )
    finally:
        _cycle_lock.release()


def start_scheduler() -> None:
    global _scheduler

    settings = get_settings()
    if not settings.scheduler_enabled:
        print("[scheduler] disabled by config")
        return

    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    _scheduler.add_job(
        run_pool_collect_cycle,
        trigger="interval",
        minutes=settings.scheduler_interval_minutes,
        id="pool_collect_cycle",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    if settings.gap_check_enabled:
        _scheduler.add_job(
            run_daily_gap_inspection,
            trigger="cron",
            hour=settings.gap_check_hour,
            minute=settings.gap_check_minute,
            id="daily_gap_inspection",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
    _scheduler.start()
    print(
        "[scheduler] started",
        {
            "interval_minutes": settings.scheduler_interval_minutes,
            "timezone": settings.scheduler_timezone,
            "step_retry_count": settings.scheduler_step_retry_count,
            "step_retry_delay_seconds": settings.scheduler_step_retry_delay_seconds,
            "gap_check_enabled": settings.gap_check_enabled,
            "gap_check_hour": settings.gap_check_hour,
            "gap_check_minute": settings.gap_check_minute,
        },
    )

    if settings.scheduler_run_on_startup:
        run_pool_collect_cycle()


def stop_scheduler() -> None:
    global _scheduler

    if _scheduler is None:
        return

    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] stopped")
    _scheduler = None
