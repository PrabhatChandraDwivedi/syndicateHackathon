from __future__ import annotations

import os
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.pipeline import run_pipeline
from app.harness.evidence import build_pack
from app.memory.rules import RuleStore

STATE: dict = {'run': None, 'rules': RuleStore(os.environ.get('RULES_PATH', './data/rules.json'))}

app = FastAPI(title='ReconcileOS')


def get_run() -> dict:
    if STATE['run'] is None:
        STATE['run'] = run_pipeline(db_path=':memory:', data_dir='./seed/data', policy_path=None)
    return STATE['run']


class DecisionInput(BaseModel):
    action: str
    actor_id: Optional[str] = None
    note: Optional[str] = None


@app.post("/run")
async def run_endpoint():
    run_result = run_pipeline(db_path=':memory:', data_dir='./seed/data', policy_path=None)
    STATE['run'] = run_result
    return {
        'run_id': run_result.get('run_id'),
        'counts': run_result.get('counts'),
        'exceptions': run_result.get('exceptions'),
        'audit_ok': run_result.get('audit_ok')
    }


@app.get("/cases")
async def get_cases(status: Optional[str] = Query(None), workflow: Optional[str] = Query(None)):
    run = get_run()
    cases = run.get('cases', [])
    if status is not None:
        cases = [c for c in cases if c.get('status') == status]
    if workflow is not None:
        cases = [c for c in cases if c.get('workflow') == workflow]
    return {'cases': cases}


@app.get("/cases/{case_id}")
async def get_case(case_id: str):
    run = get_run()
    case = next((c for c in run.get('cases', []) if str(c.get('case_id')) == case_id), None)
    if case is None:
        return JSONResponse(status_code=404, content={'detail': 'case not found'})
    return case


@app.post("/cases/{case_id}/decision")
async def decision(case_id: str, payload: DecisionInput):
    run = get_run()
    case = next((c for c in run.get('cases', []) if str(c.get('case_id')) == case_id), None)
    if case is None:
        return JSONResponse(status_code=404, content={'detail': 'case not found'})

    allowed_actions = {'approve', 'edit', 'reject', 'defer'}
    action = payload.action
    if action not in allowed_actions:
        return JSONResponse(status_code=400, content={'detail': 'invalid action'})

    # Record the decision in the case
    case['action'] = action
    case['actor_id'] = payload.actor_id
    case['note'] = payload.note
    case['status'] = 'recorded'
    return {'case_id': case_id, 'action': action, 'status': 'recorded'}


@app.get("/cases/{case_id}/evidence-pack")
async def evidence_pack(case_id: str):
    run = get_run()
    case = next((c for c in run.get('cases', []) if str(c.get('case_id')) == case_id), None)
    if case is None:
        return JSONResponse(status_code=404, content={'detail': 'case not found'})

    pack_bytes = build_pack(case, audit_events=[], transactions=None)
    headers = {'Content-Disposition': f'attachment; filename={case_id}_evidence.zip'}
    return Response(content=pack_bytes, media_type='application/zip', headers=headers)


@app.get("/close-readiness")
async def close_readiness(period: Optional[str] = Query(None)):
    run = get_run()
    cases = run.get('cases', [])
    total_cases = len(cases)
    auto_resolved = sum(1 for c in cases if c.get('status') == 'auto_resolved')
    needs_review = sum(1 for c in cases if c.get('status') == 'needs_review')
    readiness = round(auto_resolved / total_cases, 4) if total_cases else 0.0
    return {
        'period': period,
        'total_cases': total_cases,
        'auto_resolved': auto_resolved,
        'needs_review': needs_review,
        'readiness': readiness,
        'exceptions': run.get('exceptions')
    }


@app.get("/rules")
async def get_rules():
    rules = STATE['rules'].all_rules()
    rules_dicts = [asdict(r) for r in rules]
    return {'rules': rules_dicts}


@app.post("/rules/{rule_id}/disable")
async def disable_rule(rule_id: str):
    result = STATE['rules'].disable(rule_id)
    return {'rule_id': rule_id, 'disabled': result}


@app.get("/metrics")
async def metrics():
    run = get_run()
    return {
        'counts': run.get('counts'),
        'exceptions': run.get('exceptions'),
        'audit_ok': run.get('audit_ok'),
        'run_id': run.get('run_id')
    }


@app.get("/audit/verify")
async def audit_verify():
    run = get_run()
    return {'ok': bool(run.get('audit_ok')), 'broken_at': None}


@app.get("/health")
async def health():
    return {'status': 'ok'}


@app.post("/admin/reset")
async def admin_reset():
    STATE['run'] = None
    return {'reset': True}
