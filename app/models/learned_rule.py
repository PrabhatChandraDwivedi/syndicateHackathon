from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel

class LearnedRule(BaseModel):
    rule_id: str
    rule_type: Optional[str] = None
    pattern: Optional[str] = None
    target: Optional[str] = None
    scope: Optional[str] = None
    source_case_id: Optional[str] = None
    confidence: Optional[float] = None
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    use_count: Optional[int] = None
    status: Optional[str] = None
    never_auto: Optional[bool] = None
