from __future__ import annotations

import inspect
import time
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

# Optional: agent components (best-effort)
try:
    from app.agent.loop import ReconciliationAgent
    from app.harness.modelrouter import ModelRouter
except Exception:
    ReconciliationAgent = None  # type: ignore
    ModelRouter = None  # type: ignore

# Data directory used by GST/Close endpoints and the pipeline
DATA_DIR = os.environ.get('DATA_DIR', './seed/data')

# Default agent goal
DEFAULT_GOAL = ("You own the month-end close. Run the reconciliation, check GST against GSTR-2B, "
                "and check the three-way month close. Review every open case: consult the learned rules "
                "and the policy, resolve what is safe to resolve, ask the human when you are genuinely unsure, "
                "and escalate anything that needs a person.")

# Global state
STATE: dict = {
    'run': None,
    'rules': RuleStore(os.environ.get('RULES_PATH', './data/rules.json')),
    'audit_writer': None,
    'audit_events': [],
    'agent': None,
    'questions': [],
    'gst': None,
    'close': None,
    'tool_history': [],
    'agent_last': None,
    'goal': DEFAULT_GOAL,
    'outbox': None
}


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
    """Return the current run, or an empty result when nothing has run yet.

    This deliberately does NOT run the pipeline lazily. Work happens because the
    agent decided to do it (or because POST /run was called explicitly), so a
    read never manufactures a run behind the caller's back.
    """
    return STATE['run'] or {}


class DecisionInput(BaseModel):
    action: str
    actor_id: Optional[str] = None
    note: Optional[str] = None


class AgentRunRequest(BaseModel):
    goal: Optional[str] = None
    max_steps: Optional[int] = None


# Internal helpers for agent integration

def _build_agent_registry(run_fn, gst_fn, close_fn):
    from app.agent.tools_recon import build_registry
    from app.policy.engine import load_policy
    policy = load_policy()
    import inspect
    sig = inspect.signature(build_registry)
    if 'outbox' in sig.parameters:
        return build_registry(
            STATE,
            policy,
            STATE.get('rules'),
            run_fn=run_fn,
            gst_fn=gst_fn,
            close_fn=close_fn,
            outbox=STATE.get('outbox')
        )
    else:
        return build_registry(
            STATE,
            policy,
            STATE.get('rules'),
            run_fn=run_fn,
            gst_fn=gst_fn,
            close_fn=close_fn,
        )


def _do_run_impl():
    rules_path = _get_run_rules_path()
    run_result = _safe_run_pipeline(rules_path=rules_path, data_dir=DATA_DIR)
    STATE['run'] = run_result
    STATE['agent_last'] = {'tool': 'run', 'result': run_result}
    STATE.setdefault('tool_history', [])
    STATE['tool_history'].append({'tool': 'run', 'result': run_result})
    return run_result


def _do_gst_impl():
    # Load seed data and reconcile GST
    paths = generate(DATA_DIR)
    purchase_path = paths.get('purchase_register')
    gstr_path = paths.get('gstr2b')

    purchase_rows = load_csv(purchase_path) if purchase_path else []
    gstr_rows = load_csv(gstr_path) if gstr_path else []

    result = reconcile_gst(purchase_rows or [], gstr_rows or [], tolerance=1.0)

    matched = result.get('matched')
    itc_at_risk = result.get('itc_at_risk')
    counts = result.get('counts', {})
    exceptions = result.get('exceptions', [])

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

    gst_result = {
        'matched': matched,
        'itc_at_risk': itc_at_risk,
        'counts': counts,
        'exceptions': exs_out
    }

    STATE['gst'] = gst_result
    STATE['agent_last'] = {'tool': 'gst', 'result': gst_result}
    STATE.setdefault('tool_history', [])
    STATE['tool_history'].append({'tool': 'gst', 'result': gst_result})

    return gst_result


def _do_close_impl():
    try:
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

        close_result = {
            'summary': summary,
            'readiness': readiness,
            'unexplained_bank': unexplained_bank,
            'rows': rows_out
        }

        STATE['close'] = close_result
        STATE['agent_last'] = {'tool': 'close', 'result': close_result}
        STATE.setdefault('tool_history', [])
        STATE['tool_history'].append({'tool': 'close', 'result': close_result})

        return close_result
    except Exception as e:
        return {'error': str(e), 'summary': {'closed': 0, 'partial': 0, 'orphan': 0, 'total': 0}, 'readiness': 0.0, 'unexplained_bank': [], 'rows': []}


# FastAPI application
app = FastAPI(title='ReconcileOS')


def _agent_run_sequence():
    # Sequence of runs for the agent: run -> gst -> close
    run_result = _do_run_impl()
    gst_result = _do_gst_impl()
    close_result = _do_close_impl()
    return {
        'run': run_result,
        'gst': gst_result,
        'close': close_result
    }


