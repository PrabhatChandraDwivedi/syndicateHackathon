from enum import Enum
from typing import Dict

class ExceptionType(str, Enum):
    UNMATCHED_SOURCE = "unmatched_source"
    UNMATCHED_TARGET = "unmatched_target"
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_OUT_OF_TOLERANCE = "date_out_of_tolerance"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    MERCHANT_UNRESOLVED = "merchant_unresolved"
    SPLIT_PAYMENT = "split_payment"
    AMBIGUOUS_MATCH = "ambiguous_match"

SEVERITY: Dict[ExceptionType, int] = {
    ExceptionType.DUPLICATE_TRANSACTION: 5,
    ExceptionType.AMOUNT_MISMATCH: 4,
    ExceptionType.UNMATCHED_SOURCE: 3,
    ExceptionType.UNMATCHED_TARGET: 3,
    ExceptionType.AMBIGUOUS_MATCH: 3,
    ExceptionType.DATE_OUT_OF_TOLERANCE: 2,
    ExceptionType.SPLIT_PAYMENT: 2,
    ExceptionType.MERCHANT_UNRESOLVED: 1,
}

def severity_of(exc: ExceptionType) -> int:
    return SEVERITY[exc]

def classify(matched: bool = False, amount_delta: float = 0.0, date_delta_days: int = 0,
             is_duplicate: bool = False, merchant_id: str | None = None,
             candidate_count: int = 0, amount_tolerance: float = 0.01,
             date_tolerance_days: int = 3) -> ExceptionType | None:
    if is_duplicate:
        return ExceptionType.DUPLICATE_TRANSACTION
    if not matched and candidate_count == 0:
        return ExceptionType.UNMATCHED_SOURCE
    if not matched and candidate_count > 1:
        return ExceptionType.AMBIGUOUS_MATCH
    if abs(amount_delta) > amount_tolerance:
        return ExceptionType.AMOUNT_MISMATCH
    if abs(date_delta_days) > date_tolerance_days:
        return ExceptionType.DATE_OUT_OF_TOLERANCE
    if merchant_id is None:
        return ExceptionType.MERCHANT_UNRESOLVED
    return None
