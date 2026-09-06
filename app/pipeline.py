import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.db.store import connect, init_db, insert_row, query, count
from app.adapters.csv_source import ingest_file, load_csv
from app.engine.normalize import normalize_transaction, NormalizedTransaction
from app.models.merchant import Merchant
from app.engine.matching import reconcile, Match
from app.policy.engine import load_policy, decide
from app.harness.audit import AuditWriter
from app.harness.tracing import init_tracing, span, current_run_id, trace_id
from seed.generate import generate
from app.memory.rules import RuleStore
from app.engine.adjudicator import is_ambiguous, adjudicate
from app.harness.modelrouter import ModelRouter

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
def run_pipeline(db_path: str = ':memory:', data_dir: str = './seed/data', policy_path: str | None = None, rules_path: Optional[str] = None, use_llm: bool = True) -> dict:
    init_tracing()
    run_id = current_run_id()

    # Determine rules path
    if rules_path is None:
        rules_path = os.environ.get('RULES_PATH', './data/rules.json')

    # Initialize Rules Store (memory)
    rule_store = RuleStore(rules_path)

    # Build ModelRouter if using LLM adjudication
    router = ModelRouter() if use_llm else None

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
    learned_rules_applied_count = 0
    flagged_for_review_count = 0

    for i, match in enumerate(matches, start=1):
        case_id = f'case_{i:03d}'
        workflow = 'card_to_bank'

        # Pattern: compute stable pattern for the case
        pattern = ''
        selected_source: Optional[NormalizedTransaction] = None
        if match.source_ids:
            for sid in match.source_ids:
                for s in sources:
                    candidates = []
                    for attr in ('id', 'transaction_id', 'txn_id', 'source_id', 'external_id'):
                        if getattr(s, attr, None) is not None:
                            candidates.append(getattr(s, attr))
                    if sid in candidates:
                        selected_source = s
                        break
                if selected_source:
                    break
        if selected_source is not None:
            merchant_id = getattr(selected_source, 'merchant_id', None)
            if merchant_id:
                pattern = str(merchant_id)
            else:
                descriptor = getattr(selected_source, 'normalized_descriptor', None)
                if descriptor:
                    pattern = str(descriptor)
        else:
            pattern = ''

        # Prepare source_ids and candidate_target_ids
        source_ids_json = json.dumps(match.source_ids)
        candidate_target_ids_json = json.dumps([match.target_id] if match.target_id else [])
        confidence = match.confidence
        method = match.method
        exception_type = match.exception_type
        amount_delta = match.amount_delta
        reasons_json = json.dumps(match.reasons)

        # Compute amount_for_match (needed for policy decision)
        amount_for_match = 0.0
        if match.source_ids:
            amount_for_match = _sum_source_amounts(sources, match.source_ids)
        if amount_for_match == 0.0 and match.target_id:
            t_amt = _amount_from_target(targets, match.target_id)
            if t_amt is not None:
                amount_for_match = t_amt

        # LLM adjudication (optional)
        adjudicated = False
        adjudication_reason = None
        adjudication_model = None
        adjudication_payload_applied = False  # local flag for audit

        if use_llm and match.target_id is not None and is_ambiguous(confidence) and (match.target_id is not None):
            # Build source dict for adjudication
            adjudication_source = None
            if selected_source is not None:
                adjudication_source = _txn_to_row(selected_source)

            # Build candidate dicts for adjudication
            adjudication_candidates: List[Dict[str, Any]] = []
            if targets:
                for t in targets:
                    target_ids = []
                    for attr in ('id', 'transaction_id', 'txn_id', 'target_id', 'external_id'):
                        v = getattr(t, attr, None)
                        if v is not None:
                            target_ids.append(v)
                    if match.target_id in target_ids:
                        adjudication_candidates.append(_txn_to_row(t))

            if adjudication_source is not None and adjudication_candidates:
                try:
                    adjudicate_result = adjudicate(adjudication_source, adjudication_candidates, router=router, max_tokens=400)
                    if isinstance(adjudicate_result, dict):
                        adjudicated = bool(adjudicate_result.get('adjudicated'))
                        adjudication_reason = adjudicate_result.get('reason')
                        adjudication_model = adjudicate_result.get('model')
                        adjudication_payload_applied = adjudicated
                except Exception:
                    adjudicated = False
                    adjudication_reason = None
                    adjudication_model = None

        # Learned rule and policy decision
        # a. Determine pattern-based rule BEFORE policy decision
        learned_rule_applied = None
        learned_rule_status: Optional[str] = None
        decision_reason = None
        flagged_for_review = False

        policy_decision = decide(confidence, amount_for_match, exception_type, policy)
        # Determine blocking by policy
        blocked = False
        if isinstance(policy_decision, dict):
            blocked_types = policy_decision.get('blocked_exception_types')
            if isinstance(blocked_types, list) and isinstance(exception_type, str) and exception_type in blocked_types:
                blocked = True

        # Get candidate rule if any, pass amount for envelope safety
        rule = rule_store.match(pattern, amount=amount_for_match) if pattern else None
        # Determine status from policy first
        status = 'auto_resolved' if isinstance(policy_decision, dict) and policy_decision.get('action') == 'auto_resolve' else 'needs_review'

        if not blocked and rule is not None:
            if rule.action == 'auto_resolve':
                status = 'auto_resolved'
                # Apply learned rule
                try:
                    updated_rule = rule_store.record_application(rule.rule_id)
                except Exception:
                    updated_rule = None
                learned_rule_applied = rule.rule_id

                # Determine status for the learned rule after application
                new_status = None
                if updated_rule is not None and getattr(updated_rule, 'status', None) is not None:
                    new_status = getattr(updated_rule, 'status')
                if new_status is None and getattr(rule, 'status', None) is not None:
                    new_status = getattr(rule, 'status')

                learned_rule_status = new_status
                flagged_for_review = (new_status == 'provisional')
                decision_reason = f'learned rule {rule.rule_id} from case {getattr(rule, "created_from_case", None)}'
                if learned_rule_status is not None:
                    # Count cases flagged for review
                    if flagged_for_review:
                        flagged_for_review_count += 1
                learned_rules_applied_count += 1
            elif rule.action == 'always_review':
                status = 'needs_review'
                learned_rule_applied = rule.rule_id
                # decision_reason remains from policy (if any)
                # Do not modify learned_rule_status/flagged_for_review for always_review
            else:
                # If rule action is something else, do not alter status
                pass
        # If no rule or blocked, decision_reason from policy if available
        if decision_reason is None:
            if isinstance(policy_decision, dict) and 'reason' in policy_decision:
                decision_reason = policy_decision.get('reason')

        # Build case dict
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
            'decision': policy_decision,
            'status': status,
            'pattern': pattern,
            'learned_rule_applied': learned_rule_applied,
            'learned_rule_status': learned_rule_status,
            'flagged_for_review': flagged_for_review,
            'decision_reason': decision_reason,
            'adjudicated': adjudicated,
            'adjudication_reason': adjudication_reason,
            'adjudication_model': adjudication_model
        }

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
            'decision': policy_decision,
            'adjudicated': adjudicated,
            'adjudication_reason': adjudication_reason,
            'adjudication_model': adjudication_model,
            'after_state': status,
            'pattern': pattern,
            'policy_version': policy_decision.get('policy_version') if isinstance(policy_decision, dict) else None,
            'neatlogs_trace_id': trace_id(),
        }
        if learned_rule_applied is not None:
            audit_payload['learned_rule_id'] = learned_rule_applied

        try:
            auditor.append(audit_payload)
        except Exception:
            pass

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
        'audit_ok': audit_ok,
        'learned_rules_applied': learned_rules_applied_count,
        'flagged_for_review': flagged_for_review_count
    }

    return summary
