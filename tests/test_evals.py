import sys, os
import json

# Ensure the package is importable from the repository root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_expected_for():
    from evals.golden import GOLDEN, expected_for
    assert expected_for('C001') is not None
    assert expected_for('NOPE') is None

def test_index_cases_maps_multi_source_case():
    from evals.run import index_cases
    case = {
        'case_id': 'case-multi',
        'source_ids': json.dumps(['C001','C002','C004']),
        'candidate_target_ids': json.dumps(['B001','B002','B004']),
        'status':'auto_resolved',
        'confidence': 0.99,
        'method':'seed',
        'exception_type': None
    }
    mapping = index_cases([case])
    assert mapping['C001'] is case
    assert mapping['C002'] is case
    assert mapping['C004'] is case

def test_score_perfect_set():
    from evals.run import score
    case1 = {
        'case_id': 'case-multi',
        'source_ids': json.dumps(['C001','C002','C004']),
        'candidate_target_ids': json.dumps(['B001','B002','B004']),
        'status':'auto_resolved',
        'confidence': 0.99,
        'method':'seed',
        'exception_type': None
    }
    case2 = {
        'case_id': 'case-c009',
        'source_ids': json.dumps(['C009']),
        'candidate_target_ids': json.dumps([]),
        'status':'needs_review',
        'confidence': 0.9,
        'method':'seed',
        'exception_type': None
    }
    case3 = {
        'case_id': 'case-c010',
        'source_ids': json.dumps(['C010']),
        'candidate_target_ids': json.dumps([]),
        'status':'needs_review',
        'confidence': 0.9,
        'method':'seed',
        'exception_type': None
    }
    case4 = {
        'case_id': 'case-c007',
        'source_ids': json.dumps(['C007']),
        'candidate_target_ids': json.dumps(['B006']),
        'status':'needs_review',
        'confidence': 0.95,
        'method':'seed',
        'exception_type': None
    }
    metrics = score([case1, case2, case3, case4])
    assert metrics['unsafe_auto_resolve'] == 0
    assert metrics['status_accuracy'] == 1.0

def test_render_scorecard_pass_and_fail():
    from evals.run import render_scorecard
    metrics_pass = {'unsafe_auto_resolve': 0, 'total': 6, 'matched': 6, 'status_correct': 6, 'missing': 0, 'match_rate': 1.0, 'status_accuracy': 1.0}
    metrics_fail = {'unsafe_auto_resolve': 1, 'total': 6, 'matched': 6, 'status_correct': 6, 'missing': 0, 'match_rate': 1.0, 'status_accuracy': 1.0}
    s_pass = render_scorecard(metrics_pass, run_id='RUN1')
    s_fail = render_scorecard(metrics_fail, run_id='RUN2')
    assert s_pass.strip().endswith("RESULT: PASS")
    assert s_fail.strip().endswith("RESULT: FAIL")

def test_main_writes_file(tmp_path):
    from evals.run import main
    out_path = tmp_path / "scorecard.md"
    out_path_str = str(out_path)
    metrics = main(out_path_str)
    assert os.path.exists(out_path_str)
    assert os.path.getsize(out_path_str) > 0
    assert isinstance(metrics, dict)
    assert 'run_id' in metrics
