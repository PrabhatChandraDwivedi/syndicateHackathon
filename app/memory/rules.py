import json
import os
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class LearnedRule:
    rule_id: str
    pattern: str
    action: str
    created_from_case: str
    hit_count: int = 0
    enabled: bool = True

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
                self._rules = {d['rule_id']: LearnedRule(**d) for d in data}
        except (json.JSONDecodeError, OSError, TypeError):
            self._rules = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = [asdict(r) for r in self._rules.values()]
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def learn(self, pattern: str, action: str, case_id: str) -> LearnedRule:
        rid = rule_id_for(pattern, action)
        if rid in self._rules:
            return self._rules[rid]
        rule = LearnedRule(
            rule_id=rid,
            pattern=pattern,
            action=action,
            created_from_case=case_id,
            enabled=True,
            hit_count=0
        )
        self._rules[rid] = rule
        self.save()
        return rule

    def match(self, pattern: str) -> Optional[LearnedRule]:
        for r in self._rules.values():
            if r.enabled and r.pattern.lower() == pattern.lower():
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
