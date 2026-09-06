from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.financial_transaction import FinancialTransaction


def file_id(path: str) -> str:
    """Return the first 16 hex characters of the sha256 of the file's raw bytes."""
    with open(path, "rb") as f:
        file_hash = hashlib.sha256(f.read())
    return file_hash.hexdigest()[:16]


def load_csv(path: str) -> list[dict]:
    """Read the file with csv.DictReader and return the rows as plain dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def to_transactions(rows: list[dict], source: str, source_file_id: Optional[str] = None) -> list[FinancialTransaction]:
    """Map each row to a FinancialTransaction."""
    transactions: list[FinancialTransaction] = []

    for row in rows:
        row_id = row.get("id")
        # Skip any row whose 'id' is missing or blank.
        if not row_id or not str(row_id).strip():
            continue

        amount_raw = row.get("amount", "")
        if amount_raw and amount_raw.strip():
            try:
                amount = float(amount_raw)
            except (ValueError, TypeError):
                amount = None
        else:
            amount = None

        transaction = FinancialTransaction(
            id=str(row_id).strip(),
            source=source,  # Override argument, NOT the csv column
            account_id=row.get("account_id"),
            date=row.get("date"),
            amount=amount,
            currency=row.get("currency"),
            counterparty_raw=row.get("counterparty_raw"),
            reference_raw=row.get("reference_raw"),
            raw_payload=row,  # The whole original row dict
            source_file_id=source_file_id,
            ingested_at=datetime.now(timezone.utc).isoformat(),
            external_id=row.get("reference_raw"),
        )
        transactions.append(transaction)

    return transactions


def ingest_file(path: str, source: str) -> list[FinancialTransaction]:
    """Convenience wrapper to compute file id, load CSV, and return transactions."""
    fid = file_id(path)
    rows = load_csv(path)
    return to_transactions(rows, source, fid)
