import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.policy.engine import load_policy, decide


def test_load_policy_returns_version_v1():
    policy = load_policy()
    assert policy['version'] == 'v1'


def test_duplicate_transaction_forces_human_review():
    policy = load_policy()
    result = decide(confidence=0.99, amount=100, exception_type='duplicate_transaction', policy=policy)
    assert result['action'] == 'human_review'
    assert 'blocked exception type: duplicate_transaction' in result['reason']


def test_amount_exceeds_materiality_forces_human_review():
    policy = load_policy()
    result = decide(confidence=0.99, amount=100000, exception_type=None, policy=policy)
    assert result['action'] == 'human_review'
    assert result['reason'] == 'amount exceeds materiality threshold'


def test_high_confidence_within_limits_auto_resolves():
    policy = load_policy()
    result = decide(confidence=0.9, amount=1000, exception_type=None, policy=policy)
    assert result['action'] == 'auto_resolve'
    assert result['reason'] == 'high confidence within auto-resolve limits'


def test_medium_confidence_reviews():
    policy = load_policy()
    result = decide(confidence=0.7, amount=500, exception_type=None, policy=policy)
    assert result['action'] == 'human_review'
    assert result['reason'] == 'medium confidence requires review'


def test_low_confidence_reviews():
    policy = load_policy()
    result = decide(confidence=0.1, amount=500, exception_type=None, policy=policy)
    assert result['action'] == 'human_review'
    assert result['reason'] == 'confidence below review threshold'


def test_policy_version_echoed_back():
    policy = load_policy()
    result = decide(confidence=0.5, amount=500, exception_type=None, policy=policy)
    assert result['policy_version'] == 'v1'
