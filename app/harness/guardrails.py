from typing import Any, Dict, List, Set, Union
from dataclasses import dataclass

class GuardrailError(Exception):
    pass

@dataclass
class ValidationResult:
    ok: bool
    errors: List[str]
    value: Union[Dict[str, Any], None] = None

def validate_ids_exist(proposed_ids: List[str], known_ids: Set[str]) -> ValidationResult:
    if not proposed_ids:
        return ValidationResult(ok=False, errors=['no ids proposed'])
    errors = []
    for pid in proposed_ids:
        if pid not in known_ids:
            errors.append(f'unknown id: {pid}')
    if errors:
        return ValidationResult(ok=False, errors=errors)
    return ValidationResult(ok=True, errors=[], value={'ids': proposed_ids})

def validate_confidence(value: Union[int, float]) -> ValidationResult:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ValidationResult(ok=False, errors=['confidence must be numeric'])
    if value < 0.0 or value > 1.0:
        return ValidationResult(ok=False, errors=['confidence out of range'])
    return ValidationResult(ok=True, errors=[], value={'confidence': float(value)})

def validate_amount_conservation(source_amounts: List[float], target_amount: float, tolerance: float = 0.01) -> ValidationResult:
    ssum = round(sum(source_amounts), 2)
    if abs(ssum - target_amount) <= tolerance:
        return ValidationResult(ok=True, errors=[], value={'sum': ssum})
    else:
        return ValidationResult(ok=False, errors=[f'amount not conserved: sources sum to {ssum:.2f}, target is {target_amount:.2f}'])

def validate_match_proposal(proposal: Dict[str, Any], known_source_ids: Set[str], known_target_ids: Set[str]) -> ValidationResult:
    errors = []
    required_keys = {'source_ids', 'target_id', 'confidence'}
    for key in required_keys:
        if key not in proposal:
            errors.append(f'missing field: {key}')

    if not errors:
        source_ids = proposal.get('source_ids', [])
        target_id = proposal.get('target_id')
        confidence = proposal.get('confidence')

        res_ids = validate_ids_exist(source_ids, known_source_ids)
        if not res_ids.ok:
            errors.extend(res_ids.errors)

        if target_id not in known_target_ids:
            errors.append(f'unknown id: {target_id}')

        res_conf = validate_confidence(confidence)
        if not res_conf.ok:
            errors.extend(res_conf.errors)

    if errors:
        return ValidationResult(ok=False, errors=errors)
    return ValidationResult(ok=True, errors=[], value=proposal)

def enforce(result: ValidationResult) -> Dict[str, Any]:
    if result.ok:
        return result.value
    else:
        raise GuardrailError(f'guardrail rejected: {"; ".join(result.errors)}')
