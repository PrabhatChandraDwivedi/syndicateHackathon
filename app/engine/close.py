from dataclasses import dataclass
from typing import Optional


def norm_ref(ref: Optional[str]) -> str:
    """Normalize a reference string to uppercase alphanumeric."""
    if not ref:
        return ''
    # Uppercase, strip whitespace, keep only A-Z and 0-9
    return ''.join(ch for ch in ref.upper().strip() if ch.isalnum())


@dataclass
class CloseRow:
    order_ref: str
    ops_id: Optional[str]
    erp_id: Optional[str]
    bank_id: Optional[str]
    status: str
    ops_net: float
    erp_amount: float
    bank_amount: float
    variance: float


def three_way_match(
    ops: list[dict],
    erp: list[dict],
    bank: list[dict],
    tolerance: float = 0.01,
) -> dict:
    # Index rows by normalized reference (order_ref for ERP/OPS, reference_raw for Bank)
    # First occurrence wins on duplicates
    erp_index = {}
    for row in erp:
        key = norm_ref(row.get('order_ref'))
        if key and key not in erp_index:
            erp_index[key] = row

    bank_index = {}
    for row in bank:
        key = norm_ref(row.get('reference_raw'))
        if key and key not in bank_index:
            bank_index[key] = row

    # Process OPS to find order_ref keys and derive amounts
    # We process this first to build the ops_keys set for bank matching
    ops_rows_data = []
    ops_keys = set()
    for row in ops:
        key = norm_ref(row.get('order_ref'))
        if key:
            ops_keys.add(key)

        # Calculate ops_net
        gross = float(row.get('gross_amount', 0))
        fees = float(row.get('fees', 0))
        net_raw = row.get('net_amount')
        # Use net_amount if present, else gross - fees
        ops_net = round(float(net_raw) if net_raw is not None else (gross - fees), 2)
        ops_rows_data.append({'key': key, 'ops_net': ops_net})

    # Collect unexplained bank
    unexplained_bank_ids = []
    for b_key, b_row in bank_index.items():
        if b_key not in ops_keys:
            unexplained_bank_ids.append(b_row.get('id', ''))

    # Build CloseRows
    closed_count = 0
    partial_count = 0
    orphan_count = 0
    total_count = 0

    close_rows = []
    for ops_data in ops_rows_data:
        key = ops_data['key']
        ops_net = ops_data['ops_net']

        erp_entry = erp_index.get(key)
        erp_amt = erp_entry.get('amount', 0) if erp_entry else 0.0
        erp_id = erp_entry.get('id') if erp_entry else None

        bank_entry = bank_index.get(key)
        bank_amt = bank_entry.get('amount', 0) if bank_entry else 0.0
        bank_id = bank_entry.get('id') if bank_entry else None

        variance = round(ops_net - bank_amt, 2)

        has_erp = erp_entry is not None
        has_bank = bank_entry is not None

        is_closed = has_erp and has_bank and abs(variance) <= tolerance

        if is_closed:
            status = 'closed'
            closed_count += 1
        elif has_erp or has_bank:
            status = 'partial'
            partial_count += 1
        else:
            status = 'orphan'
            orphan_count += 1

        total_count += 1

        row = CloseRow(
            order_ref=key,
            ops_id=None,
            erp_id=erp_id,
            bank_id=bank_id,
            status=status,
            ops_net=ops_net,
            erp_amount=erp_amt,
            bank_amount=bank_amt,
            variance=variance,
        )
        close_rows.append(row)

    # Calculate readiness
    readiness = round(closed_count / total_count, 4) if total_count else 0.0

    return {
        'rows': close_rows,
        'summary': {
            'closed': closed_count,
            'partial': partial_count,
            'orphan': orphan_count,
            'total': total_count,
        },
        'unexplained_bank': unexplained_bank_ids,
        'readiness': readiness,
    }
