from dataclasses import dataclass
from typing import Optional


def _f(value) -> float:
    """Coerce a numeric-like value to a float, handling strings with commas and blanks."""
    try:
        if value is None:
            return 0.0
        s = str(value).replace(",", "").strip()
        return float(s) if s != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def norm_ref(ref: Optional[str]) -> str:
    """Normalize a reference string to uppercase, preserving hyphens.
    Keeps alphanumeric characters and hyphen (-)."""
    if not ref:
        return ''
    s = str(ref).strip().upper()
    return ''.join(ch for ch in s if ch.isalnum() or ch == '-')


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
    # Index ERP and Bank by normalized reference
    erp_index: dict[str, dict] = {}
    for row in erp:
        key = norm_ref(row.get('order_ref'))
        if key and key not in erp_index:
            erp_index[key] = row

    bank_index: dict[str, dict] = {}
    for row in bank:
        key = norm_ref(row.get('reference_raw'))
        if key and key not in bank_index:
            bank_index[key] = row

    # OPS rows: collect keys and compute ops_net
    ops_rows_data: list[dict] = []
    ops_keys: set[str] = set()
    for row in ops:
        key = norm_ref(row.get('order_ref'))
        if key:
            ops_keys.add(key)

        gross = _f(row.get('gross_amount'))
        fees = _f(row.get('fees'))
        net_raw = row.get('net_amount')
        has_net = not (net_raw is None or (isinstance(net_raw, str) and net_raw.strip() == ''))
        if has_net:
            ops_net = round(_f(net_raw), 2)
        else:
            ops_net = round(gross - fees, 2)

        ops_rows_data.append({'key': key, 'ops_net': ops_net})

    # Bank rows that did not map to OPS
    unexplained_bank_ids = []
    for b_key, b_row in bank_index.items():
        if b_key not in ops_keys:
            unexplained_bank_ids.append(b_row.get('id', ''))

    closed_count = 0
    partial_count = 0
    orphan_count = 0
    total_count = 0

    close_rows: list[CloseRow] = []
    for ops_data in ops_rows_data:
        key = ops_data['key']
        ops_net = ops_data['ops_net']

        erp_entry = erp_index.get(key)
        erp_amt = _f(erp_entry.get('amount', 0)) if erp_entry else 0.0
        erp_id = erp_entry.get('id') if erp_entry else None

        bank_entry = bank_index.get(key)
        bank_amt = _f(bank_entry.get('amount', 0)) if bank_entry else 0.0
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
