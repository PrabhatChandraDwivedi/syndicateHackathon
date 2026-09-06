from __future__ import annotations

import inspect
from typing import Optional

import os
from dataclasses import asdict
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.pipeline import run_pipeline
from app.harness.evidence import build_pack
from app.memory.rules import RuleStore
from app.harness.audit import AuditWriter
from app.harness.tracing import trace_id

from app.engine.gst import reconcile_gst
from app.engine.close import three_way_match
from app.adapters.csv_source import load_csv
from seed.generate import generate

# Data directory used by GST/Close endpoints and the pipeline
DATA_DIR = os.environ.get('DATA_DIR', './seed/data')

# Global state
STATE: dict = {
    'run': None,
    'rules': RuleStore(os.environ.get('RULES_PATH', './data/rules.json')),
    'audit_writer': None,
    'audit_events': []
}

# FastAPI application
app = FastAPI(title='ReconcileOS')


def get_audit_writer() -> AuditWriter:
    aw = STATE.get('audit_writer')
    if aw is None:
        # Auditor uses the same DB/file path as the environment specifies
        db_path = os.environ.get('AUDIT_DB_PATH', './data/audit.db')
        aw = AuditWriter(db_path)
        STATE['audit_writer'] = aw
    return aw


def _safe_run_pipeline(rules_path: Optional[str] = None, data_dir: Optional[str] = None):
    # Use the module-level DATA_DIR by default to keep datasets in sync
    dir_to_use = data_dir if data_dir is not None else DATA_DIR
    # Attempt to call the new signature if present; fall back to legacy if needed
    base_kw = {'db_path': ':memory:', 'data_dir': dir_to_use, 'policy_path': None}
    try:
        sig = inspect.signature(run_pipeline)
        # Build kwargs only from parameters that exist
        if 'rules_path' in sig.parameters:
            base_kw['rules_path'] = rules_path
        if 'use_llm' in sig.parameters:
            base_kw['use_llm'] = True
        return run_pipeline(**base_kw)
    except Exception:
        # Fallback to legacy call (best-effort)
        return run_pipeline(db_path=':memory:', data_dir=dir_to_use, policy_path=None)


def _get_run_rules_path() -> Optional[str]:
    return os.environ.get('RULES_PATH', './data/rules.json')


def get_run() -> dict:
    if STATE['run'] is None:
        rules_path = _get_run_rules_path()
        STATE['run'] = _safe_run_pipeline(rules_path=rules_path)
    return STATE['run']


class DecisionInput(BaseModel):
    action: str
    actor_id: Optional[str] = None
    note: Optional[str] = None


@app.post("/run")
async def run_endpoint():
    # Pass through rules path so learned rules are honored
    rules_path = _get_run_rules_path()
    run_result = _safe_run_pipeline(rules_path=rules_path, data_dir=DATA_DIR)
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

    # Prepare before_state and pattern
    before_state = case.get('status')
    pattern = case.get('pattern')

    # Determine learning action
    learned_rule_id = None
    learned_happened = False

    # Safety: if exception_type is in unsafe set, do not learn
    exception_type = case.get('exception_type')
    unsafe_exceptions = {'duplicate_transaction', 'amount_mismatch', 'split_payment'}

    # Only learn for approve/reject and only if there's a non-empty pattern and not unsafe
    if action in {'approve', 'reject'} and isinstance(pattern, str) and pattern.strip() and exception_type not in unsafe_exceptions:
        learned_action = 'auto_resolve' if action == 'approve' else 'always_review'
        # Learn and capture the learned rule id if available
        try:
            learned_rule = STATE['rules'].learn(pattern, learned_action, case_id)
            learned_rule_id = getattr(learned_rule, 'id', None)
            if learned_rule_id is None:
                learned_rule_id = getattr(learned_rule, 'rule_id', None)
            learned_happened = True
            # Attach learned_rule_applied to the case for visibility
            case['learned_rule_applied'] = learned_rule_id
        except Exception:
            # If learning fails for any reason, do not crash the API; just don't attach a rule
            learned_rule_id = None
            learned_happened = False

    # Write HUMAN DECISION AUDIT EVENT
    actor_id = payload.actor_id or 'finance_user_01'
    audit_event = {
        'event_type': 'human_decision',
        'actor_type': 'human',
        'actor_id': actor_id,
        'case_id': case_id,
        'before_state': before_state,
        'after_state': action,
        'neatlogs_trace_id': trace_id(),
        'pattern': pattern
    }
    try:
        writer = get_audit_writer()
        writer.append(audit_event)
    except Exception:
        # If auditing fails, still continue; do not block user flow
        pass
    STATE['audit_events'].append(audit_event)

    # Update the case in STATE/UI representation
    case['human_action'] = action
    case['actor_id'] = actor_id
    case['note'] = payload.note
    if action == 'approve':
        case['status'] = 'auto_resolved'
    elif action == 'reject':
        case['status'] = 'needs_review'
    # For 'edit'/'defer' we do not modify status per spec

    return {'case_id': case_id, 'action': action, 'status': 'recorded', 'learned_rule_id': learned_rule_id, 'pattern': pattern}


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


