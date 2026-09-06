from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from typing import Any

class FinancialTransaction(BaseModel):
    id: str
    source: str
    account_id: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    counterparty_raw: Optional[str] = None
    reference_raw: Optional[str] = None
    raw_payload: Optional[Any] = None
    source_file_id: Optional[str] = None
    ingested_at: Optional[str] = None
    external_id: Optional[str] = None