# NEW ENDPOINTS: GST and Month-Close workflows
EMPTY_GST = {'matched': 0, 'itc_at_risk': 0.0,
             'counts': {'purchase': 0, 'gstr2b': 0}, 'exceptions': [], 'ran': False}
EMPTY_CLOSE = {'summary': {'closed': 0, 'partial': 0, 'orphan': 0, 'total': 0},
               'readiness': 0.0, 'unexplained_bank': [], 'rows': [], 'ran': False}


@app.get("/gst/reconcile")
async def gst_reconcile_endpoint():
    """Report the last GST check. Reading never triggers one -- the agent does."""
    return STATE.get('gst') or dict(EMPTY_GST)


def _do_gst_impl():
    """Perform the GST check. Called by the agent's reconcile_gst tool."""
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

        out = {
            'matched': matched,
            'itc_at_risk': itc_at_risk,
            'counts': counts,
            'exceptions': exs_out,
            'ran': True,
        }
        STATE['gst'] = out
        return out
    except Exception as e:
        return {'error': str(e), 'matched': 0, 'itc_at_risk': 0.0, 'counts': {'purchase': 0, 'gstr2b': 0}, 'exceptions': [], 'ran': True}


@app.get("/close/status")
async def close_status_endpoint():
    """Report the last month-close check. Reading never triggers one."""
    return STATE.get('close') or dict(EMPTY_CLOSE)


def _do_close_impl():
    """Perform the three-way close. Called by the agent's check_month_close tool."""
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

        out = {
            'summary': summary,
            'readiness': readiness,
            'unexplained_bank': unexplained_bank,
            'rows': rows_out,
            'ran': True,
        }
        STATE['close'] = out
        return out
    except Exception as e:
        return {'error': str(e), 'summary': {'closed': 0, 'partial': 0, 'orphan': 0, 'total': 0}, 'readiness': 0.0, 'unexplained_bank': [], 'rows': [], 'ran': True}


# REST ENDPOINTS
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

    # Initialize controls
    learned_rule_id = None
    revoked_rule_id = None
    learned_happened = False

    # Safety: do not learn from unsafe exceptions
    exception_type = case.get('exception_type')
    unsafe_exceptions = {'duplicate_transaction', 'amount_mismatch', 'split_payment'}

    # REVERSAL: If the action is 'reject' and a previously learned rule exists for this case, revoke it
    if action == 'reject':
        prev_id = case.get('learned_rule_applied')
        if prev_id:
            try:
                STATE['rules'].revoke(prev_id, reason=f'reversed by human on case {case_id}')
                revoked_rule_id = prev_id
            except Exception:
                revoked_rule_id = None

    # Determine learning action and possibly learn a new rule
    if action in {'approve', 'reject'} and isinstance(pattern, str) and pattern.strip() and exception_type not in unsafe_exceptions:
        learned_action = 'auto_resolve' if action == 'approve' else 'always_review'
        try:
            learned_rule = STATE['rules'].learn(pattern, learned_action, case_id, amount=case.get('amount'))
            learned_rule_id = getattr(learned_rule, 'id', None)
            if learned_rule_id is None:
                learned_rule_id = getattr(learned_rule, 'rule_id', None)
            learned_happened = True
            case['learned_rule_applied'] = learned_rule_id
        except Exception:
            learned_rule_id = None
            learned_happened = False

    # Record application for the new learned rule if we learned one
    if learned_rule_id is not None:
        try:
            STATE['rules'].record_application(learned_rule_id)
        except Exception:
            pass

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

    return {'case_id': case_id, 'action': action, 'status': 'recorded', 'learned_rule_id': learned_rule_id, 'pattern': pattern, 'revoked_rule_id': revoked_rule_id}


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
    rules_out = []
    for r in rules:
        r_dict = asdict(r)
        # Expose additional fields if present; otherwise fill with None
        for key in ('status', 'applied_count', 'max_amount', 'learned_amount', 'revoked_reason'):
            if key not in r_dict:
                value = getattr(r, key, None)
                r_dict[key] = value if value is not None else None
        rules_out.append(r_dict)
    return {'rules': rules_out}


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
    STATE['agent'] = None
    STATE['questions'] = []
    STATE['gst'] = None
    STATE['close'] = None
    STATE['tool_history'] = []
    STATE['agent_last'] = None
    # Recreate the outbox
    try:
        STATE['outbox'] = Outbox(os.environ.get('OUTBOX_PATH', './data/outbox.db'))
    except Exception:
        STATE['outbox'] = None
    return {'reset': True}


