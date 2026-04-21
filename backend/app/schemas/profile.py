from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AssetProfileResponse(BaseModel):
    symbol: str
    name: Optional[str]
    sector: Optional[str]
    description: Optional[str]
    website: Optional[str]
    twitter: Optional[str]
    extra: Dict[str, Any]
    updated_at: datetime
