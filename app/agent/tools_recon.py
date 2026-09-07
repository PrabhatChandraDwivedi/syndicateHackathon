from __future__ import annotations

from typing import Dict, Any, List, Optional, Callable

from app.harness.tools import ToolRegistry, ToolSpec
from app.memory.rules import RuleStore
from app.policy.engine import decide
from pydantic import BaseModel, Field

from app.agent.vendor_email import draft_and_enqueue, drafts_from_gst

# Safety BLOCKED exception types
BLOCKED = ('duplicate_transaction', 'amount_mismatch', 'split_payment')


# Pydantic models for all tools (shared across registry instances)
class RunReconciliationArgs(BaseModel):
    period: str = Field('', description='Optional period for reconciliation run, e.g. "2024-01"')


class ListOpenCasesArgs(BaseModel):
    status: str = Field('needs_review', description='Status to filter cases by')
    limit: int = Field(20, ge=1, description='Maximum number of cases to return')


class GetCaseArgs(BaseModel):
    case_id: str = Field(..., description='Case identifier to fetch')


class RecallRuleArgs(BaseModel):
    pattern: str = Field(..., description='Pattern to look up learned rules')


class CheckPolicyArgs(BaseModel):
    case_id: str = Field(..., description='Case identifier to evaluate against policy')


class ResolveCaseArgs(BaseModel):
    case_id: str = Field(..., description='Case identifier to auto-resolve')
    rationale: str = Field(..., description='Rationale provided by agent for auto-resolution')


class EscalateToHumanArgs(BaseModel):
    case_id: str = Field(..., description='Case identifier to escalate')
    reason: str = Field(..., description='Reason for escalation')


class ReconcileGstArgs(BaseModel):
    period: str = Field('', description='Optional GST period for reconciliation')


class CheckMonthCloseArgs(BaseModel):
    period: str = Field('', description='Optional month-close period to check')


class AskHumanArgs(BaseModel):
    question: str = Field(..., description='Question to present to a human')
    case_id: str = Field('', description='Case this is about; leave empty for a general question')


# new: DraftVendorEmailArgs
class DraftVendorEmailArgs(BaseModel):
    invoice_number: str = Field(..., description='Invoice number')
    supplier_gstin: str = Field(..., description='Supplier GSTIN')
    reason: str = Field(..., description='Reason for chaser')
    taxable_value: float = Field(0.0, description='Taxable value')
    tax_at_risk: float = Field(0.0, description='Tax at risk')


class DraftVendorEmailArgsLocal(DraftVendorEmailArgs):
    pass