# NEW ENDPOINTS: agent-driven workflow
@app.post("/agent/run")
async def agent_run(req: AgentRunRequest = None):
    # Build internal registry for agent (best-effort)
    def run_fn():
        return _do_run_impl()

    def gst_fn():
        return _do_gst_impl()

    def close_fn():
        return _do_close_impl()

    try:
        goal = (req.goal if req and req.goal else STATE.get('goal', DEFAULT_GOAL))
        max_steps = (req.max_steps if req and req.max_steps is not None else 8)

        registry = _build_agent_registry(run_fn, gst_fn, close_fn)

        open_cases = [
            {'case_id': c.get('case_id'), 'pattern': c.get('pattern'),
             'confidence': c.get('confidence'), 'exception_type': c.get('exception_type')}
            for c in (STATE.get('run') or {}).get('cases', [])
            if c.get('status') == 'needs_review'
        ][:10]
        try:
            router = ModelRouter()
            agent = ReconciliationAgent(registry, router=router, max_steps=max_steps)
            result = agent.run(goal, context={'open_cases': open_cases})
        except Exception as e:
            result = {'goal': goal, 'completed': False, 'summary': f'agent run failed: {e}',
                      'steps': [], 'step_count': 0, 'tool_calls': 0,
                      'stopped_reason': 'router_error'}
        tool_history = []
        if hasattr(registry, 'history'):
            try:
                for tc in registry.history():
                    tool_history.append({'name': getattr(tc, 'name', None),
                                         'ok': getattr(tc, 'ok', None),
                                         'error': getattr(tc, 'error', None)})
            except Exception:
                tool_history = []
        result['tool_history'] = tool_history
        result['questions'] = STATE.get('questions', [])
        STATE['agent'] = result
        return result
    except Exception as e:
        agent_result = {
            'goal': STATE.get('goal', DEFAULT_GOAL),
            'completed': False,
            'summary': f'router_error: {str(e)}',
            'stopped_reason': 'router_error',
            'steps': [],
            'step_count': 0,
            'tool_calls': 0,
            'tool_history': [],
            'questions': STATE.get('questions', [])
        }
        STATE['agent'] = agent_result
        return agent_result


@app.get("/agent/questions")
async def agent_questions():
    return {'questions': STATE.get('questions', [])}


@app.get("/agent/last")
async def agent_last():
    default_agent = {
        'goal': '',
        'completed': False,
        'summary': 'no agent run yet',
        'steps': [],
        'step_count': 0,
        'tool_calls': 0,
        'stopped_reason': 'no_router',
        'tool_history': [],
        'questions': []
    }
    agent = STATE.get('agent')
    if isinstance(agent, dict) and agent:
        # Ensure full shape
        for key in default_agent:
            agent.setdefault(key, default_agent[key])
        STATE['agent'] = agent
        return agent
    else:
        STATE['agent'] = default_agent
        return default_agent


# NEW: initialize outbox at import time
try:
    from app.harness.notify import Outbox
    STATE['outbox'] = Outbox(os.environ.get('OUTBOX_PATH', './data/outbox.db'))
except Exception:
    STATE['outbox'] = None


# NEW ENDPOINTS: outbox
@app.get("/outbox")
async def outbox_status():
    try:
        outbox = STATE.get('outbox')
        if outbox is None:
            return {'pending': [], 'stats': {}}
        pending = outbox.pending(limit=50)
        stats = outbox.stats()
        return {'pending': pending, 'stats': stats}
    except Exception as e:
        return {'error': str(e), 'pending': [], 'stats': {}}


@app.post("/outbox/{msg_id}/send")
async def outbox_send(msg_id: str):
    try:
        outbox = STATE.get('outbox')
        if outbox is None:
            return {'msg_id': msg_id, 'status': 'not_initialized'}
        pending = outbox.pending(limit=1000)
        found = any((p.get('id') == msg_id or p.get('msg_id') == msg_id or p.get('message_id') == msg_id) for p in pending)
        if not found:
            return JSONResponse(status_code=404, content={'detail': 'message not found'})
        outbox.mark_sent(msg_id)
        return {'msg_id': msg_id, 'status': 'sent'}
    except Exception as e:
        return {'error': str(e), 'msg_id': msg_id}


@app.post("/outbox/send-all")
async def outbox_send_all():
    try:
        outbox = STATE.get('outbox')
        if outbox is None:
            return {'attempted': 0, 'sent': 0, 'failed': 0}

        pending = outbox.pending(limit=10000)
        attempted = len(pending)
        sent = 0
        failed = 0
        for m in pending:
            mid = m.get('id') or m.get('msg_id') or m.get('message_id') or m.get('msgId')
            if mid is None:
                failed += 1
                continue
            try:
                outbox.mark_sent(mid)
                sent += 1
            except Exception:
                failed += 1

        return {'attempted': attempted, 'sent': sent, 'failed': failed}
    except Exception as e:
        return {'error': str(e), 'attempted': 0, 'sent': 0, 'failed': 0}
