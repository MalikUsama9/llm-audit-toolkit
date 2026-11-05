import pytest
from audit.stats import percentile, latency_stats

def test_empty_returns_none():
    assert percentile([], 50) is None

def test_single_value():
    assert percentile([120], 95) == 120

def test_p50_odd_and_even():
    assert percentile([1, 2, 3], 50) == 2
    assert percentile([1, 2, 3, 4], 50) == 2.5

def test_p95_known_value():
    assert percentile(list(range(1, 101)), 95) == pytest.approx(95.05)

def test_unsorted_input():
    assert percentile([5, 1, 3], 50) == 3

def test_bad_p():
    with pytest.raises(ValueError):
        percentile([1, 2], 101)

def test_latency_stats_ignores_errors():
    rows = [
        {"latency_ms": 100, "error": None},
        {"latency_ms": 200, "error": None},
        {"latency_ms": 99999, "error": "timeout"},  # must be excluded
    ]
    s = latency_stats(rows)
    assert s["n_ok"] == 2 and s["p50"] == 150