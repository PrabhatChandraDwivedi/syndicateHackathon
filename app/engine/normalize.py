from __future__ import annotations

import re
from typing import List, Optional, Any, Tuple

from dateutil.parser import parse as dateutil_parse
from pydantic import BaseModel

# Re-export repo models for convenience
from app.models.financial_transaction import FinancialTransaction
from app.models.merchant import Merchant

# 1. NOISE_TOKENS
NOISE_TOKENS = frozenset({
    "POS", "VISA", "MASTERCARD", "RUPAY", "AMEX", "UPI", "NEFT", "IMPS", "RTGS", "ACH",
    "ATM", "DEBIT", "CREDIT", "CARD", "PURCHASE", "PAYMENT", "TXN", "TRANSACTION",
    "REF", "REFNO", "AUTH", "APPROVED", "INR", "USD", "PVT", "LTD", "LIMITED", "INDIA",
    "ONLINE", "WWW", "COM"
})


# 2. normalize_descriptor
def normalize_descriptor(raw: str | None) -> str:
    """
    Normalize a raw text descriptor by removing noise tokens, numbers, and
    short references, returning a clean string of keywords.
    """
    if not raw or not str(raw).strip():
        return ""

    # Uppercase and replace non-alphanumeric (except space) with space
    # Using a space as a separator.
    text = re.sub(r'[^A-Z0-9 ]', ' ', str(raw).upper())

    # Split on whitespace
    tokens = text.split()

    filtered_tokens = []
    for token in tokens:
        # Skip noise tokens
        if token in NOISE_TOKENS:
            continue
        # Skip entirely digits
        if token.isdigit():
            continue
        # Skip mix of letters and digits with 6+ chars (ref codes)
        if len(token) >= 6 and any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
            continue
        # Skip length 1 tokens
        if len(token) == 1:
            continue

        filtered_tokens.append(token)

    return " ".join(filtered_tokens)


# 3. normalize_amount
def normalize_amount(amount: float | int | str | None) -> float | None:
    """
    Normalize amount string, handling commas, parentheses for negatives, and currency symbols.
    Returns the amount rounded to 2 decimal places or None on failure.
    """
    if amount is None:
        return None

    try:
        # Convert to string to handle stripping
        s = str(amount)

        # Remove commas
        s = s.replace(",", "")

        # Handle parentheses for negatives
        negative = False
        if s.startswith("(") and s.endswith(")"):
            negative = True
            s = s[1:-1]

        # Strip whitespace
        s = s.strip()

        # Strip any remaining non-numeric characters (symbols, currency letters, etc.)
        # Keep only digits, dots, and negative sign for parsing
        s = re.sub(r'[^\d.-]', '', s)

        if not s:
            return None

        val = float(s)

        if negative:
            val = -val

        return round(val, 2)
    except (ValueError, TypeError):
        return None


# 4. normalize_date
def normalize_date(value: str | None) -> str | None:
    """
    Parse a date string into ISO format YYYY-MM-DD.
    Uses dateutil.parser.parse with dayfirst=True.
    Returns None on any failure.
    """
    if not value or not str(value).strip():
        return None

    try:
        dt = dateutil_parse(str(value).strip(), dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# 5. NormalizedTransaction
class NormalizedTransaction(BaseModel):
    id: str
    source: str
    normalized_descriptor: str
    merchant_id: Optional[str] = None
    merchant_confidence: float = 0.0
    amount: Optional[float] = None
    date: Optional[str] = None
    currency: Optional[str] = None


# 6. resolve_merchant
def resolve_merchant(
    descriptor: str,
    merchants: List[Merchant],
    threshold: float = 80.0
) -> Tuple[Optional[str], float]:
    """
    Resolve a normalized descriptor to a merchant using fuzzy string matching.
    Returns (merchant_id, score) if score >= threshold, else (None, score).
    """
    if not descriptor or not merchants:
        return (None, 0.0)

    # Build candidate list: (candidate_string, merchant_id)
    candidates = []
    for m in merchants:
        # Add canonical name
        if m.canonical_name:
            candidates.append((m.canonical_name, m.merchant_id))
        # Add aliases
        if m.aliases:
            for alias in m.aliases:
                if alias:
                    candidates.append((alias, m.merchant_id))

    if not candidates:
        return (None, 0.0)

    # Normalize candidates for comparison
    norm_descriptor = normalize_descriptor(descriptor)
    normalized_candidates = [
        (normalize_descriptor(cand), mid)
        for cand, mid in candidates
    ]

    # Score candidates
    from rapidfuzz import fuzz
    scores = []
    for norm_cand, mid in normalized_candidates:
        score = fuzz.token_set_ratio(norm_descriptor, norm_cand)
        scores.append((score, mid))

    if not scores:
        return (None, 0.0)

    best_score, best_mid = max(scores, key=lambda x: x[0])

    if best_score >= threshold:
        return (best_mid, round(best_score, 2))
    return (None, round(best_score, 2))


# 7. normalize_transaction
def normalize_transaction(
    txn: FinancialTransaction,
    merchants: Optional[List[Merchant]] = None
) -> NormalizedTransaction:
    """
    Convert a FinancialTransaction into a NormalizedTransaction.
    """
    if merchants is None:
        merchants = []

    # Build descriptor
    descriptor_raw = txn.counterparty_raw or txn.reference_raw
    descriptor = normalize_descriptor(descriptor_raw)

    # Normalize attributes
    amount = normalize_amount(txn.amount)
    date = normalize_date(txn.date)
    currency = (txn.currency or "INR").upper()

    # Resolve merchant
    merchant_id, confidence = resolve_merchant(descriptor, merchants)

    return NormalizedTransaction(
        id=txn.id,
        source=txn.source,
        normalized_descriptor=descriptor,
        merchant_id=merchant_id,
        merchant_confidence=confidence,
        amount=amount,
        date=date,
        currency=currency
    )
