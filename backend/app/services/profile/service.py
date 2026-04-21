from __future__ import annotations

from datetime import datetime, timezone
import time
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.asset_profile import AssetProfile
from app.services.binance.client import BinanceFuturesClient

_coingecko_rate_lock = Lock()
_coingecko_last_request_ts = 0.0


class ProfileService:
    @staticmethod
    def get_profile(db: Session, symbol: str, refresh: bool = False) -> AssetProfile:
        normalized_symbol = symbol.upper().strip()
        existing = db.scalar(select(AssetProfile).where(AssetProfile.symbol == normalized_symbol))
        if existing is not None and not refresh:
            return existing

        payload = ProfileService._fetch_profile_payload_for_symbol(normalized_symbol)
        if payload is None:
            if existing is not None:
                return existing
            empty = AssetProfile(
                symbol=normalized_symbol,
                name=None,
                sector=None,
                description=None,
                website=None,
                twitter=None,
                extra={"status": "not_found"},
                updated_at=datetime.now(timezone.utc),
            )
            db.add(empty)
            db.commit()
            db.refresh(empty)
            return empty

        if existing is None:
            existing = AssetProfile(symbol=normalized_symbol)
            db.add(existing)

        existing.name = payload.get("name")
        existing.sector = payload.get("sector")
        existing.description = payload.get("description")
        existing.website = payload.get("website")
        existing.twitter = payload.get("twitter")
        existing.extra = payload.get("extra", {})
        existing.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(existing)
        return existing

    @staticmethod
    def _fetch_profile_payload_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
        settings = get_settings()
        base_asset = _resolve_base_asset(symbol)
        if not base_asset:
            return None

        coin = _search_coingecko_coin(
            query=base_asset,
            base_url=settings.coingecko_api_base_url,
            timeout_seconds=settings.coingecko_http_timeout_seconds,
            min_interval_seconds=settings.coingecko_min_request_interval_seconds,
            retry_count=settings.coingecko_retry_count,
            retry_base_delay_seconds=settings.coingecko_retry_base_delay_seconds,
        )
        if coin is None:
            return None

        details = _fetch_coingecko_coin_details(
            coin_id=coin["id"],
            base_url=settings.coingecko_api_base_url,
            timeout_seconds=settings.coingecko_http_timeout_seconds,
            min_interval_seconds=settings.coingecko_min_request_interval_seconds,
            retry_count=settings.coingecko_retry_count,
            retry_base_delay_seconds=settings.coingecko_retry_base_delay_seconds,
        )

        description = ((details.get("description") or {}).get("en") or "").strip()
        if len(description) > 1200:
            description = description[:1200] + "..."

        links = details.get("links") or {}
        homepage = None
        homepages = links.get("homepage") or []
        if isinstance(homepages, list):
            homepage = next((x for x in homepages if isinstance(x, str) and x.strip()), None)

        twitter = links.get("twitter_screen_name")
        twitter_url = f"https://x.com/{twitter}" if isinstance(twitter, str) and twitter else None

        categories = details.get("categories") or []
        sector = categories[0] if isinstance(categories, list) and categories else None

        return {
            "name": details.get("name"),
            "sector": sector,
            "description": description or None,
            "website": homepage,
            "twitter": twitter_url,
            "extra": {
                "coingecko_id": details.get("id"),
                "symbol": details.get("symbol"),
                "market_cap_rank": details.get("market_cap_rank"),
                "categories": categories if isinstance(categories, list) else [],
                "source": "coingecko",
            },
        }


def _resolve_base_asset(symbol: str) -> Optional[str]:
    client = BinanceFuturesClient()
    try:
        rows = client.fetch_usdt_perpetual_symbols()
    except Exception:
        return None

    for row in rows:
        if row.get("symbol") == symbol:
            return row.get("baseAsset")
    return None


def _search_coingecko_coin(
    query: str,
    base_url: str,
    timeout_seconds: float,
    min_interval_seconds: float,
    retry_count: int,
    retry_base_delay_seconds: float,
) -> Optional[Dict[str, Any]]:
    payload = _coingecko_get_json(
        path="/search",
        params={"query": query},
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        min_interval_seconds=min_interval_seconds,
        retry_count=retry_count,
        retry_base_delay_seconds=retry_base_delay_seconds,
    )

    coins = payload.get("coins", []) if isinstance(payload, dict) else []
    if not isinstance(coins, list) or not coins:
        return None

    exact_symbol = query.lower()
    for item in coins:
        symbol = str(item.get("symbol", "")).lower()
        if symbol == exact_symbol:
            return item

    return coins[0]


def _fetch_coingecko_coin_details(
    coin_id: str,
    base_url: str,
    timeout_seconds: float,
    min_interval_seconds: float,
    retry_count: int,
    retry_base_delay_seconds: float,
) -> Dict[str, Any]:
    payload = _coingecko_get_json(
        path=f"/coins/{coin_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        min_interval_seconds=min_interval_seconds,
        retry_count=retry_count,
        retry_base_delay_seconds=retry_base_delay_seconds,
    )

    if not isinstance(payload, dict):
        raise RuntimeError("Invalid CoinGecko coin details payload")
    return payload


def _coingecko_get_json(
    path: str,
    params: Dict[str, Any],
    base_url: str,
    timeout_seconds: float,
    min_interval_seconds: float,
    retry_count: int,
    retry_base_delay_seconds: float,
) -> Any:
    max_attempts = max(1, retry_count + 1)
    url = f"{base_url.rstrip('/')}{path}"
    last_error: Optional[Exception] = None

    for attempt in range(max_attempts):
        _wait_for_coingecko_slot(min_interval_seconds)
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.get(url, params=params)

            if resp.status_code == 429:
                retry_after = _parse_retry_after_seconds(resp.headers.get("Retry-After"))
                delay = max(retry_after, retry_base_delay_seconds * (2 ** attempt))
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                    continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts - 1:
                raise
            time.sleep(retry_base_delay_seconds * (2 ** attempt))

    if last_error:
        raise last_error
    raise RuntimeError("CoinGecko request failed without error")


def _wait_for_coingecko_slot(min_interval_seconds: float) -> None:
    global _coingecko_last_request_ts
    min_interval = max(0.0, min_interval_seconds)
    with _coingecko_rate_lock:
        now = time.monotonic()
        wait_seconds = (_coingecko_last_request_ts + min_interval) - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        _coingecko_last_request_ts = now


def _parse_retry_after_seconds(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        parsed = float(value)
    except Exception:
        return 0.0
    return max(0.0, parsed)
