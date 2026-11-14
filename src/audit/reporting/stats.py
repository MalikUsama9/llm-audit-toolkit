"""Statistics helpers: confidence intervals, paired flip test, percentiles."""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n (95% by default).

    Better than the plain +/- formula for small n or proportions near 0 or 1.
    Returns (low, high). With n == 0 there is no data, so it returns (0.0, 0.0).
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def paired_flip_test(fixed: int, broken: int) -> float:
    """Exact two-sided binomial (sign) test on the cases that changed.

    fixed  = cases that went wrong -> right between run A and run B
    broken = cases that went right -> wrong
    Cases that did not change carry no information and are ignored.
    Null hypothesis: a changed case is equally likely to go either way.
    Returns the p-value (1.0 if no case changed).
    """
    n = fixed + broken
    if n == 0:
        return 1.0
    k = min(fixed, broken)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def flip_counts(a: dict, b: dict) -> tuple[int, int]:
    """Count (fixed, broken) between two runs.

    a and b map case_id -> True/False (answer judged correct).
    Only case ids present in BOTH runs are compared.
    """
    fixed = sum(1 for c in a.keys() & b.keys() if not a[c] and b[c])
    broken = sum(1 for c in a.keys() & b.keys() if a[c] and not b[c])
    return fixed, broken


def percentile(values: list[float], q: float) -> float:
    """q-th percentile (0-100) using linear interpolation. Empty list -> 0.0."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q / 100
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


def p50(values: list[float]) -> float:
    """Median."""
    return percentile(values, 50)


def p95(values: list[float]) -> float:
    """95th percentile."""
    return percentile(values, 95)
