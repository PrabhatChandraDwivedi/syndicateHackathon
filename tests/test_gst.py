import sys
import os

# Add parent directory to path to import app module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine.gst import (
    normalize_invoice_number,
    match_key,
    total_tax,
    GSTExceptionRow,
    reconcile_gst
)


def test_normalize_invoice_number():
    assert normalize_invoice_number(None) == ""
    assert normalize_invoice_number("") == ""
    assert normalize_invoice_number("inv-2026/001") == "INV2026001"
    assert normalize_invoice_number("INV-2026/001") == "INV2026001"
    assert normalize_invoice_number("Invoice-001/ABC") == "INVOICE001ABC"


def test_match_key():
    row = {
        'supplier_gstin': 'abc-123',
        'invoice_number': 'INV-2026/001'
    }
    # GSTIN: abc-123 -> ABC-123 -> ABC123 (strip removes dash?) No, strip only removes whitespace. 
    # But dash is removed in normalize.
    # normalize is purely alphanumeric filter + upper.
    key = match_key(row)
    # 'abc-123'.upper().strip() -> 'ABC-123'
    # 'INV-2026/001'.upper() -> 'INV-2026/001' -> normalized -> 'INV2026001'
    # Result: 'ABC-123|INV2026001'
    assert '|' in key
    assert key == "ABC-123|INV2026001"


def test_match_key_none_gstin():
    row = {
        'supplier_gstin': None,
        'invoice_number': 'INV-01'
    }
    key = match_key(row)
    assert key == "|INV01"


def test_match_key_none_inv():
    row = {
        'supplier_gstin': 'GST123',
        'invoice_number': None
    }
    key = match_key(row)
    assert key == "GST123|"


def test_total_tax():
    assert total_tax({'igst': 10, 'cgst': 5, 'sgst': 5}) == 20.0
    assert total_tax({'taxable_value': 100}) == 0.0
    assert total_tax({}) == 0.0
    assert total_tax({'igst': None, 'cgst': '20'}) == 20.0


def test_reconcile_gst_clean_match():
    purchases = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    gstr = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    result = reconcile_gst(purchases, gstr)
    assert result['matched'] == 1
    assert len(result['exceptions']) == 0
    assert result['itc_at_risk'] == 0.0


def test_reconcile_gst_value_mismatch():
    purchases = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    gstr = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 102, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    result = reconcile_gst(purchases, gstr, tolerance=1.0)
    assert result['matched'] == 0
    assert len(result['exceptions']) == 1
    exc = result['exceptions'][0]
    assert exc.exception_type == 'value_mismatch'
    assert exc.taxable_delta == -2.0
    assert exc.tax_delta == 0.0


def test_reconcile_gst_missing_in_gstr2b():
    purchases = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    gstr = []  # Empty
    result = reconcile_gst(purchases, gstr)
    assert result['matched'] == 0
    assert len(result['exceptions']) == 1
    exc = result['exceptions'][0]
    assert exc.exception_type == 'missing_in_gstr2b'
    assert exc.purchase_row is not None
    assert exc.gstr_row is None
    assert exc.taxable_delta == 0.0
    assert result['itc_at_risk'] == 20.0  # Sum of tax (10+5+5)


def test_reconcile_gst_missing_in_purchase_register():
    purchases = []
    gstr = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}
    ]
    result = reconcile_gst(purchases, gstr)
    assert result['matched'] == 0
    assert len(result['exceptions']) == 1
    exc = result['exceptions'][0]
    assert exc.exception_type == 'missing_in_purchase_register'
    assert exc.gstr_row is not None
    assert exc.purchase_row is None


def test_reconcile_gst_tolerance_passes():
    # Delta 0.9 <= 1.0 -> Match
    purchases = [{'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5}]
    gstr = [{'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 99.1, 'igst': 10, 'cgst': 5, 'sgst': 5}]
    result = reconcile_gst(purchases, gstr, tolerance=1.0)
    assert result['matched'] == 1
    assert len(result['exceptions']) == 0


def test_reconcile_gst_duplicates_keep_first():
    # Purchase has variant 1. GSTR has variant 2. Keep purchase variant 1 (the first in list).
    purchases = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 100, 'igst': 10, 'cgst': 5, 'sgst': 5},
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 200, 'igst': 20, 'cgst': 10, 'sgst': 10} # Duplicate, ignored
    ]
    gstr = [
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 200, 'igst': 20, 'cgst': 10, 'sgst': 10},
        {'supplier_gstin': 'ABC', 'invoice_number': 'INV-1', 'taxable_value': 300, 'igst': 30, 'cgst': 15, 'sgst': 15} # Duplicate, ignored
    ]
    result = reconcile_gst(purchases, gstr)
    # Since purchase row is 100 and GSTR is 200, mismatch.
    assert result['matched'] == 0
    assert len(result['exceptions']) == 1
    # Should use the first purchase row (100) and first GSTR row (200)
    assert result['exceptions'][0].taxable_delta == -100.0


def test_counts():
    p_rows = [{'supplier_gstin': 'A', 'invoice_number': '1'}]
    g_rows = [{'supplier_gstin': 'A', 'invoice_number': '1'}]
    result = reconcile_gst(p_rows, g_rows)
    assert result['counts']['purchase'] == 1
    assert result['counts']['gstr2b'] == 1
