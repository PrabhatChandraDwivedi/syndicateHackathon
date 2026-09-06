from typing import List, Dict, Any
from dataclasses import dataclass


def normalize_invoice_number(num: str | None) -> str:
    """
    Uppercase, remove every character that is not A-Z or 0-9.
    Returns '' for None/blank.
    """
    if num is None:
        return ""
    # Keep only alphanumeric characters, convert to uppercase
    cleaned = "".join(c for c in num if c.isalnum())
    return cleaned.upper()


def match_key(row: dict) -> str:
    """
    Returns the match key: supplier_gstin|normalized_invoice_number
    """
    gstin = (row.get('supplier_gstin') or '').upper().strip()
    inv_num = normalize_invoice_number(row.get('invoice_number'))
    return f"{gstin}|{inv_num}"


def total_tax(row: dict) -> float:
    """
    Returns round(igst + cgst + sgst, 2).
    Missing/None values are treated as 0.0.
    """
    try:
        igst = float(row.get('igst') or 0)
        cgst = float(row.get('cgst') or 0)
        sgst = float(row.get('sgst') or 0)
    except (TypeError, ValueError):
        igst = 0.0
        cgst = 0.0
        sgst = 0.0

    return round(igst + cgst + sgst, 2)


@dataclass
class GSTExceptionRow:
    key: str
    exception_type: str
    purchase_row: dict | None
    gstr_row: dict | None
    taxable_delta: float
    tax_delta: float


def reconcile_gst(
    purchase_rows: List[Dict[str, Any]], 
    gstr_rows: List[Dict[str, Any]], 
    tolerance: float = 1.0
) -> Dict[str, Any]:
    """
    Reconciles GST data.
    Returns a dict with matched count, exceptions, ITC at risk, and counts.
    """
    # Index rows by match key, keeping first occurrence if duplicates exist
    p_lookup: Dict[str, Dict[str, Any]] = {}
    for row in purchase_rows:
        k = match_key(row)
        if k not in p_lookup:
            p_lookup[k] = row

    g_lookup: Dict[str, Dict[str, Any]] = {}
    for row in gstr_rows:
        k = match_key(row)
        if k not in g_lookup:
            g_lookup[k] = row

    matched_count = 0
    exceptions: List[GSTExceptionRow] = []
    itc_at_risk_sum = 0.0

    # Get intersection of keys
    common_keys = set(p_lookup.keys()) & set(g_lookup.keys())

    # Handle matches and mismatches
    for key in common_keys:
        p_row = p_lookup[key]
        g_row = g_lookup[key]

        p_taxable = float(p_row.get('taxable_value') or 0)
        g_taxable = float(g_row.get('taxable_value') or 0)

        p_tax = total_tax(p_row)
        g_tax = total_tax(g_row)

        delta_taxable = abs(p_taxable - g_taxable)
        delta_tax = abs(p_tax - g_tax)

        # Check if within tolerance for both
        if delta_taxable <= tolerance and delta_tax <= tolerance:
            matched_count += 1
        else:
            exception = GSTExceptionRow(
                key=key,
                exception_type='value_mismatch',
                purchase_row=p_row,
                gstr_row=g_row,
                taxable_delta=round(p_taxable - g_taxable, 2),
                tax_delta=round(p_tax - g_tax, 2)
            )
            exceptions.append(exception)

    # Handle Purchase rows NOT in GSTR-2B
    purchase_missing_keys = set(p_lookup.keys()) - set(g_lookup.keys())
    for key in purchase_missing_keys:
        p_row = p_lookup[key]
        itc_at_risk_sum += total_tax(p_row)
        exceptions.append(GSTExceptionRow(
            key=key,
            exception_type='missing_in_gstr2b',
            purchase_row=p_row,
            gstr_row=None,
            taxable_delta=0.0,
            tax_delta=0.0
        ))

    # Handle GSTR rows NOT in Purchase Register
    gstr_missing_keys = set(g_lookup.keys()) - set(p_lookup.keys())
    for key in gstr_missing_keys:
        g_row = g_lookup[key]
        exceptions.append(GSTExceptionRow(
            key=key,
            exception_type='missing_in_purchase_register',
            purchase_row=None,
            gstr_row=g_row,
            taxable_delta=0.0,
            tax_delta=0.0
        ))

    return {
        'matched': matched_count,
        'exceptions': exceptions,
        'itc_at_risk': round(itc_at_risk_sum, 2),
        'counts': {
            'purchase': len(purchase_rows),
            'gstr2b': len(gstr_rows)
        }
    }
