import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from pathlib import Path
from app.memory.rules import RuleStore, LearnedRule, rule_id_for

# Fix asyncio deprecation warning
@pytest.fixture(autouse=True)
def setup_loop():
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_closed():
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            asyncio.new_event_loop()
    except RuntimeError:
        pass
    yield

def test_learn_then_match_returns_rule_with_hit_count(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    
    rule = store.learn("pattern1", "action1", "case1")
    
    assert rule.hit_count == 0
    
    matched = store.match("pattern1")
    assert matched is not None
    assert matched is rule
    assert matched.hit_count == 1

def test_learning_same_pattern_action_returns_one_rule(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    
    r1 = store.learn("a", "b", "c")
    r2 = store.learn("a", "b", "d")
    
    assert r1 is r2
    assert r1.rule_id == r2.rule_id
    assert len(store.all_rules()) == 1

def test_rule_id_for_deterministic():
    id1 = rule_id_for("pattern", "action")
    id2 = rule_id_for("pattern", "action")
    id3 = rule_id_for("Pattern", "Action")
    assert id1 == id2
    assert id1 == id3

def test_disabled_rule_still_in_all_rules(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    
    rule = store.learn("a", "b", "c")
    
    # Before disable
    assert store.match("a") is not None
    assert len(store.all_rules()) == 1
    assert store.all_rules()[0].enabled == True
    
    store.disable(rule.rule_id)
    
    # Should not match
    assert store.match("a") is None
    
    # But should still be in all_rules
    rules = store.all_rules()
    assert len(rules) == 1
    assert rules[0].enabled == False

def test_case_insensitive_match(tmp_path):
    path = tmp_path / "rules.json"
    store = RuleStore(str(path))
    store.learn("HelloWorld", "DoSomething", "c")
    
    r = store.match("helloworld")
    assert r is not None
    assert r.pattern == "HelloWorld"
    assert r.hit_count == 1

def test_nonexistent_path_starts_empty(tmp_path):
    path = tmp_path / "nonexistent" / "dir" / "rules.json"
    store = RuleStore(str(path))
    
    # Should not raise
    assert len(store.all_rules()) == 0
    
    # Should remain empty
    matched = store.match("test")
    assert matched is None

def test_rules_persist(tmp_path):
    path = tmp_path / "persist.json"
    
    store1 = RuleStore(str(path))
    store1.learn("a", "b", "c")
    store1.match("a")
    
    r1 = store1.all_rules()[0]
    assert r1.hit_count == 1
    
    store2 = RuleStore(str(path))
    r2 = store2.all_rules()[0]
    
    # Hit count should persist
    assert r2.hit_count == 1
    
    # Should be able to increment on the second store
    store2.match("a")
    assert r2.hit_count == 2
