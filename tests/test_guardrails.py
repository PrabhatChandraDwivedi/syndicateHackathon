import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from app.harness.guardrails import (
    GuardrailError,
    ValidationResult,
    enforce,
    validate_amount_conservation,
    validate_confidence,
    validate_ids_exist,
    validate_match_proposal,
)

def test_valid_proposal_passes():
    res = validate_match_proposal(
        {
            "source_ids": ["A", "B"],
            "target_id": "C",
            "confidence": 1.0,
        },
        known_source_ids={"A", "B"},
        known_target_ids={"C"},
    )
    assert res.ok
    assert res.value["source_ids"] == ["A", "B"]

def test_hallucinated_target_id_rejected():
    res = validate_match_proposal(
        {
            "source_ids": ["A"],
            "target_id": "Z",
            "confidence": 1.0,
        },
        known_source_ids={"A"},
        known_target_ids={"B"},
    )
    assert not res.ok
    assert "unknown id: Z" in res.errors

def test_empty_source_ids_rejected():
    res = validate_match_proposal(
        {"source_ids": [], "target_id": "A", "confidence": 1.0},
        known_source_ids={"A"},
        known_target_ids={"A"},
    )
    assert not res.ok
    assert "no ids proposed" in res.errors

def test_confidence_float_pass():
    res = validate_confidence(0.9)
    assert res.ok
    assert res.value["confidence"] == 0.9

def test_confidence_int_pass():
    res = validate_confidence(1)
    assert res.ok
    assert res.value["confidence"] == 1.0

def test_confidence_float_too_high():
    res = validate_confidence(1.5)
    assert not res.ok
    assert "confidence out of range" in res.errors

def test_confidence_string_rejected():
    res = validate_confidence("abc")
    assert not res.ok
    assert "confidence must be numeric" in res.errors

def test_confidence_bool_rejected():
    res = validate_confidence(True)
    assert not res.ok
    assert "confidence must be numeric" in res.errors

def test_amount_conservation_pass():
    res = validate_amount_conservation([400.0, 850.5], 1250.5)
    assert res.ok
    assert res.value["sum"] == 1250.5

def test_amount_conservation_fail():
    res = validate_amount_conservation([400.0, 850.4], 1250.5)
    assert not res.ok
    err = res.errors[0]
    assert "sources sum to 1250.40" in err
    assert "target is 1250.50" in err

def test_multiple_errors():
    proposal = {
        "source_ids": ["X", "Y"],
        "target_id": "Z",
        "confidence": 2.0,
    }
    res = validate_match_proposal(
        proposal,
        known_source_ids={"A", "B"},
        known_target_ids={"C", "D"},
    )
    assert not res.ok
    assert len(res.errors) > 1
    # The code checks target_id which will also report 'unknown id: Z'
    # and source_ids will report 'unknown id: X' and 'unknown id: Y'
    # So we expect 3 errors of type 'unknown id:'
    assert len([e for e in res.errors if "unknown id:" in e]) == 3

def test_enforce_success():
    proposal = {"source_ids": ["A"], "target_id": "B", "confidence": 1.0}
    res = validate_match_proposal(proposal, {"A"}, {"B"})
    result = enforce(res)
    assert result == proposal

def test_enforce_failure():
    proposal = {"source_ids": ["A"], "target_id": "B", "confidence": 1.5}
    res = validate_match_proposal(proposal, {"A"}, {"B"})
    with pytest.raises(GuardrailError) as exc_info:
        enforce(res)
    assert exc_info.value.args[0].startswith("guardrail rejected: ")
