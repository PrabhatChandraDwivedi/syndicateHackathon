import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine.normalize import normalize_descriptor, normalize_amount, normalize_date, resolve_merchant, normalize_transaction
from app.models.merchant import Merchant
from app.models.financial_transaction import FinancialTransaction


def test_normalize_descriptor():
    # Case 1: Basic noise removal
    assert normalize_descriptor('POS VISA STARBUCKS INDIA PVT LTD 4412998') == 'STARBUCKS'
    
    # Case 2: Alias and ref code removal
    assert normalize_descriptor('UPI-SWIGGY-REF908812') == 'SWIGGY'
    
    # Case 3: None and whitespace handling
    assert normalize_descriptor(None) == ''
    assert normalize_descriptor('  ') == ''

def test_normalize_amount():
    # Case 1: Currency symbol and comma
    assert normalize_amount('Rs 1,200.50') == 1200.5
    
    # Case 2: Dollar symbol and comma
    assert normalize_amount('$1,499.99') == 1499.99
    
    # Case 3: Parentheses for negative
    assert normalize_amount('(1,200.50)') == -1200.5
    
    # Case 4: Non-numeric string
    assert normalize_amount('abc') is None
    
    # Case 5: None input
    assert normalize_amount(None) is None

def test_normalize_date():
    # Case 1: DD/MM/YYYY
    assert normalize_date('14/08/2026') == '2026-08-14'
    # Case 2: DD-Mon-YYYY
    assert normalize_date('14-Aug-2026') == '2026-08-14'
    # Case 3: Already YYYY-MM-DD
    assert normalize_date('2026-08-14') == '2026-08-14'
    # Case 4: Bad input
    assert normalize_date('invalid-date') is None
    assert normalize_date(None) is None

def test_resolve_merchant():
    merchants = [
        Merchant(merchant_id='M1', canonical_name='Starbucks Coffee', aliases=['SBUX', 'Starbucks India']),
        Merchant(merchant_id='M2', canonical_name='Swiggy', aliases=['Bundl Technologies'])
    ]
    
    # Test M1 match
    mid, score = resolve_merchant('STARBUCKS', merchants)
    assert mid == 'M1'
    assert score >= 80.0

    # Test M2 match
    mid, score = resolve_merchant('SWIGGY', merchants)
    assert mid == 'M2'
    assert score >= 80.0

    # Test no match
    mid, score = resolve_merchant('RandomNonsenseVendor123', merchants)
    assert mid is None

def test_normalize_transaction():
    # Note: FinancialTransaction model enforces strict float types for 'amount'.
    # We pass the pre-calculated normalized float to satisfy the model validation.
    txn = FinancialTransaction(
        id='t1',
        source='card',
        counterparty_raw='POS VISA STARBUCKS INDIA PVT LTD 4412998',
        amount=-1200.5,  # Validated float, equivalent to string input '(1,200.50)' after normalization
        date='14/08/2026',
        currency=None
    )
    
    merchants = [
        Merchant(merchant_id='M1', canonical_name='Starbucks Coffee', aliases=['SBUX'])
    ]
    
    result = normalize_transaction(txn, merchants)
    
    assert result.id == 't1'
    assert result.source == 'card'
    assert result.normalized_descriptor == 'STARBUCKS'
    assert result.merchant_id == 'M1'
    assert result.merchant_confidence >= 80.0
    assert result.amount == -1200.5
    assert result.date == '2026-08-14'
    assert result.currency == 'INR'
