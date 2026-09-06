import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app.models.financial_transaction import FinancialTransaction
from app.adapters.csv_source import ingest_file, file_id


def test_ingest_file_returns_2_transactions(tmp_path):
    csv_content = "id,source,account_id,date,amount,currency,counterparty_raw,reference_raw\n1,src,acc1,2023-01-01,100.50,USD,John Doe,REF1\n,src,acc2,2023-01-02,,EUR,,\n3,src,acc3,2023-01-03,invalid,GBP,,\n"

    test_file = tmp_path / "test.csv"
    test_file.write_text(csv_content)

    transactions = ingest_file(str(test_file), "override_source")

    assert len(transactions) == 2


def test_bad_amount_yields_none(tmp_path):
    csv_content = "id,source,amount\n1,test,10\n2,test,abc\n"

    test_file = tmp_path / "test.csv"
    test_file.write_text(csv_content)

    transactions = ingest_file(str(test_file), "test")

    assert len(transactions) == 2
    tx_bad = [t for t in transactions if t.id == "2"][0]
    assert tx_bad.amount is None


def test_file_id_stable(tmp_path):
    csv_content = "id,source,amount\n1,src,10\n"
    test_file = tmp_path / "test.csv"
    test_file.write_text(csv_content)

    fid1 = file_id(str(test_file))
    fid2 = file_id(str(test_file))

    assert len(fid1) == 16
    assert fid1 == fid2


def test_source_argument_overrides_csv(tmp_path):
    csv_content = "id,source,amount\n1,test_csv_source,10\n"

    test_file = tmp_path / "test.csv"
    test_file.write_text(csv_content)

    transactions = ingest_file(str(test_file), "injected_source")

    assert len(transactions) == 1
    assert transactions[0].source == "injected_source"
    # Verify the CSV source was still in the raw payload
    assert transactions[0].raw_payload["source"] == "test_csv_source"


def test_raw_payload_round_trip(tmp_path):
    row = {
        "id": "raw_test_id",
        "source": "csv_source",
        "amount": "5.0",
        "custom_field": "custom_value",
    }
    csv_content = "id,source,amount,custom_field\n" + ",".join(row.values())

    test_file = tmp_path / "test.csv"
    test_file.write_text(csv_content)

    transactions = ingest_file(str(test_file), "test")

    assert len(transactions) == 1
    assert transactions[0].raw_payload == row
