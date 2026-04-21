from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PoolItem(BaseModel):
    symbol: str
    status: str
    source: str
    tier: Optional[str] = None
    sector: Optional[str] = None
    list_tags: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PoolListResponse(BaseModel):
    items: List[PoolItem]


class RefreshAutoRequest(BaseModel):
    binance_min_quote_volume: float = Field(default=10_000_000, ge=0)
    candidate_max_from_sources: int = Field(default=100, ge=10, le=500)


class RefreshAutoResponse(BaseModel):
    tracked_symbols: int
    coingecko_trending_count: int
    binance_gainer_count: int
    cross_count: int
    core_count: int
    tracked_count: int
    selected_before_filter: int
    selected_after_filter: int
    inserted: int
    activated: int
    deactivated: int
    skipped_manual_inactive: int


class ManualAddRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    init_now: bool = False
    days: int = Field(default=30, ge=1, le=30)


class ManualRemoveRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
