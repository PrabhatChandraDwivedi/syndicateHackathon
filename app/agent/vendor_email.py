import re
from typing import Any, Dict, Optional

from app.harness.notify import Outbox

NOT_SENT_NOTICE = "This draft was prepared automatically and has not been sent."


def recipient_for(supplier_gstin: Optional[str]) -> str:
    if not supplier_gstin:
        supplier_gstin = "unknown"
    s = supplier_gstin.strip()
    s = re.sub(r"\W+", "-", s)
    return f"ap-{s}@vendor.invalid"


def subject_for(invoice_number: str) -> str:
    return f"Action required: GST invoice {invoice_number} not reflected in GSTR-2B"


def compose_draft(
    invoice_number: str,
    supplier_gstin: str,
    reason: str,
    taxable_value: float = 0.0,
    tax_at_risk: float = 0.0,
) -> Dict[str, Any]:
    body_lines = [
        f"Invoice Number: {invoice_number}",
        f"Supplier GSTIN: {supplier_gstin}",
        f"Taxable Value: {taxable_value:.2f}",
        f"Tax at Risk: {tax_at_risk:.2f}",
        f"Reason: {reason}",
        "This invoice does not appear in our GSTR-2B for the period so we cannot claim input tax credit.",
        "Please confirm the filing status.",
        NOT_SENT_NOTICE,
    ]
    body = "\n".join(body_lines)
    return {
        "recipient": recipient_for(supplier_gstin),
        "subject": subject_for(invoice_number),
        "body": body,
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
) -> Dict[str, Any]:
    if outbox is None:
        return {"ok": False, "error": "no outbox configured"}

    # Build draft once and reuse its values for both enqueue and return
    draft = compose_draft(invoice_number, supplier_gstin, reason, taxable_value, tax_at_risk)
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
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def drafts_from_gst(
    gst_result: Dict[str, Any], outbox: Optional[Outbox], limit: int = 10
) -> Dict[str, Any]:
    exceptions = gst_result.get("exceptions", [])
    drafted_count = 0
    drafts = []

    exceptions_to_process = exceptions[:limit]

    for exc in exceptions_to_process:
        if exc.get("exception_type") == "missing_in_gstr2b":
            result = draft_and_enqueue(
                outbox,
                exc["invoice_number"],
                exc["supplier_gstin"],
                "invoice missing from GSTR-2B",
                case_id=None,
            )
            result["invoice_number"] = exc["invoice_number"]
            result["supplier_gstin"] = exc["supplier_gstin"]
            drafts.append(result)
            drafted_count += 1

    return {"drafted": drafted_count, "drafts": drafts}
