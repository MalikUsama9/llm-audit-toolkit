import pytest
from audit.reporting.stats import (
    wilson, paired_flip_test, paired_bootstrap_delta,
    flip_counts, percentile, p50, p95,
)


# ---------------------------------------------------------------- wilson
def test_wilson_known_value():
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_wilson_matches_roadmap_example():
    lo, hi = wilson(78, 100)
    assert 0.68 < lo < 0.70      # roadmap: roughly 69%-85%
    assert 0.84 < hi < 0.86


def test_wilson_contains_point_estimate():
    lo, hi = wilson(7, 10)
    assert lo <= 0.7 <= hi


def test_wilson_edges_stay_inside_0_1():
    lo, hi = wilson(0, 10)
    assert lo == pytest.approx(0.0, abs=1e-9) and 0 < hi < 1
    lo, hi = wilson(10, 10)
    assert 0 < lo < 1 and hi == pytest.approx(1.0, abs=1e-9)


def test_wilson_zero_n():
    assert wilson(0, 0) == (0.0, 0.0)


def test_wilson_narrows_with_more_data():
    lo1, hi1 = wilson(5, 10)
    lo2, hi2 = wilson(50, 100)
    assert (hi2 - lo2) < (hi1 - lo1)


# ---------------------------------------------------------------- flip test
def test_flip_test_values():
    assert paired_flip_test(8, 2) == pytest.approx(0.109375)
    assert paired_flip_test(5, 5) == pytest.approx(1.0)
    assert paired_flip_test(10, 0) == pytest.approx(2 / 1024)
    assert paired_flip_test(4, 1) == pytest.approx(0.375)
    assert paired_flip_test(1, 4) == pytest.approx(0.375)   # symmetric
    assert paired_flip_test(0, 0) == 1.0                    # no flips, no evidence


def test_flip_test_one_sided_flips_are_significant():
    assert paired_flip_test(10, 0) < 0.01


def test_flip_counts_balanced():
    a = {"c1": False, "c2": True, "c3": True, "c4": False, "only_a": True}
    b = {"c1": True, "c2": False, "c3": True, "c4": False, "only_b": True}
    assert flip_counts(a, b) == (1, 1)     # ids not in both are ignored


def test_flip_counts_order():
    # a -> b: c1 and c2 go False->True (fixed), c3 goes True->False (broken)
    a = {"c1": False, "c2": False, "c3": True}
    b = {"c1": True, "c2": True, "c3": False}
    assert flip_counts(a, b) == (2, 1)     # assumes (fixed, broken); swap if your code is (broken, fixed)


# ---------------------------------------------------------------- bootstrap
def test_bootstrap_delta_is_deterministic_and_sensible():
    a, b = [0] * 20, [1] * 20
    assert paired_bootstrap_delta(a, b) == (1.0, 1.0)       # every case improved
    assert paired_bootstrap_delta(a, a) == (0.0, 0.0)       # nothing changed
    x = paired_bootstrap_delta([0, 1, 0, 1, 1, 0], [1, 1, 0, 0, 1, 1])
    assert x == paired_bootstrap_delta([0, 1, 0, 1, 1, 0], [1, 1, 0, 0, 1, 1])  # same seed, same CI
    assert x[0] <= x[1]


def test_bootstrap_empty():
    assert paired_bootstrap_delta([], []) == (0.0, 0.0)


# ---------------------------------------------------------------- percentiles
def test_percentiles():
    assert p50([1, 2, 3, 4]) == pytest.approx(2.5)
    assert p95(list(range(1, 101))) == pytest.approx(95.05)
    assert percentile([], 50) is None
    assert percentile([7], 95) == 7.0