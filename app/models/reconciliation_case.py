from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel

class ReconciliationCase(BaseModel):
    case_id: str
    workflow: Optional[str] = None
    source_ids: Optional[List[str]] = None
    candidate_target_ids: Optional[List[str]] = None
    status: Optional[str] = None
    confidence: Optional[float] = None
    method: Optional[str] = None
    financial_impact: Optional[float] = None
    evidence: Optional[List[str]] = None
    alternatives: Optional[List[str]] = None
    exception_type: Optional[str] = None
    policy_version: Optional[str] = None
    rule_ids_used: Optional[List[str]] = None
    neatlogs_trace_id: Optional[str] = None
    token_cost_usd: Optional[float] = None
    latency_ms: Optional[float] = None
