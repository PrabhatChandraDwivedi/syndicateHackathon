import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine.scoring import score_match, date_proximity_score, band, WEIGHTS

def test_date_proximity_score_exact_match():
    assert date_proximity_score(0) == 1.0

def test_date_proximity_score_out_of_tolerance():
    assert date_proximity_score(10, 3) == 0.0
    assert date_proximity_score(-10, 3) == 0.0

def test_date_proximity_score_partial():
    # delta 1, tol 3 -> 1 - 1/4 = 0.75
    assert date_proximity_score(1, 3) == 0.75

def test_all_features_true_confidence_high():
    result = score_match(True, True, True, 0, 3)
    assert result['confidence'] == 1.0
    assert band(result['confidence']) == 'high'

def test_all_features_false_confidence_low():
    result = score_match(False, False, False, 10, 3)
    assert result['confidence'] == 0.0
    assert band(result['confidence']) == 'low'

def test_contributions_sum_to_confidence():
    # amount: 0.40, ref: 0.25, merc: 0.20, date: 0.15 (if perfect) -> 1.0
    # If date is -1: 1 - 1/4 = 0.75. Contribution = 0.15 * 0.75 = 0.1125
    # Total = 0.4 + 0.25 + 0.2 + 0.1125 = 0.9625
    result = score_match(True, True, True, -1, 3)
    assert result['confidence'] == 0.9625
    assert round(sum(result['contributions'].values()), 4) == result['confidence']

def test_reasons_order():
    result = score_match(True, True, True, 0, 3)
    assert result['reasons'] == [
        'amount matched exactly',
        'reference matched exactly',
        'merchant resolved to same entity',
        'dates within tolerance'
    ]

def test_band_thresholds():
    assert band(0.85) == 'high'
    assert band(0.851) == 'high'
    assert band(0.60) == 'medium'
    assert band(0.601) == 'medium'
    assert band(0.599) == 'low'
    assert band(0.0) == 'low'
    assert band(1.0) == 'high'

def test_date_proximity_reason():
    result = score_match(True, True, True, -1, 3)
    assert 'dates within tolerance' in result['reasons']
    result_false_date = score_match(True, True, True, 100, 3)
    assert 'dates within tolerance' not in result_false_date['reasons']

def test_weights_sum():
    assert sum(WEIGHTS.values()) == 1.0
