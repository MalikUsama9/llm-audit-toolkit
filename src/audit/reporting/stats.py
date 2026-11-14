"""Statistics helpers: confidence intervals, paired flip test, bootstrap, percentiles."""
from __future__ import annotations

import math
import random


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


def paired_bootstrap_delta(
    a: list[int],
    b: list[int],
    iters: int = 5000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap CI for mean(b) - mean(a) on paired cases.

    a and b are 0/1 outcomes for the SAME cases, in the same order. Cases are
    resampled together (with replacement), so the pairing is preserved.
    Returns (low, high) at the 1 - alpha level (95% by default). Deterministic
    for a given seed. With no cases there is no data, so it returns (0.0, 0.0).
    """
    if len(a) != len(b):
        raise ValueError(f"a and b must be the same length, got {len(a)} and {len(b)}")
    n = len(a)
    if n == 0:
        return (0.0, 0.0)
    deltas = [y - x for x, y in zip(a, b)]
    rng = random.Random(seed)
    diffs = sorted(
        sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters)
    )
    lo = int(alpha / 2 * iters)
    hi = int((1 - alpha / 2) * iters) - 1
    return (diffs[lo], diffs[max(lo, hi)])


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