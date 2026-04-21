from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Set, Tuple

import httpx
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.asset_pool import AssetPool
from app.services.binance.client import BinanceFuturesClient

STABLECOIN_BLACKLIST: Set[str] = {
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "TUSD",
    "DAI",
    "USDP",
}

MAJORS_BLACKLIST: Set[str] = {
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "TRX",
}


class PoolService:
    @staticmethod
    def list_pool(db: Session, status: Optional[str], source: Optional[str]) -> List[AssetPool]:
        stmt = select(AssetPool).order_by(AssetPool.symbol.asc())
        filters = []

        if status:
            filters.append(AssetPool.status == status)
        if source:
            filters.append(AssetPool.source == source)

        if filters:
            stmt = stmt.where(and_(*filters))

        return list(db.scalars(stmt))

    @staticmethod
    def manual_add(db: Session, symbol: str) -> AssetPool:
        normalized_symbol = symbol.upper().strip()
        stmt = select(AssetPool).where(AssetPool.symbol == normalized_symbol)
        row = db.scalar(stmt)

        if row is None:
            row = AssetPool(
                symbol=normalized_symbol,
                status="active",
                source="manual",
                list_tags={"manual": True},
            )
            db.add(row)
        else:
            row.status = "active"
            row.source = "manual"
            tags = dict(row.list_tags or {})
            tags["manual"] = True
            row.list_tags = tags

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def manual_remove(db: Session, symbol: str) -> AssetPool:
        normalized_symbol = symbol.upper().strip()
        stmt = select(AssetPool).where(AssetPool.symbol == normalized_symbol)
        row = db.scalar(stmt)

        if row is None:
            row = AssetPool(
                symbol=normalized_symbol,
                status="inactive",
                source="manual",
                list_tags={"manual": True, "manual_inactive": True},
            )
            db.add(row)
        else:
            row.status = "inactive"
            row.source = "manual"
            tags = dict(row.list_tags or {})
            tags["manual"] = True
            tags["manual_inactive"] = True
            row.list_tags = tags

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def refresh_auto_pool(
        db: Session,
        binance_min_quote_volume: float,
        candidate_max_from_sources: int,
    ) -> dict:
        settings = get_settings()
        client = BinanceFuturesClient()
        tradable = client.fetch_usdt_perpetual_symbols()

        symbol_to_base = {item["symbol"]: item["baseAsset"] for item in tradable}
        tradable_symbols = list(symbol_to_base.keys())

        binance_ranked = _fetch_binance_futures_gainers(
            client=client,
            allowed_symbols=set(tradable_symbols),
            min_quote_volume=Decimal(str(binance_min_quote_volume)),
        )
        coingecko_ranked = _fetch_coingecko_trending_symbols(
            base_url=settings.coingecko_api_base_url,
            timeout_seconds=settings.coingecko_http_timeout_seconds,
            allowed_symbols=set(tradable_symbols),
        )

        binance_set = set(binance_ranked)
        coingecko_set = set(coingecko_ranked)

        cross = [s for s in binance_ranked if s in coingecko_set]
        binance_only = [s for s in binance_ranked if s not in coingecko_set]
        coingecko_only = [s for s in coingecko_ranked if s not in binance_set]

        merged_order = _dedupe_keep_order(cross + binance_only + coingecko_only)
        selected_raw = merged_order[:candidate_max_from_sources]
        selected_before_filter = len(selected_raw)

        selected: List[str] = []
        for symbol in selected_raw:
            base = symbol_to_base.get(symbol, "")
            if base in STABLECOIN_BLACKLIST or base in MAJORS_BLACKLIST:
                continue
            selected.append(symbol)

        selected_set = set(selected)

        existing_rows = list(db.scalars(select(AssetPool)))
        existing_map = {row.symbol: row for row in existing_rows}

        inserted = 0
        activated = 0
        skipped_manual_inactive = 0
        core_count = 0
        tracked_count = 0

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        cross_set = set(cross)

        for symbol in selected:
            row = existing_map.get(symbol)
            tag_payload = {
                "auto_pool": True,
                "selected_at": now_iso,
                "pool_tier": "core",
                "core_last_seen_at": now_iso,
                "source_mix": {
                    "coingecko_trending": symbol in coingecko_set,
                    "binance_futures_gainer": symbol in binance_set,
                    "cross_cg_binance": symbol in cross_set,
                },
            }

            if row is None:
                db.add(
                    AssetPool(
                        symbol=symbol,
                        status="active",
                        source="auto",
                        list_tags=tag_payload,
                    )
                )
                inserted += 1
                core_count += 1
                continue

            if row.source == "manual" and row.status == "inactive":
                skipped_manual_inactive += 1
                continue

            if row.status != "active":
                activated += 1
            row.status = "active"

            if row.source == "auto":
                row.list_tags = tag_payload
            else:
                tags = dict(row.list_tags or {})
                tags.update({
                    "auto_matched": True,
                    "pool_tier": "core",
                    "core_last_seen_at": now_iso,
                    "source_mix": tag_payload["source_mix"],
                })
                row.list_tags = tags
            core_count += 1

        deactivated = 0
        for row in existing_rows:
            if row.source != "auto":
                continue
            if row.symbol in selected_set:
                continue

            tags = dict(row.list_tags or {})
            if row.status != "active":
                row.status = "active"
                activated += 1
            tags["pool_tier"] = "tracked"
            tags["retained_from_history"] = True
            tags["retained_at"] = now_iso
            row.list_tags = tags
            tracked_count += 1

        db.commit()

        return {
            "tracked_symbols": len(tradable_symbols),
            "coingecko_trending_count": len(coingecko_ranked),
            "binance_gainer_count": len(binance_ranked),
            "cross_count": len(cross),
            "core_count": core_count,
            "tracked_count": tracked_count,
            "selected_before_filter": selected_before_filter,
            "selected_after_filter": len(selected),
            "inserted": inserted,
            "activated": activated,
            "deactivated": deactivated,
            "skipped_manual_inactive": skipped_manual_inactive,
        }


def _fetch_binance_futures_gainers(
    client: BinanceFuturesClient,
    allowed_symbols: Set[str],
    min_quote_volume: Decimal,
) -> List[str]:
    tickers = client.fetch_24h_tickers()
    ranked: List[Tuple[str, Decimal]] = []

    for item in tickers:
        symbol = item.get("symbol")
        if symbol not in allowed_symbols:
            continue

        try:
            change_pct = Decimal(str(item.get("priceChangePercent", "0")))
            quote_volume = Decimal(str(item.get("quoteVolume", "0")))
        except Exception:
            continue

        if change_pct <= 0:
            continue
        if quote_volume < min_quote_volume:
            continue

        ranked.append((symbol, change_pct))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in ranked]


def _fetch_coingecko_trending_symbols(
    base_url: str,
    timeout_seconds: float,
    allowed_symbols: Set[str],
) -> List[str]:
    url = f"{base_url.rstrip('/')}/search/trending"
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    coins = payload.get("coins", []) if isinstance(payload, dict) else []
    mapped: List[str] = []

    for row in coins:
        item = row.get("item", {}) if isinstance(row, dict) else {}
        token_symbol = str(item.get("symbol", "")).upper().strip()
        if not token_symbol:
            continue
        futures_symbol = f"{token_symbol}USDT"
        if futures_symbol not in allowed_symbols:
            continue
        mapped.append(futures_symbol)

    return _dedupe_keep_order(mapped)


def _dedupe_keep_order(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
