from typing import List, Dict, Optional

GOLDEN: List[Dict[str, object]] = [
    {'source_id': 'C001', 'expected_target': 'B001', 'expected_status': 'auto_resolved'},
    {'source_id': 'C002', 'expected_target': 'B002', 'expected_status': 'auto_resolved'},
    {'source_id': 'C004', 'expected_target': 'B004', 'expected_status': 'auto_resolved'},
    {'source_id': 'C009', 'expected_target': None,   'expected_status': 'needs_review'},
    {'source_id': 'C010', 'expected_target': None,   'expected_status': 'needs_review'},
    {'source_id': 'C007', 'expected_target': 'B006', 'expected_status': 'needs_review'},
]

def expected_for(source_id: str) -> Optional[Dict[str, object]]:
    for g in GOLDEN:
        if g.get('source_id') == source_id:
            return g
    return None
