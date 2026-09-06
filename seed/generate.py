import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


# Constants holding demo data as lists of dicts for easy DictWriter handling
_MERCHANTS_ROWS: List[Dict[str, Any]] = [
    {"merchant_id": "M1", "canonical_name": "Starbucks Coffee", "aliases": "SBUX|Starbucks India", "default_gl_code": "6010"},
    {"merchant_id": "M2", "canonical_name": "Swiggy", "aliases": "Bundl Technologies|Swiggy Foods", "default_gl_code": "6020"},
    {"merchant_id": "M3", "canonical_name": "Amazon Web Services", "aliases": "AWS|Amazon Web Svcs", "default_gl_code": "6030"},
    {"merchant_id": "M4", "canonical_name": "Uber India", "aliases": "Uber BV|Uber Rides", "default_gl_code": "6040"},
    {"merchant_id": "M5", "canonical_name": "Zoom Video", "aliases": "Zoom Communications", "default_gl_code": "6050"},
]

_CARD_ROWS: List[Dict[str, Any]] = [
    {"id": "C001", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-03", "amount": "450.00", "currency": "INR", "counterparty_raw": "POS VISA STARBUCKS INDIA PVT LTD 4412998", "reference_raw": "REF4412998"},
    {"id": "C002", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-04", "amount": "1250.50", "currency": "INR", "counterparty_raw": "UPI-SWIGGY-REF908812", "reference_raw": "REF908812"},
    {"id": "C003", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-05", "amount": "89000.00", "currency": "INR", "counterparty_raw": "AWS EMEA SARL AMAZON WEB SERVICES", "reference_raw": "INV-AWS-8891"},
    {"id": "C004", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-07", "amount": "320.75", "currency": "INR", "counterparty_raw": "UBER INDIA SYSTEMS POS 771234", "reference_raw": "REF771234"},
    {"id": "C005", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-09", "amount": "14999.00", "currency": "INR", "counterparty_raw": "ZOOM VIDEO COMMUNICATIONS ONLINE", "reference_raw": "ZM-55521"},
    {"id": "C006", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-11", "amount": "600.00", "currency": "INR", "counterparty_raw": "POS STARBUCKS COFFEE 998123", "reference_raw": "REF998123"},
    {"id": "C007", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-12", "amount": "400.00", "currency": "INR", "counterparty_raw": "SWIGGY ORDER 100234", "reference_raw": "REF100234"},
    {"id": "C008", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-12", "amount": "850.50", "currency": "INR", "counterparty_raw": "SWIGGY ORDER 100235", "reference_raw": "REF100235"},
    {"id": "C009", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-15", "amount": "2750.00", "currency": "INR", "counterparty_raw": "UNKNOWN VENDOR XYZ 5567", "reference_raw": "REF5567"},
    {"id": "C010", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-03", "amount": "450.00", "currency": "INR", "counterparty_raw": "POS VISA STARBUCKS INDIA PVT LTD 4412998", "reference_raw": "REF4412998"},
    {"id": "C011", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-14", "amount": "3200.00", "currency": "INR", "counterparty_raw": "POS UBER INDIA SYSTEMS 88231", "reference_raw": "REFUBER8823"},
]

_BANK_ROWS: List[Dict[str, Any]] = [
    {"id": "B001", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-03", "amount": "450.00", "currency": "INR", "counterparty_raw": "STARBUCKS INDIA", "reference_raw": "REF4412998"},
    {"id": "B002", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-04", "amount": "1250.50", "currency": "INR", "counterparty_raw": "SWIGGY", "reference_raw": "REF908812"},
    {"id": "B003", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-06", "amount": "89000.00", "currency": "INR", "counterparty_raw": "AMAZON WEB SERVICES EMEA", "reference_raw": "INV-AWS-8891"},
    {"id": "B004", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-08", "amount": "320.75", "currency": "INR", "counterparty_raw": "UBER INDIA", "reference_raw": "REF771234"},
    {"id": "B005", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-10", "amount": "14999.00", "currency": "INR", "counterparty_raw": "ZOOM VIDEO", "reference_raw": "ZM-55521"},
    {"id": "B006", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-12", "amount": "1250.50", "currency": "INR", "counterparty_raw": "SWIGGY AGGREGATED PAYOUT", "reference_raw": "BULK-7781"},
    {"id": "B007", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-13", "amount": "600.00", "currency": "INR", "counterparty_raw": "STARBUCKS", "reference_raw": "REF998123"},
    {"id": "B008", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-20", "amount": "5000.00", "currency": "INR", "counterparty_raw": "UNMATCHED BANK CREDIT", "reference_raw": "REF9999"},
    {"id": "B009", "source": "bank", "account_id": "BANK-4471", "date": "2026-08-16", "amount": "3200.00", "currency": "INR", "counterparty_raw": "UBER INDIA", "reference_raw": "BULK9001"},
]


# File headers for consistency
_MERCHANTS_HEADER = ["merchant_id", "canonical_name", "aliases", "default_gl_code"]
_CARD_HEADER = ["id", "source", "account_id", "date", "amount", "currency", "counterparty_raw", "reference_raw"]


# New datasets for GST reconciliation and three-way month close
_PURCHASE_HEADER = ["supplier_gstin", "invoice_number", "invoice_date", "taxable_value", "igst", "cgst", "sgst"]
_PURCHASE_ROWS: List[Dict[str, Any]] = [
    {"supplier_gstin": "29AABCU9603R1ZM", "invoice_number": "INV-2026-001", "invoice_date": "2026-08-05", "taxable_value": "89000.00", "igst": "0.00", "cgst": "8010.00", "sgst": "8010.00"},
    {"supplier_gstin": "27AAACS1429B1ZQ", "invoice_number": "INV-2026-002", "invoice_date": "2026-08-09", "taxable_value": "14999.00", "igst": "0.00", "cgst": "1349.91", "sgst": "1349.91"},
    {"supplier_gstin": "29AABCU9603R1ZM", "invoice_number": "INV-2026-003", "invoice_date": "2026-08-12", "taxable_value": "25000.00", "igst": "4500.00", "cgst": "0.00", "sgst": "0.00"},
    {"supplier_gstin": "07AAGFF2194N1Z1", "invoice_number": "INV-2026-004", "invoice_date": "2026-08-15", "taxable_value": "12000.00", "igst": "0.00", "cgst": "1080.00", "sgst": "1080.00"},
    {"supplier_gstin": "24AAACC1206D1ZM", "invoice_number": "INV-2026-005", "invoice_date": "2026-08-18", "taxable_value": "5000.00", "igst": "0.00", "cgst": "450.00", "sgst": "450.00"},
]

_GSTR2B_HEADER = _PURCHASE_HEADER
_GSTR2B_ROWS: List[Dict[str, Any]] = [
    {"supplier_gstin": "29AABCU9603R1ZM", "invoice_number": "INV-2026-001", "invoice_date": "2026-08-05", "taxable_value": "89000.00", "igst": "0.00", "cgst": "8010.00", "sgst": "8010.00"},
    {"supplier_gstin": "27AAACS1429B1ZQ", "invoice_number": "INV-2026-002", "invoice_date": "2026-08-09", "taxable_value": "14000.00", "igst": "0.00", "cgst": "1260.00", "sgst": "1260.00"},
    {"supplier_gstin": "29AABCU9603R1ZM", "invoice_number": "INV-2026-003", "invoice_date": "2026-08-12", "taxable_value": "25000.00", "igst": "4500.00", "cgst": "0.00", "sgst": "0.00"},
    {"supplier_gstin": "24AAACC1206D1ZM", "invoice_number": "INV-2026-005", "invoice_date": "2026-08-18", "taxable_value": "5000.00", "igst": "0.00", "cgst": "450.00", "sgst": "450.00"},
    {"supplier_gstin": "33AAKCS1234M1Z5", "invoice_number": "INV-2026-099", "invoice_date": "2026-08-20", "taxable_value": "7500.00", "igst": "0.00", "cgst": "675.00", "sgst": "675.00"},
]

_OPS_HEADER = ["ops_id", "order_ref", "date", "gross_amount", "fees", "net_amount", "channel"]
_OPS_ROWS: List[Dict[str, Any]] = [
    {"ops_id": "OPS001", "order_ref": "ORD-5001", "date": "2026-08-03", "gross_amount": "10000.00", "fees": "300.00", "net_amount": "9700.00", "channel": "web"},
    {"ops_id": "OPS002", "order_ref": "ORD-5002", "date": "2026-08-05", "gross_amount": "25000.00", "fees": "750.00", "net_amount": "24250.00", "channel": "web"},
    {"ops_id": "OPS003", "order_ref": "ORD-5003", "date": "2026-08-08", "gross_amount": "5000.00", "fees": "150.00", "net_amount": "4850.00", "channel": "retail"},
    {"ops_id": "OPS004", "order_ref": "ORD-5004", "date": "2026-08-12", "gross_amount": "18000.00", "fees": "540.00", "net_amount": "17460.00", "channel": "web"},
]

_ERP_HEADER = ["id", "order_ref", "invoice_date", "amount"]
_ERP_ROWS: List[Dict[str, Any]] = [
    {"id": "ERP001", "order_ref": "ORD-5001", "invoice_date": "2026-08-03", "amount": "9700.00"},
    {"id": "ERP002", "order_ref": "ORD-5002", "invoice_date": "2026-08-05", "amount": "24250.00"},
    {"id": "ERP003", "order_ref": "ORD-5003", "invoice_date": "2026-08-08", "amount": "4850.00"},
]

_SETTLEMENTS_HEADER = ["id", "reference_raw", "date", "amount"]
_SETTLEMENTS_ROWS: List[Dict[str, Any]] = [
    {"id": "SET001", "reference_raw": "ORD-5001", "date": "2026-08-05", "amount": "9700.00"},
    {"id": "SET002", "reference_raw": "ORD-5002", "date": "2026-08-07", "amount": "24250.00"},
    {"id": "SET003", "reference_raw": "ORD-5003", "date": "2026-08-10", "amount": "4000.00"},
    {"id": "SET009", "reference_raw": "ORD-9999", "date": "2026-08-15", "amount": "1200.00"},
]


def generate(out_dir: str) -> Dict[str, Path]:
    """
    Generate seed data files in the specified directory.
    
    Creates the directory if it does not exist.
    Writes merchants.csv, card.csv, and bank.csv.
    Also writes GST/GL reconciliation datasets: purchase_register.csv, gstr2b.csv,
    and three-way month close datasets: ops.csv, erp.csv, settlements.csv.
    Returns a mapping of logical name to the file path.
    """
    output_path = Path(out_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Write merchants.csv
    merchants_path = output_path / "merchants.csv"
    with merchants_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_MERCHANTS_HEADER)
        writer.writeheader()
        writer.writerows(_MERCHANTS_ROWS)
    
    # Write card.csv
    card_path = output_path / "card.csv"
    with card_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CARD_HEADER)
        writer.writeheader()
        writer.writerows(_CARD_ROWS)
    
    # Write bank.csv
    bank_path = output_path / "bank.csv"
    with bank_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CARD_HEADER)
        writer.writeheader()
        writer.writerows(_BANK_ROWS)
    
    # Write GST reconciliation datasets
    purchase_path = output_path / "purchase_register.csv"
    with purchase_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_PURCHASE_HEADER)
        writer.writeheader()
        writer.writerows(_PURCHASE_ROWS)
    
    gstr2b_path = output_path / "gstr2b.csv"
    with gstr2b_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_GSTR2B_HEADER)
        writer.writeheader()
        writer.writerows(_GSTR2B_ROWS)
    
    # Write OPS/ERP/SETTLEMENTS files
    ops_path = output_path / "ops.csv"
    with ops_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_OPS_HEADER)
        writer.writeheader()
        writer.writerows(_OPS_ROWS)
    
    erp_path = output_path / "erp.csv"
    with erp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_ERP_HEADER)
        writer.writeheader()
        writer.writerows(_ERP_ROWS)
    
    settlements_path = output_path / "settlements.csv"
    with settlements_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SETTLEMENTS_HEADER)
        writer.writeheader()
        writer.writerows(_SETTLEMENTS_ROWS)
    
    return {
        "merchants": merchants_path,
        "card": card_path,
        "bank": bank_path,
        "purchase_register": purchase_path,
        "gstr2b": gstr2b_path,
        "ops": ops_path,
        "erp": erp_path,
        "settlements": settlements_path
    }
