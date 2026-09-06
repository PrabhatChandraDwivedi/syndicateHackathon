import os
import yaml

from typing import Dict, Any


DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'policies.yaml')


def load_policy(path: str | None = None) -> Dict[str, Any]:
    """Load YAML policy from path or default location.

    Args:
        path: Optional path to the YAML file.

    Returns:
        The parsed policy dictionary.

    Raises:
        FileNotFoundError: If the policy file is not found.
    """
    if path is None:
        path = DEFAULT_POLICY_PATH

    with open(path, 'r') as f:
        return yaml.safe_load(f)


def decide(confidence: float, amount: float, exception_type: str | None, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Determine match resolution action based on policy rules.

    Args:
        confidence: The match confidence score.
        amount: The transaction amount.
        exception_type: The type of exception detected (if any).
        policy: The loaded policy dictionary.

    Returns:
        A dictionary with keys 'action', 'reason', and 'policy_version'.
    """
    # Rule 1: Blocked Exception Type
    if (
        exception_type is not None
        and exception_type in policy.get('blocked_exception_types', [])
    ):
        return {
            'action': 'human_review',
            'reason': f'blocked exception type: {exception_type}',
            'policy_version': policy['version']
        }

    # Rule 2: Materiality Threshold
    if amount is not None and amount > policy['materiality']['threshold_amount']:
        return {
            'action': 'human_review',
            'reason': 'amount exceeds materiality threshold',
            'policy_version': policy['version']
        }

    # Rule 3: Auto Resolve
    if (
        confidence >= policy['auto_resolve']['min_confidence']
        and amount <= policy['auto_resolve']['max_amount']
    ):
        return {
            'action': 'auto_resolve',
            'reason': 'high confidence within auto-resolve limits',
            'policy_version': policy['version']
        }

    # Rule 4: Review Threshold
    if confidence >= policy['review']['min_confidence']:
        return {
            'action': 'human_review',
            'reason': 'medium confidence requires review',
            'policy_version': policy['version']
        }

    # Rule 5: Default
    return {
        'action': 'human_review',
        'reason': 'confidence below review threshold',
        'policy_version': policy['version']
    }
