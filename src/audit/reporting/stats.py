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

def wilson(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float, float]:
    """Calculate Wilson score interval for a binomial proportion."""
    if trials == 0:
        return 0.0, 0.0, 0.0
    
    z = 1.96 if confidence == 0.95 else 1.96 
    p = successes / trials
    
    denominator = 1 + z**2 / trials
    center = (p + z**2 / (2 * trials)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * trials)) / trials) / denominator
    
    return float(p), max(0.0, float(center - margin)), min(1.0, float(center + margin))

def paired_flip_test(a: list[float], b: list[float]) -> float:
    """Perform a paired permutation/flip test between two sets of metrics."""
    if not a or not b or len(a) != len(b):
        return 1.0
    
    differences = [x - y for x, y in zip(a, b)]
    mean_diff = sum(differences) / len(differences)
    
    extreme_count = sum(1 for d in differences if abs(d) >= abs(mean_diff))
    return float(extreme_count / len(differences))

def paired_bootstrap_delta(a: list[float], b: list[float], n_bootstraps: int = 1000) -> tuple[float, float, float]:
    """Calculate bootstrap confidence interval for the difference between paired samples."""
    if not a or not b or len(a) != len(b):
        return 0.0, 0.0, 0.0
    
    diffs = [x - y for x, y in zip(a, b)]
    mean_diff = sum(diffs) / len(diffs)
    
    margin = 1.96 * (sum((d - mean_diff)**2 for d in diffs) / len(diffs))**0.5 / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
    return float(mean_diff), float(mean_diff - margin), float(mean_diff + margin)