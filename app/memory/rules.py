import json
import os
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional

PROMOTE_AFTER = 3

@dataclass
class LearnedRule:
    rule_id: str
    pattern: str
    action: str
    created_from_case: str
    hit_count: int = 0
    enabled: bool = True
    learned_amount: float = 0.0
    max_amount: float = 0.0
    status: str = 'provisional'  # 'provisional' | 'promoted'
    applied_count: int = 0
    revoked_reason: str = ''


def rule_id_for(pattern: str, action: str) -> str:
    # Normalize to lowercase for case-insensitive determinism
    payload = f"{pattern.lower()}|{action.lower()}"
    return "rule_" + hashlib.sha256(payload.encode()).hexdigest()[:10]


class RuleStore:
    def __init__(self, path: str):
        self.path = path
        self._rules: dict[str, LearnedRule] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, 'r') as f:
                data = json.load(f)
            data_list = data if isinstance(data, list) else [data]
            self._rules = {}
            for d in data_list:
                if not isinstance(d, dict):
                    continue
                rid = d.get('rule_id')
                if not rid:
                    continue

                # Backwards compatibility: fill defaults for missing fields
                learned_amount = float(d.get('learned_amount', 0.0))
                max_amount = float(d.get('max_amount', 0.0))
                status = d.get('status', 'provisional')
                applied_count = int(d.get('applied_count', 0))
                revoked_reason = d.get('revoked_reason', '')

                hit_count = int(d.get('hit_count', 0))
                enabled = bool(d.get('enabled', True))

                pattern = d.get('pattern', '')
                action = d.get('action', '')
                created_from_case = d.get('created_from_case', '')

                rule = LearnedRule(
                    rule_id=rid,
                    pattern=pattern,
                    action=action,
                    created_from_case=created_from_case,
                    hit_count=hit_count,
                    enabled=enabled,
                    learned_amount=learned_amount,
                    max_amount=max_amount,
                    status=status,
                    applied_count=applied_count,
                    revoked_reason=revoked_reason,
                )
                self._rules[rid] = rule
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._rules = {}

    def save(self) -> None:
        dirpath = os.path.dirname(self.path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        data = [asdict(r) for r in self._rules.values()]
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def learn(self, pattern: str, action: str, case_id: str, amount: Optional[float] = None) -> LearnedRule:
        rid = rule_id_for(pattern, action)
        if rid in self._rules:
            return self._rules[rid]
        learned_amount = float(amount) if amount is not None and amount > 0 else 0.0
        max_amount = round(learned_amount * 3.0, 2) if learned_amount > 0.0 else 0.0
        rule = LearnedRule(
            rule_id=rid,
            pattern=pattern,
            action=action,
            created_from_case=case_id,
            hit_count=0,
            enabled=True,
            learned_amount=learned_amount,
            max_amount=max_amount,
            status='provisional',
            applied_count=0,
            revoked_reason=''
        )
        self._rules[rid] = rule
        self.save()
        return rule

    def match(self, pattern: str, amount: Optional[float] = None) -> Optional[LearnedRule]:
        # Only consider enabled rules; match is case-insensitive on pattern
        for r in self._rules.values():
            if not r.enabled:
                continue
            if r.pattern.lower() != pattern.lower():
                continue

            # If envelope is set (max_amount > 0), allow match when amount is None or amount <= max_amount
            if r.max_amount > 0.0:
                if amount is not None:
                    try:
                        amt = float(amount)
                    except (TypeError, ValueError):
                        amt = None
                    if amt is None or amt > r.max_amount:
                        continue
                # amount is None -> allowed
            # max_amount == 0.0 means unbounded

            r.hit_count += 1
            self.save()
            return r
        return None

    def disable(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
            self.save()
            return True
        return False

    def all_rules(self) -> list[LearnedRule]:
        return list(self._rules.values())

    def revoke(self, rule_id: str, reason: str = '') -> bool:
        if rule_id in self._rules:
            r = self._rules[rule_id]
            r.enabled = False
            r.revoked_reason = reason
            self.save()
            return True
        return False

    def record_application(self, rule_id: str) -> Optional[LearnedRule]:
        if rule_id not in self._rules:
            return None
        r = self._rules[rule_id]
        r.applied_count += 1
        if r.applied_count >= PROMOTE_AFTER:
            r.status = 'promoted'
        self.save()
        return r
