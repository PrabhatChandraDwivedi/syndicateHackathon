import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine.subsetsum import find_subset, find_all_subsets


def test_find_subset_basic():
    # 400.00 + 850.50 = 1250.50
    amounts = [400.00, 850.50, 99.0]
    target = 1250.50
    result = find_subset(amounts, target)
    assert result == [0, 1]


def test_find_subset_single_exact():
    amounts = [50.0]
    target = 50.0
    result = find_subset(amounts, target)
    assert result == [0]


def test_find_subset_no_match():
    amounts = [10.0, 20.0]
    target = 100.0
    result = find_subset(amounts, target)
    assert result is None


def test_find_subset_empty():
    amounts = []
    target = 1.0
    result = find_subset(amounts, target)
    assert result is None


def test_find_subset_tolerance():
    # 100.0 + 200.0 = 300.0
    # Target 300.005, diff is 0.005 <= 0.01 (tolerance)
    amounts = [100.0, 200.0]
    target = 300.005
    result = find_subset(amounts, target, tolerance=0.01)
    assert result == [0, 1]


def test_find_subset_max_items_respected():
    # Sum needed is 4 (indices 0+1+2+3), but max_items is 3
    amounts = [1.0, 1.0, 1.0, 1.0]
    target = 4.0
    result = find_subset(amounts, target, max_items=3)
    assert result is None


def test_find_all_subsets_multiple():
    amounts = [1.0, 1.0, 2.0]
    target = 2.0
    results = find_all_subsets(amounts, target)
    # Should find [2] (single 2) and [0, 1] (sum of two 1s)
    # Since smallest size first, [2] should be first.
    assert len(results) > 1
    assert [2] in results
    assert [0, 1] in results
