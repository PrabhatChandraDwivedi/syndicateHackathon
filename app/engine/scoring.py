from typing import Dict

# Module-level weights as specified
WEIGHTS: Dict[str, float] = {
    'amount_exact': 0.40,
    'reference_exact': 0.25,
    'merchant_match': 0.20,
    'date_proximity': 0.15
}

def date_proximity_score(date_delta_days: int, tolerance_days: int = 3) -> float:
    """
    Returns a score for date proximity.
    1.0 if exact match (delta 0).
    0.0 if outside tolerance.
    Otherwise returns a linear gradient within the tolerance.
    """
    if date_delta_days == 0:
        return 1.0
    if abs(date_delta_days) > tolerance_days:
        return 0.0
    return round(1.0 - (abs(date_delta_days) / (tolerance_days + 1)), 4)

def score_match(
    amount_exact: bool,
    reference_exact: bool,
    merchant_match: bool,
    date_delta_days: int,
    tolerance_days: int = 3
) -> Dict[str, object]:
    """
    Calculates confidence score and contributions for a reconciliation match.
    """
    # Calculate raw contributions
    amount_contribution = WEIGHTS['amount_exact'] if amount_exact else 0.0
    reference_contribution = WEIGHTS['reference_exact'] if reference_exact else 0.0
    merchant_contribution = WEIGHTS['merchant_match'] if merchant_match else 0.0
    date_contribution = WEIGHTS['date_proximity'] * date_proximity_score(date_delta_days, tolerance_days)

    # Round contributions for the dict
    contributions = {
        'amount_exact': round(amount_contribution, 4),
        'reference_exact': round(reference_contribution, 4),
        'merchant_match': round(merchant_contribution, 4),
        'date_proximity': round(date_contribution, 4)
    }

    # Sum contributions, clamp, and round final confidence
    confidence_raw = sum(contributions.values())
    confidence = max(0.0, min(1.0, confidence_raw))
    confidence = round(confidence, 4)

    # Build reasons list in specified order
    reasons = []
    if contributions['amount_exact'] > 0:
        reasons.append('amount matched exactly')
    if contributions['reference_exact'] > 0:
        reasons.append('reference matched exactly')
    if contributions['merchant_match'] > 0:
        reasons.append('merchant resolved to same entity')
    if contributions['date_proximity'] > 0:
        reasons.append('dates within tolerance')

    return {
        'confidence': confidence,
        'contributions': contributions,
        'reasons': reasons
    }

def band(confidence: float) -> str:
    """Returns the confidence band based on threshold values."""
    if confidence >= 0.85:
        return 'high'
    elif confidence >= 0.60:
        return 'medium'
    else:
        return 'low'
