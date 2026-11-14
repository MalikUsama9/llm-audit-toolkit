import pytest
from audit.reporting.stats import (
    wilson, paired_flip_test, flip_counts, percentile, p50, p95,
)


def test_wilson_known_value():
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_wilson_edges():
    assert wilson(0, 0) == (0.0, 0.0)
    lo, hi = wilson(10, 10)
    assert hi == pytest.approx(1.0) and lo < 1.0
    lo, hi = wilson(0, 10)
    assert lo == pytest.approx(0.0) and hi > 0.0


def test_wilson_narrows_with_more_data():
    lo1, hi1 = wilson(5, 10)
    lo2, hi2 = wilson(50, 100)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_flip_test_values():
    assert paired_flip_test(8, 2) == pytest.approx(0.109375)
    assert paired_flip_test(5, 5) == pytest.approx(1.0)
    assert paired_flip_test(10, 0) == pytest.approx(2 / 1024)
    assert paired_flip_test(0, 0) == 1.0


def test_flip_counts():
    a = {"c1": False, "c2": True, "c3": True, "c4": False, "only_a": True}
    b = {"c1": True, "c2": False, "c3": True, "c4": False, "only_b": True}
    assert flip_counts(a, b) == (1, 1)


def test_percentiles():
    assert p50([1, 2, 3, 4]) == pytest.approx(2.5)
    assert p95(list(range(1, 101))) == pytest.approx(95.05)
    assert percentile([], 50) == 0.0
    assert percentile([7], 95) == 7.0
