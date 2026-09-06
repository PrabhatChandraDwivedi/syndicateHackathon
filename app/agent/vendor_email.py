"""Vendor chaser drafts for GST findings.

Prepares emails; never sends them. Drafts go into the outbox as pending and a
human decides what leaves the building.
"""

import re
from typing import Any, Dict, Optional

from app.harness.notify import Outbox

NOT_SENT_NOTICE = "This draft was prepared automatically and has not been sent."

# Findings worth chasing a supplier about, and why.
CHASEABLE = {
    "missing_in_gstr2b": "invoice missing from GSTR-2B",
    "value_mismatch": "value filed in GSTR-2B differs from our purchase register",
}

SUBJECTS = {
    "missing_in_gstr2b": "Action required: GST invoice {inv} not reflected in GSTR-2B",
    "value_mismatch": "Action required: GST invoice {inv} filed with a different value",
}

EXPLANATION = {
    "missing_in_gstr2b": (
        "This invoice does not appear in our GSTR-2B for the period, so we cannot claim "
        "input tax credit against it."
    ),
    "value_mismatch": (
        "This invoice appears in our GSTR-2B for the period, but the value filed does not "
        "match the value on our purchase register, so part of the input tax credit is at risk."
    ),
}


def recipient_for(supplier_gstin: Optional[str]) -> str:
    if not supplier_gstin:
        supplier_gstin = "unknown"
    s = re.sub(r"\W+", "-", supplier_gstin.strip())
    return f"ap-{s}@vendor.invalid"


def subject_for(invoice_number: str, exception_type: str = "missing_in_gstr2b") -> str:
    template = SUBJECTS.get(exception_type, SUBJECTS["missing_in_gstr2b"])
    return template.format(inv=invoice_number)


def compose_draft(
    invoice_number: str,
    supplier_gstin: str,
    reason: str,
    taxable_value: float = 0.0,
    tax_at_risk: float = 0.0,
    exception_type: str = "missing_in_gstr2b",
) -> Dict[str, Any]:
    body_lines = [
        f"Invoice Number: {invoice_number}",
        f"Supplier GSTIN: {supplier_gstin}",
        f"Taxable Value: {taxable_value:.2f}",
        f"Tax at Risk: {tax_at_risk:.2f}",
        f"Reason: {reason}",
        EXPLANATION.get(exception_type, EXPLANATION["missing_in_gstr2b"]),
        "Please confirm the filing status and share the acknowledgement reference.",
        NOT_SENT_NOTICE,
    ]
    return {
        "recipient": recipient_for(supplier_gstin),
        "subject": subject_for(invoice_number, exception_type),
        "body": "\n".join(body_lines),
        "channel": "email",
    }


def draft_and_enqueue(
    outbox: Optional[Outbox],
    invoice_number: str,
    supplier_gstin: str,
    reason: str,
    taxable_value: float = 0.0,
    tax_at_risk: float = 0.0,
    case_id: Optional[str] = None,
    exception_type: str = "missing_in_gstr2b",
) -> Dict[str, Any]:
    if outbox is None:
        return {"ok": False, "error": "no outbox configured"}

    # Build the draft once so what we report is what we stored.
    draft = compose_draft(
        invoice_number, supplier_gstin, reason, taxable_value, tax_at_risk, exception_type
    )
    try:
        draft_id = outbox.enqueue(
            draft["channel"], draft["recipient"], draft["subject"], draft["body"], case_id
        )
        return {
            "ok": True,
            "draft_id": draft_id,
            "recipient": draft["recipient"],
            "subject": draft["subject"],
            "status": "pending",
            "case_id": case_id,
            "invoice_number": invoice_number,
            "supplier_gstin": supplier_gstin,
            "exception_type": exception_type,
        }
    except Exception as e:  # noqa: BLE001 - never raise into the agent
        return {"ok": False, "error": str(e)}


def _f(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _amounts(exc: Dict[str, Any]) -> tuple:
    """Best available taxable value and tax at risk for a GST exception.

    A missing invoice carries zero deltas -- the whole invoice is at risk, so the
    real figures come off the purchase register row. A value mismatch is only at
    risk for the difference, so the deltas are the right numbers.
    """
    etype = exc.get("exception_type")
    if etype == "value_mismatch":
        return abs(_f(exc.get("taxable_delta"))), abs(_f(exc.get("tax_delta")))

    row = exc.get("purchase_row") or {}
    taxable = _f(row.get("taxable_value"))
    tax = _f(row.get("igst")) + _f(row.get("cgst")) + _f(row.get("sgst"))
    if not taxable and not tax:
        taxable, tax = abs(_f(exc.get("taxable_delta"))), abs(_f(exc.get("tax_delta")))
    return round(taxable, 2), round(tax, 2)


def drafts_from_gst(
    gst_result: Dict[str, Any], outbox: Optional[Outbox], limit: int = 10
) -> Dict[str, Any]:
    """Draft a chaser for every GST finding a supplier has to answer for.

    Both an unfiled invoice and one filed at the wrong value put input tax credit
    at risk, so both are chased. A row that exists only in GSTR-2B is our own
    bookkeeping gap, not the supplier's, so it is left alone.
    """
    drafts = []
    for exc in gst_result.get("exceptions", []):
        if len(drafts) >= limit:
            break
        etype = exc.get("exception_type")
        if etype not in CHASEABLE:
            continue
        taxable, tax = _amounts(exc)
        result = draft_and_enqueue(
            outbox,
            exc.get("invoice_number", ""),
            exc.get("supplier_gstin", ""),
            CHASEABLE[etype],
            taxable_value=taxable,
            tax_at_risk=tax,
            exception_type=etype,
        )
        result["invoice_number"] = exc.get("invoice_number", "")
        result["supplier_gstin"] = exc.get("supplier_gstin", "")
        drafts.append(result)

    return {"drafted": sum(1 for d in drafts if d.get("ok")), "drafts": drafts}