def build_registry(state: dict,
                   policy: dict,
                   rules: RuleStore | None = None,
                   run_fn: Optional[Callable[[], dict]] = None,
                   gst_fn: Optional[Callable[[], dict]] = None,
                   close_fn: Optional[Callable[[], dict]] = None,
                   outbox=None) -> ToolRegistry:
    """
    Build and return a ToolRegistry wired with reconciliation tools.

    - state: mutable dict holding the current run under state['run'] (may start as None)
    - policy: policy config used by the decide() function
    - rules: optional RuleStore to recall rules from memory
    - run_fn: injected callable that performs a reconciliation run and returns a dict with 'cases'
    - gst_fn: injected callable that performs GST reconciliation and returns a dict
    - close_fn: injected callable that performs month-close checks and returns a dict
    - outbox: optional Outbox instance to enqueue drafts like vendor emails
    """

    registry = ToolRegistry()

    def current_cases() -> List[Dict[str, Any]]:
        """Return the list of current cases from the mutable state."""
        run = state.get('run') or {}
        if not isinstance(run, dict):
            return []
        cases = run.get('cases', []) or []
        return list(cases)

    def find_case(case_id: str) -> Optional[Dict[str, Any]]:
        for c in current_cases():
            if str(c.get('case_id')) == str(case_id):
                return c
        return None

    # 1. run_reconciliation
    class RunReconciliationArgsLocal(RunReconciliationArgs):
        pass

    def run_reconciliation(args: RunReconciliationArgsLocal) -> Dict[str, Any]:
        if run_fn is None:
            return {'ok': False, 'error': 'no runner configured'}
        try:
            run = run_fn()
            state['run'] = run
            cases = run.get('cases', []) if isinstance(run, dict) else []
            run_id = run.get('run_id') or run.get('id') or run.get('run')
            counts = run.get('counts', len(cases))
            exceptions = run.get('exceptions', 0)
            needs_review = sum(1 for c in cases if str(c.get('status')) == 'needs_review')
            auto_resolved = sum(1 for c in cases if str(c.get('status')) == 'auto_resolved')
            return {
                'ok': True,
                'run_id': run_id,
                'counts': counts,
                'exceptions': exceptions,
                'needs_review': needs_review,
                'auto_resolved': auto_resolved
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    registry.register(
        ToolSpec(
            name='run_reconciliation',
            description='Run the reconciliation workflow. This tool starts the agent-driven reconciliation using an injected runner. '
                        'If no runner is configured, it returns an error instead of attempting work.',
            args_model=RunReconciliationArgsLocal,
            fn=run_reconciliation,
            dangerous=False
        )
    )

    # 2. list_open_cases
    class ListOpenCasesArgsLocal(ListOpenCasesArgs):
        pass

    def list_open_cases(args: ListOpenCasesArgsLocal) -> Dict[str, Any]:
        all_cases = current_cases()
        matched = []
        for c in all_cases:
            if str(c.get('status')) == str(args.status):
                matched.append({
                    'case_id': c.get('case_id'),
                    'pattern': c.get('pattern'),
                    'confidence': c.get('confidence'),
                    'exception_type': c.get('exception_type'),
                    'status': c.get('status'),
                    'amount_delta': c.get('amount_delta', 0.0)
                })
        if len(matched) > args.limit:
            matched = matched[:args.limit]
        return {'count': len(matched), 'cases': matched}

    registry.register(
        ToolSpec(
            name='list_open_cases',
            description='List cases currently open for review. Filter by status and cap results with limit. Helpful for the agent to survey workload.',
            args_model=ListOpenCasesArgsLocal,
            fn=list_open_cases,
            dangerous=False
        )
    )

    # 3. get_case
    class GetCaseArgsLocal(GetCaseArgs):
        pass

    def get_case(args: GetCaseArgsLocal) -> Dict[str, Any]:
        case = find_case(args.case_id)
        if case is None:
            return {'error': f'case not found: {args.case_id}'}
        return case

    registry.register(
        ToolSpec(
            name='get_case',
            description='Fetch the full case data for a given case_id. If not found, returns an error.',
            args_model=GetCaseArgsLocal,
            fn=get_case,
            dangerous=False
        )
    )

    # 4. recall_rule
    class RecallRuleArgsLocal(RecallRuleArgs):
        pass

    def recall_rule(args: RecallRuleArgsLocal) -> Dict[str, Any]:
        if rules is None:
            return {'found': False, 'rule_id': None, 'action': None, 'hit_count': None}
        learned = rules.match(args.pattern)
        if learned is None:
            return {'found': False, 'rule_id': None, 'action': None, 'hit_count': None}
        # Attempt to extract fields robustly
        rule_id = None
        action = None
        hit_count = None
        if isinstance(learned, dict):
            rule_id = learned.get('rule_id')
            action = learned.get('action')
            hit_count = learned.get('hit_count')
        else:
            rule_id = getattr(learned, 'rule_id', None)
            action = getattr(learned, 'action', None)
            hit_count = getattr(learned, 'hit_count', None)
        return {'found': True, 'rule_id': rule_id, 'action': action, 'hit_count': hit_count}

    registry.register(
        ToolSpec(
            name='recall_rule',
            description='Recall a learned rule by pattern. Returns whether a rule was found and its action details if available.',
            args_model=RecallRuleArgsLocal,
            fn=recall_rule,
            dangerous=False
        )
    )

    # 5. check_policy
    class CheckPolicyArgsLocal(CheckPolicyArgs):
        pass

    def check_policy(args: CheckPolicyArgsLocal) -> Dict[str, Any]:
        case = find_case(args.case_id)
        if case is None:
            return {'error': f'case not found: {args.case_id}'}
        confidence = float(case.get('confidence', 0.0) or 0.0)
        amount = float(case.get('amount', 0.0) or 0.0)
        exception_type = case.get('exception_type')
        decision = decide(confidence, amount, exception_type, policy)
        blocked = (exception_type in BLOCKED) if exception_type is not None else False
        return {
            'action': decision.get('action'),
            'reason': decision.get('reason'),
            'policy_version': decision.get('policy_version'),
            'blocked': blocked
        }

    registry.register(
        ToolSpec(
            name='check_policy',
            description='Evaluate a case against policy to decide an action. Returns the suggested action, reason, and policy version, plus whether the case type is BLOCKED.',
            args_model=CheckPolicyArgsLocal,
            fn=check_policy,
            dangerous=False
        )
    )

    # 6. resolve_case
    class ResolveCaseArgsLocal(ResolveCaseArgs):
        pass

    def resolve_case(args: ResolveCaseArgsLocal) -> Dict[str, Any]:
        case = find_case(args.case_id)
        if case is None:
            return {'ok': False, 'error': f'case not found: {args.case_id}'}
        exception_type = case.get('exception_type')
        if exception_type in BLOCKED:
            return {
                'ok': False,
                'refused': True,
                'reason': f'policy blocks auto-resolution of {exception_type}; this case requires a human'
            }
        confidence = float(case.get('confidence', 0.0) or 0.0)
        amount = float(case.get('amount', 0.0) or 0.0)
        decision = decide(confidence, amount, exception_type, policy)
        if decision.get('action') != 'auto_resolve':
            return {'ok': False, 'refused': True, 'reason': decision.get('reason')}
        case['status'] = 'auto_resolved'
        case['agent_rationale'] = args.rationale
        return {'ok': True, 'case_id': case.get('case_id'), 'status': 'auto_resolved'}

    registry.register(
        ToolSpec(
            name='resolve_case',
            description='Automatically resolve a case based on policy. This is a sensitive operation that may be blocked by safety rules.',
            args_model=ResolveCaseArgsLocal,
            fn=resolve_case,
            dangerous=True
        )
    )

    # 7. escalate_to_human
    class EscalateToHumanArgsLocal(EscalateToHumanArgs):
        pass

    def escalate_to_human(args: EscalateToHumanArgsLocal) -> Dict[str, Any]:
        case = find_case(args.case_id)
        if case is None:
            return {'ok': False, 'error': f'case not found: {args.case_id}'}
        case['status'] = 'needs_review'
        case['escalation_reason'] = args.reason
        return {'ok': True, 'case_id': case.get('case_id'), 'status': 'needs_review'}

    registry.register(
        ToolSpec(
            name='escalate_to_human',
            description='Escalate a case to human review with a provided reason. This is a dangerous operation that moves the case out of auto-resolution.',
            args_model=EscalateToHumanArgsLocal,
            fn=escalate_to_human,
            dangerous=True
        )
    )

    # 8. reconcile_gst
    class ReconcileGstArgsLocal(ReconcileGstArgs):
        pass

    def reconcile_gst(args: ReconcileGstArgsLocal) -> Dict[str, Any]:
        if gst_fn is None:
            return {'ok': False, 'error': 'no gst runner configured'}
        try:
            gst = gst_fn()
            state['gst'] = gst
            return {
                'ok': True,
                'matched': gst.get('matched'),
                'itc_at_risk': gst.get('itc_at_risk'),
                'exception_count': gst.get('exception_count'),
                'exception_types': gst.get('exception_types', {})
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    registry.register(
        ToolSpec(
            name='reconcile_gst',
            description='Run GST reconciliation using an injected GST runner. Returns a summary of matches and at-risk ITCs.',
            args_model=ReconcileGstArgsLocal,
            fn=reconcile_gst,
            dangerous=False
        )
    )

    # 9. check_month_close
    class CheckMonthCloseArgsLocal(CheckMonthCloseArgs):
        pass

    def check_month_close(args: CheckMonthCloseArgsLocal) -> Dict[str, Any]:
        if close_fn is None:
            return {'ok': False, 'error': 'no close runner configured'}
        try:
            close = close_fn()
            state['close'] = close
            summary = close.get('summary', close)
            readiness = close.get('readiness', 0.0)
            unexplained_bank_count = close.get('unexplained_bank_count', 0)
            return {
                'ok': True,
                'summary': summary,
                'readiness': readiness,
                'unexplained_bank_count': unexplained_bank_count
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    registry.register(
        ToolSpec(
            name='check_month_close',
            description='Check if month close readiness is sufficient using an injected close runner. Returns a readiness score and any unexplained bank items.',
            args_model=CheckMonthCloseArgsLocal,
            fn=check_month_close,
            dangerous=False
        )
    )

    # 10. ask_human
    class AskHumanArgsLocal(AskHumanArgs):
        pass

    def ask_human(args: AskHumanArgsLocal) -> Dict[str, Any]:
        """Record a question for a person.

        A question about a specific case is attached to it. A question that is not
        about any case -- or names one that does not exist -- is still recorded
        rather than rejected. Refusing to let the agent speak because its case id
        is wrong just makes it retry forever, which is worse than a loose question.
        """
        case = find_case(args.case_id) if args.case_id else None
        state.setdefault('questions', []).append(
            {'case_id': args.case_id or None, 'question': args.question}
        )
        if case is None:
            return {'ok': True, 'case_id': None, 'question': args.question,
                    'status': 'asked',
                    'note': 'recorded as a general question; it is not attached to a case'}
        case['status'] = 'needs_review'
        case['agent_question'] = args.question
        return {'ok': True, 'case_id': case.get('case_id'), 'question': args.question, 'status': 'needs_review'}

    registry.register(
        ToolSpec(
            name='ask_human',
            description=('Ask a person a question. Pass case_id when the question is about a '
                         'specific case, or an empty string for a general question. Use this '
                         'sparingly and never more than once for the same thing -- the answer '
                         'arrives later, not during this run, so asking again will not help.'),
            args_model=AskHumanArgsLocal,
            fn=ask_human,
            dangerous=True
        )
    )

    # 11. draft_vendor_email
    class DraftVendorEmailArgsLocal(DraftVendorEmailArgs):
        pass

    def draft_vendor_email(args: DraftVendorEmailArgsLocal) -> Dict[str, Any]:
        if outbox is None:
            return {'ok': False, 'error': 'no outbox configured'}
        try:
            recipient = f'ap-{args.supplier_gstin.upper()}@vendor.invalid'
            subject = f'Action required: GST invoice {args.invoice_number} not reflected in GSTR-2B'
            body = (
                f'This is a draft email to vendor about GST invoice not reflected in GSTR-2B. '
                f'Invoice number: {args.invoice_number}. '
                f'Supplier GSTIN: {args.supplier_gstin}. '
                f'Taxable value: {args.taxable_value:.2f}. '
                f'Tax at risk: {args.tax_at_risk:.2f}. '
                f'This invoice does not appear in our GSTR-2B for the period so we cannot claim input tax credit. '
                f'Reason: {args.reason}. Please confirm the filing status. '
                f'This draft was prepared automatically and has not been sent.'
            )
            draft_res = draft_and_enqueue(outbox, args.invoice_number, args.supplier_gstin, args.reason,
                                          args.taxable_value, args.tax_at_risk, case_id=None)
            if isinstance(draft_res, dict):
                ok = draft_res.get('ok', True)
                if not ok:
                    return {'ok': False, 'error': draft_res.get('error')}
                draft_id = draft_res.get('draft_id')
            else:
                draft_id = draft_res
            return {'ok': True, 'draft_id': int(draft_id) if isinstance(draft_id, (int, float)) else draft_id,
                    'recipient': recipient, 'subject': subject, 'status': 'pending'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    registry.register(
        ToolSpec(
            name='draft_vendor_email',
            description='Prepare a draft email to vendor about GST invoice not reflected in GSTR-2B. This tool only PREPARES a draft for human approval and never sends anything.',
            args_model=DraftVendorEmailArgsLocal,
            fn=draft_vendor_email,
            dangerous=True
        )
    )

    # 12. draft_all_gst_chasers
    class DraftAllGstChasersArgs(BaseModel):
        limit: int = Field(10, ge=1, description='Maximum number of GST chasers to draft')

    def draft_all_gst_chasers(args: DraftAllGstChasersArgs) -> Dict[str, Any]:
        if outbox is None:
            return {'ok': False, 'error': 'no outbox configured'}
        gst = state.get('gst')
        if gst is None:
            return {'ok': False, 'error': 'run reconcile_gst first'}
        try:
            drafts_result = drafts_from_gst(gst, outbox, limit=args.limit)
            return {'ok': True, 'drafted': drafts_result.get('drafted'), 'drafts': drafts_result.get('drafts')}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    registry.register(
        ToolSpec(
            name='draft_all_gst_chasers',
            description='Draft GST chasers for unfiled invoices after GST check. This enqueues drafts for human review and does not send anything.',
            args_model=DraftAllGstChasersArgs,
            fn=draft_all_gst_chasers,
            dangerous=True
        )
    )

    return registry
