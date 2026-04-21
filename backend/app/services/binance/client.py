from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from app.core.config import get_settings


INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
}


class BinanceFuturesClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.binance_fapi_base_url.rstrip("/")
        self._timeout = settings.binance_http_timeout_seconds

    def fetch_usdt_perpetual_symbols(self) -> List[Dict[str, str]]:
        payload = self._get_dict("/fapi/v1/exchangeInfo", {})
        symbols = payload.get("symbols", [])
        result: List[Dict[str, str]] = []

        for item in symbols:
            if item.get("status") != "TRADING":
                continue
            if item.get("quoteAsset") != "USDT":
                continue
            if item.get("contractType") != "PERPETUAL":
                continue
            symbol = item.get("symbol")
            base_asset = item.get("baseAsset")
            if not symbol or not base_asset:
                continue
            result.append({"symbol": symbol, "baseAsset": base_asset})

        return result

    def fetch_24h_tickers(self) -> List[dict]:
        return self._get_list("/fapi/v1/ticker/24hr", {})

    def fetch_latest_closed_kline(self, symbol: str, interval: str) -> Optional[list]:
        interval_ms = INTERVAL_MS[interval]
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        end_time_ms = now_ms - (now_ms % interval_ms) - 1

        rows = self.fetch_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=end_time_ms - interval_ms,
            end_time_ms=end_time_ms,
            limit=1,
        )
        if not rows:
            return None
        return rows[-1]

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1500,
    ) -> List[list]:
        return self._get_list(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            },
        )

    def fetch_open_interest_hist(
        self,
        symbol: str,
        period: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 500,
    ) -> List[dict]:
        return self._get_list(
            "/futures/data/openInterestHist",
            {
                "symbol": symbol,
                "period": period,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            },
        )

    def _get_list(self, path: str, params: dict) -> list:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self._base_url}{path}", params=params)
            resp.raise_for_status()
            payload = resp.json()

        if isinstance(payload, dict) and "code" in payload and "msg" in payload:
            raise RuntimeError(f"Binance API error: {payload}")
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected Binance payload type: {type(payload).__name__}")
        return payload

    def _get_dict(self, path: str, params: dict) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self._base_url}{path}", params=params)
            resp.raise_for_status()
            payload = resp.json()

        if isinstance(payload, dict) and "code" in payload and "msg" in payload:
            raise RuntimeError(f"Binance API error: {payload}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected Binance payload type: {type(payload).__name__}")
        return payload


def paginate_klines(
    client: BinanceFuturesClient,
    symbol: str,
    interval: str,
    interval_ms: int,
    start_ms: int,
    end_ms: int,
    limit: int = 1500,
) -> List[list]:
    rows: List[list] = []
    cursor = start_ms

    while cursor <= end_ms:
        batch_end = min(end_ms, cursor + interval_ms * (limit - 1))
        chunk = client.fetch_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=cursor,
            end_time_ms=batch_end,
            limit=limit,
        )

        if not chunk:
            cursor = batch_end + interval_ms
            continue

        rows.extend(chunk)
        last_open_ms = int(chunk[-1][0])
        next_cursor = last_open_ms + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    return rows


def paginate_open_interest(
    client: BinanceFuturesClient,
    symbol: str,
    period: str,
    period_ms: int,
    start_ms: int,
    end_ms: int,
    limit: int = 500,
) -> List[dict]:
    rows: List[dict] = []
    cursor = start_ms

    while cursor <= end_ms:
        batch_end = min(end_ms, cursor + period_ms * (limit - 1))
        chunk = client.fetch_open_interest_hist(
            symbol=symbol,
            period=period,
            start_time_ms=cursor,
            end_time_ms=batch_end,
            limit=limit,
        )

        if not chunk:
            cursor = batch_end + period_ms
            continue

        rows.extend(chunk)
        last_ts = int(chunk[-1]["timestamp"])
        next_cursor = last_ts + period_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    return rows
