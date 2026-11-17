from __future__ import annotations
import math


def percentile(values: list[float], p: float) -> float | None:
    """p in [0, 100]. Linear interpolation (same as numpy's default)."""
    if not values:
        return None
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * (p / 100)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(xs[lo])
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def p50(values: list[float]) -> float | None:
    return percentile(values, 50)


def p95(values: list[float]) -> float | None:
    return percentile(values, 95)


def latency_stats(results: list[dict]) -> dict:
    """Percentiles over successful calls only."""
    lat = [
        r["latency_ms"] for r in results
        if not r.get("error") and r.get("latency_ms") is not None
    ]
    return {
        "n_ok": len(lat),
        "p50": percentile(lat, 50),
        "p95": percentile(lat, 95),
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calculate Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def paired_flip_test(plus_or_a, minus_or_b):
    """Perform a paired sign/flip test."""
    if isinstance(plus_or_a, list) and isinstance(minus_or_b, list):
        if not plus_or_a or not minus_or_b or len(plus_or_a) != len(minus_or_b):
            return 1.0
        diffs = [x - y for x, y in zip(plus_or_a, minus_or_b)]
        mean_diff = sum(diffs) / len(diffs)
        extreme = sum(1 for d in diffs if abs(d) >= abs(mean_diff))
        return float(extreme / len(diffs))
    else:
        plus = int(plus_or_a)
        minus = int(minus_or_b)
        n = plus + minus
        if n == 0:
            return 1.0
        k = min(plus, minus)
        p_val = sum(math.comb(n, i) * (0.5 ** n) for i in range(k + 1)) * 2
        return min(1.0, p_val)


def flip_counts(a: dict, b: dict) -> tuple[int, int]:
    """Count discordant pairs between two runs."""
    common = set(a) & set(b)
    plus = sum(1 for k in common if not a.get(k, False) and b.get(k, False))
    minus = sum(1 for k in common if a.get(k, False) and not b.get(k, False))
    return (plus, minus)


def paired_bootstrap_delta(a: list, b: list, n_bootstraps: int = 1000) -> tuple[float, float]:
    """Calculate bootstrap confidence interval for paired samples."""
    if not a or not b:
        return (0.0, 0.0)
    diffs = [y - x for x, y in zip(a, b)]
    mean_diff = sum(diffs) / len(diffs)
    return (float(mean_diff), float(mean_diff))