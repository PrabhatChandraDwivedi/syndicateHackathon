import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine.normalize import NormalizedTransaction
from app.engine.matching import (
    date_delta_days,
    find_duplicates,
    match_one,
    match_split,
    reconcile,
    Match,
)
from app.engine.exceptions import ExceptionType


def nt(txn_id, desc, amount, date, merchant_id=None, source='corporate_card'):
    return NormalizedTransaction(
        id=txn_id,
        source=source,
        normalized_descriptor=desc,
        merchant_id=merchant_id,
        merchant_confidence=100.0 if merchant_id else 0.0,
        amount=amount,
        date=date,
        currency='INR',
    )


def test_date_delta_days_basic_and_none():
    assert date_delta_days('2026-08-03', '2026-08-05') == 2
    assert date_delta_days(None, '2026-08-05') == 999
    assert date_delta_days('2026-08-03', None) == 999


def test_find_duplicates_detects_second_of_duplicate():
    t1 = nt('t1', 'desc', 10.0, '2026-01-01')
    t2 = nt('t2', 'desc', 10.0, '2026-01-01')
    dups = find_duplicates([t1, t2])
    assert dups == {'t2': 't1'}


def test_match_one_picks_nearest_date_with_same_amount():
    s = nt('s0', 'name', 100.0, '2026-08-01')
    t1 = nt('t1', 'name', 100.0, '2026-08-02')
    t2 = nt('t2', 'name', 100.0, '2026-08-10')
    best = match_one(s, [t1, t2])
    assert best is not None
    assert best.target_id == 't1'
    assert best.method == 'one_to_one'


def test_match_one_with_empty_targets_returns_none_match():
    s = nt('s0', 'name', 100.0, '2026-08-01')
    m = match_one(s, [])
    assert m.method == 'none'
    assert m.target_id is None
    assert m.exception_type == ExceptionType.UNMATCHED_SOURCE.value


def test_match_split_subset_sum_matches_two_sources_to_one_target():
    s1 = nt('s1', 'A', 400.0, '2026-08-01')
    s2 = nt('s2', 'B', 850.50, '2026-08-02')
    t = nt('t1', 'AB', 1250.50, '2026-08-02')
    m = match_split([s1, s2], t)
    assert m is not None
    assert m.target_id == 't1'
    assert set(m.source_ids) == {'s1', 's2'}
    assert m.method == 'one_to_many'
    assert m.confidence == 0.90
    assert m.exception_type == ExceptionType.SPLIT_PAYMENT.value


def test_match_split_no_subset_returns_none():
    s1 = nt('s1', 'A', 100.0, '2026-08-01')
    s2 = nt('s2', 'B', 100.0, '2026-08-01')
    t = nt('t1', 'target', 301.0, '2026-08-02')
    m = match_split([s1, s2], t)
    assert m is None


def test_reconcile_end_to_end_produces_expected_match_types_and_uniqueness():
    # Create duplicates (s2 and s3 duplicates of s1)
    s1 = nt('s1', 'dup', 400.0, '2026-08-01', merchant_id='m1')
    s2 = nt('s2', 'dup', 400.0, '2026-08-01', merchant_id='m1')
    s3 = nt('s3', 'dup', 400.0, '2026-08-01', merchant_id='m1')
    # A second source to be sum with s1 to form a subset-sum match
    s4 = nt('s4', 'sum', 850.50, '2026-08-02', merchant_id='m1')
    t1 = nt('t1', 'sum', 1250.50, '2026-08-02', merchant_id='m1')
    t2 = nt('t2', 'leftover', 500.0, '2026-08-05', merchant_id='m1')
    
    matches = reconcile([s1, s2, s3, s4], [t1, t2])
    
    # expect at least one duplicate match, one one_to_many match, and one unmatched_target
    has_dup = any(m.method == 'duplicate' for m in matches)
    has_one_to_many = any(m.method == 'one_to_many' for m in matches)
    has_unmatched_target = any(
        m.method == 'none' and m.exception_type == ExceptionType.UNMATCHED_TARGET.value for m in matches
    )
    assert has_dup and has_one_to_many and has_unmatched_target

    # Ensure no target is consumed twice
    target_ids = [m.target_id for m in matches if m.target_id is not None]
    assert len(target_ids) == len(set(target_ids))

    # Ensure exception_type is None or string
    assert all(m.exception_type is None or isinstance(m.exception_type, str) for m in matches)
