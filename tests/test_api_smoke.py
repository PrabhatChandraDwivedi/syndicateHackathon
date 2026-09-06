import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_api_smoke(client):
    # Health
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"

    # Trigger a run
    resp = client.post("/run")
    assert resp.status_code == 200
    run_data = resp.json()
    assert "run_id" in run_data
    assert "counts" in run_data
    assert run_data.get("run_id") is not None

    # Get cases
    resp = client.get("/cases")
    assert resp.status_code == 200
    cases_data = resp.json()
    cases = cases_data.get("cases", [])
    assert isinstance(cases, list)
    assert len(cases) > 0

    first_case = cases[0]
    case_id = str(first_case.get("case_id"))
    assert case_id

    # Get specific case
    resp = client.get(f"/cases/{case_id}")
    assert resp.status_code == 200
    case_detail = resp.json()
    assert str(case_detail.get("case_id")) == case_id

    # Filter by status (needs_review)
    resp = client.get("/cases?status=needs_review")
    assert resp.status_code == 200
    reviewed_cases = resp.json().get("cases", [])
    if reviewed_cases:
        assert all(c.get("status") == "needs_review" for c in reviewed_cases)

    # Decision on a case
    resp = client.post(f"/cases/{case_id}/decision", json={"action": "approve"})
    assert resp.status_code == 200
    decision_info = resp.json()
    assert decision_info.get("case_id") == case_id
    assert decision_info.get("status") == "recorded"

    # Invalid action should fail
    resp = client.post(f"/cases/{case_id}/decision", json={"action": "nonsense"})
    assert resp.status_code == 400

    # Evidence pack
    resp = client.get(f"/cases/{case_id}/evidence-pack")
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK")

    # Close readiness
    resp = client.get("/close-readiness")
    assert resp.status_code == 200
    readiness_data = resp.json()
    readiness = readiness_data.get("readiness")
    assert isinstance(readiness, float)
    assert 0.0 <= readiness <= 1.0

    # Metrics
    resp = client.get("/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "counts" in metrics

    # Rules
    resp = client.get("/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert "rules" in rules

    # Admin reset
    resp = client.post("/admin/reset")
    assert resp.status_code == 200
    reset_info = resp.json()
    assert reset_info.get("reset") is True
