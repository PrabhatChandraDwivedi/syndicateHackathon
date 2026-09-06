import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from seed.generate import generate


def test_generate_returns_paths(tmp_path):
    paths = generate(str(tmp_path))
    assert set(paths.keys()) == {"merchants", "card", "bank"}
    assert paths["merchants"].exists()
    assert paths["card"].exists()
    assert paths["bank"].exists()


def test_generate_counts(tmp_path):
    paths = generate(str(tmp_path))
    
    # Use DictReader to skip the header row correctly regardless of implementation
    with paths["merchants"].open() as f:
        assert sum(1 for _ in csv.DictReader(f)) == 5
    
    with paths["card"].open() as f:
        assert sum(1 for _ in csv.DictReader(f)) == 10
    
    with paths["bank"].open() as f:
        assert sum(1 for _ in csv.DictReader(f)) == 8


def test_generate_deterministic(tmp_path):
    paths1 = generate(str(tmp_path))
    paths2 = generate(str(tmp_path))
    
    for name in ["merchants", "card", "bank"]:
        assert paths1[name].read_bytes() == paths2[name].read_bytes()


def test_subset_sum(tmp_path):
    paths = generate(str(tmp_path))
    
    def get_amount(file_path, row_index):
        with file_path.open() as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i == row_index:
                    return float(row["amount"])
        raise ValueError("Row not found")

    c007_amt = get_amount(paths["card"], 6)  # 0-indexed, C007 is 7th row
    c008_amt = get_amount(paths["card"], 7)
    b006_amt = get_amount(paths["bank"], 5)

    assert abs(c007_amt + c008_amt - b006_amt) < 0.001
