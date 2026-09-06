import json
import os
import datetime
from typing import List, Dict

from .golden import GOLDEN

def index_cases(cases: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    index: Dict[str, Dict[str, object]] = {}
    for case in cases:
        source_ids_json = case.get('source_ids', '[]')
        try:
            source_ids = json.loads(source_ids_json)
        except Exception:
            source_ids = []
        for sid in source_ids:
            index[str(sid)] = case
    return index

def score(cases: List[Dict[str, object]]) -> Dict[str, object]:
    index = index_cases(cases)
    total = len(GOLDEN)
    matched = 0
    status_correct = 0
    missing = 0
    unsafe_auto_resolve = 0

    for gold in GOLDEN:
        source_id = gold['source_id']
        case = index.get(source_id)
        if case is None:
            missing += 1
            continue
        candidate_target_ids_json = case.get('candidate_target_ids', '[]')
        try:
            target_list = json.loads(candidate_target_ids_json)
        except Exception:
            target_list = []
        expected_target = gold.get('expected_target')
        if expected_target is None:
            if isinstance(target_list, list) and len(target_list) == 0:
                matched += 1
        else:
            if isinstance(target_list, list) and expected_target in target_list:
                matched += 1
        if case.get('status') == gold.get('expected_status'):
            status_correct += 1
        if gold.get('expected_status') == 'needs_review' and case.get('status') == 'auto_resolved':
            unsafe_auto_resolve += 1

    match_rate = round(matched / total, 4) if total else 0.0
    status_accuracy = round(status_correct / total, 4) if total else 0.0

    return {
        'total': int(total),
        'matched': int(matched),
        'status_correct': int(status_correct),
        'missing': int(missing),
        'unsafe_auto_resolve': int(unsafe_auto_resolve),
        'match_rate': match_rate,
        'status_accuracy': status_accuracy,
    }

def render_scorecard(metrics: Dict[str, object], run_id: str) -> str:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = []
    lines.append("# ReconcileOS Evaluation Scorecard")
    lines.append("")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Generated at: {ts}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    order = ['total','matched','status_correct','missing','unsafe_auto_resolve','match_rate','status_accuracy']
    for key in order:
        value = metrics.get(key)
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("RESULT: PASS" if int(metrics.get('unsafe_auto_resolve', 0)) == 0 else "RESULT: FAIL")
    return "\n".join(lines)

def main(out_path: str = 'evals/reports/scorecard.md') -> Dict[str, object]:
    from app.pipeline import run_pipeline
    result = run_pipeline(db_path=':memory:', data_dir='./seed/data', policy_path=None)
    cases = result.get('cases', [])
    run_id = result.get('run_id')
    metrics = score(cases)
    scorecard = render_scorecard(metrics, run_id)
    dirpath = os.path.dirname(out_path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(scorecard)
    metrics['run_id'] = run_id
    return metrics

if __name__ == '__main__':
    main()
