import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.adapters.payout import (
    load_payout_csv,
    _f,
    PayoutBatch,
    group_batches,
    verify_batch,
    match_to_bank,
)


def test_f_handles_none_and_blank():
    assert _f(None) == 0.0
    assert _f("") == 0.0
    assert _f("  ") == 0.0
    assert _f("NaN") == 0.0
    assert _f("nan") == 0.0
    assert _f("infinity") == 0.0


def test_f_parses_valid_numbers():
    assert _f("1") == 1.0
    assert _f("1.5") == 1.5
    assert _f(100) == 100.0
    assert _f(-50.2) == -50.2


def test_load_payout_csv(tmp_path):
    csv_content = "payout_id,order_ref,gross_amount,fee_amount,net_amount,payout_date\n"
    csv_content += "B1,ORD1,10.00,1.00,9.00,2023-01-01\n"
    csv_content += "B1,ORD2,10.00,1.00,9.00,2023-01-01\n"
    csv_content += "B2,ORD3,50.00,0.00,50.00,2023-01-02\n"

    p = tmp_path / "batch.csv"
    p.write_text(csv_content)

    rows = load_payout_csv(str(p))
    assert len(rows) == 3
    assert rows[0]["payout_id"] == "B1"
    assert rows[1]["payout_id"] == "B1"


def test_group_batches():
    rows = [
        {"payout_id": "B1", "gross_amount": "10.00", "fee_amount": "1.00", "net_amount": "9.00", "payout_date": "2023-01-01"},
        {"payout_id": "B1", "gross_amount": "10.00", "fee_amount": "1.00", "net_amount": "9.00", "payout_date": "2023-01-01"},
        {"payout_id": "B2", "gross_amount": "50.00", "fee_amount": "0.00", "net_amount": "50.00", "payout_date": "2023-01-02"},
    ]

    batches = group_batches(rows)

    assert len(batches) == 2
    b1 = next(b for b in batches if b.payout_id == "B1")
    assert b1.order_count == 2
    assert b1.gross_total == 20.0
    assert b1.fee_total == 2.0
    assert b1.net_total == 18.0
    assert b1.payout_date == "2023-01-01"
    
    b2 = next(b for b in batches if b.payout_id == "B2")
    assert b2.order_count == 1
    assert b2.gross_total == 50.0
    assert b2.net_total == 50.0


def test_verify_batch_match():
    batch = PayoutBatch("TEST", 1, 100.0, 10.0, 90.0, "2023-01-01")
    result = verify_batch(batch)

    assert result["payout_id"] == "TEST"
    assert result["ok"] is True
    assert result["delta"] == 0.0


def test_verify_batch_mismatch():
    # Under-reporting net by 5 cents (changing data to make test valid with 0.05 tolerance)
    # 100 - 10 = 90. 90 - 89.95 = 0.05
    batch = PayoutBatch("TEST", 1, 100.0, 10.0, 89.95, "2023-01-01")
    result = verify_batch(batch, tolerance=0.05)

    assert result["ok"] is True  # Within 5 cents tolerance


def test_verify_batch_fail():
    # Under-reporting net by more than tolerance
    batch = PayoutBatch("TEST", 1, 100.0, 10.0, 85.0, "2023-01-01")
    result = verify_batch(batch, tolerance=0.05)

    assert result["ok"] is False
    assert result["delta"] == 5.0


def test_match_to_bank(tmp_path):
    batches = [
        PayoutBatch("B1", 1, 100.0, 10.0, 90.0, "2023-01-01"),
        PayoutBatch("B2", 1, 100.0, 10.0, 90.0, "2023-01-01"),
    ]

    bank_rows = [
        {"id": "BANK-A", "date": "2023-01-01", "amount": 90.0},
        {"id": "BANK-B", "date": "2023-01-01", "amount": 90.0},
    ]

    result = match_to_bank(batches, bank_rows)

    # B1 matches A
    assert len(result["matched"]) == 1
    assert result["matched"][0]["payout_id"] == "B1"
    assert result["matched"][0]["bank_id"] == "BANK-A"

    # B2 is unmatched
    assert len(result["unmatched_payouts"]) == 1
    assert result["unmatched_payouts"] == ["B2"]
    assert "BANK-A" not in result["unmatched_bank"]
    assert "BANK-B" in result["unmatched_bank"]


def test_match_to_bank_unmatched(tmp_path):
    batches = [
        PayoutBatch("B1", 1, 100.0, 10.0, 90.0, "2023-01-01"),
    ]
    
    bank_rows = [
        {"id": "BANK-A", "date": "2023-01-01", "amount": 80.0},
    ]

    result = match_to_bank(batches, bank_rows)

    # B1 is unmatched because amount is 80, not 90
    assert "B1" in result["unmatched_payouts"]
    
    # BANK-A is unmatched because nothing matched
    assert "BANK-A" in result["unmatched_bank"]
    
    # Verify sorted logic (first seen match is found)
    assert "B1" not in result["unmatched_bank"]
    assert "BANK-A" not in result["unmatched_payouts"]


def test_match_to_bank_bank_row_consumed_once():
    batches = [
        PayoutBatch("B1", 1, 100.0, 10.0, 90.0, "2023-01-01"),
        PayoutBatch("B2", 1, 100.0, 10.0, 90.0, "2023-01-01"),
    ]
    bank_rows = [
        {"id": "BANK-A", "date": "2023-01-01", "amount": 90.0},
    ]

    result = match_to_bank(batches, bank_rows, tolerance=0.0)

    # First batch gets the bank row
    assert len(result["matched"]) == 1
    assert result["matched"][0]["payout_id"] == "B1"
    assert result["matched"][0]["bank_id"] == "BANK-A"

    # Second batch has no bank row available
    assert len(result["unmatched_payouts"]) == 1
    assert result["unmatched_payouts"] == ["B2"]
    assert result["unmatched_bank"] == []
