import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline import run_pipeline

def test_run_pipeline_basic(tmp_path):
    data_dir = str(tmp_path / "seed_data")
    result = run_pipeline(db_path=":memory:", data_dir=data_dir, policy_path=None, use_llm=False)

    # Basic structure checks
    assert isinstance(result, dict)
    assert result.get('run_id')
    counts = result.get('counts', {})
    assert counts.get('sources') == 11
    assert counts.get('targets') == 9
    assert isinstance(result.get('cases'), list)
    assert counts.get('cases') == len(result['cases'])

    # Consistency check
    auto = result['counts'].get('auto_resolved', 0)
    needs = result['counts'].get('needs_review', 0)
    assert auto + needs == counts.get('cases')

    # Audit status flag
    assert result.get('audit_ok') is True

    # Presence of specific attributes in cases
    cases = result['cases']
    has_duplicate_exception = any(case.get('exception_type') == 'duplicate_transaction' for case in cases)
    assert has_duplicate_exception is True

    has_one_to_many = any(case.get('method') == 'one_to_many' for case in cases)
    assert has_one_to_many is True

    for case in cases:
        assert 'case_id' in case
        assert 'workflow' in case
        assert 'status' in case
        assert 'confidence' in case
        assert 'pattern' in case
        assert 'learned_rule_applied' in case

    # Summary handling
    summary = result.get('summary')
    assert isinstance(summary, dict) or summary is None
    if isinstance(summary, dict):
        assert isinstance(summary.get('learned_rules_applied'), int)
        assert isinstance(summary.get('flagged_for_review'), int)