@app.get("/audit")
async def audit():
    # Return all human decision/audit events accumulated in this process
    return {'audit': STATE.get('audit_events', [])}


@app.get("/audit/verify")
async def audit_verify():
    writer = get_audit_writer()
    ok = False
    broken_at = None
    try:
        result = writer.verify_chain()
        ok = bool(result)
    except Exception:
        ok = False
    return {'ok': ok, 'broken_at': broken_at}


@app.get("/health")
async def health():
    return {'status': 'ok'}


@app.post("/admin/reset")
async def admin_reset():
    STATE['run'] = None
    return {'reset': True}


# NEW ENDPOINTS: GST and Month-Close workflows
@app.get("/gst/reconcile")
async def gst_reconcile_endpoint():
    try:
        # Ensure seed CSVs exist and load them
        paths = generate(DATA_DIR)
        purchase_path = paths.get('purchase_register')
        gstr_path = paths.get('gstr2b')

        purchase_rows = load_csv(purchase_path) if purchase_path else []
        gstr_rows = load_csv(gstr_path) if gstr_path else []

        # Run GST reconciliation
        result = reconcile_gst(purchase_rows or [], gstr_rows or [], tolerance=1.0)

        matched = result.get('matched')
        itc_at_risk = result.get('itc_at_risk')
        counts = result.get('counts', {})
        exceptions = result.get('exceptions', [])

        # Convert dataclasses to dicts and enrich with invoice_number and supplier_gstin
        exs_out = []
        for ex in exceptions:
            ex_dict = asdict(ex)
            purchase_row = ex_dict.get('purchase_row')
            gstr_row = ex_dict.get('gstr_row')
            invoice_number = ''
            supplier_gstin = ''
            if isinstance(purchase_row, dict):
                invoice_number = purchase_row.get('invoice_number') or purchase_row.get('invoice') or ''
                supplier_gstin = purchase_row.get('supplier_gstin') or ''
            if not invoice_number and isinstance(gstr_row, dict):
                invoice_number = gstr_row.get('invoice_number') or gstr_row.get('invoice') or ''
                if not supplier_gstin:
                    supplier_gstin = gstr_row.get('supplier_gstin') or ''
            ex_dict['invoice_number'] = invoice_number
            ex_dict['supplier_gstin'] = supplier_gstin
            exs_out.append(ex_dict)

        return {
            'matched': matched,
            'itc_at_risk': itc_at_risk,
            'counts': counts,
            'exceptions': exs_out
        }
    except Exception as e:
        return {'error': str(e), 'matched': 0, 'itc_at_risk': 0.0, 'counts': {'purchase': 0, 'gstr2b': 0}, 'exceptions': []}


@app.get("/close/status")
async def close_status_endpoint():
    try:
        # Ensure seed CSVs exist and load them
        paths = generate(DATA_DIR)
        ops_path = paths.get('ops')
        erp_path = paths.get('erp')
        settlements_path = paths.get('settlements')

        ops_rows = load_csv(ops_path) if ops_path else []
        erp_rows = load_csv(erp_path) if erp_path else []
        settlements_rows = load_csv(settlements_path) if settlements_path else []

        result = three_way_match(ops_rows or [], erp_rows or [], settlements_rows or [], tolerance=0.01)

        rows = result.get('rows', [])
        rows_out = [asdict(r) for r in rows]

        summary = result.get('summary', {})
        readiness = result.get('readiness', 0.0)
        unexplained_bank = result.get('unexplained_bank', [])

        return {
            'summary': summary,
            'readiness': readiness,
            'unexplained_bank': unexplained_bank,
            'rows': rows_out
        }
    except Exception as e:
        return {'error': str(e), 'summary': {'closed': 0, 'partial': 0, 'orphan': 0, 'total': 0}, 'readiness': 0.0, 'unexplained_bank': [], 'rows': []}
