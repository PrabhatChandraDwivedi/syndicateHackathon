from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel

class Invoice(BaseModel):
    id: str
    invoice_number: Optional[str] = None
    entity_id: Optional[str] = None
    counterparty_id: Optional[str] = None
    invoice_type: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    taxable_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    open_amount: Optional[float] = None
    status: Optional[str] = None
    raw_payload: Optional[Any] = None
    source_file_id: Optional[str] = None
