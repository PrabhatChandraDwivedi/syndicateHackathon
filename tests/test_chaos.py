import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import copy
from app.harness.chaos import inject, ChaosConfig, summarize

def test_zero_rates():
    rows = [
        {'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'},
        {'id': 2, 'counterparty_raw': 'B', 'amount': 200, 'date': '2023-01-02'},
    ]
    config = ChaosConfig()

    result = inject(rows, config)

    assert len(result['rows']) == len(rows)
    assert all('counterparty_raw' in r for r in result['rows'])
    assert all('amount' in r and isinstance(r['amount'], (int, float)) for r in result['rows'])
    assert all(r['date'] for r in result['rows'])
    assert result['injected'] == {'duplicated': 0, 'dropped_field': 0, 'corrupted_amount': 0, 'date_skewed': 0}

def test_mutability():
    rows = [{'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'}]
    config = ChaosConfig(duplicate_rate=0.0, drop_field_rate=0.0, corrupt_amount_rate=0.0, date_skew_rate=0.0, seed=42)

    original_rows = copy.deepcopy(rows)
    original_row = copy.deepcopy(rows[0])

    injected_result = inject(rows, config)

    assert rows == original_rows
    assert rows[0] == original_row
    expected = {'rows': copy.deepcopy(original_rows), 'injected': {'duplicated': 0, 'dropped_field': 0, 'corrupted_amount': 0, 'date_skewed': 0}}
    assert injected_result == expected

def test_duplicate_rate_one():
    rows = [
        {'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'},
        {'id': 2, 'counterparty_raw': 'B', 'amount': 200, 'date': '2023-01-02'},
        {'id': 3, 'counterparty_raw': 'C', 'amount': 300, 'date': '2023-01-03'},
    ]
    config = ChaosConfig(duplicate_rate=1.0, seed=42)
    result = inject(rows, config)
    assert len(result['rows']) == len(rows) * 2
    assert result['injected']['duplicated'] == len(rows)

def test_drop_field_rate_one():
    rows = [{'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'}]
    config = ChaosConfig(drop_field_rate=1.0, seed=42)
    result = inject(rows, config)
    for row in result['rows']:
        assert 'counterparty_raw' not in row
    assert result['injected']['dropped_field'] == 1

def test_corrupt_amount_rate_one():
    rows = [{'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'}]
    config = ChaosConfig(corrupt_amount_rate=1.0, seed=42)
    result = inject(rows, config)
    for row in result['rows']:
        assert row['amount'] == 'NOT_A_NUMBER'
    assert result['injected']['corrupted_amount'] == 1

def test_date_skew_rate_one():
    rows = [{'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'}]
    config = ChaosConfig(date_skew_rate=1.0, seed=42)
    result = inject(rows, config)
    for row in result['rows']:
        assert row['date'] == ''
    assert result['injected']['date_skewed'] == 1

def test_determinism():
    rows = [
        {'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'},
        {'id': 2, 'counterparty_raw': 'B', 'amount': 200, 'date': '2023-01-02'},
    ]
    config = ChaosConfig(seed=99, duplicate_rate=0.5)

    result1 = inject(rows, config)
    result2 = inject(rows, config)

    assert result1['rows'] == result2['rows']
    assert result1['injected'] == result2['injected']

    config2 = ChaosConfig(seed=98, duplicate_rate=0.5)
    result3 = inject(rows, config2)

    assert result3['rows'] != result1['rows']

def test_summarize_contains_fault_names():
    rows = [{'id': 1, 'counterparty_raw': 'A', 'amount': 100, 'date': '2023-01-01'}]
    config = ChaosConfig(drop_field_rate=0.5, corrupt_amount_rate=0.5, date_skew_rate=0.5, seed=42)

    report = inject(rows, config)
    summary = summarize(report)

    assert 'chaos:' in summary
    assert 'duplicated' in summary
    assert 'dropped_field' in summary
    assert 'corrupted_amount' in summary
    assert 'date_skewed' in summary
