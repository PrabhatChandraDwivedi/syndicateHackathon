from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel

class RunRecord(BaseModel):
    run_id: str
    started_at: Optional[str] = None
    policy_version: Optional[str] = None
    rule_snapshot_id: Optional[str] = None
    source_file_ids: Optional[str] = None
    neatlogs_trace_id: Optional[str] = None
    metrics_json: Optional[Any] = None
