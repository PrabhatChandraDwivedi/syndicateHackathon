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
    {"id": "C010", "source": "corporate_card", "account_id": "CARD-9012", "date": "2026-08-18", "amount": "450.00", "currency": "INR", "counterparty_raw": "POS VISA STARBUCKS INDIA PVT LTD 4412998", "reference_raw": "REF4412998"},
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
]

# File headers for consistency
_MERCHANTS_HEADER = ["merchant_id", "canonical_name", "aliases", "default_gl_code"]
_CARD_HEADER = ["id", "source", "account_id", "date", "amount", "currency", "counterparty_raw", "reference_raw"]


def generate(out_dir: str) -> Dict[str, Path]:
    """
    Generate seed data files in the specified directory.
    
    Creates the directory if it does not exist.
    Writes merchants.csv, card.csv, and bank.csv.
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
    
    return {
        "merchants": merchants_path,
        "card": card_path,
        "bank": bank_path
    }
