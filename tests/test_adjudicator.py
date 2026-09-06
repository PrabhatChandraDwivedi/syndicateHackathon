import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app.harness.guardrails import ValidationResult

from app.engine.adjudicator import adjudicate, build_prompt, is_ambiguous, parse_response


class FakeRouter:
    def __init__(self, response_text: str):
        self.response_text = response_text

    def complete(self, prompt: str, max_tokens: int = 1000):
        return {
            "provider": "fake",
            "model": "fake_model",
            "text": self.response_text,
            "attempts": 1,
        }


class FakeValidationResult:
    def __init__(self, ok: bool):
        self.ok = ok
        self.errors = [] if ok else ["Invalid ID"]
        self.value = "Fake Value"


def validate_ids_exist(proposed_ids, known_ids):
    # Mock implementation to avoid dependency on real guardrails module for tests if not fully mocked
    # However, prompt asks to use the module. I'll create a simple shim that works with the signature.
    if not proposed_ids:
        return FakeValidationResult(True)
    if proposed_ids[0] not in known_ids:
        return FakeValidationResult(False)
    return FakeValidationResult(True)


def test_is_ambiguous_boundaries():
    assert is_ambiguous(0.59) is False
    assert is_ambiguous(0.60) is True
    assert is_ambiguous(0.84) is True
    assert is_ambiguous(0.85) is False
    assert is_ambiguous(0.99) is False
    assert is_ambiguous(0.60) is True
    assert is_ambiguous(0.85) is False


def test_build_prompt_header_and_data():
    source = {"id": "SRC", "date": "2023-01-01", "amount": "100", "descriptor": "Groceries"}
    candidates = [
        {"id": "C001", "date": "2023-01-01", "amount": "100", "descriptor": "Groceries"},
        {"id": "C002", "date": "2023-01-02", "amount": "50", "descriptor": "Books"},
    ]
    prompt1 = build_prompt(source, candidates)
    prompt2 = build_prompt(source, candidates)
    assert "RECONCILIATION ADJUDICATION" in prompt1
    assert source["id"] in prompt1
    assert "C001" in prompt1
    assert "C002" in prompt1
    assert prompt1 == prompt2


def test_parse_response_clean_json():
    text = '{"target_id": "A1", "reason": "Best match"}'
    result = parse_response(text)
    assert result["target_id"] == "A1"
    assert result["reason"] == "Best match"


def test_parse_response_wrapped():
    text = "Here is the decision: ```json\n{\"target_id\": \"A2\", \"reason\": \"Deep text\"}\n```"
    result = parse_response(text)
    assert result["target_id"] == "A2"
    assert result["reason"] == "Deep text"


def test_parse_response_no_json():
    text = "Just some text"
    result = parse_response(text)
    assert result["target_id"] is None
    assert result["reason"] == "unparseable model response"


def test_parse_response_invalid_json():
    text = "This is not json {target_id: 'A3'}"
    result = parse_response(text)
    assert result["target_id"] is None


def test_adjudicate_no_candidates():
    source = {"id": "SRC", "date": "2023", "amount": "10", "descriptor": "test"}
    result = adjudicate(source, [])
    assert result["adjudicated"] is False
    assert result["reason"] == "no candidates"


def test_adjudicate_no_router():
    source = {"id": "SRC", "date": "2023", "amount": "10", "descriptor": "test"}
    candidates = [{"id": "B001", "date": "2023", "amount": "10", "descriptor": "test"}]
    result = adjudicate(source, candidates)
    assert result["adjudicated"] is False
    assert result["reason"] == "no router configured"


def test_adjudicate_success():
    source = {"id": "SRC", "date": "2023", "amount": "10", "descriptor": "test"}
    candidates = [
        {"id": "B001", "date": "2023", "amount": "10", "descriptor": "test"},
        {"id": "B002", "date": "2023", "amount": "20", "descriptor": "test"},
    ]
    router = FakeRouter('{"target_id": "B001", "reason": "Exact match"}')
    result = adjudicate(source, candidates, router)
    assert result["adjudicated"] is True
    assert result["target_id"] == "B001"
    assert result["reason"] == "Exact match"


def test_adjudicate_reject_hallucination():
    source = {"id": "SRC", "date": "2023", "amount": "10", "descriptor": "test"}
    candidates = [
        {"id": "B001", "date": "2023", "amount": "10", "descriptor": "test"},
        {"id": "B002", "date": "2023", "amount": "20", "descriptor": "test"},
    ]
    router = FakeRouter('{"target_id": "B999", "reason": "My name is Hal"}')
    result = adjudicate(source, candidates, router)
    assert result["adjudicated"] is False
    assert result["target_id"] is None
    assert result["reason"] == "model proposed an id that is not a candidate"


def test_adjudicate_router_exception():
    source = {"id": "SRC", "date": "2023", "amount": "10", "descriptor": "test"}
    candidates = [
        {"id": "B001", "date": "2023", "amount": "10", "descriptor": "test"},
    ]

    class FailingRouter:
        def complete(self, prompt, max_tokens=1000):
            raise RuntimeError("Network down")

    result = adjudicate(source, candidates, FailingRouter())
    assert result["adjudicated"] is False
    assert result["target_id"] is None
    assert "adjudication failed" in result["reason"]
