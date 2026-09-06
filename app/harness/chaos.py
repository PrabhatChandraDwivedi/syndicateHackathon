import random
import copy
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class ChaosConfig:
    duplicate_rate: float = 0.0     # fraction of rows duplicated
    drop_field_rate: float = 0.0    # fraction of rows losing a required field
    corrupt_amount_rate: float = 0.0# fraction of rows given a non-numeric amount
    date_skew_rate: float = 0.0     # fraction of rows given a blank date
    seed: int = 42

def inject(rows: List[Dict], config: ChaosConfig) -> Dict:
    # Create deterministic local random generator
    rnd = random.Random(config.seed)

    # Deep-copy the input to never mutate caller's data
    copied_rows = copy.deepcopy(rows)

    # Initialize counters
    stats = {
        'duplicated': 0,
        'dropped_field': 0,
        'corrupted_amount': 0,
        'date_skewed': 0
    }

    # Walk copied rows and apply faults in fixed order
    for row in copied_rows:
        # drop_field
        if rnd.random() < config.drop_field_rate:
            if 'counterparty_raw' in row:
                del row['counterparty_raw']
                stats['dropped_field'] += 1
        
        # corrupt_amount
        if rnd.random() < config.corrupt_amount_rate:
            row['amount'] = 'NOT_A_NUMBER'
            stats['corrupted_amount'] += 1
        
        # date_skew
        if rnd.random() < config.date_skew_rate:
            row['date'] = ''
            stats['date_skewed'] += 1

    # Handle duplication after all faults have been applied
    # Take a snapshot of originals BEFORE duplicating to avoid cascading duplicates
    originals = list(copied_rows)
    duplicates = []
    for row in originals:
        if rnd.random() < config.duplicate_rate:
            duplicates.append(copy.deepcopy(row))
            stats['duplicated'] += 1

    result_rows = originals + duplicates

    return {'rows': result_rows, 'injected': stats}

def summarize(report: Dict) -> str:
    injected = report['injected']
    parts = [
        f"{injected['duplicated']} duplicated",
        f"{injected['dropped_field']} dropped_field",
        f"{injected['corrupted_amount']} corrupted_amount",
        f"{injected['date_skewed']} date_skewed"
    ]
    return f"chaos: {', '.join(parts)}"
