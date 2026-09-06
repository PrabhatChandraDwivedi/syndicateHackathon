from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel

class OpsRecord(BaseModel):
    ops_id: str
    order_ref: Optional[str] = None
    date: Optional[str] = None
    gross_amount: Optional[float] = None
    fees: Optional[float] = None
    net_amount: Optional[float] = None
    channel: Optional[str] = None
    raw_payload: Optional[Any] = None
