import pytest

def test_post_ingest_bank(client):
    response = client.post("/ingest/bank")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_post_run(client):
    response = client.post("/run")
    assert response.status_code == 200
    assert response.json() == {"run_id": "run_001", "neatlogs_trace_id": "trace_001"}

def test_get_close_readiness_with_period(client):
    response = client.get("/close-readiness", params={"period": "2026-08"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": {"period": "2026-08", "readiness": 0.5}}

def test_get_cases(client):
    response = client.get("/cases")
    assert response.status_code == 200
    assert response.json() == {"cases": []}

def test_get_case_detail(client):
    response = client.get("/cases/case_1")
    assert response.status_code == 200
    assert response.json() == {"case_id": "case_1", "evidence": []}

def test_post_case_decision(client):
    response = client.post("/cases/case_1/decision")
    assert response.status_code == 200
    assert response.json() == {"case_id": "case_1", "status": "queued"}

def test_get_rules(client):
    response = client.get("/rules")
    assert response.status_code == 200
    assert response.json() == {"rules": []}

def test_post_disable_rule(client):
    response = client.post("/rules/r1/disable")
    assert response.status_code == 200
    assert response.json() == {"disabled": "r1"}

def test_get_audit(client):
    response = client.get("/audit")
    assert response.status_code == 200
    assert response.json() == {"audit": []}

def test_get_audit_verify(client):
    response = client.get("/audit/verify")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "broken_at": None}

def test_get_runs(client):
    response = client.get("/runs")
    assert response.status_code == 200
    assert response.json() == {"runs": []}

def test_get_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json() == {"metrics": {}}
