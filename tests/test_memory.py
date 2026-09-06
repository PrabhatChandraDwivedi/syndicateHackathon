import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from app.memory.rules import RuleStore, LearnedRule, rule_id_for


def test_learning_with_amount_sets_envelope(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    r = store.learn("Pattern A", "Action A", "case0", amount=1000.0)
    assert isinstance(r, LearnedRule)
    assert r.learned_amount == 1000.0
    assert r.max_amount == 3000.0

    r2 = store.learn("Pattern A", "Action A", "case1", amount=200.0)
    # idempotent: same rule returned
    assert r2 is r
    assert r2.learned_amount == 1000.0
    assert r2.max_amount == 3000.0


def test_scoped_match_within_envelope(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    r = store.learn("Pattern X", "Do X", "caseX", amount=1000.0)
    matched = store.match("Pattern X", amount=2500.0)
    assert matched is r
    assert r.hit_count == 1

    # amount beyond envelope should not match
    unmatched = store.match("Pattern X", amount=5000.0)
    assert unmatched is None


def test_unbounded_matches_any_amount(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    r = store.learn("Unbounded", "Act", "caseY", amount=None)
    assert r.learned_amount == 0.0
    assert r.max_amount == 0.0
    matched = store.match("Unbounded", amount=999999.0)
    assert matched is r


def test_no_widen_on_repeat(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    r = store.learn("Pattern A", "Action A", "caseA", amount=1000.0)
    r_dup = store.learn("Pattern A", "Action A", "caseB", amount=5000.0)
    assert r_dup is r
    assert r_dup.learned_amount == 1000.0
    assert r_dup.max_amount == 3000.0


def test_promotion_and_revocation_and_visibility(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    r = store.learn("PromPattern", "PromAction", "caseP", amount=1000.0)
    # Apply three times
    r1 = store.record_application(r.rule_id)
    assert r1 is not None
    assert r1.applied_count == 1
    r2 = store.record_application(r.rule_id)
    assert r2.applied_count == 2
    r3 = store.record_application(r.rule_id)
    assert r3 is not None
    assert r3.applied_count == 3
    assert r3.status == 'promoted'

    # Revoke
    ok = store.revoke(r.rule_id, reason="test revoke")
    assert ok
    assert r.enabled is False
    # After revoke, match should fail
    m = store.match("PromPattern", amount=1000.0)
    assert m is None
    # all_rules should include revoked reason
    all_rules = store.all_rules()
    found = next((rr for rr in all_rules if rr.rule_id == r.rule_id), None)
    assert found is not None
    assert found.revoked_reason == "test revoke"


def test_backward_compat_loads_legacy_json(tmp_path):
    path = tmp_path / "legacy_rules.json"
    legacy_rule = {
        'rule_id': 'legacy1',
        'pattern': 'legacy',
        'action': 'do',
        'created_from_case': 'caseLegacy',
        'hit_count': 5,
        'enabled': True
    }
    with open(path, 'w') as f:
        json.dump([legacy_rule], f, indent=2)

    store = RuleStore(str(path))
    rules = store.all_rules()
    assert len(rules) == 1
    rr = rules[0]
    assert rr.rule_id == 'legacy1'
    assert rr.pattern == 'legacy'
    assert rr.action == 'do'
    assert rr.created_from_case == 'caseLegacy'
    assert rr.hit_count == 5
    assert rr.enabled is True
    # new fields defaults
    assert rr.learned_amount == 0.0
    assert rr.max_amount == 0.0
    assert rr.status == 'provisional'
    assert rr.applied_count == 0
    assert rr.revoked_reason == ''
