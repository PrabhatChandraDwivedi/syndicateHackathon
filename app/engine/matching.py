import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from app.engine.normalize import NormalizedTransaction
from app.engine.subsetsum import find_subset
from app.engine.scoring import score_match
from app.engine.exceptions import ExceptionType, classify


def _exc_value(exc):
    return exc.value if exc is not None else None


def date_delta_days(d1: Optional[str], d2: Optional[str]) -> int:
    if d1 is None or d2 is None:
        return 999
    date1 = datetime.date.fromisoformat(d1)
    date2 = datetime.date.fromisoformat(d2)
    return abs((date2 - date1).days)


@dataclass
class Match:
    source_ids: List[str]
    target_id: Optional[str]
    confidence: float
    method: str
    reasons: List[str]
    exception_type: Optional[str]
    amount_delta: float


def find_duplicates(sources: List[NormalizedTransaction]) -> Dict[str, str]:
    duplicates: Dict[str, str] = {}
    seen: Dict[str, str] = {}
    
    # Track amounts, dates, descriptors to find exact matches
    # Key: (amount_str, date_str, descriptor_str)
    normalized_key = lambda t: (str(t.amount), t.date, t.normalized_descriptor)
    
    for t in sources:
        key = normalized_key(t)
        if key in seen:
            duplicates[t.id] = seen[key]
        else:
            seen[key] = t.id
    return duplicates


def match_one(
    source: NormalizedTransaction,
    targets: List[NormalizedTransaction],
    date_tolerance_days: int = 3,
    amount_tolerance: float = 0.01
) -> Match:
    if not targets:
        return Match(
            source_ids=[source.id],
            target_id=None,
            confidence=0.0,
            method="none",
            reasons=[],
            exception_type=ExceptionType.UNMATCHED_SOURCE.value,
            amount_delta=0.0
        )

    best_match: Optional[Match] = None
    best_conf = -1.0
    best_delta = float('inf')
    best_key: Optional[tuple] = None

    for target in targets:
        amount_exact = source.amount is not None and target.amount is not None and abs(source.amount - target.amount) <= amount_tolerance
        reference_exact = bool(source.reference) and bool(target.reference) and source.reference == target.reference
        merchant_match = (source.merchant_id is not None and 
                          target.merchant_id is not None and 
                          source.merchant_id == target.merchant_id)
        delta = date_delta_days(source.date, target.date)
        
        score = score_match(amount_exact, reference_exact, merchant_match, delta, date_tolerance_days)
        conf = score['confidence']
        
        # Rank candidates by (reference_exact, confidence, -date_delta)
        key = (reference_exact, conf, -delta)
        if best_match is None or key > best_key:
            best_key = key
            best_conf = conf
            best_delta = delta
            
            if source.amount is not None and target.amount is not None:
                delta_amount = round(source.amount - target.amount, 2)
            else:
                delta_amount = 0.0
            
            best_match = Match(
                source_ids=[source.id],
                target_id=target.id,
                confidence=conf,
                method="one_to_one",
                reasons=score['reasons'],
                exception_type=_exc_value(classify(
                    matched=conf >= 0.60,
                    amount_delta=delta_amount,
                    date_delta_days=delta,
                    is_duplicate=False,
                    merchant_id=source.merchant_id,
                    candidate_count=len(targets),
                    amount_tolerance=amount_tolerance,
                    date_tolerance_days=date_tolerance_days
                )),
                amount_delta=delta_amount
            )

    # Fix: ensure the exception_type reflects the winner's exact delta
    if best_match is not None:
        best_match.exception_type = _exc_value(classify(
            matched=best_match.confidence >= 0.60,
            amount_delta=best_match.amount_delta,
            date_delta_days=best_delta,
            is_duplicate=False,
            merchant_id=source.merchant_id,
            candidate_count=len(targets),
            amount_tolerance=amount_tolerance,
            date_tolerance_days=date_tolerance_days
        ))

    return best_match


def match_split(
    sources: List[NormalizedTransaction],
    target: NormalizedTransaction,
    date_tolerance_days: int = 3,
    amount_tolerance: float = 0.01
) -> Optional[Match]:
    qualifying_sources = []
    for s in sources:
        s_date_delta = date_delta_days(s.date, target.date)
        if s_date_delta <= date_tolerance_days and s.amount is not None:
            qualifying_sources.append(s)
    
    if len(qualifying_sources) < 2:
        return None
        
    amounts = [s.amount for s in qualifying_sources]
    indices = find_subset(amounts, target.amount, max_items=4)
    
    if indices and len(indices) >= 2:
        source_ids = [qualifying_sources[i].id for i in indices]
        return Match(
            source_ids=source_ids,
            target_id=target.id,
            confidence=0.90,
            method="one_to_many",
            reasons=["aggregated payout matched by subset-sum"],
            exception_type=ExceptionType.SPLIT_PAYMENT.value,
            amount_delta=0.0
        )
    
    return None


def reconcile(
    sources: List[NormalizedTransaction],
    targets: List[NormalizedTransaction],
    date_tolerance_days: int = 3,
    amount_tolerance: float = 0.01
) -> List[Match]:
    matches: List[Match] = []
    
    # State management
    consumed_source_ids = set()
    consumed_target_ids = set()
    
    # 1. Duplicates
    dup_map = find_duplicates(sources)
    for dup_id, first_id in dup_map.items():
        matches.append(Match(
            source_ids=[dup_id],
            target_id=None,
            confidence=1.0,
            method="duplicate",
            reasons=[f"identical amount, date and descriptor as {first_id}"],
            exception_type=ExceptionType.DUPLICATE_TRANSACTION.value,
            amount_delta=0.0
        ))
        consumed_source_ids.add(dup_id)
    
    # 2. Splits
    remaining_targets = [t for t in targets if t.id not in consumed_target_ids]
    current_sources = [s for s in sources if s.id not in consumed_source_ids]
    
    for target in remaining_targets:
        split_match = match_split(current_sources, target, date_tolerance_days, amount_tolerance)
        if split_match:
            matches.append(split_match)
            # Mark targets consumed
            consumed_target_ids.add(target.id)
            # Mark sources consumed
            for s_id in split_match.source_ids:
                consumed_source_ids.add(s_id)
            # Update current sources to reflect consumed ones
            current_sources = [s for s in sources if s.id not in consumed_source_ids]
    
    # 3. One-to-one
    remaining_targets = [t for t in targets if t.id not in consumed_target_ids]
    for source in [s for s in sources if s.id not in consumed_source_ids]:
        one_one_match = match_one(source, remaining_targets, date_tolerance_days, amount_tolerance)
        matches.append(one_one_match)
        
        # If confidence is high enough, mark the target as consumed
        if one_one_match.confidence >= 0.60 and one_one_match.target_id:
            consumed_target_ids.add(one_one_match.target_id)
        
        # Source is consumed by definition (matched)
        consumed_source_ids.add(source.id)
        
        # Update remaining targets for subsequent iterations
        remaining_targets = [t for t in targets if t.id not in consumed_target_ids]
    
    # 4. Leftover Targets
    for target in targets:
        if target.id not in consumed_target_ids:
            matches.append(Match(
                source_ids=[],
                target_id=target.id,
                confidence=0.0,
                method="none",
                reasons=[],
                exception_type=ExceptionType.UNMATCHED_TARGET.value,
                amount_delta=0.0
            ))
    
    return matches
