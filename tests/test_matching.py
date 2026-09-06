import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.engine.normalize import NormalizedTransaction
from app.engine.matching import (
    date_delta_days,
    find_duplicates,
    match_one,
    match_split,
    reconcile,
)

# Helper to construct NormalizedTransaction instances as described
def nt(txn_id, desc, amount, date, merchant_id=None, reference='', source='corporate_card'):
    return NormalizedTransaction(
        id=txn_id,
        source=source,
        normalized_descriptor=desc,
        merchant_id=merchant_id,
        merchant_confidence=100.0 if merchant_id else 0.0,
        amount=amount,
        date=date,
        currency='INR',
        reference=reference
    )

def test_date_delta_days_basic():
    assert date_delta_days('2026-08-03', '2026-08-05') == 2

def test_date_delta_days_none_handling():
    assert date_delta_days(None, '2026-08-05') == 999
    assert date_delta_days('2026-08-03', None) == 999

def test_find_duplicates_flag_second_as_duplicate():
    t1 = nt('A1', 'desc', 100.0, '2026-08-01')
    t2 = nt('A2', 'desc', 100.0, '2026-08-01')
    dups = find_duplicates([t1, t2])
    assert t2.id in dups
    assert dups[t2.id] == t1.id

def test_match_one_picks_same_amount_nearest_date():
    src = nt('S', 'desc', 100.0, '2026-08-01')
    t1 = nt('T1', 'desc', 100.0, '2026-08-01')
    t2 = nt('T2', 'desc', 100.0, '2026-08-05')
    m = match_one(src, [t1, t2])
    assert m.target_id == t1.id

def test_match_one_empty_targets():
    src = nt('S', 'desc', 50.0, '2026-08-01')
    m = match_one(src, [])
    assert m.method == 'none'
    assert m.target_id is None

def test_match_split_aggregates_subset_sum():
    s1 = nt('S1', 'desc', 400.0, '2026-08-01')
    s2 = nt('S2', 'desc', 850.50, '2026-08-02')
    target = nt('T', 'desc', 1250.50, '2026-08-03')
    m = match_split([s1, s2], target)
    assert m is not None
    assert set(m.source_ids) == {s1.id, s2.id}
    assert m.target_id == target.id
    assert m.method == "one_to_many"

def test_match_split_none_when_no_subset():
    s1 = nt('S1', 'desc', 400.0, '2026-08-01')
    s2 = nt('S2', 'desc', 500.0, '2026-08-02')
    target = nt('T', 'desc', 1000.0, '2026-08-03')
    m = match_split([s1, s2], target)
    assert m is None

def test_reconcile_end_to_end_duplicate_then_split_then_unmatched():
    s1 = nt('S1', 'desc', 100.0, '2026-08-01')
    s1_dup = nt('S1_dup', 'desc', 100.0, '2026-08-01')
    s2 = nt('S2', 'desc', 400.0, '2026-08-02')
    s3 = nt('S3', 'desc', 850.50, '2026-08-02')
    t_split = nt('T_SPLIT', 'desc', 1250.50, '2026-08-02')
    t_unmatched = nt('T_UNMATCH', 'desc', 300.0, '2026-08-03')
    
    matches = reconcile([s1, s1_dup, s2, s3], [t_split, t_unmatched])
    # Expect: 1 duplicate, 1 split, 1 unmatched target
    dup_count = sum(1 for m in matches if m.method == 'duplicate')
    split_count = sum(1 for m in matches if m.method == 'one_to_many')
    none_count = sum(1 for m in matches if m.method == 'none')
    assert dup_count == 1
    assert split_count == 1
    assert none_count == 1

def test_reconcile_no_double_consumption_for_targets():
    s1 = nt('S1', 'desc', 100.0, '2026-08-01')
    s1_dup = nt('S1_dup', 'desc', 100.0, '2026-08-01')
    s2 = nt('S2', 'desc', 400.0, '2026-08-02')
    s3 = nt('S3', 'desc', 850.50, '2026-08-02')
    t_split = nt('T_SPLIT', 'desc', 1250.50, '2026-08-02')
    t_unmatched = nt('T_UNMATCH', 'desc', 300.0, '2026-08-03')
    
    matches = reconcile([s1, s1_dup, s2, s3], [t_split, t_unmatched])
    # Ensure T_SPLIT is only consumed once
    consumed = [m for m in matches if m.target_id == t_split.id]
    assert len(consumed) == 1

def test_reference_matching_precedence():
    src = nt('S', 'desc', 100.0, '2026-08-01', reference='REF123')
    t_match = nt('T1', 'desc', 100.0, '2026-08-01', reference='REF123')
    t_diff = nt('T2', 'desc', 100.0, '2026-08-01', reference='DIFF')
    m = match_one(src, [t_match, t_diff])
    assert m.target_id == t_match.id

def test_empty_references_not_treated_as_reference_match():
    src = nt('S', 'desc', 50.0, '2026-08-01', reference='')
    t1 = nt('T1', 'desc', 50.0, '2026-08-01', reference='')
    t2 = nt('T2', 'desc', 50.0, '2026-08-01', reference='')
    m = match_one(src, [t1, t2])
    assert m.confidence < 1.0
    assert m.target_id in {t1.id, t2.id}

def test_same_amount_same_reference_preferred():
    src = nt('S', 'desc', 100.0, '2026-08-01', reference='REF')
    t1 = nt('T1', 'desc', 100.0, '2026-08-01', reference='REF')
    t2 = nt('T2', 'desc', 100.0, '2026-08-01', reference='OTHER')
    m = match_one(src, [t1, t2])
    assert m.target_id == t1.id

def test_full_signal_match_confidence_one():
    src = nt('S', 'desc', 200.0, '2026-08-01', reference='REF', merchant_id='M1')
    t = nt('T', 'desc', 200.0, '2026-08-01', reference='REF', merchant_id='M1')
    m = match_one(src, [t])
    assert m.confidence == 1.0
    assert m.target_id == t.id
