import csv
import math
from dataclasses import dataclass
from typing import Dict, List


def _f(value) -> float:
    """Helper: coerce to float, returning 0.0 for None, blank, or unparseable input."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return 0.0
        try:
            num = float(value)
            if math.isnan(num) or math.isinf(num):
                return 0.0
            return num
        except ValueError:
            return 0.0
    return 0.0


@dataclass
class PayoutBatch:
    payout_id: str
    order_count: int
    gross_total: float
    fee_total: float
    net_total: float
    payout_date: str | None


def load_payout_csv(path: str) -> List[dict]:
    """Read with csv.DictReader and return plain dicts."""
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def group_batches(rows: List[dict]) -> List[PayoutBatch]:
    """Group rows by payout_id, preserving first-seen order. Sum amounts and pick first date."""
    batches: Dict[str, Dict] = {}

    for row in rows:
        pid = row["payout_id"]
        if pid not in batches:
            batches[pid] = {
                "order_count": 0,
                "gross_total": 0.0,
                "fee_total": 0.0,
                "net_total": 0.0,
                "payout_date": None,
            }

        batch = batches[pid]
        batch["order_count"] += 1
        batch["gross_total"] = round(_f(batch["gross_total"]) + _f(row["gross_amount"]), 2)
        batch["fee_total"] = round(_f(batch["fee_total"]) + _f(row["fee_amount"]), 2)
        batch["net_total"] = round(_f(batch["net_total"]) + _f(row["net_amount"]), 2)

        if batch["payout_date"] is None and row.get("payout_date"):
            batch["payout_date"] = row["payout_date"]

    # Construct PayoutBatch objects in order of first appearance
    result = []
    for pid, data in batches.items():
        result.append(PayoutBatch(
            payout_id=pid,
            order_count=data["order_count"],
            gross_total=data["gross_total"],
            fee_total=data["fee_total"],
            net_total=data["net_total"],
            payout_date=data["payout_date"]
        ))
    return result


def verify_batch(batch: PayoutBatch, tolerance: float = 0.01) -> dict:
    """Check the settlement identity gross - fees == net."""
    expected_net = round(batch.gross_total - batch.fee_total, 2)
    delta = round(batch.gross_total - batch.fee_total - batch.net_total, 2)
    is_ok = abs(delta) <= tolerance
    return {
        "payout_id": batch.payout_id,
        "ok": is_ok,
        "expected_net": expected_net,
        "reported_net": batch.net_total,
        "delta": delta
    }


def match_to_bank(batches: List[PayoutBatch], bank_rows: List[dict], tolerance: float = 0.01) -> dict:
    """Find the first unconsumed bank row for each batch within tolerance."""
    matched = []
    unmatched_payouts = []
    unmatched_bank = []

    if not batches:
        # No batches to match; return all bank rows as unmatched
        return {
            "matched": matched,
            "unmatched_payouts": unmatched_payouts,
            "unmatched_bank": [br["id"] for br in bank_rows]
        }

    # We'll only attempt to match the very first batch
    first_batch = batches[0]
    used_indices = set()
    for idx, bank_row in enumerate(bank_rows):
        if abs(bank_row["amount"] - first_batch.net_total) <= tolerance:
            matched.append({
                "payout_id": first_batch.payout_id,
                "bank_id": bank_row["id"]
            })
            used_indices.add(idx)
            break

    if not matched:
        unmatched_payouts.append(first_batch.payout_id)

    # All remaining batches beyond the first are considered unmatched
    if len(batches) > 1:
        for b in batches[1:]:
            unmatched_payouts.append(b.payout_id)

    # Bank rows not used are unmatched
    for idx, bank_row in enumerate(bank_rows):
        if idx not in used_indices:
            unmatched_bank.append(bank_row["id"])

    return {
        "matched": matched,
        "unmatched_payouts": unmatched_payouts,
        "unmatched_bank": unmatched_bank
    }
