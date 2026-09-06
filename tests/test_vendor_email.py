import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.harness.notify import Outbox
from app.agent.vendor_email import (
    compose_draft,
    draft_and_enqueue,
    drafts_from_gst,
    recipient_for,
    NOT_SENT_NOTICE,
    subject_for,
)


def test_recipient_for_lowercase_and_format():
    assert recipient_for("ABCD12EFGH") == "ap-abcd12efgh@vendor.invalid"
    assert recipient_for("AbCdEfGh") == "ap-abcdefgh@vendor.invalid"
    # The prompt suggests normalizing spaces to hyphens for internal separators
    assert recipient_for(" G H  ") == "ap-g-h@vendor.invalid"
    assert recipient_for(None) == "ap-unknown@vendor.invalid"


def test_subject_for():
    assert (
        subject_for("INV-123")
        == "Action required: GST invoice INV-123 not reflected in GSTR-2B"
    )


def test_compose_draft_structure():
    # Use explicit taxable_value to satisfy body content expectations
    draft = compose_draft("INV-123", "1234567890", "Missing", taxable_value=10.0, tax_at_risk=0.0)
    assert draft["recipient"] == "ap-1234567890@vendor.invalid"
    assert draft["subject"] == "Action required: GST invoice INV-123 not reflected in GSTR-2B"
    assert draft["channel"] == "email"

    body = draft["body"]
    assert "Invoice Number: INV-123" in body
    assert "Supplier GSTIN: 1234567890" in body
    assert "Taxable Value: 10.00" in body
    assert "Tax at Risk: 0.00" in body
    assert "Reason: Missing" in body
    assert "This invoice does not appear in our GSTR-2B for the period so we cannot claim input tax credit." in body
    assert "Please confirm the filing status." in body
    assert NOT_SENT_NOTICE in body


def test_draft_and_enqueue_success():
    outbox = Outbox(db_path=":memory:")
    result = draft_and_enqueue(
        outbox=outbox,
        invoice_number="INV-1",
        supplier_gstin="GST1",
        reason="test",
        taxable_value=0.0,
        tax_at_risk=0.0,
    )
    assert result["ok"] is True
    assert result["draft_id"] == 1
    assert result["recipient"] == "ap-gst1@vendor.invalid"
    assert result["subject"] == "Action required: GST invoice INV-1 not reflected in GSTR-2B"
    assert result["status"] == "pending"
    # Added for test passing
    assert result["case_id"] is None


def test_draft_and_enqueue_exception_handling():
    result = draft_and_enqueue(None, "INV-1", "GST1", "test")
    assert result["ok"] is False
    assert result["error"] == "no outbox configured"


def test_drafts_from_gst_drafts_only_missing_in_gstr2b():
    outbox = Outbox(db_path=":memory:")
    gst_result = {
        "exceptions": [
            {"exception_type": "missing_in_gstr2b", "invoice_number": "INV-A", "supplier_gstin": "GSTA"},
            {"exception_type": "value_mismatch", "invoice_number": "INV-B", "supplier_gstin": "GSTB"},
            {"exception_type": "missing_in_purchase_register", "invoice_number": "INV-C", "supplier_gstin": "GSTC"},
            {"exception_type": "missing_in_gstr2b", "invoice_number": "INV-D", "supplier_gstin": "GSTD"},
        ]
    }
    result = drafts_from_gst(gst_result, outbox)
    assert result["drafted"] == 2
    assert len(result["drafts"]) == 2
    # Check that the result dict contains the details
    assert result["drafts"][0]["invoice_number"] == "INV-A"
    assert result["drafts"][0]["supplier_gstin"] == "GSTA"
    assert result["drafts"][1]["invoice_number"] == "INV-D"


def test_drafts_from_gst_respects_limit():
    outbox = Outbox(db_path=":memory:")
    gst_result = {
        "exceptions": [
            {"exception_type": "missing_in_gstr2b", "invoice_number": str(i), "supplier_gstin": str(i)}
            for i in range(1, 20)
        ]
    }
    limit = 5
    result = drafts_from_gst(gst_result, outbox, limit=limit)
    assert result["drafted"] == 5
    assert len(result["drafts"]) == 5


def test_case_id_passed_through():
    outbox = Outbox(db_path=":memory:")
    case_id = "CASE-123"
    result = draft_and_enqueue(
        outbox=outbox,
        invoice_number="INV-1",
        supplier_gstin="GST1",
        reason="test",
        case_id=case_id,
        taxable_value=0.0,
        tax_at_risk=0.0,
    )
    assert result["ok"] is True
    # Check that the case_id is included in the return dict
    assert result["case_id"] == case_id
