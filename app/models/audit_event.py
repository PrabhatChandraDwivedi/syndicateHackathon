from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel

class AuditEvent(BaseModel):
    seq: Optional[int] = None
    timestamp: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    case_id: Optional[str] = None
    event_type: Optional[str] = None
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    inputs_hash: Optional[str] = None
    policy_version: Optional[str] = None
    model_version: Optional[str] = None
    neatlogs_trace_id: Optional[str] = None
    prev_hash: Optional[str] = None
    this_hash: Optional[str] = None
