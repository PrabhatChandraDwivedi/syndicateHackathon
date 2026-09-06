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


def test_drafts_from_gst_chases_both_supplier_faults():
    """An unfiled invoice AND one filed at the wrong value both put input tax
    credit at risk, so both are chased. A row that exists only in GSTR-2B is our
    own bookkeeping gap, not the supplier's, so it is left alone."""
    gst_result = {'exceptions': [
        {'exception_type': 'missing_in_gstr2b', 'invoice_number': 'INV-1', 'supplier_gstin': 'ABC'},
        {'exception_type': 'value_mismatch', 'invoice_number': 'INV-2', 'supplier_gstin': 'DEF',
         'taxable_delta': 999.0, 'tax_delta': 179.82},
        {'exception_type': 'missing_in_purchase_register', 'invoice_number': 'INV-9',
         'supplier_gstin': 'XYZ'},
    ]}
    outbox = Outbox(":memory:")
    result = drafts_from_gst(gst_result, outbox)
    assert result['drafted'] == 2
    drafted = {d['invoice_number'] for d in result['drafts']}
    assert drafted == {'INV-1', 'INV-2'}
    assert 'INV-9' not in drafted

    # Each finding gets its own message, not one generic template.
    subjects = {m['subject'] for m in outbox.pending()}
    assert any('not reflected in GSTR-2B' in s for s in subjects)
    assert any('different value' in s for s in subjects)

    # A value mismatch chases only the difference, not the whole invoice.
    mismatch = [m for m in outbox.pending() if 'different value' in m['subject']][0]
    assert '999.00' in mismatch['body']
    assert '179.82' in mismatch['body']


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
