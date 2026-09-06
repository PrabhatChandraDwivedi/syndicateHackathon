import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.store import connect, init_db, insert_row, insert_many, query, count


def test_init_db_idempotent():
    conn = connect(':memory:')
    init_db(conn)
    init_db(conn)  # Should not raise
    # Simple sanity check that tables exist
    result = query(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='FinancialTransaction'")
    assert len(result) == 1


def test_insert_row_round_trip():
    conn = connect(':memory:')
    init_db(conn)
    row = {
        'id': 'txn1',
        'source': 'bank',
        'amount': 100.0,
        'counterparty_raw': 'TestParty'
    }
    insert_row(conn, 'FinancialTransaction', row)
    results = query(conn, 'SELECT * FROM FinancialTransaction')
    assert len(results) == 1
    res = results[0]
    # Raw value is 'txn1', not '"txn1"'
    assert res['id'] == 'txn1'
    assert res['source'] == 'bank'
    assert res['amount'] == 100.0
    assert res['counterparty_raw'] == 'TestParty'


def test_json_serialization():
    conn = connect(':memory:')
    init_db(conn)
    payload = {'nested': 'data', 'list': [1, 2, 3], 'null': None}
    row = {
        'id': 'txn2',
        'source': 'bank',
        'amount': 50.0,
        'counterparty_raw': 'Bob',
        'raw_payload': payload
    }
    insert_row(conn, 'FinancialTransaction', row)
    results = query(conn, 'SELECT raw_payload FROM FinancialTransaction WHERE id=?', ('txn2',))
    assert len(results) == 1
    # The value stored should be a JSON string
    result_str = results[0]['raw_payload']
    assert isinstance(result_str, str)
    assert '{' in result_str or result_str == 'null'


def test_count_insert_many():
    conn = connect(':memory:')
    init_db(conn)
    rows = [
        {'id': 'a', 'source': 'bank', 'amount': 10.0, 'counterparty_raw': 'A'},
        {'id': 'b', 'source': 'bank', 'amount': 20.0, 'counterparty_raw': 'B'},
        {'id': 'c', 'source': 'bank', 'amount': 30.0, 'counterparty_raw': 'C'},
    ]
    insert_many(conn, 'FinancialTransaction', rows)
    assert count(conn, 'FinancialTransaction') == 3
