from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel

class ActionState(BaseModel):
    idempotency_key: str
    case_id: Optional[str] = None
    action_type: Optional[str] = None
    status: Optional[str] = None
    result: Optional[Any] = None
    attempts: Optional[int] = None
