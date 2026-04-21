from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.asset_profile import AssetProfile
from app.services.binance.client import BinanceFuturesClient


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
        )
        if coin is None:
            return None

        details = _fetch_coingecko_coin_details(
            coin_id=coin["id"],
            base_url=settings.coingecko_api_base_url,
            timeout_seconds=settings.coingecko_http_timeout_seconds,
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


def _search_coingecko_coin(query: str, base_url: str, timeout_seconds: float) -> Optional[Dict[str, Any]]:
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.get(f"{base_url.rstrip('/')}/search", params={"query": query})
        resp.raise_for_status()
        payload = resp.json()

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
) -> Dict[str, Any]:
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.get(
            f"{base_url.rstrip('/')}/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    if not isinstance(payload, dict):
        raise RuntimeError("Invalid CoinGecko coin details payload")
    return payload
