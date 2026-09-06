import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agent.vendor_email import NOT_SENT_NOTICE, recipient_for, subject_for, compose_draft, draft_and_enqueue, drafts_from_gst
from app.harness.notify import Outbox


def test_recipient_for():
    r = recipient_for('07AAGFF2194N1Z1')
    assert r.endswith('@vendor.invalid')
    assert isinstance(r, str)
    r2 = recipient_for(None)
    assert r2.endswith('@vendor.invalid')
    assert isinstance(r2, str)


def test_subject_for():
    s = subject_for('INV-2026-004')
    assert 'INV-2026-004' in s


def test_compose_draft_keys():
    d = compose_draft('INV-2026-004', '07AAGFF2194N1Z1', 'not filed')
    assert set(d.keys()) == {'recipient', 'subject', 'body', 'channel'}
    assert d['channel'] == 'email'


def test_compose_draft_body():
    d = compose_draft('INV-2026-004', '07AAGFF2194N1Z1', 'not filed', 12000.0, 2160.0)
    body = d['body']
    assert 'INV-2026-004' in body
    assert '07AAGFF2194N1Z1' in body
    assert '12000.00' in body
    assert '2160.00' in body
    assert NOT_SENT_NOTICE in body


def test_draft_and_enqueue():
    outbox = Outbox(':memory:')
    res = draft_and_enqueue(outbox, 'INV-2026-004', '07AAGFF2194N1Z1', 'not filed', 12000.0, 2160.0, case_id=None)
    assert res.get('ok') is True
    assert isinstance(res.get('draft_id'), int)
    assert res.get('recipient') is not None
    assert res.get('subject') is not None
    pending = outbox.pending(limit=50)
    found_item = None
    for item in pending:
        if item.get('recipient') == res.get('recipient') and item.get('subject') == res.get('subject'):
            found_item = item
            break
    assert found_item is not None
    assert found_item.get('status') == 'pending'


def test_draft_and_enqueue_no_outbox():
    res = draft_and_enqueue(None, 'INV-2026-004', '07AAGFF2194N1Z1', 'not filed')
    assert res.get('ok') is False
    assert 'error' in res


def test_drafts_from_gst_filters():
    gst_result = {'exceptions': [
        {'exception_type': 'missing_in_gstr2b', 'invoice_number': 'INV-1', 'supplier_gstin': 'ABC'},
    ]}
    outbox = Outbox(":memory:")
    result = drafts_from_gst(gst_result, outbox)
    assert result['drafted'] == 1
    assert isinstance(result['drafts'], list)
    assert len(result['drafts']) == 1
    assert result['drafts'][0]['invoice_number'] == 'INV-1'


def test_drafts_from_gst_limit():
    gst_result = {'exceptions': [
        {'exception_type': 'missing_in_gstr2b', 'invoice_number': 'INV-1', 'supplier_gstin': 'A'},
        {'exception_type': 'missing_in_gstr2b', 'invoice_number': 'INV-2', 'supplier_gstin': 'B'},
        {'exception_type': 'missing_in_gstr2b', 'invoice_number': 'INV-3', 'supplier_gstin': 'C'},
    ]}
    outbox = Outbox(":memory:")
    result = drafts_from_gst(gst_result, outbox, limit=2)
    assert result['drafted'] == 2
    assert len(result['drafts']) == 2
