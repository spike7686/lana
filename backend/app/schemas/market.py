from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class KlinePoint(BaseModel):
    symbol: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float]
    trades: Optional[int]


class KlineListResponse(BaseModel):
    items: List[KlinePoint]


class OIPoint(BaseModel):
    symbol: str
    ts: datetime
    sum_open_interest: Optional[float]
    sum_open_interest_value: Optional[float]


class OIListResponse(BaseModel):
    items: List[OIPoint]
