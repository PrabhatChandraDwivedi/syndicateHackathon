import json
import re
from typing import Dict, Any, Optional, List

from app.harness.modelrouter import ModelRouter
from app.harness.guardrails import validate_ids_exist, ValidationResult

AMBIGUOUS_LOW = 0.60
AMBIGUOUS_HIGH = 0.85


def is_ambiguous(confidence: float) -> bool:
    """True when AMBIGUOUS_LOW <= confidence < AMBIGUOUS_HIGH."""
    return AMBIGUOUS_LOW <= confidence < AMBIGUOUS_HIGH


def build_prompt(source: Dict[str, str], candidates: List[Dict[str, str]]) -> str:
    """Construct a deterministic prompt for the LLM."""
    prompt_parts = [
        "RECONCILIATION ADJUDICATION",
        f"SOURCE ID: {source['id']}",
        f"DATE: {source['date']}",
        f"AMOUNT: {source['amount']}",
        f"DESCRIPTOR: {source['descriptor']}",
        "",
        "CANDIDATES:",
    ]

    for i, cand in enumerate(candidates, start=1):
        prompt_parts.append(
            f"{i}. ID: {cand['id']}, DATE: {cand['date']}, AMOUNT: {cand['amount']}, DESCRIPTOR: {cand['descriptor']}"
        )

    prompt_parts.extend(
        [
            "",
            "Select the best candidate based on data consistency. Reply with ONLY a JSON object of the form",
            '{"target_id": "<id or null>", "reason": "<short reason>"}',
        ]
    )
    return "\n".join(prompt_parts)


def parse_response(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from text."""
    try:
        # Find the first occurrence of {
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if not match:
            return {"target_id": None, "reason": "unparseable model response"}
        json_str = match.group(0)
        data = json.loads(json_str)
        if "target_id" not in data or "reason" not in data:
            return {"target_id": None, "reason": "unparseable model response"}
        return data
    except (json.JSONDecodeError, Exception):
        return {"target_id": None, "reason": "unparseable model response"}


def adjudicate(
    source: Dict[str, str],
    candidates: List[Dict[str, str]],
    router: Optional[ModelRouter] = None,
    max_tokens: int = 400,
) -> Dict[str, Any]:
    """Adjudicate ambiguous reconciliation matches."""
    if not candidates:
        return {"target_id": None, "reason": "no candidates", "model": None, "adjudicated": False}

    if router is None:
        return {"target_id": None, "reason": "no router configured", "model": None, "adjudicated": False}

    known_ids = {c["id"] for c in candidates}
    try:
        prompt = build_prompt(source, candidates)
        response = router.complete(prompt, max_tokens=max_tokens)
        parsed = parse_response(response.get("text", ""))
    except Exception as e:
        return {"target_id": None, "reason": f"adjudication failed: {e}", "model": None, "adjudicated": False}

    target_id = parsed.get("target_id")
    reason = parsed.get("reason", "no reason provided")

    # Guardrail: validate target_id is a real candidate
    if target_id is None:
        return {"target_id": None, "reason": reason, "model": response.get("model", None), "adjudicated": True}

    # Ensure the target_id is actually one of the candidates
    validation: ValidationResult = validate_ids_exist([target_id], known_ids)
    if not validation.ok:
        return {
            "target_id": None,
            "reason": "model proposed an id that is not a candidate",
            "model": response.get("model", None),
            "adjudicated": False,
        }

    return {
        "target_id": target_id,
        "reason": reason,
        "model": response.get("model", None),
        "adjudicated": True,
    }
