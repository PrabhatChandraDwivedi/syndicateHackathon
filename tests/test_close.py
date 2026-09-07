import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.engine.close import three_way_match


def rows_to_tuples(res):
    return [
        (
            r.order_ref,
            r.ops_id,
            r.erp_id,
            r.bank_id,
            r.status,
            r.ops_net,
            r.erp_amount,
            r.bank_amount,
            r.variance,
        )
        for r in res['rows']
    ]


def test_closed_single_row():
    ops = [
        {'order_ref': 'ORD-5001', 'gross_amount': '100.00', 'fees': '0.00', 'net_amount': '100.00'},
    ]
    erp = [
        {'order_ref': 'ORD-5001', 'id': 'ERP5001', 'amount': '100.00'}
    ]
    bank = [
        {'reference_raw': 'ORD-5001', 'id': 'BANK5001', 'amount': '100.00'}
    ]
    result = three_way_match(ops, erp, bank)
    rows = result['rows']
    assert len(rows) == 1
    row = rows[0]
    assert row.order_ref == 'ORD-5001'
    assert row.ops_id is None
    assert row.erp_id == 'ERP5001'
    assert row.bank_id == 'BANK5001'
    assert row.status == 'closed'
    assert row.ops_net == 100.0
    assert row.erp_amount == 100.0
    assert row.bank_amount == 100.0
    assert row.variance == 0.0
    assert result['readiness'] == 1.0
    assert result['summary'] == {'closed': 1, 'partial': 0, 'orphan': 0, 'total': 1}
    assert result['unexplained_bank'] == []


def test_all_numeric_strings_match_float_version():
    ops_str = [
        {'order_ref': 'abc-2', 'gross_amount': '50.50', 'fees': '0.50', 'net_amount': '50.00'}
    ]
    erp_str = [
        {'order_ref': 'ABC-2', 'id': 'ERP2', 'amount': '50.00'}
    ]
    bank_str = [
        {'reference_raw': 'abc-2', 'id': 'BANK2', 'amount': '50.00'}
    ]

    ops_num = [
        {'order_ref': 'ABC-2', 'gross_amount': 50.50, 'fees': 0.50, 'net_amount': 50.00}
    ]
    erp_num = [
        {'order_ref': 'ABC-2', 'id': 'ERP2', 'amount': 50.00}
    ]
    bank_num = [
        {'reference_raw': 'ABC-2', 'id': 'BANK2', 'amount': 50.00}
    ]

    res_str = three_way_match(ops_str, erp_str, bank_str)
    res_num = three_way_match(ops_num, erp_num, bank_num)

    def _rows_to_tuples(res):
        return rows_to_tuples(res)

    assert _rows_to_tuples(res_str) == _rows_to_tuples(res_num)
    assert res_str['readiness'] == res_num['readiness']
    assert res_str['summary'] == res_num['summary']
    assert res_str['unexplained_bank'] == res_num['unexplained_bank']


def test_net_amount_empty_string_fallback():
    ops = [
        {'order_ref': 'ghi-3', 'gross_amount': '9700.00', 'fees': '0', 'net_amount': ''},
    ]
    erp = [
        {'order_ref': 'GHI-3', 'id': 'ERP3', 'amount': '9700.00'}
    ]
    bank = [
        {'reference_raw': 'ghi-3', 'id': 'BANK3', 'amount': '9700.00'}
    ]
    result = three_way_match(ops, erp, bank)
    rows = result['rows']
    assert len(rows) == 1
    row = rows[0]
    assert row.order_ref == 'GHI-3'
    assert row.erp_id == 'ERP3'
    assert row.bank_id == 'BANK3'
    assert row.status == 'closed'
    assert row.ops_net == 9700.0
    assert row.erp_amount == 9700.0
    assert row.bank_amount == 9700.0
    assert row.variance == 0.0
    assert result['readiness'] == 1.0
    assert result['summary'] == {'closed': 1, 'partial': 0, 'orphan': 0, 'total': 1}
    assert result['unexplained_bank'] == []
