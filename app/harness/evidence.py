import io
import json
import zipfile
import os
import datetime
from typing import List, Dict, Any, Optional

def build_manifest(case: dict, audit_events: list[dict]) -> dict:
    return {
        'case_id': case.get('case_id'),
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'event_count': len(audit_events),
        'status': case.get('status'),
        'confidence': case.get('confidence')
    }

def build_pack(case: dict, audit_events: list[dict], transactions: Optional[list[dict]] = None) -> bytes:
    if transactions is None:
        transactions = []

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = build_manifest(case, audit_events)
        zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))
        zf.writestr('case.json', json.dumps(case, indent=2, default=str))
        zf.writestr('audit_events.json', json.dumps(audit_events, indent=2, default=str))
        zf.writestr('transactions.json', json.dumps(transactions, indent=2, default=str))
        zf.writestr('README.txt', f"Case ID: {case.get('case_id')}\nThis pack is a self-contained record of how this reconciliation case was decided.")
    buffer.seek(0)
    return buffer.getvalue()

def write_pack(path: str, case: dict, audit_events: list[dict], transactions: Optional[list[dict]] = None) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = build_pack(case, audit_events, transactions)
    with open(path, 'wb') as f:
        f.write(data)
    return path

def read_pack_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return sorted(zf.namelist())
