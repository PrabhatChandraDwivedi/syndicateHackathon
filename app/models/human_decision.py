from __future__ import annotations
from typing import List, Optional, Any
from pydantic import BaseModel

class HumanDecision(BaseModel):
    case_id: Optional[str] = None
    actor_id: Optional[str] = None
    action: Optional[str] = None
    final_allocations: Optional[str] = None
    comment: Optional[str] = None
    created_rule_ids: Optional[List[str]] = None
