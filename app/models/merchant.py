from __future__ import annotations
from typing import List, Optional, Any
from pydantic import BaseModel

class Merchant(BaseModel):
    merchant_id: str
    canonical_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    default_gl_code: Optional[str] = None
