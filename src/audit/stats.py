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