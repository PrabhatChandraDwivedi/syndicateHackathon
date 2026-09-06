from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Any
from . import core as core  # type: ignore

app = FastAPI()

class RunResponse(BaseModel):
    run_id: str
    neatlogs_trace_id: Optional[str] = None

class IngestResponse(BaseModel):
    status: str

class GenericResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None

@app.post("/ingest/{source}")
async def ingest_source(source: str):
    return IngestResponse(status="ok")

@app.post("/run")
async def run():
    return RunResponse(run_id="run_001", neatlogs_trace_id="trace_001")

@app.get("/close-readiness")
async def close_readiness(period: Optional[str] = None):
    return GenericResponse(ok=True, data={"period": period, "readiness": 0.5})

@app.get("/cases")
async def cases(status: Optional[str] = None, workflow: Optional[str] = None):
    return {"cases": []}

@app.get("/cases/{case_id}")
async def case_detail(case_id: str):
    return {"case_id": case_id, "evidence": []}

@app.post("/cases/{case_id}/decision")
async def decision(case_id: str):
    return {"case_id": case_id, "status": "queued"}

@app.get("/rules")
async def rules():
    return {"rules": []}

@app.post("/rules/{id}/disable")
async def disable_rule(id: str):
    return {"disabled": id}

@app.get("/audit")
async def audit(case_id: Optional[str] = None):
    return {"audit": []}

@app.get("/audit/verify")
async def audit_verify():
    return {"ok": True, "broken_at": None}

@app.get("/cases/{case_id}/evidence-pack")
async def evidence_pack(case_id: str):
    return {"zip": None}

@app.get("/runs")
async def runs():
    return {"runs": []}

@app.get("/runs/{id}")
async def run_detail(id: str):
    return {"run_id": id}

@app.get("/metrics")
async def metrics():
    return {"metrics": {}}

@app.post("/admin/reset")
async def admin_reset():
    return {"reset": "seed"}
