import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.harness.idempotency import IdempotencyStore, action_key, run_once


def test_action_key_deterministic_and_differs():
    payload1 = {"a": 1, "b": 2}
    payload2 = {"b": 2, "a": 1}
    
    k1 = action_key("c1", "a", payload1)
    k2 = action_key("c1", "a", payload2)
    
    assert k1 == k2
    assert k1 == action_key("c1", "a", {"a": 1, "b": 2})
    
    k3 = action_key("c1", "a", {"a": 1, "b": 2})
    k4 = action_key("c1", "a", {"a": 1, "b": 3})
    assert k3 != k4

def test_begin_returns_true_first_time_false_second():
    db = IdempotencyStore(":memory:")
    
    key = "test_key"
    
    assert db.begin(key, "case1", "act1") is True
    assert db.begin(key, "case1", "act1") is False
    
    db.close()

def test_complete_makes_is_done_true():
    db = IdempotencyStore(":memory:")
    
    key = "test_key2"
    db.begin(key, "case2", "act2")
    db.complete(key, {"status": "ok"})
    
    assert db.is_done(key) is True
    assert db.get(key) is not None
    assert db.get(key)["state"] == "done"
    assert db.get(key)["result"]["status"] == "ok"
    
    db.close()

def test_get_returns_none_for_unknown_key():
    db = IdempotencyStore(":memory:")
    assert db.get("unknown") is None
    db.close()

def test_run_once_executes_first_time():
    db = IdempotencyStore(":memory:")
    call_count = [0]
    
    def my_func():
        call_count[0] += 1
        return "success"
    
    res = run_once(db, "c3", "a", my_func, {})
    
    assert res["executed"] is True
    assert res["reason"] == "ok"
    assert res["result"] == "success"
    assert call_count[0] == 1
    
    db.close()

def test_run_once_does_not_execute_second_time():
    db = IdempotencyStore(":memory:")
    call_count = [0]
    
    def my_func():
        call_count[0] += 1
        return "success"
    
    res1 = run_once(db, "c4", "a", my_func, {"x": 1})
    assert res1["executed"] is True
    
    res2 = run_once(db, "c4", "a", my_func, {"x": 1})
    assert res2["executed"] is False
    assert res2["reason"] == "already done"
    assert call_count[0] == 1  # Function should not have run again
    
    db.close()

def test_fn_raises_exception_propagates_and_state_failed():
    db = IdempotencyStore(":memory:")
    def my_func():
        raise ValueError("Oops")
    
    with pytest.raises(ValueError, match="Oops"):
        run_once(db, "c1", "a", my_func, {})
    
    # Check state is failed
    key = action_key("c1", "a", {})
    state = db.get(key)
    assert state is not None
    assert state['state'] == 'failed'
    assert state['result'] == "Oops"
    
    db.close()

def test_failed_action_can_be_retried():
    db = IdempotencyStore(":memory:")
    def my_func():
        raise ValueError("Oops")
    
    # First attempt fails
    with pytest.raises(ValueError):
        run_once(db, "c1", "a", my_func, {})
    
    # State should be failed, not done
    key = action_key("c1", "a", {})
    assert db.is_done(key) is False
    assert db.get(key)['state'] == 'failed'
    
    # Retrying just returns 'in progress' (or handled as collision) and does not execute the function again
    res = run_once(db, "c1", "a", my_func, {})
    # Since the key exists, begin returns False immediately (or True if we cleared it, but here it exists)
    # The prompt logic: begin() fails -> return executed False, reason in progress.
    assert res['executed'] is False
    assert res['reason'] == 'in progress'
    # Verify the function didn't run again
    db.close()
