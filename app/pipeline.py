import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.db.store import connect, init_db, insert_row, query, count
from app.adapters.csv_source import ingest_file, load_csv
from app.engine.normalize import normalize_transaction, NormalizedTransaction
from app.models.merchant import Merchant
from app.engine.matching import reconcile, Match
from app.policy.engine import load_policy, decide
from app.harness.audit import AuditWriter
from app.harness.tracing import init_tracing, span, current_run_id, trace_id
from seed.generate import generate


def load_merchants(path: str) -> List[Merchant]:
    rows = load_csv(path)
    merchants: List[Merchant] = []
    for row in rows:
        merchant_id = row.get('merchant_id')
        canonical_name = row.get('canonical_name')
        aliases_raw = row.get('aliases', '')
        if isinstance(aliases_raw, str):
            aliases = [a for a in aliases_raw.split('|') if a]
        elif isinstance(aliases_raw, list):
            aliases = [a for a in aliases_raw if a]
        else:
            aliases = []
        default_gl_code = row.get('default_gl_code')
        merchants.append(Merchant(
            merchant_id=merchant_id,
            canonical_name=canonical_name,
            aliases=aliases,
            default_gl_code=default_gl_code
        ))
    return merchants


def _sum_source_amounts(sources: List[NormalizedTransaction], source_ids: List[str]) -> float:
    total = 0.0
    for sid in source_ids:
        for s in sources:
            candidates = []
            for attr in ('id', 'transaction_id', 'txn_id', 'source_id', 'external_id'):
                if getattr(s, attr, None) is not None:
                    candidates.append(getattr(s, attr))
            if sid in candidates:
                amt = getattr(s, 'amount', None)
                if isinstance(amt, (int, float)):
                    total += abs(float(amt))
                else:
                    amt2 = getattr(s, 'value', None)
                    if isinstance(amt2, (int, float)):
                        total += abs(float(amt2))
                break
    return total


def _amount_from_target(targets: List[NormalizedTransaction], target_id: str) -> float | None:
    for t in targets:
        candidates = []
        for attr in ('id', 'transaction_id', 'txn_id', 'target_id', 'external_id'):
            if getattr(t, attr, None) is not None:
                candidates.append(getattr(t, attr))
        if target_id in candidates:
            amt = getattr(t, 'amount', None)
            if isinstance(amt, (int, float)):
                return abs(float(amt))
            amt2 = getattr(t, 'value', None)
            if isinstance(amt2, (int, float)):
                return abs(float(amt2))
    return None


def _txn_to_row(txn: Any) -> Dict[str, Any]:
    if hasattr(txn, 'model_dump'):
        row = txn.model_dump()
        raw = row.get('raw_payload')
        if isinstance(raw, dict):
            row['raw_payload'] = json.dumps(raw)
        return row
    if isinstance(txn, dict):
        return dict(txn)
    return {}


@span('run_pipeline', kind='WORKFLOW')
def run_pipeline(db_path: str = ':memory:', data_dir: str = './seed/data', policy_path: str | None = None) -> dict:
    init_tracing()
    run_id = current_run_id()

    # Ensure seed data exists
    paths = generate(data_dir)

    # Initialize DB
    conn = connect(db_path)
    init_db(conn)

    # Load merchants for normalization
    merchants = load_merchants(paths['merchants'])

    # Ingest and persist card/bank transactions
    card_txns = ingest_file(paths['card'], 'corporate_card')
    bank_txns = ingest_file(paths['bank'], 'bank')

    # Persist to DB (best-effort; swallow DB errors to keep flow running if schema isn't as expected)
    for txn in card_txns:
        try:
            row = _txn_to_row(txn)
            insert_row(conn, 'financial_transaction', row)
        except Exception:
            pass
    for txn in bank_txns:
        try:
            row = _txn_to_row(txn)
            insert_row(conn, 'financial_transaction', row)
        except Exception:
            pass

    # Normalize
    sources = [normalize_transaction(txn, merchants) for txn in card_txns]
    targets = [normalize_transaction(txn, merchants) for txn in bank_txns]

    # Reconcile
    matches = reconcile(sources, targets)

    # Policy
    policy = load_policy(policy_path)

    auditor = AuditWriter(db_path)
    cases: List[Dict[str, Any]] = []
    auto_resolved = 0
    needs_review = 0
    exceptions_counts: Dict[str, int] = {}

    for i, match in enumerate(matches, start=1):
        case_id = f'case_{i:03d}'
        workflow = 'card_to_bank'
        source_ids_json = json.dumps(match.source_ids)
        candidate_target_ids_json = json.dumps([match.target_id] if match.target_id else [])
        confidence = match.confidence
        method = match.method
        exception_type = match.exception_type
        amount_delta = match.amount_delta
        reasons_json = json.dumps(match.reasons)

        # Compute amount for decision
        amount_for_match = 0.0
        if match.source_ids:
            amount_for_match = _sum_source_amounts(sources, match.source_ids)
        if amount_for_match == 0.0 and match.target_id:
            t_amt = _amount_from_target(targets, match.target_id)
            if t_amt is not None:
                amount_for_match = t_amt

        decision = decide(confidence, amount_for_match, exception_type, policy)

        status = 'auto_resolved' if isinstance(decision, dict) and decision.get('action') == 'auto_resolve' else 'needs_review'

        # Audit payload
        audit_payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'actor_type': 'agent',
            'actor_id': 'reconcile_engine',
            'case_id': case_id,
            'event_type': 'case_created',
            'workflow': workflow,
            'source_ids': source_ids_json,
            'candidate_target_ids': candidate_target_ids_json,
            'confidence': confidence,
            'method': method,
            'exception_type': exception_type,
            'amount_delta': amount_delta,
            'reasons': reasons_json,
            'decision': decision,
            'neatlogs_trace_id': trace_id(),
            'after_state': status,
            'policy_version': decision.get('policy_version') if isinstance(decision, dict) else None,
        }
        try:
            auditor.append(audit_payload)
        except Exception:
            pass

        case_dict = {
            'case_id': case_id,
            'workflow': workflow,
            'source_ids': source_ids_json,
            'candidate_target_ids': candidate_target_ids_json,
            'confidence': confidence,
            'method': method,
            'exception_type': exception_type,
            'amount_delta': amount_delta,
            'reasons': reasons_json,
            'decision': decision,
            'status': status
        }

        cases.append(case_dict)

        if status == 'auto_resolved':
            auto_resolved += 1
        else:
            needs_review += 1

        exc_type = exception_type
        if exc_type:
            exceptions_counts[exc_type] = exceptions_counts.get(exc_type, 0) + 1

    # Finalize audit
    audit_status = auditor.verify_chain()
    audit_ok = audit_status.get('ok') if isinstance(audit_status, dict) else False
    auditor.close()

    summary: Dict[str, Any] = {
        'run_id': run_id,
        'cases': cases,
        'counts': {
            'sources': len(sources),
            'targets': len(targets),
            'cases': len(cases),
            'auto_resolved': auto_resolved,
            'needs_review': needs_review,
        },
        'exceptions': exceptions_counts,
        'audit_ok': audit_ok
    }

    return summary
