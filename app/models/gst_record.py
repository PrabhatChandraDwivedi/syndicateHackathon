from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel

class GSTRecord(BaseModel):
    supplier_gstin: Optional[str] = None
    recipient_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    taxable_value: Optional[float] = None
    igst: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    source: Optional[str] = None
    raw_payload: Optional[Any] = None
