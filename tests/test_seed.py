import csv
import sys, os
from decimal import Decimal
from pathlib import Path
from seed.generate import generate

# Header to ensure the repository root is on PYTHONPATH during tests
import sys, os  # noqa: E402
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_seed_generation(tmp_path):
    out_dir = str(tmp_path)
    first = generate(out_dir)

    merchants = first["merchants"]
    card = first["card"]
    bank = first["bank"]

    merchants_rows = _read_rows(merchants)
    card_rows = _read_rows(card)
    bank_rows = _read_rows(bank)

    assert len(merchants_rows) == 5
    assert len(card_rows) == 11
    assert len(bank_rows) == 9

    amount_C007 = Decimal(next(row["amount"] for row in card_rows if row["id"] == "C007"))
    amount_C008 = Decimal(next(row["amount"] for row in card_rows if row["id"] == "C008"))
    sum_card = amount_C007 + amount_C008
    amount_B006 = Decimal(next(row["amount"] for row in bank_rows if row["id"] == "B006"))
    assert sum_card == amount_B006

    second = generate(out_dir)

    for key in first.keys():
        p1 = first[key]
        p2 = second[key]
        b1 = p1.read_bytes()
        b2 = p2.read_bytes()
        assert b1 == b2

    # Ensure new datasets exist and have correct row counts
    purchase_register = second["purchase_register"]
    gstr2b = second["gstr2b"]
    ops = second["ops"]
    erp = second["erp"]
    settlements = second["settlements"]

    pr_rows = _read_rows(purchase_register)
    g2b_rows = _read_rows(gstr2b)
    ops_rows = _read_rows(ops)
    erp_rows = _read_rows(erp)
    settlements_rows = _read_rows(settlements)

    assert len(pr_rows) == 5
    assert len(g2b_rows) == 5
    assert len(ops_rows) == 4
    assert len(erp_rows) == 3
    assert len(settlements_rows) == 4
