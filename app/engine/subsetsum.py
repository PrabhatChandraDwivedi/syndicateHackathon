import itertools
from typing import List


def find_subset(
    amounts: List[float],
    target: float,
    tolerance: float = 0.01,
    max_items: int = 4,
) -> List[int] | None:
    """
    Finds a subset of indices whose amounts sum to the target within a tolerance.
    Searches from the smallest subset size upwards, limited by max_items.
    """
    if not amounts:
        return None

    max_combinations = min(max_items, len(amounts))

    # Iterate subset size from 1 up to max_items (or total items if smaller)
    for size in range(1, max_combinations + 1):
        # Generate combinations of indices
        for indices in itertools.combinations(range(len(amounts)), size):
            total = sum(amounts[i] for i in indices)
            if abs(total - target) <= tolerance:
                return list(indices)  # indices is already sorted by combinations

    return None


def find_all_subsets(
    amounts: List[float],
    target: float,
    tolerance: float = 0.01,
    max_items: int = 4,
    limit: int = 10,
) -> List[List[int]]:
    """
    Finds all matching subsets of indices up to a limit, sorted by size.
    """
    if not amounts:
        return []

    results: List[List[int]] = []
    max_combinations = min(max_items, len(amounts))

    for size in range(1, max_combinations + 1):
        for indices in itertools.combinations(range(len(amounts)), size):
            total = sum(amounts[i] for i in indices)
            if abs(total - target) <= tolerance:
                results.append(list(indices))
                if len(results) >= limit:
                    return results

    return results
