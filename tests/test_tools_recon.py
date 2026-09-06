import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.harness.notify import Outbox
from app.agent.tools_recon import build_registry


def test_draft_vendor_email_with_outbox():
    state = {'run': {'cases': []}}
    policy = {}
    outbox = Outbox(db_path=':memory:')
    registry = build_registry(state, policy, outbox=outbox)
    tool = None
    for t in getattr(registry, 'tools', []):
        if getattr(t, 'name', None) == 'draft_vendor_email':
            tool = t
            break
    assert tool is not None

    args = tool.args_model(invoice_number='INV-100', supplier_gstin='27ABCDEF', reason='test', taxable_value=0.0, tax_at_risk=0.0)
    res = tool.fn(args)
    assert res.get('ok') is True
    assert isinstance(res.get('draft_id'), int)
    assert res.get('recipient') == 'ap-27ABCDEF@vendor.invalid'
    assert 'INV-100' in res.get('subject','')
    pending = outbox.pending(limit=50)
    found_item = None
    for item in pending:
        if item.get('recipient') == 'ap-27ABCDEF@vendor.invalid' and 'INV-100' in item.get('subject',''):
            found_item = item
            break
    assert found_item is not None
    body = found_item.get('body','')
    assert '27ABCDEF' in body
    assert 'has not been sent' in body
    assert found_item.get('status') == 'pending'


def test_draft_vendor_email_outbox_none():
    state = {'run': {'cases': []}}
    policy = {}
    registry = build_registry(state, policy, outbox=None)
    tool = None
    for t in getattr(registry, 'tools', []):
        if getattr(t, 'name', None) == 'draft_vendor_email':
            tool = t
            break
    assert tool is not None

    args = tool.args_model(invoice_number='INV-101', supplier_gstin='27XYZ', reason='test', taxable_value=0.0, tax_at_risk=0.0)
    res = tool.fn(args)
    assert res == {'ok': False, 'error': 'no outbox configured'}


def test_resolve_case_duplicate_guardrail_unchanged():
    state = {'run': {'cases': [
        {'case_id': 'C-1', 'exception_type': 'duplicate_transaction', 'status': 'needs_review', 'confidence': 0.6, 'amount': 50.0}
    ]}}
    policy = {}

    registry = build_registry(state, policy)
    tool = None
    for t in getattr(registry, 'tools', []):
        if getattr(t, 'name', None) == 'resolve_case':
            tool = t
            break
    assert tool is not None

    args = tool.args_model(case_id='C-1', rationale='blocked by policy')
    res = tool.fn(args)
    assert res.get('refused') is True
    # status should remain unchanged
    assert state['run']['cases'][0]['status'] == 'needs_review'
