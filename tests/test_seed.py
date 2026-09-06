import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import csv
from decimal import Decimal


def test_seed_generation_counts_and_relations(tmp_path):
    from seed.generate import generate
    output_dir = tmp_path
    paths = generate(str(output_dir))

    # Verify counts
    with open(paths["merchants"], newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        rows = list(reader)
        assert len(rows) == 5  # 5 merchants

    with open(paths["card"], newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        rows = list(reader)
        assert len(rows) == 11  # 11 card rows (including C011)

    with open(paths["bank"], newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        rows = list(reader)
        assert len(rows) == 9  # 9 bank rows (including B009)

    # Verify new rows exist
    with open(paths["card"], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        ids = [row["id"] for row in reader]
        assert "C011" in ids

    with open(paths["bank"], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        ids = [row["id"] for row in reader]
        assert "B009" in ids

    # Ensure the existing reconciliation assertion remains:
    # C007 + C008 == B006
    with open(paths["card"], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        amount_map = {row["id"]: row["amount"] for row in reader}
    with open(paths["bank"], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        bank_map = {row["id"]: row["amount"] for row in reader}
    c007 = Decimal(amount_map["C007"])
    c008 = Decimal(amount_map["C008"])
    b006 = Decimal(bank_map["B006"])
    assert c007 + c008 == b006
